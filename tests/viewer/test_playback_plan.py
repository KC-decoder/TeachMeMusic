"""DEV-005 Task 5B.2 deterministic playback-plan evidence."""

from __future__ import annotations

import inspect
from dataclasses import replace
from fractions import Fraction
from pathlib import Path

import pytest

from teachmemusic.score import (
    CanonicalMusicPackage,
    CanonicalScoreContent,
    ScoreDocument,
    parse_musicxml_package,
)
from teachmemusic.viewer import (
    PlaybackPlanError,
    PlaybackProjectionError,
    build_playback_plan,
    playback_plan,
    playback_plan_to_json,
    playback_state_at,
    validate_playback_plan,
)

_FIXTURES = Path(__file__).parents[1] / "fixtures" / "scores"


def _fixture(directory: str, name: str) -> CanonicalMusicPackage:
    path = _FIXTURES / directory / name
    return parse_musicxml_package(path.read_bytes(), logical_name=path.name)


def _hot_cross_buns() -> CanonicalMusicPackage:
    return _fixture(
        "TMM-REF-CANDIDATE-001-Hot-Cross-Buns",
        "musicxml-17-hot-cross-buns-final-shelbygtdrew.mxl",
    )


def _happy_birthday() -> CanonicalMusicPackage:
    return _fixture(
        "TMM-REF-CANDIDATE-002-Happy-Birthday",
        "happy-birthday-to-you-c-major.mxl",
    )


def _score(body: str) -> bytes:
    return (
        '<?xml version="1.0" encoding="utf-8"?>'
        '<score-partwise version="4.0"><part-list><score-part id="P1">'
        "<part-name>Piano</part-name></score-part></part-list>"
        f'<part id="P1">{body}</part></score-partwise>'
    ).encode()


def test_hot_cross_buns_has_exact_timing_rests_and_source_identity() -> None:
    """TEST-VIEWER-PLAYBACK-001: explicit 96 QPM produces the expected timeline."""

    plan = build_playback_plan(_hot_cross_buns())

    assert plan.duration_microseconds == 20_000_000
    assert len(plan.notes) == 17
    assert len(plan.measure_visits) == 8
    assert [control.quarter_notes_per_minute for control in plan.tempo_controls] == [96]
    assert (plan.notes[0].midi_pitch, plan.notes[0].start_microseconds) == (71, 0)
    assert plan.notes[0].end_microseconds == 1_250_000
    assert plan.notes[2].end_microseconds == 4_375_000
    assert plan.notes[3].start_microseconds == 5_000_000
    assert all(note.source_events[0].event_id for note in plan.notes)
    assert {source.clef.sign for note in plan.notes for source in note.source_events} == {"G"}
    assert validate_playback_plan(plan) == ()


def test_happy_birthday_requires_and_records_explicit_fallback_tempo() -> None:
    """TEST-VIEWER-PLAYBACK-002: absent source tempo is never silently invented."""

    package = _happy_birthday()
    with pytest.raises(PlaybackProjectionError) as captured:
        build_playback_plan(package)
    assert captured.value.code == "VIEWER_PLAYBACK_TEMPO_REQUIRED"

    plan = build_playback_plan(package, fallback_tempo_qpm=120)
    assert plan.duration_microseconds == 12_000_000
    assert plan.tempo_controls[0].origin == "caller-fallback"
    assert [item.code for item in plan.diagnostics] == ["VIEWER_PLAYBACK_TEMPO_FALLBACK"]


def test_happy_birthday_chords_are_simultaneous_and_clefs_remain_distinct() -> None:
    """TEST-VIEWER-PLAYBACK-003: chord notes and piano clef groups survive projection."""

    plan = build_playback_plan(_happy_birthday(), fallback_tempo_qpm=Fraction(120))
    first_chord = [note for note in plan.notes if note.chord_id is not None][:3]

    assert len(plan.notes) == 52
    assert len({note.chord_id for note in plan.notes if note.chord_id is not None}) == 9
    assert [note.midi_pitch for note in first_chord] == [48, 52, 55]
    assert {(note.start_microseconds, note.end_microseconds) for note in first_chord} == {
        (500_000, 1_500_000)
    }
    assert {
        (source.clef.sign, source.clef.line)
        for note in plan.notes
        for source in note.source_events
        if source.clef is not None
    } == {("G", 2), ("F", 4)}


def test_simple_repeat_is_expanded_with_distinct_occurrences() -> None:
    """TEST-VIEWER-PLAYBACK-004: a bounded repeat creates two traceable visits."""

    source = _score(
        '<measure number="1"><attributes><divisions>1</divisions>'
        "<time><beats>1</beats><beat-type>4</beat-type></time>"
        "<clef><sign>G</sign><line>2</line></clef></attributes>"
        '<barline location="left"><repeat direction="forward"/></barline>'
        '<sound tempo="60"/><note><pitch><step>C</step><octave>4</octave></pitch>'
        "<duration>1</duration><voice>1</voice><type>quarter</type><staff>1</staff>"
        '</note><barline location="right"><repeat direction="backward" times="2"/>'
        "</barline></measure>"
    )
    package = parse_musicxml_package(source, logical_name="repeat.musicxml")

    plan = build_playback_plan(package)

    assert plan.duration_microseconds == 2_000_000
    assert [visit.source_measure_index for visit in plan.measure_visits] == [0, 0]
    assert [(note.start_microseconds, note.end_microseconds) for note in plan.notes] == [
        (0, 1_000_000),
        (1_000_000, 2_000_000),
    ]
    assert plan.notes[0].id != plan.notes[1].id
    assert [item.code for item in plan.diagnostics] == ["VIEWER_PLAYBACK_REPEATS_EXPANDED"]


def test_sounding_tie_becomes_one_sustained_note_with_both_sources() -> None:
    """TEST-VIEWER-PLAYBACK-005: tied attacks merge without losing canonical IDs."""

    source = _score(
        '<measure number="1"><attributes><divisions>1</divisions>'
        "<time><beats>1</beats><beat-type>4</beat-type></time>"
        "<clef><sign>G</sign><line>2</line></clef></attributes>"
        '<sound tempo="120"/><note><pitch><step>C</step><octave>4</octave></pitch>'
        '<duration>1</duration><tie type="start"/><voice>1</voice><type>quarter</type>'
        '<staff>1</staff><notations><tied type="start"/></notations></note></measure>'
        '<measure number="2"><note><pitch><step>C</step><octave>4</octave></pitch>'
        '<duration>1</duration><tie type="stop"/><voice>1</voice><type>quarter</type>'
        '<staff>1</staff><notations><tied type="stop"/></notations></note></measure>'
    )
    package = parse_musicxml_package(source, logical_name="tie.musicxml")

    plan = build_playback_plan(package)

    assert len(plan.notes) == 1
    assert (plan.notes[0].start_microseconds, plan.notes[0].end_microseconds) == (
        0,
        1_000_000,
    )
    assert len(plan.notes[0].source_events) == 2


def test_tempo_change_and_transport_boundaries_are_deterministic() -> None:
    """TEST-VIEWER-PLAYBACK-006: tempo integration and seeking share one timeline."""

    source = _score(
        '<measure number="1"><attributes><divisions>1</divisions>'
        "<time><beats>4</beats><beat-type>4</beat-type></time>"
        "<clef><sign>G</sign><line>2</line></clef></attributes>"
        '<sound tempo="60"/><note><pitch><step>C</step><octave>4</octave></pitch>'
        "<duration>2</duration><voice>1</voice><type>half</type><staff>1</staff></note>"
        '<sound tempo="120"/><note><pitch><step>D</step><octave>4</octave></pitch>'
        "<duration>2</duration><voice>1</voice><type>half</type><staff>1</staff></note>"
        "</measure>"
    )
    package = parse_musicxml_package(source, logical_name="tempo.musicxml")
    plan = build_playback_plan(package)

    assert plan.duration_microseconds == 3_000_000
    assert [control.at_microseconds for control in plan.tempo_controls] == [0, 2_000_000]
    assert [(note.start_microseconds, note.end_microseconds) for note in plan.notes] == [
        (0, 2_000_000),
        (2_000_000, 3_000_000),
    ]
    before = playback_state_at(plan, 1_999_999)
    boundary = playback_state_at(plan, 2_000_000)
    complete = playback_state_at(plan, 3_000_000)
    assert before.active_note_ids == (plan.notes[0].id,)
    assert boundary.active_note_ids == (plan.notes[1].id,)
    assert complete.active_note_ids == () and complete.completed


def test_playback_contract_serialization_is_stable_and_fails_closed() -> None:
    """TEST-VIEWER-PLAYBACK-007: JSON is deterministic and invalid timing is rejected."""

    plan = build_playback_plan(_hot_cross_buns())
    assert playback_plan_to_json(plan) == playback_plan_to_json(plan)

    invalid = replace(
        plan,
        notes=(replace(plan.notes[0], end_microseconds=0), *plan.notes[1:]),
    )
    assert {issue.code for issue in validate_playback_plan(invalid)} == {"PLAYBACK_NOTE_TIME"}
    with pytest.raises(PlaybackPlanError):
        playback_plan_to_json(invalid)


def test_playback_projection_has_no_source_xml_or_audio_engine_backdoor() -> None:
    """TEST-VIEWER-PLAYBACK-008: planning consumes only the public canonical package."""

    source = inspect.getsource(playback_plan)
    assert "teachmemusic.score.musicxml" not in source
    assert "lxml" not in source
    assert "Tone.js" not in source
    assert "source: bytes" not in source
    assert "original_musicxml" not in source


def test_canonical_tempo_mutation_controls_the_plan() -> None:
    """TEST-VIEWER-PLAYBACK-009: timing follows canonical state, not source bytes."""

    package = _hot_cross_buns()
    document = next(item for item in package.documents if isinstance(item, ScoreDocument))
    assert isinstance(document.content, CanonicalScoreContent)
    score = document.content.score
    part = score.parts[0]
    measure = part.measures[0]
    changed_sound = replace(measure.sounds[0], tempo=Fraction(120))
    changed_measure = replace(measure, sounds=(changed_sound,))
    changed_part = replace(part, measures=(changed_measure, *part.measures[1:]))
    changed_score = replace(score, parts=(changed_part,))
    changed_document = replace(document, content=replace(document.content, score=changed_score))
    changed_package = replace(
        package,
        documents=tuple(
            changed_document if item is document else item for item in package.documents
        ),
    )

    original = build_playback_plan(package)
    changed = build_playback_plan(changed_package)

    assert original.duration_microseconds == 20_000_000
    assert changed.duration_microseconds == 16_000_000
    assert changed.tempo_controls[0].quarter_notes_per_minute == 120


def test_dacapo_fine_and_explicit_embedded_sections_expand_deterministically() -> None:
    """TEST-VIEWER-PLAYBACK-010: Da Capo/Fine can resume a later embedded section."""

    source = _score(
        '<measure number="1"><attributes><divisions>1</divisions>'
        "<time><beats>1</beats><beat-type>4</beat-type></time>"
        "<clef><sign>G</sign><line>2</line></clef></attributes>"
        '<sound tempo="60"/><note><pitch><step>C</step><octave>4</octave></pitch>'
        "<duration>1</duration><voice>1</voice><type>quarter</type><staff>1</staff>"
        '</note><sound fine="yes"/></measure><measure number="2">'
        "<note><pitch><step>D</step><octave>4</octave></pitch><duration>1</duration>"
        "<voice>1</voice><type>quarter</type><staff>1</staff></note></measure>"
        '<measure number="3"><note><pitch><step>E</step><octave>4</octave></pitch>'
        "<duration>1</duration><voice>1</voice><type>quarter</type><staff>1</staff>"
        '</note><sound dacapo="yes"/></measure><measure number="4">'
        "<note><pitch><step>F</step><octave>4</octave></pitch><duration>1</duration>"
        "<voice>1</voice><type>quarter</type><staff>1</staff></note></measure>"
    )
    package = parse_musicxml_package(source, logical_name="navigation.musicxml")

    plan = build_playback_plan(package, navigation_section_starts=(0, 3))

    assert [visit.source_measure_index for visit in plan.measure_visits] == [0, 1, 2, 0, 3]
    assert [visit.entry_reason for visit in plan.measure_visits] == [
        "initial",
        "sequential",
        "sequential",
        "jump",
        "jump",
    ]
    assert plan.navigation_section_starts == (0, 3)
    assert plan.duration_microseconds == 5_000_000
    assert {item.code for item in plan.diagnostics} == {
        "VIEWER_PLAYBACK_NAVIGATION_EXPANDED",
        "VIEWER_PLAYBACK_NAVIGATION_SECTIONS",
    }


def test_unspecified_grace_cluster_requires_and_records_explicit_policy() -> None:
    """TEST-VIEWER-PLAYBACK-011: caller grace timing is visible and deterministic."""

    source = _score(
        '<measure number="1"><attributes><divisions>4</divisions>'
        "<time><beats>1</beats><beat-type>4</beat-type></time>"
        "<clef><sign>G</sign><line>2</line></clef></attributes>"
        '<sound tempo="60"/><note><grace/><pitch><step>D</step><octave>4</octave>'
        "</pitch><voice>1</voice><type>eighth</type><staff>1</staff></note>"
        "<note><grace/><pitch><step>E</step><octave>4</octave></pitch><voice>1</voice>"
        "<type>eighth</type><staff>1</staff></note><note><pitch><step>F</step>"
        "<octave>4</octave></pitch><duration>4</duration><voice>1</voice>"
        "<type>quarter</type><staff>1</staff></note></measure>"
    )
    package = parse_musicxml_package(source, logical_name="grace.musicxml")
    with pytest.raises(PlaybackProjectionError) as captured:
        build_playback_plan(package)
    assert captured.value.code == "VIEWER_PLAYBACK_GRACE_POLICY_REQUIRED"

    plan = build_playback_plan(package, grace_fallback_percent=25)

    assert [(note.start_microseconds, note.end_microseconds) for note in plan.notes] == [
        (0, 125_000),
        (125_000, 250_000),
        (250_000, 1_000_000),
    ]
    assert [item.duration_quarter_notes for item in plan.grace_realizations] == [
        Fraction(1, 8),
        Fraction(1, 8),
    ]
    assert {item.origin for item in plan.grace_realizations} == {"caller-fallback"}
    assert plan.duration_microseconds == 1_000_000


def test_source_grace_timing_precedes_caller_fallback() -> None:
    """TEST-VIEWER-PLAYBACK-012: explicit MusicXML grace timing wins."""

    source = _score(
        '<measure number="1"><attributes><divisions>4</divisions></attributes>'
        '<sound tempo="60"/><note><grace steal-time-following="20"/>'
        "<pitch><step>D</step><octave>4</octave></pitch><voice>1</voice>"
        "<type>eighth</type></note><note><pitch><step>E</step><octave>4</octave>"
        "</pitch><duration>4</duration><voice>1</voice><type>quarter</type></note>"
        "</measure>"
    )
    plan = build_playback_plan(
        parse_musicxml_package(source, logical_name="source-grace.musicxml"),
        grace_fallback_percent=40,
    )

    assert plan.grace_realizations[0].origin == "source-steal-following"
    assert plan.grace_realizations[0].duration_quarter_notes == Fraction(1, 5)
    assert [(note.start_microseconds, note.end_microseconds) for note in plan.notes] == [
        (0, 200_000),
        (200_000, 1_000_000),
    ]
    assert "VIEWER_PLAYBACK_GRACE_FALLBACK" not in {item.code for item in plan.diagnostics}


def test_first_and_second_endings_select_the_matching_repeat_pass() -> None:
    """TEST-VIEWER-PLAYBACK-013: volta measures are selected, not duplicated."""

    source = _score(
        '<measure number="1"><attributes><divisions>1</divisions>'
        "<clef><sign>G</sign><line>2</line></clef></attributes>"
        '<barline location="left"><repeat direction="forward"/></barline>'
        '<sound tempo="60"/><note><pitch><step>C</step><octave>4</octave></pitch>'
        "<duration>1</duration><type>quarter</type></note></measure>"
        '<measure number="2"><barline location="left"><ending number="1" '
        'type="start"/></barline><note><pitch><step>D</step><octave>4</octave>'
        "</pitch><duration>1</duration><type>quarter</type></note>"
        '<barline location="right"><ending number="1" type="stop"/>'
        '<repeat direction="backward"/></barline></measure>'
        '<measure number="3"><barline location="left"><ending number="2" '
        'type="start"/></barline><note><pitch><step>E</step><octave>4</octave>'
        "</pitch><duration>1</duration><type>quarter</type></note>"
        '<barline location="right"><ending number="2" type="discontinue"/>'
        "</barline></measure>"
    )
    plan = build_playback_plan(parse_musicxml_package(source, logical_name="endings.musicxml"))

    assert [visit.source_measure_index for visit in plan.measure_visits] == [0, 1, 0, 2]
    assert [note.midi_pitch for note in plan.notes] == [60, 62, 60, 64]
    assert {item.code for item in plan.diagnostics} == {
        "VIEWER_PLAYBACK_REPEATS_EXPANDED",
        "VIEWER_PLAYBACK_ENDINGS_EXPANDED",
    }


def test_missing_navigation_target_still_fails_closed() -> None:
    """TEST-VIEWER-PLAYBACK-014: unresolved Dal Segno cannot be guessed."""

    source = _score(
        '<measure number="1"><attributes><divisions>1</divisions></attributes>'
        '<sound tempo="60"/><note><rest/><duration>1</duration><type>quarter</type>'
        '</note><sound dalsegno="missing"/></measure>'
    )
    package = parse_musicxml_package(source, logical_name="missing-segno.musicxml")

    with pytest.raises(PlaybackProjectionError) as captured:
        build_playback_plan(package)

    assert captured.value.code == "VIEWER_PLAYBACK_NAVIGATION_TARGET"
