"""Resolving a credential reference to its value, at the moment it is needed.

A connector's configuration holds a *reference*, never a secret: ``env:NAME`` (an environment variable the
platform fills from the customer's secret store) or ``file:/absolute/path`` (a mounted secret file, as
container orchestrators provide). Values are never logged, never put in an error message and never stored.
Fetching from a secret manager is done by the deployment, which injects the value as one of the above.
"""

from __future__ import annotations

import os
import re

_ENV = re.compile(r"^[A-Z_][A-Z0-9_]{0,63}$")
MAX_BYTES = 4096


class CredentialError(ValueError):
    """The reference is invalid or does not resolve. The message never contains the value."""


def check_ref(ref: object) -> str:
    """Validate a reference's shape without reading it."""
    if not isinstance(ref, str):
        raise CredentialError("credential_ref must be text such as env:NAME or file:/path")
    kind, _, rest = ref.partition(":")
    if kind == "env":
        if not _ENV.match(rest):
            raise CredentialError(
                "env references need an upper-case variable name, for example env:ANTHROPIC_ADMIN_KEY"
            )
    elif kind == "file":
        if not rest.startswith("/") or ".." in rest.split("/") or len(rest) > 512 or "\x00" in rest:
            raise CredentialError("file references need an absolute path with no '..'")
    else:
        raise CredentialError("credential_ref must start with env: or file:")
    return ref


def resolve(ref: str) -> str:
    check_ref(ref)
    kind, _, rest = ref.partition(":")
    if kind == "env":
        value = os.environ.get(rest, "")
        where = f"environment variable {rest}"
    else:
        try:
            with open(rest, "rb") as fh:
                raw = fh.read(MAX_BYTES + 1)
        except OSError:
            raise CredentialError(f"the credential file {rest} could not be read") from None
        if len(raw) > MAX_BYTES:
            raise CredentialError("the credential file is larger than a credential should be")
        try:
            value = raw.decode("utf-8")
        except UnicodeDecodeError:
            raise CredentialError("the credential file is not text") from None
        where = f"file {rest}"
    value = value.strip()
    if not value:
        raise CredentialError(f"{where} is empty or not set")
    if any(c.isspace() or ord(c) < 32 for c in value):
        raise CredentialError(f"{where} does not look like a single-line credential")
    return value
