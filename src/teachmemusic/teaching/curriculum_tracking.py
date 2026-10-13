"""Tracker projection, graph contracts, and optional W&B publishing."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from fractions import Fraction
from importlib import import_module
from typing import Protocol, cast

from teachmemusic.performance import AttemptCompletion, ObservationDimension

from .curriculum_contracts import (
    CurriculumActionInventory,
    CurriculumActionSelection,
    CurriculumDecisionSnapshot,
    CurriculumExperimentManifest,
    CurriculumLearningOutcome,
    CurriculumMetricSourceRecord,
    CurriculumMetricSummaryExport,
    CurriculumPolicyAction,
    CurriculumResearchReward,
    CurriculumTransitionResult,
    ResearchRewardComponentStatus,
    SemanticReference,
)
from .curriculum_validation import (
    CurriculumValidationError,
    require_valid_curriculum_experiment_manifest,
    require_valid_curriculum_metric_source_record,
    require_valid_curriculum_metric_summary_export,
)

TrackerScalar = str | int | float | bool

_TRACKER_METADATA_KEYS = (
    "summary/id",
    "summary/fingerprint",
    "summary/version",
    "source/id",
    "source/fingerprint",
    "score/id",
    "graph/id",
    "graph/fingerprint",
    "policy/identity",
    "policy/configuration_id",
    "policy/configuration_fingerprint",
    "decision/first_sequence",
    "decision/last_sequence",
)
_TRACKER_POINT_KEYS = (
    "decision/sequence",
    "decision/input_fingerprint",
    "node/current_id",
    "node/next_id",
    "support/prior_id",
    "support/next_id",
    "policy/action",
    "policy/behavior_probability_numerator",
    "policy/behavior_probability_denominator",
    "outcome/completion",
    "reward/component_id",
    "reward/dimension",
    "reward/status",
    "reward/value_available",
    "reward/value_numerator",
    "reward/value_denominator",
    "reward/matched_observations",
    "reward/discrepancy_observations",
    "reward/unresolved_observations",
    "reward/reason_code",
)


class TrackerPublishMode(StrEnum):
    """Whether a tracker adapter is inert, local-only, or externally connected."""

    DISABLED = "disabled"
    OFFLINE = "offline"
    ONLINE = "online"


class TrackerPublishStatus(StrEnum):
    """Observable result of one explicit publishing request."""

    DISABLED = "disabled"
    STORED_OFFLINE = "stored-offline"
    PUBLISHED_ONLINE = "published-online"


class MetricGraphFamily(StrEnum):
    """The four governed graph families required by Task 9K.4."""

    PERFORMANCE = "performance"
    SUPPORT = "support"
    RETENTION = "retention"
    TRANSFER = "transfer"


class MetricGraphAvailability(StrEnum):
    """Whether one graph has source-backed values in this exact trajectory."""

    AVAILABLE = "available"
    UNAVAILABLE = "unavailable"


@dataclass(frozen=True, slots=True)
class TrackerMetricPoint:
    """One immutable tracker-neutral row of primitive scalar values."""

    step: int
    values: tuple[tuple[str, TrackerScalar], ...]

    def to_dict(self) -> dict[str, TrackerScalar]:
        """Return a fresh mutable boundary object for a third-party client."""

        return dict(self.values)


@dataclass(frozen=True, slots=True)
class CurriculumTrackerBatch:
    """De-identified scalar batch derived from one governed summary."""

    summary_ref: SemanticReference
    metadata: tuple[tuple[str, TrackerScalar], ...]
    points: tuple[TrackerMetricPoint, ...]

    def metadata_dict(self) -> dict[str, TrackerScalar]:
        """Return a fresh tracker configuration mapping."""

        return dict(self.metadata)


@dataclass(frozen=True, slots=True)
class CurriculumMetricGraph:
    """Graph-ready view that names every contributing tracker-batch row."""

    family: MetricGraphFamily
    summary_ref: SemanticReference
    x_key: str
    y_key: str
    series_key: str
    filters: tuple[tuple[str, tuple[str, ...]], ...]
    candidate_source_steps: tuple[int, ...]
    plotted_source_steps: tuple[int, ...]
    availability: MetricGraphAvailability
    reason_code: str


@dataclass(frozen=True, slots=True)
class CurriculumMetricReconciliationReceipt:
    """Non-authoritative proof that every graph reconciled to one trajectory."""

    manifest_ref: SemanticReference
    source_record_ref: SemanticReference
    summary_ref: SemanticReference
    graph_families: tuple[MetricGraphFamily, ...]
    tracker_point_count: int
    plotted_coordinate_count: int
    unavailable_graph_families: tuple[MetricGraphFamily, ...]


@dataclass(frozen=True, slots=True)
class TrackerPublishReceipt:
    """Non-authoritative receipt that always points back to the source summary."""

    tracker: str
    mode: TrackerPublishMode
    status: TrackerPublishStatus
    summary_ref: SemanticReference
    point_count: int
    external_run_id: str | None = None
    external_run_url: str | None = None


@dataclass(frozen=True, slots=True)
class WandbTrackerConfiguration:
    """Credential-free W&B settings; disabled mode is the safe default."""

    project: str = "teachmemusic"
    entity: str | None = None
    mode: TrackerPublishMode = TrackerPublishMode.DISABLED
    allow_external_transmission: bool = False
    run_name: str | None = None
    tags: tuple[str, ...] = ("teachmemusic", "deterministic-baseline")


class TrackerPublisher(Protocol):
    """Tracker-neutral outbound port."""

    def publish(self, batch: CurriculumTrackerBatch) -> TrackerPublishReceipt: ...


class _SemanticallyIdentified(Protocol):
    @property
    def id(self) -> str: ...

    @property
    def semantic_fingerprint(self) -> str: ...


class WandbRun(Protocol):
    """Small W&B run surface used by the adapter and test doubles."""

    id: str | None
    url: str | None

    def log(
        self,
        data: dict[str, TrackerScalar],
        *,
        step: int | None = None,
        commit: bool | None = None,
    ) -> None: ...

    def finish(self) -> None: ...


class WandbClient(Protocol):
    """Small W&B SDK surface loaded only for an enabled publishing request."""

    def init(self, **kwargs: object) -> WandbRun | None: ...


class MetricTrackerError(RuntimeError):
    """Raised when an explicit metric-publishing request cannot be completed."""


class MetricGraphError(ValueError):
    """Raised when graph data cannot be reconciled to its tracker batch."""


class MetricGraphReconciliationError(MetricGraphError):
    """Raised when a graph projection drifts from authoritative trajectory evidence."""


def build_curriculum_tracker_batch(
    summary: CurriculumMetricSummaryExport,
) -> CurriculumTrackerBatch:
    """Flatten an approved summary into exact tracker-neutral scalar rows."""

    require_valid_curriculum_metric_summary_export(summary)
    summary_ref = SemanticReference(
        "curriculum-metric-summary-export",
        summary.id,
        summary.semantic_fingerprint,
    )
    metadata: tuple[tuple[str, TrackerScalar], ...] = (
        ("summary/id", summary.id),
        ("summary/fingerprint", summary.semantic_fingerprint),
        ("summary/version", summary.summary_version),
        ("source/id", summary.source_record_ref.id),
        ("source/fingerprint", summary.source_record_ref.semantic_fingerprint),
        ("score/id", summary.score_id),
        ("graph/id", summary.graph_ref.id),
        ("graph/fingerprint", summary.graph_ref.semantic_fingerprint),
        ("policy/identity", summary.policy_identity),
        ("policy/configuration_id", summary.policy_configuration_ref.id),
        ("policy/configuration_fingerprint", summary.policy_configuration_ref.semantic_fingerprint),
        ("decision/first_sequence", summary.first_decision_sequence),
        ("decision/last_sequence", summary.last_decision_sequence),
    )
    points: list[TrackerMetricPoint] = []
    step = 0
    for decision in summary.decision_metrics:
        for component in decision.reward_components:
            value_available = component.value is not None
            numerator = component.value.numerator if component.value is not None else 0
            denominator = component.value.denominator if component.value is not None else 0
            values: tuple[tuple[str, TrackerScalar], ...] = (
                ("decision/sequence", decision.decision_sequence),
                ("decision/input_fingerprint", decision.metric_input_fingerprint),
                ("node/current_id", decision.current_node_id),
                ("node/next_id", decision.next_node_id),
                ("support/prior_id", decision.prior_support_state_ref.id),
                ("support/next_id", decision.next_support_state_ref.id),
                ("policy/action", decision.selected_action.value),
                (
                    "policy/behavior_probability_numerator",
                    decision.behavior_probability.numerator,
                ),
                (
                    "policy/behavior_probability_denominator",
                    decision.behavior_probability.denominator,
                ),
                ("outcome/completion", decision.completion.value),
                ("reward/component_id", component.component_id),
                ("reward/dimension", component.dimension.value if component.dimension else ""),
                ("reward/status", component.status.value),
                ("reward/value_available", value_available),
                ("reward/value_numerator", numerator),
                ("reward/value_denominator", denominator),
                ("reward/matched_observations", component.matched_observation_count),
                (
                    "reward/discrepancy_observations",
                    component.discrepancy_observation_count,
                ),
                ("reward/unresolved_observations", component.unresolved_observation_count),
                ("reward/reason_code", component.reason_code),
            )
            if component.value is not None:
                values = (*values, ("reward/value_plot", float(component.value)))
            if component.component_id == "attempt-completion":
                support_changed = (
                    decision.prior_support_state_ref != decision.next_support_state_ref
                )
                values = (
                    *values,
                    ("support/change_plot", float(support_changed)),
                    (
                        "support/change_status",
                        "changed" if support_changed else "unchanged",
                    ),
                )
            points.append(TrackerMetricPoint(step=step, values=values))
            step += 1
    return CurriculumTrackerBatch(
        summary_ref=summary_ref,
        metadata=metadata,
        points=tuple(points),
    )


def build_curriculum_metric_graphs(
    batch: CurriculumTrackerBatch,
) -> tuple[CurriculumMetricGraph, ...]:
    """Define graph-ready performance, support, retention, and transfer views."""

    _require_valid_tracker_batch(batch)
    rows = tuple((point.step, point.to_dict()) for point in batch.points)
    all_steps = tuple(step for step, _ in rows)
    performance_steps = tuple(
        step for step, values in rows if values["reward/value_available"] is True
    )
    support_steps = tuple(step for step, values in rows if "support/change_plot" in values)
    retention_candidates = tuple(
        step
        for step, values in rows
        if values["policy/action"] == CurriculumPolicyAction.RUN_RETENTION.value
    )
    retention_steps = tuple(
        step
        for step, values in rows
        if step in retention_candidates and values["reward/value_available"] is True
    )
    transfer_candidates = tuple(
        step
        for step, values in rows
        if values["policy/action"] == CurriculumPolicyAction.RUN_TRANSFER.value
    )
    transfer_steps = tuple(
        step
        for step, values in rows
        if step in transfer_candidates and values["reward/value_available"] is True
    )

    return (
        _metric_graph(
            MetricGraphFamily.PERFORMANCE,
            batch.summary_ref,
            "reward/value_plot",
            "reward/component_id",
            (),
            all_steps,
            performance_steps,
            "PERFORMANCE_VALUES_NOT_AVAILABLE",
        ),
        _metric_graph(
            MetricGraphFamily.SUPPORT,
            batch.summary_ref,
            "support/change_plot",
            "support/next_id",
            (("reward/component_id", ("attempt-completion",)),),
            support_steps,
            support_steps,
            "SUPPORT_TRANSITIONS_NOT_AVAILABLE",
        ),
        _metric_graph(
            MetricGraphFamily.RETENTION,
            batch.summary_ref,
            "reward/value_plot",
            "reward/component_id",
            (("policy/action", (CurriculumPolicyAction.RUN_RETENTION.value,)),),
            retention_candidates,
            retention_steps,
            (
                "RETENTION_OUTCOME_NOT_PRESENT"
                if not retention_candidates
                else "RETENTION_VALUES_NOT_AVAILABLE"
            ),
        ),
        _metric_graph(
            MetricGraphFamily.TRANSFER,
            batch.summary_ref,
            "reward/value_plot",
            "reward/component_id",
            (("policy/action", (CurriculumPolicyAction.RUN_TRANSFER.value,)),),
            transfer_candidates,
            transfer_steps,
            (
                "TRANSFER_OUTCOME_NOT_PRESENT"
                if not transfer_candidates
                else "TRANSFER_VALUES_NOT_AVAILABLE"
            ),
        ),
    )


def reconcile_curriculum_metric_graphs(
    graphs: tuple[CurriculumMetricGraph, ...],
    batch: CurriculumTrackerBatch,
    summary: CurriculumMetricSummaryExport,
    source: CurriculumMetricSourceRecord,
    manifest: CurriculumExperimentManifest,
    snapshots: tuple[CurriculumDecisionSnapshot, ...],
    inventories: tuple[CurriculumActionInventory, ...],
    selections: tuple[CurriculumActionSelection, ...],
    outcomes: tuple[CurriculumLearningOutcome, ...],
    rewards: tuple[CurriculumResearchReward, ...],
    transitions: tuple[CurriculumTransitionResult, ...],
) -> CurriculumMetricReconciliationReceipt:
    """Fail closed unless all graph data derives from one governed trajectory."""

    try:
        require_valid_curriculum_experiment_manifest(
            manifest,
            snapshots,
            inventories,
            selections,
            outcomes,
            rewards,
            transitions,
        )
        require_valid_curriculum_metric_source_record(source, manifest)
        require_valid_curriculum_metric_summary_export(
            summary,
            source,
            snapshots,
            selections,
            outcomes,
            rewards,
        )
    except CurriculumValidationError as exc:
        raise MetricGraphReconciliationError(
            "authoritative trajectory-to-summary reconciliation failed"
        ) from exc

    expected_batch = build_curriculum_tracker_batch(summary)
    if batch != expected_batch:
        raise MetricGraphReconciliationError(
            "tracker batch differs from the authoritative summary projection"
        )
    expected_graphs = build_curriculum_metric_graphs(expected_batch)
    if graphs != expected_graphs:
        raise MetricGraphReconciliationError(
            "metric graphs or availability decisions differ from the tracker batch"
        )

    return CurriculumMetricReconciliationReceipt(
        manifest_ref=_artifact_reference("curriculum-experiment-manifest", manifest),
        source_record_ref=_artifact_reference("curriculum-metric-source-record", source),
        summary_ref=expected_batch.summary_ref,
        graph_families=tuple(graph.family for graph in graphs),
        tracker_point_count=len(batch.points),
        plotted_coordinate_count=sum(len(graph.plotted_source_steps) for graph in graphs),
        unavailable_graph_families=tuple(
            graph.family
            for graph in graphs
            if graph.availability is MetricGraphAvailability.UNAVAILABLE
        ),
    )


def _metric_graph(
    family: MetricGraphFamily,
    summary_ref: SemanticReference,
    y_key: str,
    series_key: str,
    filters: tuple[tuple[str, tuple[str, ...]], ...],
    candidate_steps: tuple[int, ...],
    plotted_steps: tuple[int, ...],
    unavailable_reason: str,
) -> CurriculumMetricGraph:
    available = bool(plotted_steps)
    return CurriculumMetricGraph(
        family=family,
        summary_ref=summary_ref,
        x_key="decision/sequence",
        y_key=y_key,
        series_key=series_key,
        filters=filters,
        candidate_source_steps=candidate_steps,
        plotted_source_steps=plotted_steps,
        availability=(
            MetricGraphAvailability.AVAILABLE if available else MetricGraphAvailability.UNAVAILABLE
        ),
        reason_code="GRAPH_VALUES_AVAILABLE" if available else unavailable_reason,
    )


def _artifact_reference(
    artifact_type: str,
    value: _SemanticallyIdentified,
) -> SemanticReference:
    return SemanticReference(artifact_type, value.id, value.semantic_fingerprint)


def _require_valid_tracker_batch(batch: CurriculumTrackerBatch) -> None:
    if batch.summary_ref.artifact_type != "curriculum-metric-summary-export":
        raise MetricGraphError("tracker batch does not reference a metric summary")
    metadata = batch.metadata_dict()
    if len(metadata) != len(batch.metadata) or tuple(metadata) != _TRACKER_METADATA_KEYS:
        raise MetricGraphError("tracker metadata keys are incomplete, duplicated, or reordered")
    if (
        metadata["summary/id"] != batch.summary_ref.id
        or metadata["summary/fingerprint"] != batch.summary_ref.semantic_fingerprint
    ):
        raise MetricGraphError("tracker metadata differs from the governed summary reference")
    if not batch.points or tuple(point.step for point in batch.points) != tuple(
        range(len(batch.points))
    ):
        raise MetricGraphError("tracker point steps must be non-empty and contiguous")
    first_sequence = _exact_int(metadata["decision/first_sequence"], "first decision sequence")
    last_sequence = _exact_int(metadata["decision/last_sequence"], "last decision sequence")
    decision_rows: dict[int, list[dict[str, TrackerScalar]]] = {}
    shared_keys = (
        "decision/input_fingerprint",
        "node/current_id",
        "node/next_id",
        "support/prior_id",
        "support/next_id",
        "policy/action",
        "policy/behavior_probability_numerator",
        "policy/behavior_probability_denominator",
        "outcome/completion",
    )
    for point in batch.points:
        values = point.to_dict()
        if len(values) != len(point.values):
            raise MetricGraphError("tracker point keys must be unique")
        if not set(_TRACKER_POINT_KEYS).issubset(values):
            raise MetricGraphError("tracker point is missing a governed metric field")
        sequence = _exact_int(values["decision/sequence"], "decision sequence")
        _validate_tracker_point(values)
        decision_rows.setdefault(sequence, []).append(values)

    if tuple(decision_rows) != tuple(range(first_sequence, last_sequence)):
        raise MetricGraphError("tracker decisions must preserve the summary sequence")
    for rows in decision_rows.values():
        first = rows[0]
        if any(any(row[key] != first[key] for key in shared_keys) for row in rows[1:]):
            raise MetricGraphError("tracker rows disagree on decision-level values")
        component_ids = tuple(str(row["reward/component_id"]) for row in rows)
        if len(component_ids) != len(set(component_ids)):
            raise MetricGraphError("tracker decision repeats a reward component")
        if component_ids.count("attempt-completion") != 1:
            raise MetricGraphError("tracker decision requires one attempt-completion component")


def _validate_tracker_point(values: dict[str, TrackerScalar]) -> None:
    try:
        CurriculumPolicyAction(str(values["policy/action"]))
        AttemptCompletion(str(values["outcome/completion"]))
        ResearchRewardComponentStatus(str(values["reward/status"]))
        dimension = str(values["reward/dimension"])
        if dimension:
            ObservationDimension(dimension)
    except ValueError as exc:
        raise MetricGraphError("tracker point contains an unknown governed value") from exc

    probability_denominator = _exact_int(
        values["policy/behavior_probability_denominator"],
        "behavior-probability denominator",
    )
    if probability_denominator <= 0:
        raise MetricGraphError("behavior-probability denominator must be positive")
    available = values["reward/value_available"]
    if type(available) is not bool:
        raise MetricGraphError("reward value availability must be boolean")
    numerator = _exact_int(values["reward/value_numerator"], "reward numerator")
    denominator = _exact_int(values["reward/value_denominator"], "reward denominator")
    for key in (
        "reward/matched_observations",
        "reward/discrepancy_observations",
        "reward/unresolved_observations",
    ):
        if _exact_int(values[key], key) < 0:
            raise MetricGraphError("reward observation counts must be non-negative")
    if available:
        if denominator <= 0 or "reward/value_plot" not in values:
            raise MetricGraphError("available reward values require exact and plot values")
        plot_value = values["reward/value_plot"]
        if type(plot_value) is not float or plot_value != float(Fraction(numerator, denominator)):
            raise MetricGraphError("reward plot value differs from its exact fraction")
    elif numerator != 0 or denominator != 0 or "reward/value_plot" in values:
        raise MetricGraphError("unavailable reward values must not fabricate a plot value")

    component_id = str(values["reward/component_id"])
    support_keys = {"support/change_plot", "support/change_status"}
    present_support_keys = support_keys.intersection(values)
    if component_id == "attempt-completion":
        expected_change = values["support/prior_id"] != values["support/next_id"]
        if present_support_keys != support_keys:
            raise MetricGraphError("attempt completion must carry one support transition")
        if type(values["support/change_plot"]) is not float or values[
            "support/change_plot"
        ] != float(expected_change):
            raise MetricGraphError("support plot value differs from source-state identity")
        expected_status = "changed" if expected_change else "unchanged"
        if values["support/change_status"] != expected_status:
            raise MetricGraphError("support change status differs from source-state identity")
    elif present_support_keys:
        raise MetricGraphError("support transition must appear once per decision")


def _exact_int(value: TrackerScalar, name: str) -> int:
    if type(value) is not int:
        raise MetricGraphError(f"{name} must be an integer")
    return value


def publish_curriculum_metric_summary(
    summary: CurriculumMetricSummaryExport,
    publisher: TrackerPublisher,
) -> TrackerPublishReceipt:
    """Publish only the tracker-neutral batch and verify its returned receipt."""

    batch = build_curriculum_tracker_batch(summary)
    receipt = publisher.publish(batch)
    if receipt.summary_ref != batch.summary_ref:
        raise MetricTrackerError("tracker receipt does not reference the published summary")
    expected_status = {
        TrackerPublishMode.DISABLED: TrackerPublishStatus.DISABLED,
        TrackerPublishMode.OFFLINE: TrackerPublishStatus.STORED_OFFLINE,
        TrackerPublishMode.ONLINE: TrackerPublishStatus.PUBLISHED_ONLINE,
    }[receipt.mode]
    if receipt.status is not expected_status:
        raise MetricTrackerError("tracker receipt mode and status are inconsistent")
    expected_count = 0 if receipt.mode is TrackerPublishMode.DISABLED else len(batch.points)
    if receipt.point_count != expected_count:
        raise MetricTrackerError("tracker receipt has an invalid published-point count")
    return receipt


class WandbMetricPublisher:
    """Optional W&B sink with disabled, offline, and explicitly online modes."""

    def __init__(
        self,
        configuration: WandbTrackerConfiguration | None = None,
        *,
        client: WandbClient | None = None,
    ) -> None:
        self._configuration = configuration or WandbTrackerConfiguration()
        self._client = client

    def publish(self, batch: CurriculumTrackerBatch) -> TrackerPublishReceipt:
        """Send a scalar batch to W&B only when its mode explicitly permits it."""

        configuration = self._configuration
        if configuration.mode is TrackerPublishMode.DISABLED:
            return TrackerPublishReceipt(
                tracker="wandb",
                mode=configuration.mode,
                status=TrackerPublishStatus.DISABLED,
                summary_ref=batch.summary_ref,
                point_count=0,
            )
        if not configuration.project.strip():
            raise MetricTrackerError("an enabled W&B publisher requires a project name")
        if (
            configuration.mode is TrackerPublishMode.ONLINE
            and not configuration.allow_external_transmission
        ):
            raise MetricTrackerError(
                "online W&B publishing requires explicit external-transmission authorization"
            )

        client = self._client or _load_wandb_client()
        init_arguments: dict[str, object] = {
            "project": configuration.project,
            "mode": configuration.mode.value,
            "config": batch.metadata_dict(),
            "tags": configuration.tags,
        }
        if configuration.entity is not None:
            init_arguments["entity"] = configuration.entity
        if configuration.run_name is not None:
            init_arguments["name"] = configuration.run_name

        try:
            run = client.init(**init_arguments)
        except Exception as exc:
            raise MetricTrackerError("W&B run initialization failed") from exc
        if run is None:
            raise MetricTrackerError("W&B did not return a run")
        try:
            for point in batch.points:
                run.log(point.to_dict(), step=point.step, commit=True)
        except Exception as exc:
            raise MetricTrackerError("W&B metric logging failed") from exc
        finally:
            run.finish()

        status = (
            TrackerPublishStatus.STORED_OFFLINE
            if configuration.mode is TrackerPublishMode.OFFLINE
            else TrackerPublishStatus.PUBLISHED_ONLINE
        )
        return TrackerPublishReceipt(
            tracker="wandb",
            mode=configuration.mode,
            status=status,
            summary_ref=batch.summary_ref,
            point_count=len(batch.points),
            external_run_id=run.id,
            external_run_url=run.url,
        )


def _load_wandb_client() -> WandbClient:
    try:
        module = import_module("wandb")
    except ModuleNotFoundError as exc:
        raise MetricTrackerError(
            "W&B publishing requires the optional 'metrics' dependency"
        ) from exc
    return cast(WandbClient, module)
