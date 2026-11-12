"""A read-only, cursor-paged JSON client shared by the vendor API connectors.

Paced under the vendor's rate limit, bounded retries that honor ``Retry-After``, a cursor that expires
mid-query restarts it, and any unexpected shape is an error, never a guess. The credential is resolved
from a reference when a request is made and is never logged, stored or echoed in an error. The host is
fixed by the caller, so a key can only be sent where the connector was written to send it.

Numbers can be parsed as ``Decimal`` straight from the response text (``decimal_numbers=True``), so money
that arrives as a JSON number is never rounded through a binary float.
"""

from __future__ import annotations

import json
import time
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import httpx

from . import credentials

MAX_PAGES = 200
MAX_ATTEMPTS = 5
MAX_RESTARTS = 2


class SourceError(Exception):
    """A failure talking to the source. The message never contains the credential or a response body."""


class CursorExpired(Exception):
    pass


class PagedClient:
    def __init__(
        self,
        vendor: str,
        base_url: str,
        credential_ref: str,
        make_headers: Callable[[str], dict[str, str]],
        http: httpx.Client | None = None,
        sleep=time.sleep,
        min_interval: float = 1.1,
        decimal_numbers: bool = False,
    ):
        self._vendor = vendor
        self._ref = credential_ref
        self._make_headers = make_headers
        self._http = http or httpx.Client(base_url=base_url, timeout=30.0)
        self._sleep = sleep
        self._min_interval = min_interval
        self._decimal = decimal_numbers
        self._last = 0.0

    def __repr__(self) -> str:
        return f"{type(self).__name__}(<credential withheld>)"

    def _parse(self, res: httpx.Response) -> dict:
        try:
            body = json.loads(res.content, parse_float=Decimal) if self._decimal else res.json()
        except ValueError:
            raise SourceError(
                f"the {self._vendor} API returned something that is not JSON"
            ) from None
        if not isinstance(body, dict):
            raise SourceError(f"the {self._vendor} API returned an unexpected response shape")
        return body

    def _get(self, path: str, params: list[tuple[str, str]]) -> dict:
        headers = self._make_headers(credentials.resolve(self._ref))
        v = self._vendor
        for attempt in range(MAX_ATTEMPTS):
            wait = self._min_interval - (time.monotonic() - self._last)
            if wait > 0:
                self._sleep(wait)
            self._last = time.monotonic()
            try:
                res = self._http.get(path, params=params, headers=headers)
            except httpx.TransportError as exc:
                if attempt == MAX_ATTEMPTS - 1:
                    raise SourceError(
                        f"the {v} API could not be reached ({type(exc).__name__})"
                    ) from None
                self._sleep(min(2**attempt, 30))
                continue
            code = res.status_code
            if code == 200:
                return self._parse(res)
            if code == 410:
                raise CursorExpired
            if code in (429, 500, 502, 503, 504):
                if attempt == MAX_ATTEMPTS - 1:
                    raise SourceError(f"the {v} API kept refusing the request (HTTP {code})")
                retry = res.headers.get("retry-after", "")
                self._sleep(
                    min(float(retry), 60)
                    if retry.replace(".", "", 1).isdigit()
                    else min(2**attempt, 30)
                )
                continue
            if code in (401, 403):
                raise SourceError(
                    f"the {v} API rejected the credential or it lacks the access this needs (HTTP {code})"
                )
            if code == 400:
                raise SourceError(f"the {v} API rejected the request parameters (HTTP 400)")
            raise SourceError(f"the {v} API returned HTTP {code}")
        raise SourceError(f"the {v} API request did not complete")  # pragma: no cover

    def get_all(self, path: str, params: list[tuple[str, str]]) -> tuple[list[dict], str | None]:
        """Every page of one query, and the first page's ``data_refreshed_at`` when the source gives one."""
        for _ in range(MAX_RESTARTS + 1):
            try:
                return self._pages(path, params)
            except CursorExpired:
                continue
        raise SourceError(
            f"the {self._vendor} data kept being refreshed while it was read; try again later"
        )

    def _pages(self, path: str, params: list[tuple[str, str]]) -> tuple[list[dict], str | None]:
        v = self._vendor
        rows: list[dict] = []
        refreshed: str | None = None
        page: str | None = None
        for n in range(MAX_PAGES):
            body = self._get(path, params + ([("page", page)] if page else []))
            data = body.get("data")
            if not isinstance(data, list) or not isinstance(body.get("has_more"), bool):
                raise SourceError(f"the {v} API returned an unexpected response shape")
            rows += data
            if n == 0:
                refreshed = body.get("data_refreshed_at")
                if refreshed is not None and not isinstance(refreshed, str):
                    raise SourceError(f"the {v} API returned an unexpected data_refreshed_at")
            if not body["has_more"]:
                return rows, refreshed
            page = body.get("next_page")
            if not isinstance(page, str) or not page:
                raise SourceError(f"the {v} API said there was more data but gave no cursor")
        raise SourceError(f"the {v} data spans more pages than this connector will read")


def day_windows(
    lookback_days: int,
    now: datetime | None = None,
    min_start: datetime | None = None,
    span: timedelta = timedelta(days=31),
) -> list[tuple[datetime, datetime]]:
    """Day-aligned windows of at most ``span``, up to the start of today (UTC): today is still being filled."""
    now = now or datetime.now(UTC)
    end = datetime(now.year, now.month, now.day, tzinfo=UTC)
    start = end - timedelta(days=lookback_days)
    if min_start is not None:
        start = max(min_start, start)
    out = []
    while start < end:
        stop = min(start + span, end)
        out.append((start, stop))
        start = stop
    return out
