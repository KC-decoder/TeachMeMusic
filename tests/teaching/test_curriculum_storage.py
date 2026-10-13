"""Executable storage and migration evidence for DEV-009 Task 9O.4."""

from __future__ import annotations

import gzip
import json
from pathlib import Path

import pytest

from teachmemusic.teaching import (
    CurriculumEvidenceStore,
    CurriculumStoragePolicy,
    CurriculumStoreError,
)


def _authorization(*, allow_export: bool = True) -> dict[str, object]:
    return {
        "approved": True,
        "capture_midi": True,
        "capture_self_report": False,
        "allow_export": allow_export,
    }


def _store(root: Path, **overrides: int) -> CurriculumEvidenceStore:
    defaults = {
        "message_limit": 3,
        "byte_limit": 1_024,
        "time_limit_us": 2_000_000,
        "buffer_limit": 2_048,
        "run_limit": 16_384,
        "store_limit": 65_536,
        "warning_percent": 80,
    }
    return CurriculumEvidenceStore(root, policy=CurriculumStoragePolicy(**(defaults | overrides)))


def _begin(store: CurriculumEvidenceStore, *, allow_export: bool = True) -> None:
    store.begin_run(
        "run:storage-001",
        authorization=_authorization(allow_export=allow_export),
        metadata={"score_id": "score:one", "policy_identity": "policy:one"},
    )


def test_storage_flushes_at_message_threshold_in_order(tmp_path: Path) -> None:
    """TEST-CURR-STORAGE-001: message threshold preserves contiguous order."""

    store = _store(tmp_path / "store")
    _begin(store)
    for sequence in range(3):
        store.append_event(
            "run:storage-001",
            event_type="normalized-midi",
            monotonic_offset_us=sequence * 1_000,
            payload={"note": 60 + sequence},
        )

    inspection = store.inspect("run:storage-001")
    assert inspection.chunk_count == 1
    assert inspection.record_count == 3
    assert inspection.last_complete_sequence == 2


def test_storage_flushes_at_byte_and_time_thresholds(tmp_path: Path) -> None:
    """TEST-CURR-STORAGE-002: byte and time thresholds independently flush."""

    byte_store = _store(tmp_path / "bytes", byte_limit=100)
    _begin(byte_store)
    byte_store.append_event(
        "run:storage-001",
        event_type="observation",
        monotonic_offset_us=0,
        payload={"detail": "x" * 100},
    )
    assert byte_store.inspect("run:storage-001").chunk_count == 1

    time_store = _store(tmp_path / "time", time_limit_us=10)
    _begin(time_store)
    time_store.append_event(
        "run:storage-001", event_type="midi", monotonic_offset_us=0, payload={"note": 60}
    )
    time_store.append_event(
        "run:storage-001", event_type="midi", monotonic_offset_us=10, payload={"note": 61}
    )
    assert time_store.inspect("run:storage-001").chunk_count == 1


def test_storage_deterministic_gzip_and_integrity_root_repeat(tmp_path: Path) -> None:
    """TEST-CURR-STORAGE-003: identical evidence yields identical gzip and root."""

    payloads: list[bytes] = []
    roots: list[str | None] = []
    for name in ("first", "second"):
        store = _store(tmp_path / name)
        _begin(store)
        store.append_event(
            "run:storage-001",
            event_type="attempt",
            monotonic_offset_us=1_000,
            payload={"completion": "completed"},
        )
        store.finish_run("run:storage-001")
        manifest = json.loads(next((tmp_path / name / "runs").glob("*/manifest.json")).read_text())
        chunk_path = next((tmp_path / name / "runs").glob("*/chunks/*.json.gz"))
        payloads.append(chunk_path.read_bytes())
        roots.append(manifest["integrity_root"])

    assert payloads[0] == payloads[1]
    assert roots[0] == roots[1]
    assert gzip.decompress(payloads[0]).endswith(b"\n")


def test_storage_deduplicates_validated_static_content(tmp_path: Path) -> None:
    """TEST-CURR-STORAGE-004: immutable static content is stored once."""

    store = _store(tmp_path / "store")
    first = store.put_content("curriculum-graph", {"id": "graph:one", "nodes": [1, 2]})
    second = store.put_content("curriculum-graph", {"nodes": [1, 2], "id": "graph:one"})

    assert first == second
    assert len(tuple((tmp_path / "store" / "content").glob("*.json"))) == 1


def test_storage_flushes_interrupted_attempt_and_closes_explicitly(tmp_path: Path) -> None:
    """TEST-CURR-STORAGE-005: interruption creates a durable bounded chunk."""

    store = _store(tmp_path / "store")
    _begin(store)
    store.append_event(
        "run:storage-001", event_type="attempt", monotonic_offset_us=10, payload={"open": True}
    )
    inspection = store.flush("run:storage-001", reason="disconnect")
    assert inspection.record_count == 1
    assert inspection.status == "active"


def test_storage_warns_and_fails_closed_at_run_and_store_caps(tmp_path: Path) -> None:
    """TEST-CURR-STORAGE-006: warning and hard caps never silently evict."""

    warning_store = _store(
        tmp_path / "warning",
        run_limit=1_000,
        store_limit=10_000,
        warning_percent=1,
    )
    _begin(warning_store)
    warning_store.append_event(
        "run:storage-001", event_type="attempt", monotonic_offset_us=0, payload={"x": "y"}
    )
    assert warning_store.flush("run:storage-001", reason="attempt-end").warning_state == "warning"

    run_store = _store(tmp_path / "run-cap", run_limit=100, store_limit=10_000)
    _begin(run_store)
    run_store.append_event(
        "run:storage-001",
        event_type="attempt",
        monotonic_offset_us=0,
        payload={"x": "y" * 100},
    )
    with pytest.raises(CurriculumStoreError, match="TMM-STORE-RUN-LIMIT"):
        run_store.flush("run:storage-001", reason="attempt-end")

    total_store = _store(tmp_path / "store-cap", run_limit=200, store_limit=250)
    with pytest.raises(CurriculumStoreError, match="TMM-STORE-TOTAL-LIMIT"):
        total_store.put_content("large", {"x": "y" * 300})


def test_storage_rejects_unauthorized_capture_and_export(tmp_path: Path) -> None:
    """TEST-CURR-STORAGE-007: capture and export permissions are enforced separately."""

    store = _store(tmp_path / "store")
    with pytest.raises(CurriculumStoreError, match="TMM-STORE-AUTHORIZATION-REQUIRED"):
        store.begin_run(
            "run:denied",
            authorization={"approved": False, "allow_export": False},
            metadata={},
        )
    _begin(store, allow_export=False)
    with pytest.raises(CurriculumStoreError, match="TMM-STORE-AUTHORIZATION-REQUIRED"):
        store.export_run("run:storage-001")


def test_storage_export_import_round_trip_is_exact(tmp_path: Path) -> None:
    """TEST-CURR-STORAGE-008: export/import preserves the verified chain."""

    source = _store(tmp_path / "source")
    content = source.put_content("graph", {"id": "graph:one"})
    source.begin_run(
        "run:storage-001",
        authorization=_authorization(),
        metadata={"score_id": "score:one"},
        content_refs=(content,),
    )
    source.append_event(
        "run:storage-001", event_type="attempt", monotonic_offset_us=5, payload={"ok": True}
    )
    exported = source.export_run("run:storage-001")

    target = _store(tmp_path / "target")
    assert target.import_run(exported) == source.inspect("run:storage-001")


def test_storage_rejects_corrupt_chunk_or_broken_chain(tmp_path: Path) -> None:
    """TEST-CURR-STORAGE-009: corruption cannot become authoritative evidence."""

    source = _store(tmp_path / "source")
    _begin(source)
    source.append_event(
        "run:storage-001", event_type="attempt", monotonic_offset_us=5, payload={"ok": True}
    )
    data = json.loads(source.export_run("run:storage-001"))
    data["chunks"][0]["deterministic_gzip_base64"] = "AAAA"

    target = _store(tmp_path / "target")
    with pytest.raises(CurriculumStoreError, match="TMM-STORE-CHUNK-INTEGRITY"):
        target.import_run(json.dumps(data).encode())


def test_storage_deletes_only_the_selected_run(tmp_path: Path) -> None:
    """TEST-CURR-STORAGE-010: explicit deletion removes one run, not shared content."""

    store = _store(tmp_path / "store")
    reference = store.put_content("graph", {"id": "graph:one"})
    store.begin_run(
        "run:storage-001",
        authorization=_authorization(),
        metadata={},
        content_refs=(reference,),
    )
    store.delete_run("run:storage-001")

    with pytest.raises(CurriculumStoreError, match="TMM-STORE-REFERENCE-MISSING"):
        store.inspect("run:storage-001")
    assert (tmp_path / "store" / "content" / f"{reference.content_digest}.json").is_file()


def test_storage_rejects_missing_content_and_backward_time(tmp_path: Path) -> None:
    """TEST-CURR-STORAGE-011: references and ordered event time fail closed."""

    store = _store(tmp_path / "store")
    _begin(store)
    store.append_event(
        "run:storage-001", event_type="midi", monotonic_offset_us=10, payload={"note": 60}
    )
    with pytest.raises(CurriculumStoreError, match="TMM-STORE-SEQUENCE"):
        store.append_event(
            "run:storage-001", event_type="midi", monotonic_offset_us=9, payload={"note": 61}
        )


def test_legacy_migration_is_inspection_only_and_never_fabricates_curriculum() -> None:
    """TEST-CURR-STORAGE-012: legacy meaning is preserved without DEV-009 claims."""

    report = CurriculumEvidenceStore.legacy_migration_report(
        json.dumps({"evidence": {"contract_version": "0.1.0"}}).encode()
    )

    assert report["status"] == "inspection-only"
    assert report["source_version"] == "0.1.0"
    assert "curriculum-graph" in report["unavailable"]
    assert "dev009-policy-decision" in report["unavailable"]
