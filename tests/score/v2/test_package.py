"""Tests for schema-v2 identities, references, source maps, and documents."""

from dataclasses import replace

from teachmemusic.score.models import ScoreRepresentation
from teachmemusic.score.v2.documents import (
    MediaDocument,
    OpusDocument,
    SoundsDocument,
)
from teachmemusic.score.v2.identity import (
    CanonicalId,
    EntityKind,
    EntityReference,
    SourceLocation,
    SourceMapEntry,
)
from teachmemusic.score.v2.migration import migrate_v1_score
from teachmemusic.score.v2.validation import validate_package
from teachmemusic.score.v2.values import SpecifiedValue


def test_typed_references_and_source_maps_resolve_by_kind(
    hot_cross_buns_score: ScoreRepresentation,
) -> None:
    """TEST-MXML-INVARIANT-004: source maps and references resolve typed identities."""

    package = migrate_v1_score(hot_cross_buns_score)
    source = package.provenance.sources[0]
    entry = SourceMapEntry(
        entity=EntityReference(EntityKind.EVENT, "event-p1-m1-1"),
        locations=(
            SourceLocation(
                source_document=EntityReference.to(source.id),
                logical_path="/score-partwise/part[1]/measure[1]/note[1]",
                line=42,
                column=3,
                source_ordinal=1,
            ),
        ),
    )
    with_map = replace(
        package,
        provenance=replace(package.provenance, source_map=(entry,)),
    )

    assert not validate_package(with_map)

    wrong_kind = replace(
        entry,
        entity=EntityReference(EntityKind.MEASURE, "event-p1-m1-1"),
    )
    invalid = replace(
        package,
        provenance=replace(package.provenance, source_map=(wrong_kind,)),
    )
    assert "V2_REFERENCE_BROKEN" in {issue.code for issue in validate_package(invalid)}


def test_foundational_document_kinds_form_one_valid_package(
    hot_cross_buns_score: ScoreRepresentation,
) -> None:
    """TEST-MXML-INVARIANT-005: score, opus, sounds, and media documents stay typed."""

    package = migrate_v1_score(hot_cross_buns_score)
    score = package.documents[0]
    source_refs = score.source_documents
    opus_id = CanonicalId(EntityKind.OPUS, "opus:1")
    sounds_id = CanonicalId(EntityKind.SOUNDS, "sounds:1")
    media_id = CanonicalId(EntityKind.MEDIA, "media:1")
    opus = OpusDocument(
        id=opus_id,
        source_documents=source_refs,
        title=SpecifiedValue.explicit("Collection"),
        members=(EntityReference.to(score.id),),
    )
    sounds = SoundsDocument(
        id=sounds_id,
        source_documents=source_refs,
        name=SpecifiedValue.explicit("Piano"),
    )
    media = MediaDocument(
        id=media_id,
        source_documents=source_refs,
        logical_path="images/cover.png",
        media_type=SpecifiedValue.explicit("image/png"),
        sha256=SpecifiedValue.unknown(),
    )
    expanded = replace(
        package,
        documents=(opus, score, sounds, media),
        root_documents=(EntityReference.to(opus_id),),
    )

    assert not validate_package(expanded)


def test_package_rejects_dangling_roots_and_duplicate_typed_ids(
    hot_cross_buns_score: ScoreRepresentation,
) -> None:
    """TEST-MXML-INVARIANT-006: core graph rejects broken roots and duplicate identities."""

    package = migrate_v1_score(hot_cross_buns_score)
    dangling = replace(
        package,
        root_documents=(EntityReference(EntityKind.SCORE, "missing-score"),),
    )
    duplicated = replace(package, documents=(package.documents[0], package.documents[0]))

    assert "V2_REFERENCE_BROKEN" in {issue.code for issue in validate_package(dangling)}
    assert "V2_DUPLICATE_ID" in {issue.code for issue in validate_package(duplicated)}
