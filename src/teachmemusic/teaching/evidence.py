"""Append-only local teaching evidence, integrity archives, and resumption."""

from __future__ import annotations

import hashlib
import hmac
import os
import re
import tempfile
from dataclasses import dataclass, replace
from pathlib import Path

from teachmemusic._contract_codec import (
    ContractCodecError,
    contract_from_json,
    contract_to_json,
)
from teachmemusic.performance import CalibrationProfile, LearnerAttempt, Observation
from teachmemusic.performance.validation import is_stable_id

from .contracts import (
    EVIDENCE_ARCHIVE_CONTRACT_ID,
    EVIDENCE_ARCHIVE_CONTRACT_VERSION,
    ContractVersionSet,
    EvidenceArchive,
    EvidenceExport,
    EvidenceRecord,
    FeedbackAction,
    GateDecision,
    LearnerJournalEntry,
    LearnerJournalKind,
    LessonPlan,
    PlanAudit,
    PolicyDecision,
    RunEvent,
    RunEventKind,
    SupportState,
)
from .serialization import evidence_export_to_json
from .validation import TeachingValidationError, require_valid_evidence_export

DEFAULT_MAX_EVIDENCE_BYTES = 16 * 1024 * 1024
_SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")

EvidencePayload = (
    LessonPlan
    | PlanAudit
    | SupportState
    | CalibrationProfile
    | LearnerAttempt
    | Observation
    | EvidenceRecord
    | FeedbackAction
    | PolicyDecision
    | LearnerJournalEntry
    | GateDecision
)


class EvidenceRecordError(ValueError):
    """Stable failure at the append-only evidence boundary."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(f"{code}: {message}")


@dataclass(frozen=True, slots=True)
class EvidenceInspection:
    """Non-mutating summary suitable for an owner inspection screen."""

    run_id: str
    score_digest_sha256: str
    evidence_sha256: str
    plan_count: int
    audit_count: int
    support_count: int
    calibration_count: int
    attempt_count: int
    observation_count: int
    evidence_record_count: int
    feedback_count: int
    policy_decision_count: int
    journal_entry_count: int
    gate_decision_count: int
    event_count: int
    latest_sequence_number: int | None
    has_pedagogical_intervention: bool
    omissions: tuple[str, ...]


def append_evidence_payload(
    value: EvidenceExport,
    payload: EvidencePayload,
    *,
    event_id: str,
    occurred_at_utc: str,
    supersedes_event_id: str | None = None,
) -> EvidenceExport:
    """Append one typed payload and its event without rewriting prior facts."""

    _require_valid_export(value)
    updated, kind = _append_payload(value, payload)
    return append_run_event(
        updated,
        kind=kind,
        payload_id=payload.id,
        event_id=event_id,
        occurred_at_utc=occurred_at_utc,
        supersedes_event_id=supersedes_event_id,
    )


def append_run_event(
    value: EvidenceExport,
    *,
    kind: RunEventKind,
    payload_id: str,
    event_id: str,
    occurred_at_utc: str,
    supersedes_event_id: str | None = None,
) -> EvidenceExport:
    """Append an event for a payload already present in the export."""

    _require_valid_export(value)
    event = RunEvent(
        id=event_id,
        run_id=value.manifest.id,
        sequence_number=len(value.run_events),
        kind=kind,
        payload_id=payload_id,
        occurred_at_utc=occurred_at_utc,
        supersedes_event_id=supersedes_event_id,
    )
    updated = replace(value, run_events=(*value.run_events, event))
    _require_valid_export(updated)
    return updated


def create_evidence_archive(value: EvidenceExport) -> EvidenceArchive:
    """Seal an authorized deterministic export in a SHA-256 integrity envelope."""

    _require_valid_export(value)
    if not value.data_authorization.approved:
        raise EvidenceRecordError("EVIDENCE_AUTHORIZATION", "data capture has not been approved")
    if not value.data_authorization.allow_export:
        raise EvidenceRecordError(
            "EVIDENCE_EXPORT_DECLINED", "the owner did not authorize evidence export"
        )
    _require_complete_event_log(value)
    archive = EvidenceArchive(
        evidence=value,
        evidence_sha256=_evidence_digest(value),
    )
    require_valid_evidence_archive(archive)
    return archive


def evidence_archive_to_json(archive: EvidenceArchive) -> str:
    """Serialize a verified archive deterministically."""

    require_valid_evidence_archive(archive)
    try:
        return contract_to_json(archive)
    except ContractCodecError as error:
        raise EvidenceRecordError("EVIDENCE_ARCHIVE_ENCODING", str(error)) from error


def evidence_archive_from_json(payload: str) -> EvidenceArchive:
    """Strictly decode and integrity-check one archive."""

    try:
        archive = contract_from_json(payload, EvidenceArchive)
    except ContractCodecError as error:
        raise EvidenceRecordError("EVIDENCE_ARCHIVE_DECODING", str(error)) from error
    require_valid_evidence_archive(archive)
    return archive


def require_valid_evidence_archive(archive: EvidenceArchive) -> None:
    """Reject contract drift, invalid evidence, and integrity mismatch."""

    if archive.contract_id != EVIDENCE_ARCHIVE_CONTRACT_ID:
        raise EvidenceRecordError("EVIDENCE_ARCHIVE_CONTRACT", "unsupported contract ID")
    if archive.contract_version != EVIDENCE_ARCHIVE_CONTRACT_VERSION:
        raise EvidenceRecordError("EVIDENCE_ARCHIVE_VERSION", "unsupported contract version")
    if archive.integrity_algorithm != "sha256":
        raise EvidenceRecordError("EVIDENCE_INTEGRITY_ALGORITHM", "unsupported algorithm")
    if _SHA256_PATTERN.fullmatch(archive.evidence_sha256) is None:
        raise EvidenceRecordError("EVIDENCE_INTEGRITY_DIGEST", "digest is not lowercase SHA-256")
    _require_valid_export(archive.evidence)
    if not archive.evidence.data_authorization.approved:
        raise EvidenceRecordError("EVIDENCE_AUTHORIZATION", "data capture has not been approved")
    if not archive.evidence.data_authorization.allow_export:
        raise EvidenceRecordError(
            "EVIDENCE_EXPORT_DECLINED", "the owner did not authorize evidence export"
        )
    _require_complete_event_log(archive.evidence)
    actual = _evidence_digest(archive.evidence)
    if not hmac.compare_digest(actual, archive.evidence_sha256):
        raise EvidenceRecordError(
            "EVIDENCE_INTEGRITY_MISMATCH", "evidence digest does not match its contents"
        )


def resume_evidence_archive(
    archive: EvidenceArchive,
    *,
    score_digest_sha256: str,
    package_id: str,
    score_id: str,
    compatible_versions: ContractVersionSet,
) -> EvidenceExport:
    """Resume only against the exact score identity and frozen version set."""

    require_valid_evidence_archive(archive)
    manifest = archive.evidence.manifest
    if manifest.score_digest_sha256 != score_digest_sha256:
        raise EvidenceRecordError("EVIDENCE_SCORE_MISMATCH", "score digest differs")
    if manifest.package_id != package_id or manifest.score_id != score_id:
        raise EvidenceRecordError(
            "EVIDENCE_SCORE_IDENTITY_MISMATCH", "canonical package or score differs"
        )
    if manifest.versions != compatible_versions:
        raise EvidenceRecordError(
            "EVIDENCE_VERSION_MISMATCH", "run versions are not exactly compatible"
        )
    return archive.evidence


def inspect_evidence_archive(archive: EvidenceArchive) -> EvidenceInspection:
    """Return a bounded factual inventory without exposing raw score bytes."""

    require_valid_evidence_archive(archive)
    evidence = archive.evidence
    return EvidenceInspection(
        run_id=evidence.manifest.id,
        score_digest_sha256=evidence.manifest.score_digest_sha256,
        evidence_sha256=archive.evidence_sha256,
        plan_count=len(evidence.plans),
        audit_count=len(evidence.audits),
        support_count=(
            len(evidence.support_states) + sum(len(plan.exercises) for plan in evidence.plans)
        ),
        calibration_count=len(evidence.performance.calibrations),
        attempt_count=len(evidence.performance.attempts),
        observation_count=len(evidence.performance.observations),
        evidence_record_count=len(evidence.evidence_records),
        feedback_count=len(evidence.feedback_actions),
        policy_decision_count=len(evidence.policy_decisions),
        journal_entry_count=len(evidence.journal_entries),
        gate_decision_count=len(evidence.gate_decisions),
        event_count=len(evidence.run_events),
        latest_sequence_number=(
            evidence.run_events[-1].sequence_number if evidence.run_events else None
        ),
        has_pedagogical_intervention=any(
            intervention.pedagogical
            for audit in evidence.audits
            for intervention in audit.interventions
        ),
        omissions=evidence.omissions,
    )


class LocalEvidenceStore:
    """Explicit local-file archive store with bounded atomic writes."""

    def __init__(
        self,
        root: Path,
        *,
        max_bytes: int = DEFAULT_MAX_EVIDENCE_BYTES,
    ) -> None:
        if max_bytes <= 0:
            raise EvidenceRecordError("EVIDENCE_STORE_LIMIT", "max bytes must be positive")
        self._root = root
        self._max_bytes = max_bytes

    def write(self, archive: EvidenceArchive) -> Path:
        """Atomically write one owner-authorized archive."""

        payload = evidence_archive_to_json(archive).encode("utf-8")
        if len(payload) > self._max_bytes:
            raise EvidenceRecordError("EVIDENCE_STORE_LIMIT", "archive exceeds local limit")
        self._root.mkdir(parents=True, exist_ok=True, mode=0o700)
        target = self._path(archive.evidence.manifest.id)
        descriptor, temporary_name = tempfile.mkstemp(
            dir=self._root,
            prefix=f".{target.name}.",
            suffix=".tmp",
        )
        temporary = Path(temporary_name)
        try:
            os.chmod(temporary, 0o600)
            with os.fdopen(descriptor, "wb") as stream:
                stream.write(payload)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, target)
        except OSError as error:
            temporary.unlink(missing_ok=True)
            raise EvidenceRecordError("EVIDENCE_STORE_WRITE", str(error)) from error
        return target

    def read(self, run_id: str) -> EvidenceArchive:
        """Read and verify one exact run archive."""

        target = self._path(run_id)
        try:
            size = target.stat().st_size
            if size > self._max_bytes:
                raise EvidenceRecordError(
                    "EVIDENCE_STORE_LIMIT", "stored archive exceeds local limit"
                )
            payload = target.read_text(encoding="utf-8")
        except FileNotFoundError as error:
            raise EvidenceRecordError(
                "EVIDENCE_STORE_NOT_FOUND", "run archive is missing"
            ) from error
        except (OSError, UnicodeError) as error:
            raise EvidenceRecordError("EVIDENCE_STORE_READ", str(error)) from error
        archive = evidence_archive_from_json(payload)
        if archive.evidence.manifest.id != run_id:
            raise EvidenceRecordError("EVIDENCE_STORE_IDENTITY", "stored run identity differs")
        return archive

    def resume(
        self,
        run_id: str,
        *,
        score_digest_sha256: str,
        package_id: str,
        score_id: str,
        compatible_versions: ContractVersionSet,
    ) -> EvidenceExport:
        """Read, verify, and resume one compatible local run."""

        return resume_evidence_archive(
            self.read(run_id),
            score_digest_sha256=score_digest_sha256,
            package_id=package_id,
            score_id=score_id,
            compatible_versions=compatible_versions,
        )

    def inspect(self, run_id: str) -> EvidenceInspection:
        """Inspect one archive without changing it."""

        return inspect_evidence_archive(self.read(run_id))

    def delete(self, run_id: str) -> bool:
        """Delete only the named local archive; return whether it existed."""

        target = self._path(run_id)
        try:
            target.unlink()
        except FileNotFoundError:
            return False
        except OSError as error:
            raise EvidenceRecordError("EVIDENCE_STORE_DELETE", str(error)) from error
        return True

    def _path(self, run_id: str) -> Path:
        if not is_stable_id(run_id):
            raise EvidenceRecordError("EVIDENCE_RUN_ID", "run ID is not namespaced")
        token = hashlib.sha256(run_id.encode("utf-8")).hexdigest()
        return self._root / f"teachmemusic-run-{token}.json"


def _append_payload(
    value: EvidenceExport, payload: EvidencePayload
) -> tuple[EvidenceExport, RunEventKind]:
    if isinstance(payload, LessonPlan):
        return replace(value, plans=(*value.plans, payload)), RunEventKind.PLAN_GENERATED
    if isinstance(payload, PlanAudit):
        return replace(value, audits=(*value.audits, payload)), RunEventKind.PLAN_AUDITED
    if isinstance(payload, SupportState):
        return (
            replace(value, support_states=(*value.support_states, payload)),
            RunEventKind.SUPPORT_RECORDED,
        )
    performance = value.performance
    if isinstance(payload, CalibrationProfile):
        performance = replace(
            performance,
            calibrations=(*performance.calibrations, payload),
        )
        return replace(value, performance=performance), RunEventKind.CALIBRATION_RECORDED
    if isinstance(payload, LearnerAttempt):
        performance = replace(performance, attempts=(*performance.attempts, payload))
        return replace(value, performance=performance), RunEventKind.ATTEMPT_RECORDED
    if isinstance(payload, Observation):
        performance = replace(
            performance,
            observations=(*performance.observations, payload),
        )
        return replace(value, performance=performance), RunEventKind.OBSERVATION_RECORDED
    if isinstance(payload, EvidenceRecord):
        return (
            replace(value, evidence_records=(*value.evidence_records, payload)),
            RunEventKind.EVIDENCE_RECORDED,
        )
    if isinstance(payload, FeedbackAction):
        return (
            replace(value, feedback_actions=(*value.feedback_actions, payload)),
            RunEventKind.FEEDBACK_RECORDED,
        )
    if isinstance(payload, PolicyDecision):
        return (
            replace(value, policy_decisions=(*value.policy_decisions, payload)),
            RunEventKind.POLICY_DECIDED,
        )
    if isinstance(payload, LearnerJournalEntry):
        kinds = {
            LearnerJournalKind.SELF_REPORT: RunEventKind.SELF_REPORT_RECORDED,
            LearnerJournalKind.OUTSIDE_PRACTICE: RunEventKind.OUTSIDE_PRACTICE_RECORDED,
            LearnerJournalKind.PAUSE: RunEventKind.PAUSED,
            LearnerJournalKind.STOP: RunEventKind.STOPPED,
            LearnerJournalKind.DISCOMFORT: RunEventKind.STOPPED,
        }
        return (
            replace(value, journal_entries=(*value.journal_entries, payload)),
            kinds[payload.kind],
        )
    if isinstance(payload, GateDecision):
        return (
            replace(value, gate_decisions=(*value.gate_decisions, payload)),
            RunEventKind.GATE_DECIDED,
        )
    raise EvidenceRecordError(
        "EVIDENCE_PAYLOAD_TYPE", f"unsupported payload {type(payload).__name__}"
    )


def _evidence_digest(value: EvidenceExport) -> str:
    payload = evidence_export_to_json(value).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _require_complete_event_log(value: EvidenceExport) -> None:
    expected: set[tuple[RunEventKind, str]] = {
        (RunEventKind.RUN_CREATED, value.manifest.id),
        (RunEventKind.DATA_AUTHORIZED, value.data_authorization.id),
        (RunEventKind.EXPORTED, value.id),
        *((RunEventKind.PLAN_GENERATED, item.id) for item in value.plans),
        *((RunEventKind.PLAN_AUDITED, item.id) for item in value.audits),
        *((RunEventKind.SUPPORT_RECORDED, item.id) for item in value.support_states),
        *((RunEventKind.CALIBRATION_RECORDED, item.id) for item in value.performance.calibrations),
        *((RunEventKind.ATTEMPT_RECORDED, item.id) for item in value.performance.attempts),
        *((RunEventKind.OBSERVATION_RECORDED, item.id) for item in value.performance.observations),
        *((RunEventKind.EVIDENCE_RECORDED, item.id) for item in value.evidence_records),
        *((RunEventKind.FEEDBACK_RECORDED, item.id) for item in value.feedback_actions),
        *((RunEventKind.POLICY_DECIDED, item.id) for item in value.policy_decisions),
        *((RunEventKind.GATE_DECIDED, item.id) for item in value.gate_decisions),
    }
    for item in value.journal_entries:
        kind = {
            LearnerJournalKind.SELF_REPORT: RunEventKind.SELF_REPORT_RECORDED,
            LearnerJournalKind.OUTSIDE_PRACTICE: RunEventKind.OUTSIDE_PRACTICE_RECORDED,
            LearnerJournalKind.PAUSE: RunEventKind.PAUSED,
            LearnerJournalKind.STOP: RunEventKind.STOPPED,
            LearnerJournalKind.DISCOMFORT: RunEventKind.STOPPED,
        }[item.kind]
        expected.add((kind, item.id))
    actual = {(item.kind, item.payload_id) for item in value.run_events}
    missing = sorted(f"{kind.value}:{identifier}" for kind, identifier in expected - actual)
    if missing:
        raise EvidenceRecordError(
            "EVIDENCE_EVENT_LOG_INCOMPLETE",
            f"payloads lack append-only events: {missing!r}",
        )


def _require_valid_export(value: EvidenceExport) -> None:
    try:
        require_valid_evidence_export(value)
    except TeachingValidationError as error:
        raise EvidenceRecordError("EVIDENCE_EXPORT_INVALID", str(error)) from error
