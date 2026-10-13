"""Executable DEV-009 Task 9K.1 metric-source-record evidence."""

from __future__ import annotations

from dataclasses import replace

import pytest

from teachmemusic.score import CanonicalMusicPackage
from teachmemusic.teaching import (
    DEIDENTIFIED_METRIC_SUMMARY_ALLOWLIST,
    CurriculumMetricGraph,
    CurriculumMetricReconciliationReceipt,
    CurriculumPolicyAction,
    CurriculumSerializationError,
    CurriculumValidationError,
    MetricGraphAvailability,
    MetricGraphError,
    MetricGraphFamily,
    MetricGraphReconciliationError,
    MetricTrackerError,
    SemanticReference,
    TrackerPublishMode,
    TrackerPublishReceipt,
    TrackerPublishStatus,
    WandbMetricPublisher,
    WandbTrackerConfiguration,
    build_curriculum_experiment_manifest,
    build_curriculum_metric_graphs,
    build_curriculum_metric_source_record,
    build_curriculum_metric_summary_export,
    build_curriculum_tracker_batch,
    curriculum_metric_source_record_from_json,
    curriculum_metric_source_record_to_json,
    curriculum_metric_summary_export_from_json,
    curriculum_metric_summary_export_to_dict,
    curriculum_metric_summary_export_to_json,
    publish_curriculum_metric_summary,
    reconcile_curriculum_metric_graphs,
    validate_curriculum_metric_source_record,
    validate_curriculum_metric_summary_export,
)
from teachmemusic.teaching.curriculum_fingerprint import derived_id, semantic_fingerprint
from tests.teaching.test_curriculum_trajectory import _happy_birthday_transition


def _metric_source(package: CanonicalMusicPackage):
    inventory, selection, prior, outcome, reward, next_state, transition, *_ = (
        _happy_birthday_transition(package)
    )
    snapshots = (prior, next_state)
    inventories = (inventory,)
    selections = (selection,)
    outcomes = (outcome,)
    rewards = (reward,)
    transitions = (transition,)
    manifest = build_curriculum_experiment_manifest(
        snapshots,
        inventories,
        selections,
        outcomes,
        rewards,
        transitions,
    )
    record = build_curriculum_metric_source_record(
        manifest,
        snapshots,
        inventories,
        selections,
        outcomes,
        rewards,
        transitions,
    )
    return record, manifest, outcome, reward


def _metric_chain(package: CanonicalMusicPackage):
    inventory, selection, prior, outcome, reward, next_state, transition, *_ = (
        _happy_birthday_transition(package)
    )
    snapshots = (prior, next_state)
    inventories = (inventory,)
    selections = (selection,)
    outcomes = (outcome,)
    rewards = (reward,)
    transitions = (transition,)
    manifest = build_curriculum_experiment_manifest(
        snapshots,
        inventories,
        selections,
        outcomes,
        rewards,
        transitions,
    )
    source = build_curriculum_metric_source_record(
        manifest,
        snapshots,
        inventories,
        selections,
        outcomes,
        rewards,
        transitions,
    )
    summary = build_curriculum_metric_summary_export(
        source,
        manifest,
        snapshots,
        inventories,
        selections,
        outcomes,
        rewards,
        transitions,
    )
    return (
        summary,
        source,
        manifest,
        snapshots,
        inventories,
        selections,
        outcomes,
        rewards,
        transitions,
    )


def _metric_summary(package: CanonicalMusicPackage):
    summary, source, _, snapshots, _, selections, outcomes, rewards, _ = _metric_chain(package)
    return summary, source, snapshots, selections, outcomes, rewards


def test_happy_birthday_metric_source_is_compact_private_and_strict(
    happy_birthday_package: CanonicalMusicPackage,
) -> None:
    """TEST-CURR-METRICS-001: exact app-owned inputs round-trip without payloads."""

    record, manifest, outcome, reward = _metric_source(happy_birthday_package)
    repeated, _, _, _ = _metric_source(happy_birthday_package)
    payload = curriculum_metric_source_record_to_json(record)
    metric_input = record.metric_inputs[0]

    assert repeated == record
    assert record.manifest_ref.id == manifest.id
    assert metric_input.outcome_ref.id == outcome.id
    assert metric_input.research_reward_ref.id == reward.id
    assert curriculum_metric_source_record_from_json(payload) == record
    assert '"type": "curriculum-metric-source-record"' in payload
    assert "learner_context_id" not in payload
    assert "normalized_events" not in payload
    assert "raw_midi" not in payload
    assert "score_bytes" not in payload
    with pytest.raises(CurriculumSerializationError, match="unexpected"):
        curriculum_metric_source_record_from_json(
            payload.replace('"run_id"', '"unexpected": true, "run_id"')
        )


def test_metric_source_rejects_detached_or_reordered_manifest_inputs(
    happy_birthday_package: CanonicalMusicPackage,
) -> None:
    """TEST-CURR-VALIDATION-039: source references remain manifest-governed."""

    record, manifest, _, _ = _metric_source(happy_birthday_package)
    original = record.metric_inputs[0]
    changed_input = replace(
        original,
        outcome_ref=SemanticReference(
            original.outcome_ref.artifact_type,
            "curriculum-learning-outcome:foreign",
            original.outcome_ref.semantic_fingerprint,
        ),
    )
    changed = replace(record, metric_inputs=(changed_input,))
    codes = {issue.code for issue in validate_curriculum_metric_source_record(changed, manifest)}

    assert "TMM-METRICS-INPUT-FINGERPRINT-MISMATCH" in codes
    assert "TMM-METRICS-SOURCE-REFERENCE-MISMATCH" in codes
    assert "TMM-CONTRACT-FINGERPRINT-MISMATCH" in codes


def test_metric_source_builder_rejects_foreign_reward_chain(
    happy_birthday_package: CanonicalMusicPackage,
) -> None:
    """TEST-CURR-ROBUSTNESS-045: detached metric evidence cannot be indexed."""

    inventory, selection, prior, outcome, reward, next_state, transition, *_ = (
        _happy_birthday_transition(happy_birthday_package)
    )
    manifest = build_curriculum_experiment_manifest(
        (prior, next_state),
        (inventory,),
        (selection,),
        (outcome,),
        (reward,),
        (transition,),
    )
    foreign_reward = replace(reward, outcome_ref=replace(reward.outcome_ref, id="outcome:foreign"))

    with pytest.raises(CurriculumValidationError):
        build_curriculum_metric_source_record(
            manifest,
            (prior, next_state),
            (inventory,),
            (selection,),
            (outcome,),
            (foreign_reward,),
            (transition,),
        )


def test_metric_summary_is_allowlisted_deidentified_and_exact(
    happy_birthday_package: CanonicalMusicPackage,
) -> None:
    """TEST-CURR-METRICS-002: exact research metrics export without identity."""

    summary, source, _, selections, outcomes, rewards = _metric_summary(happy_birthday_package)
    repeated, *_ = _metric_summary(happy_birthday_package)
    payload = curriculum_metric_summary_export_to_json(summary)
    data = curriculum_metric_summary_export_to_dict(summary)
    decision = summary.decision_metrics[0]

    assert repeated == summary
    assert summary.source_record_ref.id == source.id
    assert decision.selected_action is selections[0].selected_candidate.action
    assert decision.behavior_probability == selections[0].behavior_probability
    assert decision.completion is outcomes[0].completion
    assert tuple(item.value for item in decision.reward_components) == tuple(
        item.value for item in rewards[0].components
    )
    assert curriculum_metric_summary_export_from_json(payload) == summary
    assert set(DEIDENTIFIED_METRIC_SUMMARY_ALLOWLIST) >= {
        "selected_action",
        "behavior_probability",
        "completion",
        "value",
    }
    assert set(data) == {
        "type",
        "schema_version",
        "id",
        "semantic_fingerprint",
        "summary_version",
        "source_record_ref",
        "score_id",
        "graph_ref",
        "policy_identity",
        "policy_configuration_ref",
        "decision_metrics",
        "first_decision_sequence",
        "last_decision_sequence",
        "resolution",
    }
    wire_keys: set[str] = set()

    def collect_wire_keys(value: object) -> None:
        if isinstance(value, dict):
            wire_keys.update(str(key) for key in value)
            for item in value.values():
                collect_wire_keys(item)
        elif isinstance(value, list):
            for item in value:
                collect_wire_keys(item)

    collect_wire_keys(data)
    assert wire_keys <= set(DEIDENTIFIED_METRIC_SUMMARY_ALLOWLIST)
    for forbidden in (
        "run_id",
        "learner_context_id",
        "attempt_ref",
        "calibration_ref",
        "raw_message_ids",
        "normalized_event_ids",
        "observation_refs",
        "score_package_digest",
        "aggregate_reward",
    ):
        assert forbidden not in payload


def test_metric_summary_rejects_projection_drift(
    happy_birthday_package: CanonicalMusicPackage,
) -> None:
    """TEST-CURR-VALIDATION-040: changed allowlisted values fail closed."""

    summary, source, snapshots, selections, outcomes, rewards = _metric_summary(
        happy_birthday_package
    )
    changed_decision = replace(
        summary.decision_metrics[0],
        selected_action=CurriculumPolicyAction.RETRY,
    )
    changed = replace(summary, decision_metrics=(changed_decision,))
    codes = {
        issue.code
        for issue in validate_curriculum_metric_summary_export(
            changed,
            source,
            snapshots,
            selections,
            outcomes,
            rewards,
        )
    }

    assert "TMM-METRICS-SUMMARY-PROJECTION-MISMATCH" in codes
    assert "TMM-CONTRACT-FINGERPRINT-MISMATCH" in codes


def test_metric_summary_strict_wire_rejects_identity_injection(
    happy_birthday_package: CanonicalMusicPackage,
) -> None:
    """TEST-CURR-ROBUSTNESS-046: non-allowlisted identity cannot enter export."""

    summary, *_ = _metric_summary(happy_birthday_package)
    payload = curriculum_metric_summary_export_to_json(summary)

    with pytest.raises(CurriculumSerializationError, match="unexpected"):
        curriculum_metric_summary_export_from_json(
            payload.replace(
                '"score_id"',
                '"learner_context_id": "learner:forbidden", "score_id"',
            )
        )


class _FakeWandbRun:
    def __init__(self) -> None:
        self.id: str | None = "wandb-run:test"
        self.url: str | None = None
        self.logged: list[tuple[dict[str, str | int | float | bool], int | None, bool | None]] = []
        self.finished = False

    def log(
        self,
        data: dict[str, str | int | float | bool],
        *,
        step: int | None = None,
        commit: bool | None = None,
    ) -> None:
        self.logged.append((data, step, commit))

    def finish(self) -> None:
        self.finished = True


class _FakeWandbClient:
    def __init__(self) -> None:
        self.run = _FakeWandbRun()
        self.init_calls: list[dict[str, object]] = []

    def init(self, **kwargs: object) -> _FakeWandbRun:
        self.init_calls.append(kwargs)
        return self.run


def test_tracker_batch_is_exact_deidentified_and_tracker_neutral(
    happy_birthday_package: CanonicalMusicPackage,
) -> None:
    """TEST-CURR-METRICS-003: approved summary becomes immutable scalar rows."""

    summary, *_ = _metric_summary(happy_birthday_package)
    original = curriculum_metric_summary_export_to_json(summary)
    batch = build_curriculum_tracker_batch(summary)

    assert batch.summary_ref.id == summary.id
    assert len(batch.points) == len(summary.decision_metrics[0].reward_components)
    assert tuple(point.step for point in batch.points) == tuple(range(len(batch.points)))
    assert dict(batch.metadata)["source/id"] == summary.source_record_ref.id
    first = batch.points[0].to_dict()
    component = summary.decision_metrics[0].reward_components[0]
    assert first["decision/sequence"] == summary.first_decision_sequence
    assert first["reward/component_id"] == component.component_id
    assert first["reward/value_numerator"] == component.value.numerator
    assert first["reward/value_denominator"] == component.value.denominator
    assert all(isinstance(value, str | int | float | bool) for value in first.values())
    assert curriculum_metric_summary_export_to_json(summary) == original
    wire = repr((batch.metadata, tuple(point.values for point in batch.points)))
    for forbidden in (
        "learner_context_id",
        "run_id",
        "raw_midi",
        "calibration_ref",
        "aggregate_reward",
    ):
        assert forbidden not in wire


def test_wandb_publisher_is_disabled_and_credential_free_by_default(
    happy_birthday_package: CanonicalMusicPackage,
) -> None:
    """TEST-CURR-TRACKER-001: default publishing performs no SDK or network work."""

    summary, *_ = _metric_summary(happy_birthday_package)
    client = _FakeWandbClient()
    receipt = publish_curriculum_metric_summary(
        summary,
        WandbMetricPublisher(client=client),
    )

    assert receipt.status is TrackerPublishStatus.DISABLED
    assert receipt.mode is TrackerPublishMode.DISABLED
    assert receipt.point_count == 0
    assert receipt.summary_ref.id == summary.id
    assert client.init_calls == []
    assert client.run.logged == []
    assert not client.run.finished


def test_wandb_offline_adapter_logs_only_approved_rows(
    happy_birthday_package: CanonicalMusicPackage,
) -> None:
    """TEST-CURR-TRACKER-002: explicit offline mode logs without credentials."""

    summary, *_ = _metric_summary(happy_birthday_package)
    client = _FakeWandbClient()
    receipt = publish_curriculum_metric_summary(
        summary,
        WandbMetricPublisher(
            WandbTrackerConfiguration(
                project="teachmemusic-tests",
                mode=TrackerPublishMode.OFFLINE,
                run_name="happy-birthday-deterministic-baseline",
            ),
            client=client,
        ),
    )

    assert receipt.status is TrackerPublishStatus.STORED_OFFLINE
    assert receipt.external_run_id == "wandb-run:test"
    assert receipt.external_run_url is None
    assert receipt.point_count == len(client.run.logged)
    assert client.run.finished
    assert len(client.init_calls) == 1
    init = client.init_calls[0]
    assert init["project"] == "teachmemusic-tests"
    assert init["mode"] == "offline"
    assert init["name"] == "happy-birthday-deterministic-baseline"
    assert "api_key" not in init
    assert "login" not in init
    assert tuple(step for _, step, _ in client.run.logged) == tuple(range(len(client.run.logged)))
    assert all(commit is True for _, _, commit in client.run.logged)
    assert all("learner_context_id" not in row for row, _, _ in client.run.logged)


def test_wandb_online_adapter_requires_and_honors_explicit_capability(
    happy_birthday_package: CanonicalMusicPackage,
) -> None:
    """TEST-CURR-TRACKER-003: authorized online mode reaches the injected sink."""

    summary, *_ = _metric_summary(happy_birthday_package)
    client = _FakeWandbClient()
    client.run.url = "https://wandb.example/teachmemusic/test"
    receipt = publish_curriculum_metric_summary(
        summary,
        WandbMetricPublisher(
            WandbTrackerConfiguration(
                project="teachmemusic-tests",
                entity="teachmemusic-research",
                mode=TrackerPublishMode.ONLINE,
                allow_external_transmission=True,
            ),
            client=client,
        ),
    )

    assert receipt.status is TrackerPublishStatus.PUBLISHED_ONLINE
    assert receipt.external_run_url == "https://wandb.example/teachmemusic/test"
    assert client.init_calls[0]["mode"] == "online"
    assert client.init_calls[0]["entity"] == "teachmemusic-research"
    assert receipt.point_count == len(client.run.logged)


def test_online_wandb_requires_explicit_transmission_authorization(
    happy_birthday_package: CanonicalMusicPackage,
) -> None:
    """TEST-CURR-ROBUSTNESS-047: online mode fails before client initialization."""

    summary, *_ = _metric_summary(happy_birthday_package)
    original = curriculum_metric_summary_export_to_json(summary)
    client = _FakeWandbClient()

    with pytest.raises(MetricTrackerError, match="explicit external-transmission"):
        publish_curriculum_metric_summary(
            summary,
            WandbMetricPublisher(
                WandbTrackerConfiguration(mode=TrackerPublishMode.ONLINE),
                client=client,
            ),
        )

    assert client.init_calls == []
    assert curriculum_metric_summary_export_to_json(summary) == original


def test_tracker_neutral_boundary_rejects_a_detached_receipt(
    happy_birthday_package: CanonicalMusicPackage,
) -> None:
    """TEST-CURR-VALIDATION-041: a tracker cannot substitute another summary."""

    summary, *_ = _metric_summary(happy_birthday_package)

    class _DetachedPublisher:
        def publish(self, batch):  # type: ignore[no-untyped-def]
            return TrackerPublishReceipt(
                tracker="detached",
                mode=TrackerPublishMode.OFFLINE,
                status=TrackerPublishStatus.STORED_OFFLINE,
                summary_ref=replace(batch.summary_ref, id="summary:foreign"),
                point_count=len(batch.points),
            )

    with pytest.raises(MetricTrackerError, match="does not reference"):
        publish_curriculum_metric_summary(summary, _DetachedPublisher())


def _summary_with_action(summary, action: CurriculumPolicyAction):  # type: ignore[no-untyped-def]
    decision = replace(summary.decision_metrics[0], selected_action=action)
    provisional = replace(
        summary,
        id="curriculum-metric-summary-export:pending",
        semantic_fingerprint="pending",
        decision_metrics=(decision,),
    )
    return replace(
        provisional,
        id=derived_id("curriculum-metric-summary-export", provisional),
        semantic_fingerprint=semantic_fingerprint(provisional),
    )


def test_metric_graphs_are_source_linked_and_preserve_unavailable_outcomes(
    happy_birthday_package: CanonicalMusicPackage,
) -> None:
    """TEST-CURR-METRICS-004: graphs expose facts without false zero outcomes."""

    summary, *_ = _metric_summary(happy_birthday_package)
    batch = build_curriculum_tracker_batch(summary)
    graphs = build_curriculum_metric_graphs(batch)
    by_family = {graph.family: graph for graph in graphs}

    assert tuple(by_family) == tuple(MetricGraphFamily)
    assert all(isinstance(graph, CurriculumMetricGraph) for graph in graphs)
    assert all(graph.summary_ref == batch.summary_ref for graph in graphs)
    assert by_family[MetricGraphFamily.PERFORMANCE].availability is (
        MetricGraphAvailability.AVAILABLE
    )
    assert by_family[MetricGraphFamily.SUPPORT].availability is (MetricGraphAvailability.AVAILABLE)
    assert by_family[MetricGraphFamily.RETENTION].availability is (
        MetricGraphAvailability.UNAVAILABLE
    )
    assert by_family[MetricGraphFamily.RETENTION].reason_code == ("RETENTION_OUTCOME_NOT_PRESENT")
    assert by_family[MetricGraphFamily.TRANSFER].availability is (
        MetricGraphAvailability.UNAVAILABLE
    )
    assert by_family[MetricGraphFamily.TRANSFER].reason_code == ("TRANSFER_OUTCOME_NOT_PRESENT")

    rows = {point.step: point.to_dict() for point in batch.points}
    performance = by_family[MetricGraphFamily.PERFORMANCE]
    assert performance.candidate_source_steps == tuple(rows)
    for step in performance.plotted_source_steps:
        row = rows[step]
        assert row[performance.y_key] == float(
            int(row["reward/value_numerator"]) / int(row["reward/value_denominator"])
        )
    support = by_family[MetricGraphFamily.SUPPORT]
    assert len(support.plotted_source_steps) == 1
    assert rows[support.plotted_source_steps[0]]["reward/component_id"] == ("attempt-completion")


@pytest.mark.parametrize(
    ("action", "family"),
    (
        (CurriculumPolicyAction.RUN_RETENTION, MetricGraphFamily.RETENTION),
        (CurriculumPolicyAction.RUN_TRANSFER, MetricGraphFamily.TRANSFER),
    ),
)
def test_metric_graphs_project_present_retention_and_transfer_actions(
    happy_birthday_package: CanonicalMusicPackage,
    action: CurriculumPolicyAction,
    family: MetricGraphFamily,
) -> None:
    """TEST-CURR-VALIDATION-042: present outcome actions become graphable."""

    summary, *_ = _metric_summary(happy_birthday_package)
    changed = _summary_with_action(summary, action)
    graph = {
        item.family: item
        for item in build_curriculum_metric_graphs(build_curriculum_tracker_batch(changed))
    }[family]

    assert graph.availability is MetricGraphAvailability.AVAILABLE
    assert graph.reason_code == "GRAPH_VALUES_AVAILABLE"
    assert set(graph.plotted_source_steps) < set(graph.candidate_source_steps)
    assert graph.plotted_source_steps


def test_metric_graphs_reject_drifted_visualization_values(
    happy_birthday_package: CanonicalMusicPackage,
) -> None:
    """TEST-CURR-ROBUSTNESS-048: a changed plot value fails reconciliation."""

    summary, *_ = _metric_summary(happy_birthday_package)
    batch = build_curriculum_tracker_batch(summary)
    point = batch.points[0]
    values = tuple(
        (key, 0.123456 if key == "reward/value_plot" else value) for key, value in point.values
    )
    changed = replace(batch, points=(replace(point, values=values), *batch.points[1:]))

    with pytest.raises(MetricGraphError, match="differs from its exact fraction"):
        build_curriculum_metric_graphs(changed)

    detached = replace(batch, summary_ref=replace(batch.summary_ref, id="summary:foreign"))
    with pytest.raises(MetricGraphError, match="governed summary reference"):
        build_curriculum_metric_graphs(detached)


def test_wandb_offline_rows_include_only_reconcilable_graph_values(
    happy_birthday_package: CanonicalMusicPackage,
) -> None:
    """TEST-CURR-TRACKER-004: offline rows retain exact graph provenance."""

    summary, *_ = _metric_summary(happy_birthday_package)
    client = _FakeWandbClient()
    publish_curriculum_metric_summary(
        summary,
        WandbMetricPublisher(
            WandbTrackerConfiguration(mode=TrackerPublishMode.OFFLINE),
            client=client,
        ),
    )

    rows = tuple(row for row, _, _ in client.run.logged)
    assert all(
        row["reward/value_plot"]
        == float(int(row["reward/value_numerator"]) / int(row["reward/value_denominator"]))
        for row in rows
        if row["reward/value_available"] is True
    )
    support_rows = tuple(row for row in rows if "support/change_plot" in row)
    assert len(support_rows) == 1
    assert support_rows[0]["reward/component_id"] == "attempt-completion"


def test_metric_graph_reconciliation_reaches_authoritative_trajectory(
    happy_birthday_package: CanonicalMusicPackage,
) -> None:
    """TEST-CURR-METRICS-005: every graph resolves through one exact trajectory."""

    (
        summary,
        source,
        manifest,
        snapshots,
        inventories,
        selections,
        outcomes,
        rewards,
        transitions,
    ) = _metric_chain(happy_birthday_package)
    batch = build_curriculum_tracker_batch(summary)
    graphs = build_curriculum_metric_graphs(batch)
    receipt = reconcile_curriculum_metric_graphs(
        graphs,
        batch,
        summary,
        source,
        manifest,
        snapshots,
        inventories,
        selections,
        outcomes,
        rewards,
        transitions,
    )

    assert isinstance(receipt, CurriculumMetricReconciliationReceipt)
    assert receipt.manifest_ref.id == manifest.id
    assert receipt.source_record_ref.id == source.id
    assert receipt.summary_ref.id == summary.id
    assert receipt.graph_families == tuple(MetricGraphFamily)
    assert receipt.tracker_point_count == len(batch.points)
    assert receipt.plotted_coordinate_count == sum(
        len(graph.plotted_source_steps) for graph in graphs
    )
    assert receipt.unavailable_graph_families == (
        MetricGraphFamily.RETENTION,
        MetricGraphFamily.TRANSFER,
    )


def test_metric_graph_reconciliation_rejects_availability_drift(
    happy_birthday_package: CanonicalMusicPackage,
) -> None:
    """TEST-CURR-VALIDATION-043: a fabricated available graph fails closed."""

    chain = _metric_chain(happy_birthday_package)
    (
        summary,
        source,
        manifest,
        snapshots,
        inventories,
        selections,
        outcomes,
        rewards,
        transitions,
    ) = chain
    batch = build_curriculum_tracker_batch(summary)
    graphs = build_curriculum_metric_graphs(batch)
    retention = replace(
        graphs[2],
        availability=MetricGraphAvailability.AVAILABLE,
        reason_code="GRAPH_VALUES_AVAILABLE",
    )

    with pytest.raises(MetricGraphReconciliationError, match="availability decisions"):
        reconcile_curriculum_metric_graphs(
            (graphs[0], graphs[1], retention, graphs[3]),
            batch,
            summary,
            source,
            manifest,
            snapshots,
            inventories,
            selections,
            outcomes,
            rewards,
            transitions,
        )


def test_metric_graph_reconciliation_rejects_batch_and_evidence_drift(
    happy_birthday_package: CanonicalMusicPackage,
) -> None:
    """TEST-CURR-ROBUSTNESS-049: downstream or authority mutation fails closed."""

    (
        summary,
        source,
        manifest,
        snapshots,
        inventories,
        selections,
        outcomes,
        rewards,
        transitions,
    ) = _metric_chain(happy_birthday_package)
    batch = build_curriculum_tracker_batch(summary)
    graphs = build_curriculum_metric_graphs(batch)
    point = batch.points[0]
    changed_values = tuple(
        (key, "DRIFTED_REASON" if key == "reward/reason_code" else value)
        for key, value in point.values
    )
    changed_batch = replace(
        batch,
        points=(replace(point, values=changed_values), *batch.points[1:]),
    )

    with pytest.raises(MetricGraphReconciliationError, match="tracker batch differs"):
        reconcile_curriculum_metric_graphs(
            graphs,
            changed_batch,
            summary,
            source,
            manifest,
            snapshots,
            inventories,
            selections,
            outcomes,
            rewards,
            transitions,
        )

    changed_component = replace(rewards[0].components[0], reason_code="DRIFTED_REASON")
    changed_reward = replace(
        rewards[0],
        components=(changed_component, *rewards[0].components[1:]),
    )
    with pytest.raises(MetricGraphReconciliationError, match="authoritative trajectory"):
        reconcile_curriculum_metric_graphs(
            graphs,
            batch,
            summary,
            source,
            manifest,
            snapshots,
            inventories,
            selections,
            outcomes,
            (changed_reward,),
            transitions,
        )
