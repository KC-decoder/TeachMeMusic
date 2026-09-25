"""Task 7J-R5 robustness evidence for the complete public package edge."""

from __future__ import annotations

import io
import zipfile
from collections.abc import Callable
from dataclasses import replace

import pytest

from teachmemusic.score import (
    CanonicalMusicPackage,
    CanonicalScoreContent,
    MediaDocument,
    OpusDocument,
    PackageRelationshipKind,
    ScoreDocument,
    SoundsDocument,
    package_from_json,
    package_to_json,
    parse_musicxml_package,
    validate_package,
)
from teachmemusic.score.musicxml.contracts import IngestionLimits
from teachmemusic.score.musicxml.diagnostics import MusicXmlBoundaryError
from teachmemusic.score.musicxml.standards import resource_root
from teachmemusic.score.v2.documents import CanonicalDocument

from .test_public_package import _container, _mxl, _opus, _score


def _span_score(endpoint_count: int) -> bytes:
    notes: list[str] = []
    for index in range(endpoint_count):
        action = "start" if index == 0 else "stop" if index == endpoint_count - 1 else "continue"
        notes.append(
            "<note>"
            f"<pitch><step>{chr(ord('C') + index)}</step><octave>4</octave></pitch>"
            "<duration>1</duration><voice>1</voice><type>quarter</type><staff>1</staff>"
            f'<notations><slur type="{action}" number="1" id="slur-{index + 1}"/>'
            "</notations></note>"
        )
    return (
        '<score-partwise version="4.0"><part-list><score-part id="P1">'
        "<part-name>Generated spans</part-name></score-part></part-list>"
        '<part id="P1"><measure number="1"><attributes><divisions>1</divisions>'
        "<staves>1</staves></attributes>"
        f"{''.join(notes)}</measure></part></score-partwise>"
    ).encode()


def _state_score(*, explicit: bool) -> bytes:
    value = ' print-object="yes"' if explicit else ""
    return (
        '<score-partwise version="4.0"><part-list><score-part id="P1">'
        "<part-name>Source state</part-name></score-part></part-list>"
        '<part id="P1"><measure number="1"><attributes><divisions>1</divisions>'
        f"<clef{value}><sign>G</sign><line>2</line></clef></attributes>"
        f"<note{value}><pitch><step>C</step><octave>4</octave></pitch>"
        "<duration>1</duration><type>quarter</type></note>"
        "</measure></part></score-partwise>"
    ).encode()


def _deflated_mxl(*, extra: tuple[tuple[str, bytes], ...] = ()) -> bytes:
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(
            "mimetype",
            b"application/vnd.recordare.musicxml",
            compress_type=zipfile.ZIP_STORED,
        )
        archive.writestr(
            "META-INF/container.xml",
            _container(("score.musicxml", "application/vnd.recordare.musicxml+xml")),
        )
        archive.writestr("score.musicxml", _score())
        for path, data in extra:
            archive.writestr(path, data)
    return stream.getvalue()


def _complete_score(package: CanonicalMusicPackage) -> ScoreDocument:
    score = next(item for item in package.documents if isinstance(item, ScoreDocument))
    assert isinstance(score.content, CanonicalScoreContent)
    return score


@pytest.mark.parametrize("endpoint_count", (2, 3, 5))
def test_generated_span_endpoints_resolve_to_public_event_anchors(endpoint_count: int) -> None:
    """TEST-MXML-PROPERTY-004: generated endpoint orders retain valid anchors."""

    package = parse_musicxml_package(_span_score(endpoint_count), logical_name="spans.musicxml")
    score = _complete_score(package).content.score
    events = score.parts[0].measures[0].events
    span = score.annotations.spans[0]

    expected_actions = ("start", *("continue" for _ in range(endpoint_count - 2)), "stop")
    assert tuple(endpoint.action for endpoint in span.endpoints) == expected_actions
    assert tuple(endpoint.anchor.event_id for endpoint in span.endpoints) == tuple(
        event.id for event in events
    )
    assert all(endpoint.anchor.part_id == score.parts[0].id for endpoint in span.endpoints)
    assert all(
        endpoint.anchor.measure_id == score.parts[0].measures[0].id for endpoint in span.endpoints
    )
    assert validate_package(package) == ()


@pytest.mark.parametrize("part_id", ("P1", "RH", "part.3", "piano_part"))
def test_generated_ids_are_stable_and_document_namespaced(part_id: str) -> None:
    """TEST-MXML-PROPERTY-005: public identities are stable and package-safe."""

    source = _score().replace(b'id="P1"', f'id="{part_id}"'.encode())
    first = parse_musicxml_package(source, logical_name="same.musicxml")
    repeated = parse_musicxml_package(source, logical_name="same.musicxml")
    relocated = parse_musicxml_package(source, logical_name="other.musicxml")
    first_part = _complete_score(first).content.score.parts[0]
    relocated_part = _complete_score(relocated).content.score.parts[0]

    assert repeated == first
    assert first_part.id.endswith(f":{part_id}")
    assert first_part.id != relocated_part.id
    assert all(staff.id.startswith(f"{first_part.id}:") for staff in first_part.staves)
    assert all(voice.id.startswith(f"{first_part.id}:") for voice in first_part.voices)
    assert all(measure.id.startswith(f"{first_part.id}:") for measure in first_part.measures)


def test_explicit_and_absent_source_states_remain_distinguishable() -> None:
    """TEST-MXML-PROPERTY-006: explicit standard state never collapses to absence."""

    absent = _complete_score(parse_musicxml_package(_state_score(explicit=False))).content.score
    explicit = _complete_score(parse_musicxml_package(_state_score(explicit=True))).content.score
    absent_measure = absent.parts[0].measures[0]
    explicit_measure = explicit.parts[0].measures[0]

    assert absent_measure.attributes[0].clefs[0].print_object is None
    assert explicit_measure.attributes[0].clefs[0].print_object is True
    assert absent_measure.events[0].print_object is None
    assert explicit_measure.events[0].print_object is True
    assert absent != explicit


@pytest.mark.parametrize(
    ("href", "resource_path", "resolved"),
    (
        ("../parts/piano.musicxml", "parts/piano.musicxml", True),
        ("../parts/My%20Part.musicxml?view=1#top", "parts/My Part.musicxml", True),
        ("../parts/missing.musicxml", "parts/piano.musicxml", False),
        ("https://example.test/piano.musicxml", "parts/piano.musicxml", False),
        ("#same-document", "parts/piano.musicxml", False),
    ),
)
def test_generated_link_targets_follow_closed_package_resolution(
    href: str,
    resource_path: str,
    resolved: bool,
) -> None:
    """TEST-MXML-PROPERTY-007: local links resolve without external fetching."""

    source = _mxl(
        rootfiles=(("scores/main.musicxml", "application/vnd.recordare.musicxml+xml"),),
        entries=(
            ("scores/main.musicxml", _score(part_link=href)),
            (resource_path, _score(title="Linked part")),
        ),
    )
    package = parse_musicxml_package(source)
    linked = tuple(
        item for item in package.relationships if item.kind is PackageRelationshipKind.LINKED_PART
    )

    assert bool(linked) is resolved
    if resolved:
        assert linked[0].href == href
    assert validate_package(package) == ()


@pytest.mark.parametrize(
    ("limit", "expected_code"),
    (
        (
            lambda source: replace(IngestionLimits(), max_input_bytes=len(source) - 1),
            "MXML_INPUT_SIZE_LIMIT",
        ),
        (
            lambda _source: replace(IngestionLimits(), max_archive_entries=2),
            "MXL_ARCHIVE_ENTRY_LIMIT",
        ),
        (
            lambda _source: replace(IngestionLimits(), max_archive_entry_bytes=100),
            "MXL_ARCHIVE_ENTRY_SIZE_LIMIT",
        ),
        (
            lambda _source: replace(IngestionLimits(), max_archive_total_bytes=200),
            "MXL_ARCHIVE_TOTAL_SIZE_LIMIT",
        ),
        (
            lambda _source: replace(IngestionLimits(), max_compression_ratio=2),
            "MXL_ARCHIVE_COMPRESSION_RATIO_LIMIT",
        ),
    ),
)
def test_public_edge_propagates_archive_budgets_before_package_mapping(
    limit: Callable[[bytes], IngestionLimits],
    expected_code: str,
) -> None:
    """TEST-MXML-SECURITY-014: public parsing obeys every archive budget."""

    source = _deflated_mxl(extra=(("zeros.bin", b"0" * 10_000),))
    limits = limit(source)
    with pytest.raises(MusicXmlBoundaryError) as captured:
        parse_musicxml_package(source, limits=limits)
    assert captured.value.primary.code == expected_code


def test_package_layer_mutations_remain_observable_and_round_trip() -> None:
    """TEST-MXML-MUTATION-003: every package document family remains observable."""

    sounds = (resource_root() / "4.0" / "schema" / "sounds.xml").read_bytes()
    package = parse_musicxml_package(
        _mxl(
            rootfiles=(("score.musicxml", "application/vnd.recordare.musicxml+xml"),),
            entries=(
                ("score.musicxml", _score()),
                ("collection.xml", _opus("score.musicxml")),
                ("sounds.xml", sounds),
                ("preview.pdf", b"%PDF-1.7\nfixture\n"),
            ),
        )
    )
    score = next(item for item in package.documents if isinstance(item, ScoreDocument))
    opus = next(item for item in package.documents if isinstance(item, OpusDocument))
    sound_document = next(item for item in package.documents if isinstance(item, SoundsDocument))
    media = next(item for item in package.documents if isinstance(item, MediaDocument))
    assert isinstance(score.content, CanonicalScoreContent)
    assert opus.content is not None
    assert sound_document.content is not None
    first_entry = sound_document.content.entries[0]
    baseline = package_to_json(package)

    changed_score = replace(
        score,
        content=replace(score.content, score=replace(score.content.score, work_title="Mutated")),
    )
    changed_opus = replace(opus, content=replace(opus.content, title="Mutated collection"))
    changed_entry = replace(first_entry, primary=first_entry.primary is not True)
    changed_sounds = replace(
        sound_document,
        content=replace(
            sound_document.content,
            entries=(changed_entry, *sound_document.content.entries[1:]),
        ),
    )
    changed_media = replace(media, sha256=replace(media.sha256, value="0" * 64))
    changed_relationship = replace(package.relationships[0], href="mutated.musicxml")
    changed_source = replace(
        package.provenance.sources[0],
        sha256=replace(package.provenance.sources[0].sha256, value="1" * 64),
    )

    mutations = (
        replace(
            package,
            documents=tuple(changed_score if item is score else item for item in package.documents),
        ),
        replace(
            package,
            documents=tuple(changed_opus if item is opus else item for item in package.documents),
        ),
        replace(
            package,
            documents=tuple(
                changed_sounds if item is sound_document else item for item in package.documents
            ),
        ),
        replace(
            package,
            documents=tuple(changed_media if item is media else item for item in package.documents),
        ),
        replace(package, relationships=(changed_relationship, *package.relationships[1:])),
        replace(
            package,
            provenance=replace(
                package.provenance,
                sources=(changed_source, *package.provenance.sources[1:]),
            ),
        ),
    )
    for mutation in mutations:
        encoded = package_to_json(mutation)
        assert encoded != baseline
        assert package_from_json(encoded) == mutation


def test_plain_and_compressed_forms_produce_identical_score_content() -> None:
    """TEST-MXML-DIFFERENTIAL-002: XML and MXL converge at the public edge."""

    source = _score()
    plain = parse_musicxml_package(source, logical_name="score.musicxml")
    compressed = parse_musicxml_package(
        _mxl(
            rootfiles=(("score.musicxml", "application/vnd.recordare.musicxml+xml"),),
            entries=(("score.musicxml", source),),
        ),
        logical_name="score.mxl",
    )

    assert _complete_score(plain).id == _complete_score(compressed).id
    assert _complete_score(plain).content == _complete_score(compressed).content
    assert plain.id != compressed.id


def test_archive_directory_order_does_not_change_package_semantics() -> None:
    """TEST-MXML-DIFFERENTIAL-003: ZIP entry order cannot reorder canonical data."""

    resources = (
        ("score.musicxml", _score(part_link="parts/piano.musicxml")),
        ("parts/piano.musicxml", _score(title="Linked")),
        ("preview.pdf", b"%PDF-1.7\nfixture\n"),
    )
    rootfiles = (("score.musicxml", "application/vnd.recordare.musicxml+xml"),)
    first = parse_musicxml_package(_mxl(rootfiles=rootfiles, entries=resources))
    reordered = parse_musicxml_package(
        _mxl(rootfiles=rootfiles, entries=tuple(reversed(resources)))
    )

    def without_outer_source(document: CanonicalDocument) -> CanonicalDocument:
        return replace(document, source_documents=document.source_documents[1:])

    assert tuple(without_outer_source(item) for item in first.documents) == tuple(
        without_outer_source(item) for item in reordered.documents
    )
    assert first.root_documents == reordered.root_documents
    assert first.relationships == reordered.relationships
    assert first.id != reordered.id


def test_invalid_declared_secondary_root_never_returns_a_partial_package() -> None:
    """TEST-MXML-SECURITY-015: one invalid declared root aborts whole-package output."""

    source = _mxl(
        rootfiles=(
            ("score.musicxml", "application/vnd.recordare.musicxml+xml"),
            ("broken.musicxml", "application/vnd.recordare.musicxml+xml"),
        ),
        entries=(("score.musicxml", _score()), ("broken.musicxml", b"not XML")),
    )

    with pytest.raises(MusicXmlBoundaryError) as captured:
        parse_musicxml_package(source)
    assert captured.value.primary.logical_path == "broken.musicxml"
