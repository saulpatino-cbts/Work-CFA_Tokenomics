"""Privacy modes and person pseudonyms for vendor usage sources (docs/adr/0012).

A connector runs in ``aggregate`` mode unless an administrator has opted into ``per_user``. In both
modes a person's identifier is never stored in the clear: ``Pseudonymizer`` replaces it with a keyed
hash. The key is customer-held and comes from a secret-store reference resolved at runtime; this
module never reads configuration and never logs or returns the key.
"""

from __future__ import annotations

import hashlib
import hmac
from enum import StrEnum


class Mode(StrEnum):
    AGGREGATE = "aggregate"
    PER_USER = "per_user"


MIN_KEY_BYTES = 16
PREFIX = "u_"
_HEX_CHARS = 32  # 128 bits


def parse_mode(value: object) -> Mode:
    """Aggregate unless per_user is asked for in exactly those words. Anything else is refused,
    so a typo can never silently widen what is collected."""
    if value is None:
        return Mode.AGGREGATE
    try:
        return Mode(value)
    except ValueError:
        raise ValueError("privacy mode must be 'aggregate' or 'per_user'") from None


def normalize(identifier: str) -> str:
    """Case and surrounding whitespace do not make a different person."""
    return identifier.strip().casefold()


class Pseudonymizer:
    def __init__(self, key: bytes):
        if not isinstance(key, bytes | bytearray) or len(key) < MIN_KEY_BYTES:
            raise ValueError(f"the pseudonymization key must be at least {MIN_KEY_BYTES} bytes")
        self._key = bytes(key)

    def __repr__(self) -> str:  # never show the key
        return "Pseudonymizer(<key withheld>)"

    def pseudonym(self, identifier: str) -> str:
        norm = normalize(identifier)
        if not norm:
            raise ValueError("an empty identifier has no pseudonym")
        mac = hmac.new(self._key, norm.encode("utf-8"), hashlib.sha256).hexdigest()
        return PREFIX + mac[:_HEX_CHARS]
