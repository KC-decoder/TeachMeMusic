"""Generic-generation evidence for the complete DEV-009 Task 9B path."""

from __future__ import annotations

import ast
import re
from collections import Counter
from fractions import Fraction
from importlib import import_module
from io import BytesIO
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

from teachmemusic.analysis import analyze_canonical_score
from teachmemusic.score import CanonicalMusicPackage, parse_musicxml_package
from teachmemusic.teaching import (
    ArtifactResolution,
    CompatibleTempoEvidence,
    NotationCondition,
    PracticeMode,
    SemanticReference,
    TempoReferenceAuthority,
    TransferTargetRequest,
    build_curriculum_combined_expected_performance,
    build_curriculum_layer_expected_performance,
    build_curriculum_passage_presentation,
    derive_passage_requirements,
    generate_acquisition_graph,
    generate_lasting_skill_graph,
    generate_prerequisite_branches,
)

_FIXTURES = Path(__file__).parents[1] / "fixtures" / "scores"
_HOT_CROSS_BUNS = (
    _FIXTURES
    / "TMM-REF-CANDIDATE-001-Hot-Cross-Buns"
    / "musicxml-17-hot-cross-buns-final-shelbygtdrew.mxl"
)
_HAPPY_BIRTHDAY = (
    _FIXTURES / "TMM-REF-CANDIDATE-002-Happy-Birthday" / "happy-birthday-to-you-c-major.mxl"
)
_MOONLIGHT = (
    _FIXTURES
    / "TMM-REF-CANDIDATE-004-Moonlight-Sonata"
    / "beethoven-piano-sonata-no-14-moonlight.mxl"
)
_GENERATOR_MODULES = (
    "teachmemusic.teaching.requirements",
    "teachmemusic.teaching.branches",
    "teachmemusic.teaching.acquisition",
    "teachmemusic.teaching.lasting_skills",
)
_FORBIDDEN_SOURCE_FRAGMENTS = (
    "hot cross buns",
    "happy birthday",
    "moonlight sonata",
    "clair de lune",
    "arabesque",
    "tmm-ref-candidate",
    "tests/fixtures",
    "tests.fixtures",
    ".musicxml",
    ".mxl",
    ".pdf",
)
_FORBIDDEN_ATTRIBUTES = {
    "fixture_path",
    "logical_name",
    "movement_title",
    "source_path",
    "title",
    "work_title",
}


def _requirements(package: CanonicalMusicPackage, *, end_measure: int = 2):
    return derive_passage_requirements(
        package,
        analyze_canonical_score(package, end_measure_ordinal=end_measure),
    )


def _tempo_evidence(requirements):
    percentages = {
        "single-layer": 70,
        "upper-layer": 85,
        "lower-layer": 70,
        "combined": 70,
    }
    return tuple(
        CompatibleTempoEvidence(
            SemanticReference(
                "practice-scope-assignment",
                scope.id,
                scope.semantic_fingerprint,
            ),
            "independent-piece",
            percentages[scope.notation_condition.value],
            percentages[scope.notation_condition.value],
            True,
            True,
            (f"evidence:{scope.notation_condition.value}",),
        )
        for scope in requirements.scopes
    )


def _acquisition(requirements):
    return generate_acquisition_graph(
        requirements,
        generate_prerequisite_branches(requirements),
        reference_tempo_bpm=Fraction(100),
        reference_authority=TempoReferenceAuthority.CALLER,
        tempo_evidence=_tempo_evidence(requirements),
    )


def _transfer_requests(source, target) -> tuple[TransferTargetRequest, ...]:
    target_scope_by_id = {item.id: item for item in target.scopes}
    requests = []
    for primitive_id in ("PRIM-LAY-001", "PRIM-RHY-002"):
        source_requirement = next(
            item for item in source.requirements if item.primitive_ref.id == primitive_id
        )
        target_requirement = next(
            item
            for item in target.requirements
            if item.primitive_ref.id == primitive_id
            and target_scope_by_id[item.practice_scope_ref.id].notation_condition.value
            == "upper-layer"
        )
        requests.append(
            TransferTargetRequest(
                source_requirement.id,
                target_requirement.id,
                ("material", "score"),
                tuple(sorted(target_requirement.canonical_evidence_refs)),
            )
        )
    return tuple(requests)


def _curriculum_signature(source_package, transfer_package):
    requirements = _requirements(source_package)
    transfer_requirements = _requirements(transfer_package)
    branches = generate_prerequisite_branches(requirements)
    acquisition = _acquisition(requirements)
    lasting = generate_lasting_skill_graph(
        requirements,
        acquisition,
        transfer_requirements,
        transfer_requests=_transfer_requests(requirements, transfer_requirements),
    )
    source_scope_by_id = {item.id: item for item in requirements.scopes}
    target_scope_by_id = {item.id: item for item in transfer_requirements.scopes}
    all_scope_by_id = source_scope_by_id | target_scope_by_id

    return (
        tuple(
            sorted(
                (
                    scope.notation_condition.value,
                    len(scope.layer_groups),
                    len(scope.active_target_ids),
                    len(scope.inactive_context_ids),
                    len(scope.component_scope_ids),
                    scope.resolution.value,
                )
                for scope in requirements.scopes
            )
        ),
        tuple(
            sorted(
                (
                    source_scope_by_id[item.practice_scope_ref.id].notation_condition.value,
                    item.primitive_ref.id,
                    item.role.value,
                    item.necessity.value,
                    tuple(
                        (parameter.name, parameter.value_type)
                        for parameter in item.target_parameters
                    ),
                    item.required_dimensions,
                    item.unobservable_dimensions,
                    len(item.canonical_evidence_refs),
                    len(item.analysis_evidence_refs),
                    len(item.prerequisite_requirement_ids),
                    item.resolution.value,
                )
                for item in requirements.requirements
            )
        ),
        tuple(sorted(Counter(item.kind.value for item in branches.nodes).items())),
        tuple(sorted(Counter(item.kind.value for item in branches.edges).items())),
        tuple(
            (
                item.kind.value,
                source_scope_by_id[item.practice_scope_ref.id].notation_condition.value,
                item.evidence_context,
                len(item.component_node_ids),
            )
            for item in acquisition.stages
        ),
        tuple(
            sorted(
                (
                    source_scope_by_id[item.practice_scope_ref.id].notation_condition.value,
                    item.state.value,
                    item.current_controlled_percentage,
                    item.supported_ceiling_percentage,
                    item.diagnostic_probe_percentages,
                )
                for item in acquisition.tempo_plans
            )
        ),
        tuple(
            tuple(
                (
                    window.checkpoint.value,
                    window.due_after_hours,
                    window.valid_after_hours,
                    window.valid_before_hours,
                )
                for window in schedule.windows
            )
            for schedule in lasting.retention_schedules
        ),
        tuple(
            (
                item.kind.value,
                all_scope_by_id[item.practice_scope_ref.id].notation_condition.value,
                item.evidence_context,
            )
            for item in lasting.stages
        ),
        tuple(
            sorted(
                (
                    item.difference_dimensions,
                    item.training_state_guard,
                )
                for item in lasting.transfer_targets
            )
        ),
        (
            branches.resolution.value,
            acquisition.resolution.value,
            lasting.resolution.value,
        ),
    )


def _rewrite_embedded_title(source: bytes, replacement: str) -> bytes:
    input_buffer = BytesIO(source)
    output_buffer = BytesIO()
    replacements = 0
    with (
        ZipFile(input_buffer) as archive,
        ZipFile(
            output_buffer,
            "w",
            compression=ZIP_DEFLATED,
        ) as changed,
    ):
        for member in archive.infolist():
            payload = archive.read(member.filename)
            if member.filename.lower().endswith((".xml", ".musicxml")):
                payload, count = re.subn(
                    rb"(<work-title(?:\s[^>]*)?>).*?(</work-title>)",
                    rb"\1" + replacement.encode("utf-8") + rb"\2",
                    payload,
                    flags=re.DOTALL,
                )
                replacements += count
            changed.writestr(member, payload)
    assert replacements > 0
    return output_buffer.getvalue()


def _cross_score_route_signature(
    package: CanonicalMusicPackage,
    *,
    end_measure: int,
) -> tuple[object, ...]:
    requirements = _requirements(package, end_measure=end_measure)
    branches = generate_prerequisite_branches(requirements)
    graph = (
        _acquisition(requirements)
        if branches.resolution is ArtifactResolution.RESOLVED
        else generate_acquisition_graph(
            requirements,
            branches,
            reference_tempo_bpm=Fraction(100),
            reference_authority=TempoReferenceAuthority.CALLER,
        )
    )
    presentations = {
        scope.id: build_curriculum_passage_presentation(package, requirements, scope.id)
        for scope in requirements.scopes
        if scope.resolution is ArtifactResolution.RESOLVED
    }
    sounding_counts: dict[str, int] = {}
    for scope in requirements.scopes:
        presentation = presentations.get(scope.id)
        if presentation is None:
            continue
        if scope.notation_condition is NotationCondition.COMBINED:
            expected = build_curriculum_combined_expected_performance(
                package,
                requirements,
                presentation,
                tuple(presentations[item] for item in scope.component_scope_ids),
                PracticeMode.INDEPENDENT_PERFORMANCE,
                tempo_bpm=Fraction(70),
            )
        else:
            expected = build_curriculum_layer_expected_performance(
                package,
                presentation,
                PracticeMode.INDEPENDENT_PERFORMANCE,
                tempo_bpm=Fraction(70),
            )
        sounding_counts[scope.id] = len(expected.notes)

    return (
        graph.resolution.value,
        tuple(
            (
                scope.notation_condition.value,
                scope.resolution.value,
                len(scope.active_target_ids),
                len(scope.inactive_context_ids),
                len(scope.component_scope_ids),
                sounding_counts.get(scope.id),
            )
            for scope in requirements.scopes
        ),
        tuple(stage.kind.value for stage in graph.stages),
        tuple(item.code for item in requirements.diagnostics),
    )


def test_generation_sources_reject_piece_specific_and_manual_plan_dependencies() -> None:
    """TEST-CURR-ROBUSTNESS-007: every 9B generator stays title-blind."""

    failures: list[str] = []
    for module_name in _GENERATOR_MODULES:
        module = import_module(module_name)
        source = Path(module.__file__).read_text(encoding="utf-8")
        tree = ast.parse(source)
        lowered = source.lower()
        for fragment in _FORBIDDEN_SOURCE_FRAGMENTS:
            if fragment in lowered:
                failures.append(f"{module_name}: forbidden source fragment {fragment!r}")
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute) and node.attr in _FORBIDDEN_ATTRIBUTES:
                failures.append(f"{module_name}:{node.lineno}: reads {node.attr!r}")
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                imported = tuple(alias.name for alias in node.names)
                parent = node.module if isinstance(node, ast.ImportFrom) else ""
                if "planner" in (parent or "") or any("planner" in item for item in imported):
                    failures.append(f"{module_name}:{node.lineno}: imports the manual planner")
            if (
                isinstance(node, ast.Constant)
                and isinstance(node.value, str)
                and re.fullmatch(r"[0-9a-f]{20,}", node.value.lower())
            ):
                failures.append(f"{module_name}:{node.lineno}: embeds a score-like digest")

    assert failures == []


def test_title_and_upload_name_changes_preserve_complete_curriculum_topology() -> None:
    """TEST-CURR-ROBUSTNESS-008: metadata cannot select a teaching branch."""

    original_source = parse_musicxml_package(
        _HOT_CROSS_BUNS.read_bytes(),
        logical_name=_HOT_CROSS_BUNS.name,
    )
    original_target = parse_musicxml_package(
        _HAPPY_BIRTHDAY.read_bytes(),
        logical_name=_HAPPY_BIRTHDAY.name,
    )
    renamed_source = parse_musicxml_package(
        _rewrite_embedded_title(_HOT_CROSS_BUNS.read_bytes(), "Anonymous Study"),
        logical_name="unseen-upload-alpha.mxl",
    )
    renamed_target = parse_musicxml_package(
        _HAPPY_BIRTHDAY.read_bytes(),
        logical_name="unseen-upload-beta.mxl",
    )

    assert _curriculum_signature(original_source, original_target) == _curriculum_signature(
        renamed_source,
        renamed_target,
    )


def test_same_generators_resolve_simple_scores_and_fail_closed_on_ambiguity(
    hot_cross_buns_package: CanonicalMusicPackage,
    happy_birthday_package: CanonicalMusicPackage,
    moonlight_package: CanonicalMusicPackage,
) -> None:
    """TEST-CURR-VALIDATION-013: one path serves every governed score."""

    resolved = []
    for package in (hot_cross_buns_package, happy_birthday_package):
        requirements = _requirements(package)
        branches = generate_prerequisite_branches(requirements)
        acquisition = _acquisition(requirements)
        resolved.append(
            (
                all(
                    scope.resolution is ArtifactResolution.RESOLVED for scope in requirements.scopes
                ),
                branches.resolution,
                acquisition.resolution,
            )
        )

    moonlight_requirements = _requirements(moonlight_package, end_measure=69)
    moonlight_branches = generate_prerequisite_branches(moonlight_requirements)
    moonlight_acquisition = generate_acquisition_graph(
        moonlight_requirements,
        moonlight_branches,
        reference_tempo_bpm=Fraction(60),
        reference_authority=TempoReferenceAuthority.CALLER,
    )

    assert resolved == [
        (True, ArtifactResolution.RESOLVED, ArtifactResolution.RESOLVED),
        (True, ArtifactResolution.RESOLVED, ArtifactResolution.RESOLVED),
    ]
    assert [item.code for item in moonlight_requirements.diagnostics] == [
        "TMM-HAND-INTERPRETATION-REQUIRED"
    ]
    assert moonlight_branches.resolution is ArtifactResolution.REVIEW_REQUIRED
    assert moonlight_acquisition.resolution is ArtifactResolution.REVIEW_REQUIRED
    assert moonlight_branches.nodes == ()
    assert moonlight_acquisition.stages == ()


def test_cross_score_route_matrix_is_exact_and_metadata_blind() -> None:
    """TEST-CURR-ROBUSTNESS-023: one matrix preserves all three route outcomes."""

    sources = (
        (_HOT_CROSS_BUNS, 8, "anonymous-study.mxl", "Anonymous Study"),
        (_HAPPY_BIRTHDAY, 8, "untitled-celebration.mxl", None),
        (_MOONLIGHT, 69, "anonymous-sonata.mxl", "Anonymous Sonata"),
    )
    original_matrix = tuple(
        _cross_score_route_signature(
            parse_musicxml_package(path.read_bytes(), logical_name=path.name),
            end_measure=end_measure,
        )
        for path, end_measure, _logical_name, _title in sources
    )
    renamed_matrix = tuple(
        _cross_score_route_signature(
            parse_musicxml_package(
                (
                    _rewrite_embedded_title(path.read_bytes(), title)
                    if title is not None
                    else path.read_bytes()
                ),
                logical_name=logical_name,
            ),
            end_measure=end_measure,
        )
        for path, end_measure, logical_name, title in sources
    )

    expected_matrix = (
        (
            "resolved",
            (("single-layer", "resolved", 20, 0, 0, 17),),
            (
                "component-acquisition",
                "pulse-integration",
                "phrase-controlled-tempo",
                "learned-to-date",
                "tempo-development",
            ),
            (),
        ),
        (
            "resolved",
            (
                ("upper-layer", "resolved", 25, 34, 0, 25),
                ("lower-layer", "resolved", 34, 25, 0, 27),
                ("combined", "resolved", 59, 0, 2, 52),
            ),
            (
                "component-acquisition",
                "component-acquisition",
                "self-paced-coordination",
                "pulse-integration",
                "phrase-controlled-tempo",
                "learned-to-date",
                "tempo-development",
            ),
            (),
        ),
        (
            "review-required",
            (("combined", "review-required", 1212, 0, 0, None),),
            (),
            ("TMM-HAND-INTERPRETATION-REQUIRED",),
        ),
    )

    assert original_matrix == expected_matrix
    assert renamed_matrix == expected_matrix
