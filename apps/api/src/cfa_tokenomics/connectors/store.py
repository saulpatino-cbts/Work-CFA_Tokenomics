"""Read-only object stores for cost exports: Amazon S3 and Azure Blob Storage.

Credentials are never configuration. Both stores use the platform's ambient identity (an IAM role or
the default AWS credential chain; an Azure managed identity or the default Azure credential chain),
so no secret is stored, logged or passed on a command line. Errors are reduced to a short class and a
fixed message so a failure cannot echo a credential, a signed URL or a response body.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol


@dataclass(frozen=True)
class ObjectInfo:
    key: str
    size: int
    etag: str
    modified: datetime


class StoreError(Exception):
    """kind is one of access_denied, not_found, unavailable, other."""

    def __init__(self, kind: str, message: str):
        super().__init__(message)
        self.kind = kind


class TooLarge(Exception):
    pass


class ObjectStore(Protocol):
    def list(self, prefix: str) -> Iterator[ObjectInfo]: ...

    def read(self, key: str, limit: int) -> bytes:
        """The object's bytes, or ``TooLarge`` if it holds more than ``limit``."""
        ...


_MESSAGES = {
    "access_denied": "access was denied; check the role's read permissions on the export location",
    "not_found": "the bucket, container or path was not found",
    "unavailable": "the storage service could not be reached; try again",
    "other": "the storage request failed",
}


def _error(kind: str, exc: Exception) -> StoreError:
    return StoreError(kind, f"{_MESSAGES[kind]} ({type(exc).__name__})")


class S3Store:
    """Amazon S3 through the default AWS credential chain (instance role, task role, SSO, ...)."""

    def __init__(self, bucket: str, region: str | None = None, client: Any = None):
        self.bucket = bucket
        if client is None:
            import boto3
            from botocore.config import Config

            client = boto3.client(
                "s3",
                region_name=region,
                config=Config(retries={"max_attempts": 5, "mode": "standard"}),
            )
        self.client = client

    def _map(self, exc: Exception) -> StoreError:
        from botocore.exceptions import ClientError

        if isinstance(exc, ClientError):
            code = str(exc.response.get("Error", {}).get("Code", ""))
            status = exc.response.get("ResponseMetadata", {}).get("HTTPStatusCode")
            if code in ("AccessDenied", "AllAccessDisabled", "InvalidAccessKeyId") or status in (
                401,
                403,
            ):
                return _error("access_denied", exc)
            if code in ("NoSuchBucket", "NoSuchKey", "404") or status == 404:
                return _error("not_found", exc)
            return _error("other", exc)
        name = type(exc).__name__
        if "Connect" in name or "Endpoint" in name or "Timeout" in name:
            return _error("unavailable", exc)
        if name == "NoCredentialsError":
            return _error("access_denied", exc)
        return _error("other", exc)

    def list(self, prefix: str) -> Iterator[ObjectInfo]:
        try:
            pages = self.client.get_paginator("list_objects_v2").paginate(
                Bucket=self.bucket, Prefix=prefix
            )
            for page in pages:
                for o in page.get("Contents", []):
                    yield ObjectInfo(
                        o["Key"],
                        int(o["Size"]),
                        str(o.get("ETag", "")).strip('"'),
                        o["LastModified"],
                    )
        except Exception as exc:
            raise self._map(exc) from None

    def read(self, key: str, limit: int) -> bytes:
        try:
            res = self.client.get_object(Bucket=self.bucket, Key=key)
            if int(res.get("ContentLength", 0)) > limit:
                raise TooLarge(key)
            data = res["Body"].read(limit + 1)
        except TooLarge:
            raise
        except Exception as exc:
            raise self._map(exc) from None
        if len(data) > limit:
            raise TooLarge(key)
        return data


class AzureBlobStore:
    """Azure Blob Storage through the default Azure credential chain (managed identity, ...)."""

    def __init__(self, account_url: str, container: str, client: Any = None):
        if client is None:
            from azure.identity import DefaultAzureCredential
            from azure.storage.blob import ContainerClient

            client = ContainerClient(account_url, container, credential=DefaultAzureCredential())
        self.client = client

    @staticmethod
    def _map(exc: Exception) -> StoreError:
        status = getattr(exc, "status_code", None)
        name = type(exc).__name__
        if status in (401, 403) or name == "ClientAuthenticationError":
            return _error("access_denied", exc)
        if status == 404 or name == "ResourceNotFoundError":
            return _error("not_found", exc)
        if name in ("ServiceRequestError", "ServiceResponseTimeoutError") or "Connect" in name:
            return _error("unavailable", exc)
        return _error("other", exc)

    def list(self, prefix: str) -> Iterator[ObjectInfo]:
        try:
            for b in self.client.list_blobs(name_starts_with=prefix):
                yield ObjectInfo(
                    b.name, int(b.size or 0), str(b.etag or "").strip('"'), b.last_modified
                )
        except Exception as exc:
            raise self._map(exc) from None

    def read(self, key: str, limit: int) -> bytes:
        try:
            data = self.client.download_blob(key, offset=0, length=limit + 1).readall()
        except Exception as exc:
            raise self._map(exc) from None
        if len(data) > limit:
            raise TooLarge(key)
        return data
