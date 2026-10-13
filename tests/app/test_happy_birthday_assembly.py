"""DEV-009 Tasks 9N.1–9N.5 Happy Birthday production assembly evidence."""

from __future__ import annotations

import hashlib
from collections import Counter
from dataclasses import replace
from fractions import Fraction
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from teachmemusic.app import create_app
from teachmemusic.app.sessions import SessionStore
from teachmemusic.performance import (
    AttemptCompletion,
    CalibrationProfile,
    LearnerAttempt,
    MidiEventKind,
    NormalizedMidiEvent,
    align_layer_attempt,
)
from teachmemusic.score import CanonicalMusicPackage
from teachmemusic.teaching import (
    AcquisitionStageKind,
    CompatibleTempoEvidence,
    CurriculumAnalysisAssembly,
    CurriculumAnalysisAssemblyError,
    CurriculumMasteryStatus,
    CurriculumPolicyAction,
    CurriculumRehearsalError,
    CurriculumValidationError,
    EvidenceContext,
    ExecutionAssignment,
    NotationCondition,
    PracticeMode,
    SemanticReference,
    SupportState,
    TempoReferenceAuthority,
    assemble_curriculum_analysis,
    assemble_curriculum_fundamentals,
    assemble_curriculum_practice,
    assemble_curriculum_remediation_rehearsal,
    build_curriculum_evidence_records,
    build_curriculum_layer_expected_performance,
    build_curriculum_rehearsal_export,
    build_curriculum_rehearsal_graph,
    curriculum_rehearsal_export_from_json,
    curriculum_rehearsal_export_to_json,
    decide_curriculum_support,
    decide_curriculum_unlock,
    reconcile_curriculum_rehearsal,
    replay_curriculum_rehearsal,
    require_valid_curriculum_analysis_manifest,
    require_valid_curriculum_fundamental_manifest,
    require_valid_curriculum_practice_manifest,
    require_valid_curriculum_remediation_manifest,
)

_FIXTURE = (
    Path(__file__).parents[1]
    / "fixtures"
    / "scores"
    / "TMM-REF-CANDIDATE-002-Happy-Birthday"
    / "happy-birthday-to-you-c-major.mxl"
)
_TOKEN = "task-9n1-token"
_HEADERS = {"X-TeachMeMusic-Token": _TOKEN}


def _uploaded_assembly() -> tuple[
    dict[str, object], CanonicalMusicPackage, CurriculumAnalysisAssembly
]:
    store = SessionStore(
        max_sessions=1,
        ttl_seconds=1_800,
        id_factory=lambda: "session:gate-one-happy-birthday",
    )
    app = create_app(launch_token=_TOKEN, store=store)
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/viewer-sessions",
            headers=_HEADERS,
            files={
                "score": (
                    _FIXTURE.name,
                    _FIXTURE.read_bytes(),
                    "application/vnd.recordare.musicxml",
                )
            },
        )
        assert response.status_code == 201, response.text
        upload = response.json()
        session = store.get(upload["session_id"])
        assembly = assemble_curriculum_analysis(
            session.package,
            score_id=upload["scores"][0]["score_id"],
        )
        return upload, session.package, assembly


def _synthetic_tempo_evidence(
    analysis_assembly: CurriculumAnalysisAssembly,
) -> tuple[CompatibleTempoEvidence, ...]:
    percentages = {
        NotationCondition.UPPER_LAYER: 85,
        NotationCondition.LOWER_LAYER: 70,
        NotationCondition.COMBINED: 70,
    }
    return tuple(
        CompatibleTempoEvidence(
            SemanticReference(
                "practice-scope-assignment",
                scope.id,
                scope.semantic_fingerprint,
            ),
            "independent-piece",
            percentages[scope.notation_condition],
            percentages[scope.notation_condition],
            True,
            True,
            (f"synthetic:9n3:{scope.notation_condition.value}",),
        )
        for scope in analysis_assembly.requirements.scopes
    )


def _practice_assembly(package, analysis_assembly):
    fundamental = assemble_curriculum_fundamentals(package, analysis_assembly)
    practice = assemble_curriculum_practice(
        package,
        analysis_assembly,
        fundamental,
        reference_tempo_bpm=Fraction(120),
        reference_authority=TempoReferenceAuthority.CALLER,
        tempo_evidence=_synthetic_tempo_evidence(analysis_assembly),
    )
    return fundamental, practice


def _upper_support_states() -> tuple[tuple[str, SupportState], ...]:
    tempo = Fraction(102)
    return (
        (
            "guided-piece",
            SupportState(
                id="support:9n4:upper:guided-piece",
                notation_visible=True,
                cursor_visible=True,
                note_names_visible=True,
                keyboard_highlighting=True,
                fingering_visible=False,
                demonstration_available=True,
                follow_mode=False,
                metronome=True,
                tempo_percent=85,
                isolated_layers=(NotationCondition.UPPER_LAYER.value,),
                isolated_dimensions=(),
                tempo_bpm=tempo,
            ),
        ),
        (
            "independent-piece",
            SupportState(
                id="support:9n4:upper:independent-piece",
                notation_visible=True,
                cursor_visible=False,
                note_names_visible=False,
                keyboard_highlighting=False,
                fingering_visible=False,
                demonstration_available=False,
                follow_mode=False,
                metronome=True,
                tempo_percent=85,
                isolated_layers=(NotationCondition.UPPER_LAYER.value,),
                isolated_dimensions=(),
                tempo_bpm=tempo,
            ),
        ),
    )


def _calibration() -> CalibrationProfile:
    return CalibrationProfile(
        id="calibration:9n4-rehearsal",
        version="calibration-v1",
        device_id="device:9n4-synthetic",
        input_name="Task 9N.4 synthetic rehearsal",
        timestamp_origin="monotonic-microseconds",
        pitch_numbering_confirmed=True,
        sustain_available=True,
        clock_offset_microseconds=0,
        clock_jitter_microseconds=1_000,
        timing_window_microseconds=50_000,
        chord_window_microseconds=50_000,
        approved=True,
        approved_at_utc="2026-10-13T12:00:00Z",
    )


def _exact_attempt(expected, *, attempt_id: str, support_state_id: str) -> LearnerAttempt:
    start = 1_000_000
    events = tuple(
        event
        for index, note in enumerate(expected.notes)
        for event in (
            NormalizedMidiEvent(
                id=f"midi-event:9n4-{index:03d}-on:{attempt_id}",
                raw_message_id=None,
                kind=MidiEventKind.NOTE_ON,
                timestamp_microseconds=start + note.start_microseconds,
                channel=1,
                note=note.midi_pitch,
                velocity=80,
            ),
            NormalizedMidiEvent(
                id=f"midi-event:9n4-{index:03d}-off:{attempt_id}",
                raw_message_id=None,
                kind=MidiEventKind.NOTE_OFF,
                timestamp_microseconds=start + note.end_microseconds,
                channel=1,
                note=note.midi_pitch,
                velocity=0,
            ),
        )
    )
    ordered = tuple(sorted(events, key=lambda item: (item.timestamp_microseconds, item.id)))
    return LearnerAttempt(
        id=attempt_id,
        run_id="run:9n4-happy-birthday",
        exercise_id=expected.exercise_id,
        calibration_id=_calibration().id,
        practice_mode=expected.practice_mode,
        support_state_id=support_state_id,
        started_at_utc="2026-10-13T12:01:00Z",
        start_microseconds=start,
        end_microseconds=ordered[-1].timestamp_microseconds + 1_000,
        completion=AttemptCompletion.COMPLETED,
        normalized_events=ordered,
    )


def _changed_first_pitch(attempt):
    note_on_index = next(
        index
        for index, event in enumerate(attempt.normalized_events)
        if event.kind is MidiEventKind.NOTE_ON
    )
    original_note = attempt.normalized_events[note_on_index].note
    assert original_note is not None
    note_off_index = next(
        index
        for index, event in enumerate(
            attempt.normalized_events[note_on_index + 1 :], note_on_index + 1
        )
        if event.kind is MidiEventKind.NOTE_OFF and event.note == original_note
    )
    events = list(attempt.normalized_events)
    events[note_on_index] = replace(events[note_on_index], note=original_note + 1)
    events[note_off_index] = replace(events[note_off_index], note=original_note + 1)
    return replace(attempt, normalized_events=tuple(events))


def _remediation_rehearsal(package, analysis_assembly):
    fundamental, practice = _practice_assembly(package, analysis_assembly)
    graph = practice.acquisition
    upper_presentation = next(
        item
        for item in practice.presentations
        if item.notation_condition is NotationCondition.UPPER_LAYER
    )
    stage = graph.stages[0]
    node = next(item for item in graph.nodes if item.id == stage.node_id)
    expected = build_curriculum_layer_expected_performance(
        package,
        upper_presentation,
        PracticeMode.INDEPENDENT_PERFORMANCE,
        tempo_bpm=Fraction(102),
    )
    support_states = _upper_support_states()
    support_by_condition = dict(support_states)
    stage_node_ids = {item.node_id for item in graph.stages}
    prerequisite_closure = tuple(
        item.id
        for item in graph.nodes
        if item.id
        in {
            dependency
            for candidate in graph.stages
            for dependency in next(
                graph_node for graph_node in graph.nodes if graph_node.id == candidate.node_id
            ).component_node_ids
            if dependency not in stage_node_ids
        }
    )
    specifications = (
        ("guided-piece", False),
        ("guided-piece", False),
        ("guided-piece", True),
        ("guided-piece", True),
        ("independent-piece", True),
    )
    decisions = []
    masteries = []
    unlocks = []
    for serial, (condition, exact) in enumerate(specifications):
        support = support_by_condition[condition]
        attempt = _exact_attempt(
            expected,
            attempt_id=f"attempt:9n4-happy-birthday-{serial}",
            support_state_id=support.id,
        )
        if not exact:
            attempt = _changed_first_pitch(attempt)
        observations = align_layer_attempt(expected, attempt, _calibration())
        records = tuple(
            item
            for item in build_curriculum_evidence_records(
                analysis_assembly.requirements,
                expected,
                attempt,
                support,
                observations,
                EvidenceContext.INDEPENDENT,
            )
            if item.requirement_ref.id == node.requirement_ref.id
        )
        projection, unlock = decide_curriculum_unlock(
            graph,
            node.id,
            support,
            records,
            previously_satisfied_node_ids=prerequisite_closure,
        )
        masteries.append(projection)
        unlocks.append(unlock)
        decisions.append(
            decide_curriculum_support(
                graph,
                node.id,
                condition,
                support_states,
                projection,
                unlock,
                decision_sequence=serial,
                history=tuple(decisions),
            )
        )
    rehearsal = assemble_curriculum_remediation_rehearsal(
        package,
        analysis_assembly,
        fundamental,
        practice,
        tuple(decisions),
    )
    return (
        fundamental,
        practice,
        node,
        expected,
        rehearsal,
        tuple(masteries),
        tuple(unlocks),
    )


def test_happy_birthday_upload_retains_the_complete_analysis_identity_chain() -> None:
    """TEST-CURR-ASSEMBLY-001: real upload reaches exact curriculum identities."""

    upload, package, assembly = _uploaded_assembly()
    manifest = assembly.manifest
    analysis = assembly.analysis
    requirements = assembly.requirements

    assert hashlib.sha256(_FIXTURE.read_bytes()).hexdigest() == (
        "32cd97167d5c3dcef483c9d3e81a9e94b81e58f504416710c38524cd48b7eacf"
    )
    assert (
        upload["package_id"]
        == manifest.package_id
        == ("package:32cd97167d5c3dcef483c9d3e81a9e94b81e58f504416710c38524cd48b7eacf")
    )
    assert upload["scores"] == [
        {
            "score_id": "score:0922d87aa4b674b8e779a9aa9efb36fd9cfffc56ae7d7aaff1aea110297b8867",
            "title": None,
        }
    ]
    assert manifest.score_id == upload["scores"][0]["score_id"]
    assert manifest.canonical_digest_sha256 == (
        "5d11adce4121bf72521b6ce49e61c857927733544a73102186737f0fde95df14"
    )
    assert manifest.analysis_id == analysis.id == "analysis:31674f2591dec9aa990ec0eb"
    assert manifest.part_ids == (
        "document:0922d87aa4b674b8e779a9aa9efb36fd9cfffc56ae7d7aaff1aea110297b8867:P1",
    )
    assert (manifest.start_measure_ordinal, manifest.end_measure_ordinal) == (1, 8)
    assert tuple(item.sha256 for item in manifest.sources) == (
        "32cd97167d5c3dcef483c9d3e81a9e94b81e58f504416710c38524cd48b7eacf",
        "964fb4320178c308c8de22bdaca04f8ac39208259970d4270af282e86fd8b597",
    )
    assert tuple(item.logical_name for item in manifest.sources) == (
        _FIXTURE.name,
        "lg-307757872161298588.xml",
    )

    scopes = {item.notation_condition: item for item in requirements.scopes}
    assert {
        condition: (len(scope.active_target_ids), len(scope.inactive_context_ids))
        for condition, scope in scopes.items()
    } == {
        NotationCondition.UPPER_LAYER: (25, 34),
        NotationCondition.LOWER_LAYER: (34, 25),
        NotationCondition.COMBINED: (59, 0),
    }
    assert len(manifest.practice_scope_refs) == 3
    assert len(manifest.requirement_refs) == len(requirements.requirements) == 48
    assert manifest.diagnostic_codes == ()
    assert manifest.id == (
        "curriculum-analysis-assembly:"
        "c5a36a522c3b6d878024045b9ec14d6f7b6a8a7aedf6119ac906c9882b532b14"
    )
    assert assemble_curriculum_analysis(package, score_id=manifest.score_id) == assembly


def test_happy_birthday_assembly_rejects_identity_drift() -> None:
    """TEST-CURR-ROBUSTNESS-051: detached source and score identities fail closed."""

    _, package, assembly = _uploaded_assembly()
    with pytest.raises(CurriculumAnalysisAssemblyError, match="TMM-ASSEMBLY-IDENTITY"):
        require_valid_curriculum_analysis_manifest(
            replace(assembly.manifest, score_id="score:detached"),
            package,
            assembly.analysis,
            assembly.requirements,
        )
    changed_source = replace(
        assembly.manifest.sources[0],
        sha256="0" * 64,
    )
    with pytest.raises(CurriculumAnalysisAssemblyError, match="TMM-ASSEMBLY-SOURCE"):
        require_valid_curriculum_analysis_manifest(
            replace(
                assembly.manifest,
                sources=(changed_source, *assembly.manifest.sources[1:]),
            ),
            package,
            assembly.analysis,
            assembly.requirements,
        )


def test_happy_birthday_generates_complete_fundamental_and_diagnostic_routes() -> None:
    """TEST-CURR-ASSEMBLY-002: every resolved requirement gets its exact branch."""

    _, package, analysis_assembly = _uploaded_assembly()
    assembly = assemble_curriculum_fundamentals(package, analysis_assembly)
    manifest = assembly.manifest
    branches = assembly.branches

    assert manifest.analysis_assembly_ref == SemanticReference(
        "curriculum-analysis-assembly",
        analysis_assembly.manifest.id,
        analysis_assembly.manifest.semantic_fingerprint,
    )
    assert manifest.resolution.value == "resolved"
    assert len(manifest.primitive_refs) == 16
    assert len(manifest.branch_requirement_refs) == 48
    assert set(manifest.branch_requirement_refs) == set(analysis_assembly.manifest.requirement_refs)
    assert len(manifest.diagnostic_exercise_refs) == 48
    assert len(manifest.prerequisite_exercise_refs) == 48
    assert len(manifest.application_exercise_refs) == 48
    assert manifest.diagnostic_codes == ()
    assert manifest.branch_set_fingerprint == (
        "54dc6681251bc565ec93aa511a495c8cebdc86ff959047987a9740d15afe9d4c"
    )
    assert manifest.id == (
        "curriculum-fundamental-assembly:"
        "dd6eed91aeb5c6e7806b8b69b4606ca3e77751a4012e1b225c02d711adb44a16"
    )
    assert len(branches.branches) == 48
    assert len(branches.exercises) == 144
    assert Counter(item.kind.value for item in branches.nodes) == {
        "application": 48,
        "diagnostic": 48,
        "prerequisite": 48,
        "primitive": 16,
    }
    assert Counter(item.kind.value for item in branches.edges) == {
        "on-satisfied": 48,
        "on-unconfirmed": 48,
        "realized-by": 144,
        "requires": 91,
        "return-to": 48,
    }
    assert assemble_curriculum_fundamentals(package, analysis_assembly) == assembly


def test_happy_birthday_fundamental_assembly_rejects_reference_drift() -> None:
    """TEST-CURR-ROBUSTNESS-052: upstream and generated route drift fail closed."""

    _, package, analysis_assembly = _uploaded_assembly()
    assembly = assemble_curriculum_fundamentals(package, analysis_assembly)
    with pytest.raises(CurriculumAnalysisAssemblyError, match="TMM-ASSEMBLY-IDENTITY"):
        require_valid_curriculum_fundamental_manifest(
            replace(
                assembly.manifest,
                analysis_assembly_ref=replace(
                    assembly.manifest.analysis_assembly_ref,
                    id="curriculum-analysis-assembly:detached",
                ),
            ),
            package,
            analysis_assembly,
            assembly.branches,
        )
    with pytest.raises(CurriculumAnalysisAssemblyError, match="TMM-ASSEMBLY-BRANCH"):
        require_valid_curriculum_fundamental_manifest(
            replace(assembly.manifest, branch_set_fingerprint="0" * 64),
            package,
            analysis_assembly,
            assembly.branches,
        )
    with pytest.raises(CurriculumValidationError):
        require_valid_curriculum_fundamental_manifest(
            assembly.manifest,
            package,
            analysis_assembly,
            replace(assembly.branches, edges=assembly.branches.edges[1:]),
        )


def test_happy_birthday_assembles_complete_layered_practice_path() -> None:
    """TEST-CURR-ASSEMBLY-003: exact upper/lower/combined practice is assembled."""

    _, package, analysis_assembly = _uploaded_assembly()
    fundamental_assembly = assemble_curriculum_fundamentals(package, analysis_assembly)
    evidence = _synthetic_tempo_evidence(analysis_assembly)
    assembly = assemble_curriculum_practice(
        package,
        analysis_assembly,
        fundamental_assembly,
        reference_tempo_bpm=Fraction(120),
        reference_authority=TempoReferenceAuthority.CALLER,
        tempo_evidence=evidence,
    )
    manifest = assembly.manifest
    graph = assembly.acquisition

    assert manifest.fundamental_assembly_ref == SemanticReference(
        "curriculum-fundamental-assembly",
        fundamental_assembly.manifest.id,
        fundamental_assembly.manifest.semantic_fingerprint,
    )
    assert manifest.reference_tempo_bpm == 120
    assert manifest.reference_authority is TempoReferenceAuthority.CALLER
    assert manifest.tempo_evidence_refs == tuple(sorted(item.evidence_refs[0] for item in evidence))
    assert manifest.diagnostic_codes == ()
    assert manifest.id == (
        "curriculum-practice-assembly:"
        "2a9c759b90e757c178d0932e0a272856ce376f92f61a87937e75ec2b2e808e0b"
    )
    assert tuple(item.notation_condition for item in assembly.presentations) == (
        NotationCondition.UPPER_LAYER,
        NotationCondition.LOWER_LAYER,
        NotationCondition.COMBINED,
    )
    assert tuple(
        (len(item.active_target_ids), len(item.inactive_context_ids))
        for item in assembly.presentations
    ) == ((25, 34), (34, 25), (59, 0))
    assert all(
        item.execution_assignment is ExecutionAssignment.UNASSIGNED
        for item in assembly.presentations
    )
    assert all(len(item.measure_ids) == 8 for item in assembly.presentations)
    assert tuple(item.kind for item in graph.stages) == (
        AcquisitionStageKind.COMPONENT_ACQUISITION,
        AcquisitionStageKind.COMPONENT_ACQUISITION,
        AcquisitionStageKind.SELF_PACED_COORDINATION,
        AcquisitionStageKind.PULSE_INTEGRATION,
        AcquisitionStageKind.PHRASE_CONTROLLED_TEMPO,
        AcquisitionStageKind.LEARNED_TO_DATE,
        AcquisitionStageKind.TEMPO_DEVELOPMENT,
    )
    assert tuple(item.current_controlled_percentage for item in graph.tempo_plans) == (
        85,
        70,
        70,
    )
    assert (len(graph.nodes), len(graph.edges), len(graph.exercises), len(graph.stages)) == (
        165,
        388,
        149,
        7,
    )
    coordination = graph.stages[2]
    assert len(coordination.component_node_ids) == 2
    assert graph.semantic_fingerprint == (
        "eada400717bc4d7cd57ed70cb39b4d1aeb7f71021931061233caa588ea51303f"
    )
    assert (
        assemble_curriculum_practice(
            package,
            analysis_assembly,
            fundamental_assembly,
            reference_tempo_bpm=Fraction(120),
            reference_authority=TempoReferenceAuthority.CALLER,
            tempo_evidence=evidence,
        )
        == assembly
    )


def test_happy_birthday_practice_assembly_rejects_route_drift() -> None:
    """TEST-CURR-ROBUSTNESS-053: practice identity and coverage drift fail closed."""

    _, package, analysis_assembly = _uploaded_assembly()
    fundamental_assembly = assemble_curriculum_fundamentals(package, analysis_assembly)
    assembly = assemble_curriculum_practice(
        package,
        analysis_assembly,
        fundamental_assembly,
        reference_tempo_bpm=Fraction(120),
        reference_authority=TempoReferenceAuthority.CALLER,
        tempo_evidence=_synthetic_tempo_evidence(analysis_assembly),
    )
    with pytest.raises(CurriculumAnalysisAssemblyError, match="TMM-ASSEMBLY-IDENTITY"):
        require_valid_curriculum_practice_manifest(
            replace(
                assembly.manifest,
                fundamental_assembly_ref=replace(
                    assembly.manifest.fundamental_assembly_ref,
                    id="curriculum-fundamental-assembly:detached",
                ),
            ),
            package,
            analysis_assembly,
            fundamental_assembly,
            assembly.acquisition,
            assembly.presentations,
        )
    with pytest.raises(CurriculumAnalysisAssemblyError, match="TMM-ASSEMBLY-PRACTICE"):
        require_valid_curriculum_practice_manifest(
            replace(
                assembly.manifest,
                acquisition_graph_ref=replace(
                    assembly.manifest.acquisition_graph_ref,
                    id="acquisition-graph-slice:detached",
                ),
            ),
            package,
            analysis_assembly,
            fundamental_assembly,
            assembly.acquisition,
            assembly.presentations,
        )
    with pytest.raises(CurriculumAnalysisAssemblyError, match="TMM-ASSEMBLY-PRACTICE"):
        require_valid_curriculum_practice_manifest(
            assembly.manifest,
            package,
            analysis_assembly,
            fundamental_assembly,
            assembly.acquisition,
            assembly.presentations[:-1],
        )
    with pytest.raises(CurriculumValidationError):
        require_valid_curriculum_practice_manifest(
            assembly.manifest,
            package,
            analysis_assembly,
            fundamental_assembly,
            assembly.acquisition,
            (
                replace(
                    assembly.presentations[0],
                    active_target_ids=assembly.presentations[0].active_target_ids[1:],
                ),
                *assembly.presentations[1:],
            ),
        )


def test_happy_birthday_rehearses_remediation_support_fading_and_progression() -> None:
    """TEST-CURR-ASSEMBLY-004: bounded recovery reaches independent progression."""

    _, package, analysis_assembly = _uploaded_assembly()
    fundamental, practice, node, expected, rehearsal, _, _ = _remediation_rehearsal(
        package,
        analysis_assembly,
    )
    decisions = rehearsal.decisions
    actions = tuple(item.action for item in decisions)

    assert actions == (
        CurriculumPolicyAction.RETRY,
        CurriculumPolicyAction.REMEDIATE,
        CurriculumPolicyAction.RETRY,
        CurriculumPolicyAction.FADE_SUPPORT,
        CurriculumPolicyAction.PROGRESS,
    )
    assert tuple(item.mastery_status for item in decisions) == (
        CurriculumMasteryStatus.NOT_MASTERED,
        CurriculumMasteryStatus.NOT_MASTERED,
        CurriculumMasteryStatus.MASTERED,
        CurriculumMasteryStatus.MASTERED,
        CurriculumMasteryStatus.MASTERED,
    )
    assert decisions[0].support_condition_after == "guided-piece"
    assert decisions[1].support_condition_after is None
    assert decisions[1].remediation_count == 1
    branch = next(
        item for item in practice.acquisition.branches if item.application_node_id == node.id
    )
    assert decisions[1].target_node_id == branch.prerequisite_node_id
    assert decisions[2].reason_code == "TMM-POLICY-STABILITY-CONFIRMATION-REQUIRED"
    assert decisions[3].support_condition_after == "independent-piece"
    assert decisions[4].support_condition_before == "independent-piece"
    assert decisions[4].target_node_id == practice.acquisition.stages[1].node_id
    assert rehearsal.manifest.action_sequence == actions
    assert rehearsal.manifest.verification_authority == "synthetic-simulation"
    assert rehearsal.manifest.human_evidence_eligible is False
    assert rehearsal.manifest.progression_target_node_id == practice.acquisition.stages[1].node_id
    assert len(expected.notes) == 25
    assert rehearsal.manifest.id == (
        "curriculum-remediation-assembly:"
        "19d0942d5bc3daca7f7102f5e59c73a1125a9aa94bcddb521fdbc76eaddf25ee"
    )
    assert (
        assemble_curriculum_remediation_rehearsal(
            package,
            analysis_assembly,
            fundamental,
            practice,
            decisions,
        )
        == rehearsal
    )


def test_happy_birthday_remediation_rehearsal_rejects_detached_or_reordered_history() -> None:
    """TEST-CURR-ROBUSTNESS-054: policy-chain and authority drift fail closed."""

    _, package, analysis_assembly = _uploaded_assembly()
    fundamental, practice, _, _, rehearsal, _, _ = _remediation_rehearsal(
        package,
        analysis_assembly,
    )
    with pytest.raises(CurriculumAnalysisAssemblyError, match="TMM-ASSEMBLY-REMEDIATION"):
        require_valid_curriculum_remediation_manifest(
            rehearsal.manifest,
            package,
            analysis_assembly,
            fundamental,
            practice,
            tuple(reversed(rehearsal.decisions)),
        )
    with pytest.raises(CurriculumAnalysisAssemblyError, match="TMM-ASSEMBLY-REMEDIATION"):
        require_valid_curriculum_remediation_manifest(
            replace(rehearsal.manifest, human_evidence_eligible=True),
            package,
            analysis_assembly,
            fundamental,
            practice,
            rehearsal.decisions,
        )


def test_happy_birthday_rehearsal_exports_graphs_reconciles_and_replays() -> None:
    """TEST-CURR-ASSEMBLY-005: exact synthetic rehearsal closes Task 9N."""

    _, package, analysis_assembly = _uploaded_assembly()
    fundamental, practice, _, _, rehearsal, masteries, unlocks = _remediation_rehearsal(
        package,
        analysis_assembly,
    )
    exported = build_curriculum_rehearsal_export(
        rehearsal,
        practice.acquisition,
        _upper_support_states(),
        masteries,
        unlocks,
    )
    payload = curriculum_rehearsal_export_to_json(exported)
    decoded = curriculum_rehearsal_export_from_json(payload)
    graph = build_curriculum_rehearsal_graph(decoded)
    replay = replay_curriculum_rehearsal(decoded, rehearsal, practice.acquisition)
    reconciliation = reconcile_curriculum_rehearsal(
        decoded,
        graph,
        rehearsal,
        practice.acquisition,
    )

    assert decoded == exported
    assert tuple(item.action for item in graph.points) == rehearsal.manifest.action_sequence
    assert tuple(item.retry_count for item in graph.points) == (1, 1, 2, 2, 0)
    assert tuple(item.remediation_count for item in graph.points) == (0, 1, 1, 1, 1)
    assert replay.exact_match_count == len(rehearsal.decisions) == 5
    assert replay.action_sequence == rehearsal.manifest.action_sequence
    assert reconciliation.decision_count == 5
    assert reconciliation.verification_authority == "synthetic-simulation"
    assert reconciliation.human_evidence_eligible is False
    assert exported.id == (
        "curriculum-rehearsal-export:"
        "38ab1b0730d88bea5a8505ba4a4e10bafc8afd9bf94f0914e5f7d220a0bffa95"
    )
    assert graph.id == (
        "curriculum-rehearsal-graph:"
        "f877230e042ae58aa7c7a09121f9f4e0c1670ca84d61082894977ef8a617ef07"
    )
    assert replay.id == (
        "curriculum-rehearsal-replay:"
        "e19bcec295a088f33d8b8144299065286ce945caae2d6fecaa1ef858c29f7b89"
    )
    assert reconciliation.id == (
        "curriculum-rehearsal-reconciliation:"
        "3002b80ea1143abe1fa7f6e8a55dc2314d170923f5ee87d6a02038c03acb1e6a"
    )
    assert '"human_evidence_eligible": false' in payload
    assert "normalized_events" not in payload
    assert "raw_midi" not in payload
    assert "learner_context" not in payload
    assert fundamental.manifest.id == practice.manifest.fundamental_assembly_ref.id


def test_happy_birthday_rehearsal_export_rejects_projection_and_authority_drift() -> None:
    """TEST-CURR-ROBUSTNESS-055: export, graph, and replay drift fail closed."""

    _, package, analysis_assembly = _uploaded_assembly()
    _, practice, _, _, rehearsal, masteries, unlocks = _remediation_rehearsal(
        package,
        analysis_assembly,
    )
    exported = build_curriculum_rehearsal_export(
        rehearsal,
        practice.acquisition,
        _upper_support_states(),
        masteries,
        unlocks,
    )
    graph = build_curriculum_rehearsal_graph(exported)

    with pytest.raises(CurriculumRehearsalError, match="TMM-REHEARSAL-RECONCILIATION"):
        reconcile_curriculum_rehearsal(
            exported,
            replace(graph, points=tuple(reversed(graph.points))),
            rehearsal,
            practice.acquisition,
        )
    with pytest.raises(CurriculumRehearsalError, match="TMM-REHEARSAL-EXPORT"):
        curriculum_rehearsal_export_from_json(
            curriculum_rehearsal_export_to_json(exported).replace(
                '"verification_authority": "synthetic-simulation"',
                '"verification_authority": "human-observation"',
            )
        )
    changed_first = replace(
        exported.decision_inputs[0],
        mastery_projection=replace(
            exported.decision_inputs[0].mastery_projection,
            id="curriculum-mastery-projection:detached",
        ),
    )
    with pytest.raises(CurriculumRehearsalError):
        replay_curriculum_rehearsal(
            replace(
                exported,
                decision_inputs=(changed_first, *exported.decision_inputs[1:]),
            ),
            rehearsal,
            practice.acquisition,
        )
