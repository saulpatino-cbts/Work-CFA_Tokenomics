"""Privacy modes and pseudonyms (ADR 0012). Keys and identifiers are SYNTHETIC test values."""

import pytest

from cfa_tokenomics.privacy import MIN_KEY_BYTES, PREFIX, Mode, Pseudonymizer, normalize, parse_mode

KEY_A = b"a" * 32  # synthetic, for tests only
KEY_B = b"b" * 32


def test_the_default_is_aggregate_and_anything_unrecognised_is_refused():
    assert parse_mode(None) is Mode.AGGREGATE
    assert parse_mode("aggregate") is Mode.AGGREGATE and parse_mode("per_user") is Mode.PER_USER
    for bad in ("", "per-user", "PER_USER", "all", "true", 1, True):
        with pytest.raises(ValueError):
            parse_mode(bad)


def test_pseudonyms_are_deterministic_and_prefixed():
    p = Pseudonymizer(KEY_A)
    a = p.pseudonym("user0001@example.test")
    assert a == p.pseudonym("user0001@example.test") and a.startswith(PREFIX)
    assert len(a) == len(PREFIX) + 32 and set(a[len(PREFIX) :]) <= set("0123456789abcdef")


def test_case_and_surrounding_whitespace_are_the_same_person():
    p = Pseudonymizer(KEY_A)
    assert p.pseudonym("  User0001@Example.TEST ") == p.pseudonym("user0001@example.test")
    assert normalize(" A@B ") == "a@b"


def test_different_people_and_different_keys_give_different_pseudonyms():
    a, b = Pseudonymizer(KEY_A), Pseudonymizer(KEY_B)
    assert a.pseudonym("user0001@example.test") != a.pseudonym("user0002@example.test")
    assert a.pseudonym("user0001@example.test") != b.pseudonym(
        "user0001@example.test"
    )  # rotation ends joins


def test_the_identifier_and_the_key_never_appear_in_the_pseudonym_or_repr():
    p = Pseudonymizer(KEY_A)
    out = p.pseudonym("user0001@example.test")
    assert "user0001" not in out and "example" not in out and KEY_A.decode() not in out
    assert "aaaa" not in repr(p) and "withheld" in repr(p)


def test_a_weak_key_or_an_empty_identifier_is_refused():
    for bad in (b"", b"short", "a string", None):
        with pytest.raises(ValueError):
            Pseudonymizer(bad)  # type: ignore[arg-type]
    assert Pseudonymizer(b"k" * MIN_KEY_BYTES)
    with pytest.raises(ValueError):
        Pseudonymizer(KEY_A).pseudonym("   ")


def test_an_unkeyed_hash_would_be_guessable_but_the_keyed_one_is_not_a_plain_digest():
    import hashlib

    plain = hashlib.sha256(b"user0001@example.test").hexdigest()[:32]
    assert Pseudonymizer(KEY_A).pseudonym("user0001@example.test") != PREFIX + plain
