"""Tests for deterministic v2 JSON and version dispatch."""

import hashlib
import json

import pytest

from teachmemusic.score.models import ScoreRepresentation
from teachmemusic.score.serializer import score_to_json
from teachmemusic.score.v2.documents import CANONICAL_SCHEMA_ID, CanonicalMusicPackage
from teachmemusic.score.v2.migration import migrate_v1_score
from teachmemusic.score.v2.serialization import (
    CanonicalSerializationError,
    canonical_from_json,
    package_from_json,
    package_to_json,
)


@pytest.mark.parametrize("score_fixture", ("hot_cross_buns_score", "happy_birthday_score"))
def test_migrated_packages_round_trip_deterministically(
    score_fixture: str,
    request: pytest.FixtureRequest,
) -> None:
    """TEST-MXML-ROUNDTRIP-001: both migrated fixtures have lossless stable v2 JSON."""

    score = request.getfixturevalue(score_fixture)
    assert isinstance(score, ScoreRepresentation)
    package = migrate_v1_score(score)

    first = package_to_json(package)
    second = package_to_json(package)

    assert first == second
    assert first.endswith("\n")
    assert package_from_json(first) == package
    assert json.loads(first)["schema_id"] == CANONICAL_SCHEMA_ID


def test_version_dispatch_keeps_v1_readable_and_v2_explicit(
    hot_cross_buns_score: ScoreRepresentation,
) -> None:
    """TEST-MXML-ROUNDTRIP-002: deserialization dispatch preserves both schema generations."""

    v1_result = canonical_from_json(score_to_json(hot_cross_buns_score))
    v2_package = migrate_v1_score(hot_cross_buns_score)
    v2_result = canonical_from_json(package_to_json(v2_package))

    assert v1_result == hot_cross_buns_score
    assert v2_result == v2_package
    assert isinstance(v2_result, CanonicalMusicPackage)


def test_schema_v2_rejects_unknown_fields_and_versions(
    hot_cross_buns_score: ScoreRepresentation,
) -> None:
    """TEST-MXML-ROUNDTRIP-003: strict v2 decoding cannot silently ignore data."""

    data = json.loads(package_to_json(migrate_v1_score(hot_cross_buns_score)))
    data["unexpected"] = "would be information loss"
    with pytest.raises(CanonicalSerializationError, match="unexpected keys"):
        package_from_json(json.dumps(data))

    del data["unexpected"]
    data["schema_version"] = "3.0.0"
    with pytest.raises(CanonicalSerializationError, match="unsupported version"):
        package_from_json(json.dumps(data))


def test_duplicate_json_keys_and_nonfinite_values_fail_closed() -> None:
    """TEST-MXML-ROUNDTRIP-005: ambiguous JSON cannot silently overwrite canonical facts."""

    with pytest.raises(CanonicalSerializationError, match="duplicate JSON key"):
        canonical_from_json('{"schema_version":1,"schema_version":2}')
    with pytest.raises(CanonicalSerializationError, match="non-finite JSON"):
        canonical_from_json('{"schema_version":NaN}')


def test_migrated_fixture_json_has_stable_compatibility_hashes(
    hot_cross_buns_score: ScoreRepresentation,
    happy_birthday_score: ScoreRepresentation,
) -> None:
    """TEST-MXML-ROUNDTRIP-004: compact golden hashes detect v2 compatibility drift."""

    hashes = tuple(
        hashlib.sha256(package_to_json(migrate_v1_score(score)).encode()).hexdigest()
        for score in (hot_cross_buns_score, happy_birthday_score)
    )

    assert hashes == (
        "533bcd3bebf4b3b6f9a80ef63ddd9289a9d28882f59cde6e5a0497f7a079126e",
        "899f77c00d45e3f4935c4c2f2fd7947cca799491c5ffef627c1c6c3286da79b8",
    )
