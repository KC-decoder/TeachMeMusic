"""Tests for append-only local teaching evidence and resumption."""

import hashlib
import json
from dataclasses import FrozenInstanceError, replace

import pytest

from teachmemusic._contract_codec import contract_to_json
from teachmemusic.teaching import (
    EVIDENCE_ARCHIVE_CONTRACT_VERSION,
    EvidenceRecordError,
    GateDecision,
    GateOutcome,
    LearnerJournalEntry,
    LearnerJournalKind,
    LocalEvidenceStore,
    RunEventKind,
    append_evidence_payload,
    append_run_event,
    create_evidence_archive,
    evidence_archive_from_json,
    evidence_archive_to_json,
    inspect_evidence_archive,
    resume_evidence_archive,
    validate_evidence_export,
)
from tests.teaching.test_contracts import valid_evidence_export


def _complete_export():
    value = valid_evidence_export()
    initial = value.plans[0].exercises[0].initial_support
    reduced = replace(
        initial,
        id="support:one:without-note-names",
        note_names_visible=False,
    )
    value = append_evidence_payload(
        value,
        reduced,
        event_id="run-event:10",
        occurred_at_utc="2026-10-01T23:10:00Z",
    )
    outside = LearnerJournalEntry(
        id="journal-entry:outside-1",
        run_id=value.manifest.id,
        kind=LearnerJournalKind.OUTSIDE_PRACTICE,
        recorded_at_utc="2026-10-01T23:11:00Z",
        text="Five minutes of unrelated scale practice.",
    )
    value = append_evidence_payload(
        value,
        outside,
        event_id="run-event:11",
        occurred_at_utc=outside.recorded_at_utc,
    )
    correction = replace(
        outside,
        id="journal-entry:outside-2",
        recorded_at_utc="2026-10-01T23:12:00Z",
        text="Correction: three minutes of unrelated scale practice.",
    )
    value = append_evidence_payload(
        value,
        correction,
        event_id="run-event:12",
        occurred_at_utc=correction.recorded_at_utc,
        supersedes_event_id="run-event:11",
    )
    gate = GateDecision(
        id="gate-decision:synthetic",
        run_id=value.manifest.id,
        gate_id="evaluation-gate:synthetic",
        outcome=GateOutcome.REMEDIATE_AND_REPEAT,
        decided_at_utc="2026-10-01T23:13:00Z",
        reason="Synthetic evidence-record test only.",
    )
    value = append_evidence_payload(
        value,
        gate,
        event_id="run-event:13",
        occurred_at_utc=gate.decided_at_utc,
    )
    return append_run_event(
        value,
        kind=RunEventKind.EXPORTED,
        payload_id=value.id,
        event_id="run-event:14",
        occurred_at_utc="2026-10-01T23:14:00Z",
    )


def test_complete_run_exports_verifies_inspects_and_resumes() -> None:
    """TEST-EVIDENCE-001: a complete run round-trips and resumes exactly."""

    value = _complete_export()
    archive = create_evidence_archive(value)
    payload = evidence_archive_to_json(archive)
    decoded = evidence_archive_from_json(payload)
    resumed = resume_evidence_archive(
        decoded,
        score_digest_sha256=value.manifest.score_digest_sha256,
        package_id=value.manifest.package_id,
        score_id=value.manifest.score_id,
        compatible_versions=value.manifest.versions,
    )
    inspection = inspect_evidence_archive(decoded)

    assert decoded == archive
    assert evidence_archive_to_json(decoded) == payload
    assert resumed == value
    assert archive.contract_version == EVIDENCE_ARCHIVE_CONTRACT_VERSION
    assert len(archive.evidence_sha256) == 64
    assert inspection.support_count == 2
    assert inspection.journal_entry_count == 2
    assert inspection.gate_decision_count == 1
    assert inspection.event_count == 15
    assert inspection.latest_sequence_number == 14
    assert "<score-partwise" not in payload


def test_archive_detects_content_and_digest_tampering() -> None:
    """TEST-EVIDENCE-002: changed evidence cannot retain the original seal."""

    payload = evidence_archive_to_json(create_evidence_archive(_complete_export()))
    tampered_content = payload.replace(
        "one-note contract test",
        "tampered contract test",
        1,
    )
    with pytest.raises(EvidenceRecordError, match="EVIDENCE_INTEGRITY_MISMATCH"):
        evidence_archive_from_json(tampered_content)

    data = json.loads(payload)
    data["evidence_sha256"] = "0" * 64
    with pytest.raises(EvidenceRecordError, match="EVIDENCE_INTEGRITY_MISMATCH"):
        evidence_archive_from_json(json.dumps(data))


def test_archive_strictly_rejects_unknown_fields_and_versions() -> None:
    """TEST-EVIDENCE-003: contract drift fails before resumption."""

    archive = create_evidence_archive(_complete_export())
    data = json.loads(evidence_archive_to_json(archive))
    data["unexpected"] = True
    with pytest.raises(EvidenceRecordError, match="EVIDENCE_ARCHIVE_DECODING"):
        evidence_archive_from_json(json.dumps(data))

    wrong_version = replace(archive, contract_version="9.9.9")
    with pytest.raises(EvidenceRecordError, match="EVIDENCE_ARCHIVE_VERSION"):
        evidence_archive_to_json(wrong_version)


@pytest.mark.parametrize(
    ("change", "code"),
    [
        ({"score_digest_sha256": "b" * 64}, "EVIDENCE_SCORE_MISMATCH"),
        ({"package_id": "package:other"}, "EVIDENCE_SCORE_IDENTITY_MISMATCH"),
        ({"score_id": "score:other"}, "EVIDENCE_SCORE_IDENTITY_MISMATCH"),
    ],
)
def test_resume_rejects_another_score(change, code: str) -> None:
    """TEST-EVIDENCE-004: score identity is exact, not best-effort."""

    archive = create_evidence_archive(_complete_export())
    arguments = {
        "score_digest_sha256": archive.evidence.manifest.score_digest_sha256,
        "package_id": archive.evidence.manifest.package_id,
        "score_id": archive.evidence.manifest.score_id,
        "compatible_versions": archive.evidence.manifest.versions,
        **change,
    }
    with pytest.raises(EvidenceRecordError, match=code):
        resume_evidence_archive(archive, **arguments)


def test_resume_rejects_incompatible_frozen_versions() -> None:
    """TEST-EVIDENCE-005: incompatible software cannot silently reinterpret a run."""

    archive = create_evidence_archive(_complete_export())
    incompatible = replace(
        archive.evidence.manifest.versions,
        policy_version="future-policy",
    )
    with pytest.raises(EvidenceRecordError, match="EVIDENCE_VERSION_MISMATCH"):
        resume_evidence_archive(
            archive,
            score_digest_sha256=archive.evidence.manifest.score_digest_sha256,
            package_id=archive.evidence.manifest.package_id,
            score_id=archive.evidence.manifest.score_id,
            compatible_versions=incompatible,
        )


def test_correction_appends_and_preserves_superseded_evidence() -> None:
    """TEST-EVIDENCE-006: a correction never rewrites the earlier fact or event."""

    value = _complete_export()

    assert value.journal_entries[0].text.startswith("Five minutes")
    assert value.journal_entries[1].text.startswith("Correction")
    assert value.run_events[11].payload_id == value.journal_entries[0].id
    assert value.run_events[12].supersedes_event_id == value.run_events[11].id
    assert tuple(item.sequence_number for item in value.run_events) == tuple(range(15))


def test_cross_kind_supersession_and_wrong_event_payload_fail_closed() -> None:
    """TEST-EVIDENCE-007: event kind and correction lineage remain typed."""

    value = valid_evidence_export()
    pause = LearnerJournalEntry(
        id="journal-entry:pause",
        run_id=value.manifest.id,
        kind=LearnerJournalKind.PAUSE,
        recorded_at_utc="2026-10-01T23:15:00Z",
        text="Learner paused the session.",
    )
    with pytest.raises(EvidenceRecordError, match="TEACH_EVENT_SUPERSEDES_KIND"):
        append_evidence_payload(
            value,
            pause,
            event_id="run-event:10",
            occurred_at_utc=pause.recorded_at_utc,
            supersedes_event_id="run-event:9",
        )

    with pytest.raises(EvidenceRecordError, match="TEACH_EVENT_KIND_PAYLOAD"):
        append_run_event(
            value,
            kind=RunEventKind.FEEDBACK_RECORDED,
            payload_id=value.manifest.id,
            event_id="run-event:10",
            occurred_at_utc="2026-10-01T23:15:00Z",
        )


def test_owner_can_decline_export_without_losing_contract_evidence() -> None:
    """TEST-EVIDENCE-008: export is impossible when the owner declines it."""

    value = valid_evidence_export()
    denied = replace(
        value,
        data_authorization=replace(value.data_authorization, allow_export=False),
    )
    with pytest.raises(EvidenceRecordError, match="EVIDENCE_EXPORT_DECLINED"):
        create_evidence_archive(denied)

    archive = create_evidence_archive(_complete_export())
    denied_evidence = replace(
        archive.evidence,
        data_authorization=replace(
            archive.evidence.data_authorization,
            allow_export=False,
        ),
    )
    denied_archive = replace(
        archive,
        evidence=denied_evidence,
        evidence_sha256=hashlib.sha256(
            contract_to_json(denied_evidence).encode("utf-8")
        ).hexdigest(),
    )
    with pytest.raises(EvidenceRecordError, match="EVIDENCE_EXPORT_DECLINED"):
        evidence_archive_to_json(denied_archive)


def test_archive_requires_an_event_for_every_present_payload() -> None:
    """TEST-EVIDENCE-009: a valid snapshot is not a complete append-only archive."""

    value = valid_evidence_export()

    with pytest.raises(EvidenceRecordError, match="EVIDENCE_EVENT_LOG_INCOMPLETE"):
        create_evidence_archive(value)


@pytest.mark.parametrize(
    ("kind", "expected_event"),
    [
        (LearnerJournalKind.SELF_REPORT, RunEventKind.SELF_REPORT_RECORDED),
        (LearnerJournalKind.OUTSIDE_PRACTICE, RunEventKind.OUTSIDE_PRACTICE_RECORDED),
        (LearnerJournalKind.PAUSE, RunEventKind.PAUSED),
        (LearnerJournalKind.STOP, RunEventKind.STOPPED),
        (LearnerJournalKind.DISCOMFORT, RunEventKind.STOPPED),
    ],
)
def test_journal_facts_use_explicit_append_only_event_families(kind, expected_event) -> None:
    """TEST-EVIDENCE-010: learner reports never masquerade as measured MIDI facts."""

    value = valid_evidence_export()
    entry = LearnerJournalEntry(
        id=f"journal-entry:{kind.value}",
        run_id=value.manifest.id,
        kind=kind,
        recorded_at_utc="2026-10-01T23:20:00Z",
        text=f"Synthetic {kind.value} record.",
    )
    updated = append_evidence_payload(
        value,
        entry,
        event_id="run-event:10",
        occurred_at_utc=entry.recorded_at_utc,
    )

    assert updated.journal_entries == (entry,)
    assert updated.run_events[-1].kind is expected_event


def test_capture_requires_prior_explicit_data_authorization() -> None:
    """TEST-EVIDENCE-011: populated learner evidence cannot claim no approval."""

    value = valid_evidence_export()
    unauthorized = replace(
        value,
        data_authorization=replace(
            value.data_authorization,
            approved=False,
            approved_at_utc=None,
        ),
    )

    codes = {issue.code for issue in validate_evidence_export(unauthorized)}
    assert "TEACH_DATA_AUTHORIZATION" in codes


def test_local_store_writes_reads_inspects_resumes_and_deletes(tmp_path) -> None:
    """TEST-EVIDENCE-012: explicit local lifecycle is bounded and reversible."""

    archive = create_evidence_archive(_complete_export())
    manifest = archive.evidence.manifest
    store = LocalEvidenceStore(tmp_path / "evidence")

    path = store.write(archive)
    assert path.is_file()
    assert path.stat().st_mode & 0o077 == 0
    assert store.read(manifest.id) == archive
    assert store.inspect(manifest.id).run_id == manifest.id
    assert (
        store.resume(
            manifest.id,
            score_digest_sha256=manifest.score_digest_sha256,
            package_id=manifest.package_id,
            score_id=manifest.score_id,
            compatible_versions=manifest.versions,
        )
        == archive.evidence
    )
    assert store.delete(manifest.id)
    assert not store.delete(manifest.id)
    with pytest.raises(EvidenceRecordError, match="EVIDENCE_STORE_NOT_FOUND"):
        store.read(manifest.id)


def test_local_store_rejects_oversized_archive(tmp_path) -> None:
    """TEST-EVIDENCE-013: a configured byte budget fails before persistence."""

    archive = create_evidence_archive(_complete_export())
    store = LocalEvidenceStore(tmp_path / "evidence", max_bytes=128)

    with pytest.raises(EvidenceRecordError, match="EVIDENCE_STORE_LIMIT"):
        store.write(archive)


def test_archive_and_inspection_values_are_immutable() -> None:
    """TEST-EVIDENCE-014: sealed evidence and its inspection cannot mutate in place."""

    archive = create_evidence_archive(_complete_export())
    inspection = inspect_evidence_archive(archive)

    with pytest.raises(FrozenInstanceError):
        archive.evidence_sha256 = "0" * 64  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        inspection.event_count = 0  # type: ignore[misc]
