"""DEV-005 Task 5B.3 governed-fixture projection coverage boundary."""

from __future__ import annotations

from pathlib import Path

from teachmemusic.score import CanonicalScoreContent, ScoreDocument, parse_musicxml_package
from teachmemusic.viewer import (
    NotationProjectionError,
    PlaybackProjectionError,
    build_notation_bundle,
    build_playback_plan,
    validate_playback_plan,
)

_FIXTURES = Path(__file__).parents[1] / "fixtures" / "scores"
_CASES = (
    (
        "TMM-REF-CANDIDATE-001-Hot-Cross-Buns",
        "musicxml-17-hot-cross-buns-final-shelbygtdrew.mxl",
        None,
        None,
    ),
    (
        "TMM-REF-CANDIDATE-002-Happy-Birthday",
        "happy-birthday-to-you-c-major.mxl",
        None,
        None,
    ),
    (
        "TMM-REF-CANDIDATE-003-Clair-de-Lune",
        "clair-de-lune-debussy.mxl",
        None,
        None,
    ),
    (
        "TMM-REF-CANDIDATE-004-Moonlight-Sonata",
        "beethoven-piano-sonata-no-14-moonlight.mxl",
        None,
        None,
    ),
    (
        "TMM-REF-CANDIDATE-005-Deux-Arabesques",
        "debussy-deux-arabesques.mxl",
        None,
        None,
    ),
)
_PLAYBACK_OPTIONS = {
    "TMM-REF-CANDIDATE-003-Clair-de-Lune": {
        "grace_fallback_percent": 25,
    },
    "TMM-REF-CANDIDATE-004-Moonlight-Sonata": {
        "grace_fallback_percent": 25,
        "navigation_section_starts": (0, 69, 133),
    },
    "TMM-REF-CANDIDATE-005-Deux-Arabesques": {
        "grace_fallback_percent": 25,
    },
}


def test_governed_projection_support_and_blockers_are_explicit() -> None:
    """TEST-VIEWER-COVERAGE-001: every fixture either projects or fails explicitly."""

    observed: list[tuple[str, str | None, str | None]] = []
    for directory, name, expected_notation, expected_playback in _CASES:
        path = _FIXTURES / directory / name
        package = parse_musicxml_package(path.read_bytes(), logical_name=path.name)
        notation_code: str | None = None
        playback_code: str | None = None
        try:
            build_notation_bundle(package)
        except NotationProjectionError as error:
            notation_code = error.code
        try:
            build_playback_plan(
                package,
                fallback_tempo_qpm=120,
                **_PLAYBACK_OPTIONS.get(directory, {}),
            )
        except PlaybackProjectionError as error:
            playback_code = error.code
        observed.append((directory, notation_code, playback_code))
        assert notation_code == expected_notation
        assert playback_code == expected_playback

    assert observed == [
        (directory, notation, playback) for directory, _, notation, playback in _CASES
    ]


def test_complex_fixture_rhythmic_projection_inventory_is_fixed() -> None:
    """TEST-VIEWER-COVERAGE-002: Slice 2 is tied to the governed rhythmic facts."""

    expected = {
        "TMM-REF-CANDIDATE-003-Clair-de-Lune": (168, 165, 84, 1, 10),
        "TMM-REF-CANDIDATE-004-Moonlight-Sonata": (971, 971, 576, 59, 49),
        "TMM-REF-CANDIDATE-005-Deux-Arabesques": (1108, 1108, 738, 2, 26),
    }
    observed: dict[str, tuple[int, int, int, int, int]] = {}

    for directory, name, _, _ in _CASES[2:]:
        path = _FIXTURES / directory / name
        package = parse_musicxml_package(path.read_bytes(), logical_name=path.name)
        document = next(item for item in package.documents if isinstance(item, ScoreDocument))
        assert isinstance(document.content, CanonicalScoreContent)
        measures = [measure for part in document.content.score.parts for measure in part.measures]
        events = [event for measure in measures for event in measure.events]
        observed[directory] = (
            sum(event.time_modification is not None or bool(event.tuplets) for event in events),
            sum(event.time_modification is not None for event in events),
            sum(len(event.tuplets) for event in events),
            sum(event.grace for event in events),
            sum(attributes.onset > 0 for measure in measures for attributes in measure.attributes),
        )

    assert observed == expected


def test_complex_fixture_note_attachment_inventory_is_fixed() -> None:
    """TEST-VIEWER-COVERAGE-003: Slice 3 covers every governed attachment kind."""

    expected = {
        "TMM-REF-CANDIDATE-003-Clair-de-Lune": (
            760,
            380,
            139,
            ("notated-tie", "slur", "sounding-tie"),
            ("accent", "arpeggiate", "fermata", "tenuto"),
        ),
        "TMM-REF-CANDIDATE-004-Moonlight-Sonata": (
            1721,
            863,
            852,
            ("notated-tie", "slide", "slur", "sounding-tie", "tremolo", "wavy-line"),
            ("accent", "fermata", "non-arpeggiate", "staccato"),
        ),
        "TMM-REF-CANDIDATE-005-Deux-Arabesques": (
            1330,
            665,
            657,
            ("notated-tie", "slur", "sounding-tie"),
            ("accent", "arpeggiate", "fermata", "staccato", "tenuto"),
        ),
    }
    observed: dict[str, tuple[int, int, int, tuple[str, ...], tuple[str, ...]]] = {}

    for directory, name, _, _ in _CASES[2:]:
        path = _FIXTURES / directory / name
        package = parse_musicxml_package(path.read_bytes(), logical_name=path.name)
        document = next(item for item in package.documents if isinstance(item, ScoreDocument))
        assert isinstance(document.content, CanonicalScoreContent)
        score = document.content.score
        events = [
            event for part in score.parts for measure in part.measures for event in measure.events
        ]
        span_markers = [marker for event in events for marker in event.span_markers]
        event_markers = [marker for event in events for marker in event.event_markers]
        observed[directory] = (
            len(span_markers),
            len(score.annotations.spans),
            len(event_markers),
            tuple(sorted({marker.kind for marker in span_markers})),
            tuple(sorted({marker.kind for marker in event_markers})),
        )

    assert observed == expected
    assert sum(item[0] for item in observed.values()) == 3811
    assert sum(item[1] for item in observed.values()) == 1908
    assert sum(item[2] for item in observed.values()) == 1648


def test_complex_fixture_direction_inventory_is_fixed() -> None:
    """TEST-VIEWER-COVERAGE-004: Slice 4 covers governed direction facts."""

    expected = {
        "TMM-REF-CANDIDATE-003-Clair-de-Lune": (
            78,
            258,
            129,
            0,
            ("dynamic", "words"),
            ("octave-shift", "pedal", "wedge"),
        ),
        "TMM-REF-CANDIDATE-004-Moonlight-Sonata": (
            227,
            233,
            118,
            3,
            ("dynamic", "pedal", "words"),
            ("pedal", "wedge"),
        ),
        "TMM-REF-CANDIDATE-005-Deux-Arabesques": (
            148,
            170,
            85,
            0,
            ("dynamic", "words"),
            ("wedge",),
        ),
    }
    observed: dict[
        str,
        tuple[int, int, int, int, tuple[str, ...], tuple[str, ...]],
    ] = {}

    for directory, name, _, _ in _CASES[2:]:
        path = _FIXTURES / directory / name
        package = parse_musicxml_package(path.read_bytes(), logical_name=path.name)
        document = next(item for item in package.documents if isinstance(item, ScoreDocument))
        assert isinstance(document.content, CanonicalScoreContent)
        score = document.content.score
        measures = [measure for part in score.parts for measure in part.measures]
        directions = [direction for measure in measures for direction in measure.directions]
        markers = [marker for measure in measures for marker in measure.time_span_markers]
        inferred = [
            endpoint
            for span in score.annotations.time_spans
            for endpoint in span.endpoints
            if endpoint.inferred
        ]
        observed[directory] = (
            len(directions),
            len(markers),
            len(score.annotations.time_spans),
            len(inferred),
            tuple(sorted({direction.family for direction in directions})),
            tuple(sorted({marker.kind for marker in markers})),
        )

    assert observed == expected
    assert sum(item[0] for item in observed.values()) == 453
    assert sum(item[1] for item in observed.values()) == 661
    assert sum(item[2] for item in observed.values()) == 332
    assert sum(item[3] for item in observed.values()) == 3


def test_complex_fixture_playback_projection_inventory_is_fixed() -> None:
    """TEST-VIEWER-COVERAGE-005: Slice 5 schedules all complex fixtures."""

    expected = {
        "TMM-REF-CANDIDATE-003-Clair-de-Lune": (1604, 1, 72, 275_667_994),
        "TMM-REF-CANDIDATE-004-Moonlight-Sonata": (8257, 59, 466, 797_459_908),
        "TMM-REF-CANDIDATE-005-Deux-Arabesques": (3299, 2, 217, 411_743_454),
    }
    observed: dict[str, tuple[int, int, int, int]] = {}

    for directory, name, _, _ in _CASES[2:]:
        path = _FIXTURES / directory / name
        package = parse_musicxml_package(path.read_bytes(), logical_name=path.name)
        plan = build_playback_plan(
            package,
            **_PLAYBACK_OPTIONS[directory],
        )
        observed[directory] = (
            len(plan.notes),
            len(plan.grace_realizations),
            len(plan.measure_visits),
            plan.duration_microseconds,
        )
        assert not validate_playback_plan(plan)

    assert observed == expected


def test_all_governed_notation_bundles_are_complete_and_deterministic() -> None:
    """TEST-VIEWER-COVERAGE-006: Slice 6 closes the five-fixture notation audit."""

    expected = {
        "TMM-REF-CANDIDATE-001-Hot-Cross-Buns": (
            30,
            "9280aea64d8ad88a34a023ecfe9ef512814eb2f67b059250f8f71d91a299a7e4",
        ),
        "TMM-REF-CANDIDATE-002-Happy-Birthday": (
            69,
            "3ce20fd1aada912a567544ea1b6754ca66d168c2e2e636b1333a2066f6ae8163",
        ),
        "TMM-REF-CANDIDATE-003-Clair-de-Lune": (
            1880,
            "a87b04a61b4b4f01f18ad9891c0fa01aa3fd628012273de71eca838f820b6957",
        ),
        "TMM-REF-CANDIDATE-004-Moonlight-Sonata": (
            6966,
            "2c0e4f0649e13ad1186ec73972acee9b4a1be732de4d9f33f2376f8bc4b43f28",
        ),
        "TMM-REF-CANDIDATE-005-Deux-Arabesques": (
            3977,
            "997d725a290b323e14891f5e7e75496602e9cf05dfd482b559cf040f22b057d0",
        ),
    }

    observed: dict[str, tuple[int, str]] = {}
    for directory, name, _, _ in _CASES:
        path = _FIXTURES / directory / name
        package = parse_musicxml_package(path.read_bytes(), logical_name=path.name)
        first = build_notation_bundle(package)
        second = build_notation_bundle(package)
        assert first == second
        observed[directory] = (len(first.renderer.anchors), first.renderer.sha256)

    assert observed == expected
