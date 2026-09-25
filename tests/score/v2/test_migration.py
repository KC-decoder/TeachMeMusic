"""Tests for deterministic schema-v1 to schema-v2 migration."""

from dataclasses import replace

import pytest

from teachmemusic.score.models import ScoreRepresentation
from teachmemusic.score.v2.documents import ScoreDocument
from teachmemusic.score.v2.migration import CanonicalMigrationError, migrate_v1_score
from teachmemusic.score.v2.provenance import TransformationKind
from teachmemusic.score.v2.validation import validate_package
from teachmemusic.score.v2.values import ValueState


@pytest.mark.parametrize("score_fixture", ("hot_cross_buns_score", "happy_birthday_score"))
def test_v1_fixtures_migrate_without_field_loss(
    score_fixture: str,
    request: pytest.FixtureRequest,
) -> None:
    """TEST-MXML-MIGRATION-001: both manual v1 proofs survive deterministic migration."""

    score = request.getfixturevalue(score_fixture)
    assert isinstance(score, ScoreRepresentation)

    package = migrate_v1_score(score)
    document = package.documents[0]

    assert isinstance(document, ScoreDocument)
    assert document.content.score == score
    assert document.content.score is score
    assert document.id.value == score.id
    assert package.root_documents[0].target_id == score.id
    assert not validate_package(package)
    assert migrate_v1_score(score) == package


def test_migration_preserves_sources_and_marks_unavailable_facts_unknown(
    hot_cross_buns_score: ScoreRepresentation,
) -> None:
    """TEST-MXML-MIGRATION-002: migration preserves evidence without inventing facts."""

    package = migrate_v1_score(hot_cross_buns_score)

    assert len(package.provenance.sources) == len(hot_cross_buns_score.provenance)
    for migrated, original in zip(
        package.provenance.sources,
        hot_cross_buns_score.provenance,
        strict=True,
    ):
        assert migrated.logical_name.value == original.logical_name
        assert migrated.sha256.value == original.sha256
        assert migrated.byte_length.state is ValueState.UNKNOWN
        assert migrated.declared_musicxml_version.state is ValueState.UNKNOWN
        assert migrated.validated_musicxml_version.state is ValueState.UNKNOWN
        assert migrated.document_form.state is ValueState.UNKNOWN
    transformation = package.provenance.transformations[0]
    assert transformation.kind is TransformationKind.MIGRATED_FROM_V1
    assert transformation.source_schema == "teachmemusic.score-representation/1"
    assert transformation.target_schema == "2.0.0"


def test_migration_validates_v1_before_creating_a_package(
    hot_cross_buns_score: ScoreRepresentation,
) -> None:
    """TEST-MXML-MIGRATION-003: invalid v1 input never produces a partial v2 package."""

    invalid = replace(hot_cross_buns_score, schema_version=999)

    with pytest.raises(CanonicalMigrationError, match="source schema-v1 score is invalid"):
        migrate_v1_score(invalid)


def test_migration_digest_must_match_retained_v1_content(
    hot_cross_buns_score: ScoreRepresentation,
) -> None:
    """TEST-MXML-MIGRATION-004: provenance cannot claim a different migration input."""

    package = migrate_v1_score(hot_cross_buns_score)
    transformation = replace(package.provenance.transformations[0], input_sha256="0" * 64)
    tampered = replace(
        package,
        provenance=replace(package.provenance, transformations=(transformation,)),
    )

    assert "V2_MIGRATION_DIGEST_MISMATCH" in {issue.code for issue in validate_package(tampered)}
