"""Durable, content-addressed local evidence storage for DEV-009."""

from __future__ import annotations

import base64
import gzip
import hashlib
import json
import os
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any

CURRICULUM_STORE_VERSION = "0.2.0"
CURRICULUM_STORE_EXPORT_VERSION = "0.1.0"


class CurriculumStoreError(ValueError):
    """Stable fail-closed storage-boundary error."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(f"{code}: {message}")


@dataclass(frozen=True, slots=True)
class CurriculumStoragePolicy:
    """Frozen local limits from ADR-0011."""

    message_limit: int = 256
    byte_limit: int = 64 * 1024
    time_limit_us: int = 2_000_000
    buffer_limit: int = 512 * 1024
    run_limit: int = 64 * 1024 * 1024
    store_limit: int = 512 * 1024 * 1024
    warning_percent: int = 80


@dataclass(frozen=True, slots=True)
class CurriculumContentReference:
    """Validated reference to one immutable static record."""

    content_type: str
    content_digest: str
    byte_length: int


@dataclass(frozen=True, slots=True)
class CurriculumStoreInspection:
    """Compact inspection result without returning evidence payloads."""

    run_id: str
    status: str
    chunk_count: int
    record_count: int
    content_count: int
    used_bytes: int
    warning_state: str
    last_complete_sequence: int
    integrity_root: str | None


@dataclass(slots=True)
class _RunBuffer:
    records: list[dict[str, Any]]
    encoded_bytes: int = 0
    first_offset_us: int | None = None


class CurriculumEvidenceStore:
    """Persist immutable records and ordered deterministic-gzip evidence chunks."""

    def __init__(
        self,
        root: Path,
        *,
        policy: CurriculumStoragePolicy | None = None,
    ) -> None:
        self.root = root
        policy = policy if policy is not None else CurriculumStoragePolicy()
        self.policy = policy
        self._validate_policy(policy)
        self.content_root = root / "content"
        self.runs_root = root / "runs"
        self.content_root.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.runs_root.mkdir(parents=True, exist_ok=True, mode=0o700)
        os.chmod(root, 0o700)
        os.chmod(self.content_root, 0o700)
        os.chmod(self.runs_root, 0o700)
        self._buffers: dict[str, _RunBuffer] = {}

    def put_content(self, content_type: str, payload: object) -> CurriculumContentReference:
        """Store one validated immutable payload exactly once by semantic bytes."""

        if not content_type.strip():
            raise CurriculumStoreError("TMM-STORE-CONTENT-TYPE", "content type is empty")
        semantic = _canonical_bytes({"content_type": content_type, "payload": payload})
        digest = hashlib.sha256(semantic).hexdigest()
        record = {
            "schema_version": CURRICULUM_STORE_VERSION,
            "type": "content-addressed-record",
            "content_type": content_type,
            "content_digest": digest,
            "byte_length": len(semantic),
            "payload": payload,
        }
        encoded = _canonical_bytes(record)
        path = self.content_root / f"{digest}.json"
        if path.exists():
            if path.read_bytes() != encoded:
                raise CurriculumStoreError(
                    "TMM-STORE-CONTENT-COLLISION",
                    "an existing digest has different validated bytes",
                )
        else:
            self._require_store_capacity(len(encoded))
            _atomic_write(path, encoded)
        return CurriculumContentReference(content_type, digest, len(semantic))

    def begin_run(
        self,
        run_id: str,
        *,
        authorization: dict[str, object],
        metadata: dict[str, object],
        content_refs: tuple[CurriculumContentReference, ...] = (),
    ) -> CurriculumStoreInspection:
        """Create one authorized local run manifest without score bytes."""

        if not run_id.strip() or "/" in run_id or ".." in run_id:
            raise CurriculumStoreError("TMM-STORE-RUN-ID", "run identity is unsafe")
        if authorization.get("approved") is not True:
            raise CurriculumStoreError(
                "TMM-STORE-AUTHORIZATION-REQUIRED",
                "local evidence capture was not approved",
            )
        run_root = self._run_root(run_id)
        if run_root.exists():
            manifest = self._read_manifest(run_id)
            requested = {
                "authorization": authorization,
                "metadata": metadata,
                "content_refs": [_content_ref_data(item) for item in content_refs],
            }
            existing = {key: manifest[key] for key in requested}
            if existing != requested:
                raise CurriculumStoreError(
                    "TMM-STORE-RUN-CONFLICT",
                    "the run identity is already bound to different inputs",
                )
            return self.inspect(run_id)
        for reference in content_refs:
            self._require_content(reference)
        run_root.mkdir(parents=True, mode=0o700)
        (run_root / "chunks").mkdir(mode=0o700)
        os.chmod(run_root, 0o700)
        os.chmod(run_root / "chunks", 0o700)
        manifest = {
            "schema_version": CURRICULUM_STORE_VERSION,
            "type": "teaching-run-manifest",
            "run_id": run_id,
            "authorization": authorization,
            "metadata": metadata,
            "content_refs": [_content_ref_data(item) for item in content_refs],
            "chunk_refs": [],
            "status": "active",
            "record_count": 0,
            "used_bytes": 0,
            "warning_state": "normal",
            "last_complete_sequence": -1,
            "integrity_root": None,
        }
        self._write_manifest(run_id, manifest)
        self._buffers[run_id] = _RunBuffer([])
        return self.inspect(run_id)

    def attach_content(
        self,
        run_id: str,
        reference: CurriculumContentReference,
    ) -> CurriculumStoreInspection:
        """Attach one existing immutable record to an active run once."""

        self._require_content(reference)
        manifest = self._read_manifest(run_id)
        self._require_active(manifest)
        encoded = _content_ref_data(reference)
        if encoded not in manifest["content_refs"]:
            manifest["content_refs"].append(encoded)
            manifest["content_refs"].sort(
                key=lambda item: (item["content_type"], item["content_digest"])
            )
            self._write_manifest(run_id, manifest)
        return self.inspect(run_id)

    def append_event(
        self,
        run_id: str,
        *,
        event_type: str,
        monotonic_offset_us: int,
        payload: object | None = None,
        payload_ref: CurriculumContentReference | None = None,
        supersedes_id: str | None = None,
    ) -> CurriculumStoreInspection:
        """Append one ordered event and flush at the first frozen threshold."""

        if (payload is None) == (payload_ref is None):
            raise CurriculumStoreError(
                "TMM-STORE-RECORD-PAYLOAD",
                "exactly one inline payload or payload reference is required",
            )
        if monotonic_offset_us < 0 or not event_type.strip():
            raise CurriculumStoreError("TMM-STORE-RECORD", "event metadata is invalid")
        manifest = self._read_manifest(run_id)
        self._require_active(manifest)
        if payload_ref is not None:
            self._require_content(payload_ref)
        buffer = self._buffers.setdefault(run_id, _RunBuffer([]))
        last_offset = (
            buffer.records[-1]["monotonic_offset_us"]
            if buffer.records
            else self._last_offset(run_id, manifest)
        )
        if last_offset is not None and monotonic_offset_us < last_offset:
            raise CurriculumStoreError(
                "TMM-STORE-SEQUENCE",
                "monotonic offsets may not move backward",
            )
        event_sequence = int(manifest["record_count"]) + len(buffer.records)
        record: dict[str, Any] = {
            "event_sequence": event_sequence,
            "event_type": event_type,
            "monotonic_offset_us": monotonic_offset_us,
            "supersedes_id": supersedes_id,
        }
        if payload_ref is None:
            record["payload"] = payload
            record["payload_ref"] = None
        else:
            record["payload"] = None
            record["payload_ref"] = _content_ref_data(payload_ref)
        encoded_length = len(_canonical_bytes(record))
        if encoded_length > self.policy.buffer_limit:
            raise CurriculumStoreError(
                "TMM-STORE-BUFFER-LIMIT",
                "one evidence record exceeds the capture buffer",
            )
        if buffer.encoded_bytes + encoded_length > self.policy.buffer_limit:
            self.flush(run_id, reason="byte-limit")
            buffer = self._buffers[run_id]
        if buffer.first_offset_us is None:
            buffer.first_offset_us = monotonic_offset_us
        buffer.records.append(record)
        buffer.encoded_bytes += encoded_length
        reason: str | None = None
        if len(buffer.records) >= self.policy.message_limit:
            reason = "message-limit"
        elif buffer.encoded_bytes >= self.policy.byte_limit:
            reason = "byte-limit"
        elif monotonic_offset_us - buffer.first_offset_us >= self.policy.time_limit_us:
            reason = "time-limit"
        if reason is not None:
            self.flush(run_id, reason=reason)
        return self.inspect(run_id)

    def flush(self, run_id: str, *, reason: str) -> CurriculumStoreInspection:
        """Atomically append one independently verifiable deterministic-gzip chunk."""

        if reason not in {
            "attempt-end",
            "pause",
            "disconnect",
            "background",
            "message-limit",
            "byte-limit",
            "time-limit",
        }:
            raise CurriculumStoreError("TMM-STORE-FLUSH-REASON", "flush reason is unknown")
        manifest = self._read_manifest(run_id)
        self._require_active(manifest)
        buffer = self._buffers.setdefault(run_id, _RunBuffer([]))
        if not buffer.records:
            return self.inspect(run_id)
        sequence = len(manifest["chunk_refs"])
        previous = manifest["integrity_root"]
        chunk_without_digest = {
            "schema_version": CURRICULUM_STORE_VERSION,
            "type": "evidence-chunk",
            "store_id": self._store_id(),
            "run_id": run_id,
            "chunk_sequence": sequence,
            "previous_chunk_digest": previous,
            "first_event_sequence": buffer.records[0]["event_sequence"],
            "last_event_sequence": buffer.records[-1]["event_sequence"],
            "monotonic_start_us": buffer.records[0]["monotonic_offset_us"],
            "monotonic_end_us": buffer.records[-1]["monotonic_offset_us"],
            "flush_reason": reason,
            "uncompressed_bytes": buffer.encoded_bytes,
            "record_count": len(buffer.records),
            "records": buffer.records,
            "resolution": "resolved",
        }
        digest = hashlib.sha256(_canonical_bytes(chunk_without_digest)).hexdigest()
        chunk = {**chunk_without_digest, "chunk_digest": digest}
        encoded = _canonical_bytes(chunk)
        compressed = gzip.compress(encoded, compresslevel=9, mtime=0)
        prospective_run_bytes = int(manifest["used_bytes"]) + len(compressed)
        if prospective_run_bytes > self.policy.run_limit:
            raise CurriculumStoreError("TMM-STORE-RUN-LIMIT", "run storage limit reached")
        self._require_store_capacity(len(compressed))
        chunk_path = self._run_root(run_id) / "chunks" / f"{sequence:08d}-{digest}.json.gz"
        try:
            _atomic_write(chunk_path, compressed)
        except OSError as error:
            raise CurriculumStoreError("TMM-STORE-FLUSH-FAILED", "chunk write failed") from error
        manifest["chunk_refs"].append(
            {
                "chunk_sequence": sequence,
                "chunk_digest": digest,
                "byte_length": len(compressed),
                "file": chunk_path.name,
            }
        )
        manifest["record_count"] = int(manifest["record_count"]) + len(buffer.records)
        manifest["used_bytes"] = prospective_run_bytes
        manifest["last_complete_sequence"] = buffer.records[-1]["event_sequence"]
        manifest["integrity_root"] = digest
        manifest["warning_state"] = self._warning_state(prospective_run_bytes)
        self._write_manifest(run_id, manifest)
        self._buffers[run_id] = _RunBuffer([])
        return self.inspect(run_id)

    def finish_run(self, run_id: str) -> CurriculumStoreInspection:
        """Flush an attempt boundary and close the run against new evidence."""

        self.flush(run_id, reason="attempt-end")
        manifest = self._read_manifest(run_id)
        manifest["status"] = "complete"
        self._write_manifest(run_id, manifest)
        return self.inspect(run_id)

    def export_run(self, run_id: str) -> bytes:
        """Export one complete integrity-checked run only when authorized."""

        self.flush(run_id, reason="attempt-end")
        manifest = self._read_manifest(run_id)
        if manifest["authorization"].get("allow_export") is not True:
            raise CurriculumStoreError(
                "TMM-STORE-AUTHORIZATION-REQUIRED",
                "run export was not authorized",
            )
        self._verify_run(manifest)
        content = [
            json.loads((self.content_root / f"{item['content_digest']}.json").read_text())
            for item in manifest["content_refs"]
        ]
        chunks = [
            {
                "chunk_digest": item["chunk_digest"],
                "deterministic_gzip_base64": base64.b64encode(
                    (self._run_root(run_id) / "chunks" / item["file"]).read_bytes()
                ).decode("ascii"),
            }
            for item in manifest["chunk_refs"]
        ]
        return _canonical_bytes(
            {
                "schema_version": CURRICULUM_STORE_EXPORT_VERSION,
                "type": "curriculum-evidence-store-export",
                "manifest": manifest,
                "content": content,
                "chunks": chunks,
            }
        )

    def import_run(self, payload: bytes) -> CurriculumStoreInspection:
        """Verify and import one exact export without mutating existing evidence."""

        try:
            data = json.loads(payload)
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise CurriculumStoreError("TMM-STORE-CHUNK-INTEGRITY", "export is invalid") from error
        if (
            not isinstance(data, dict)
            or set(data) != {"schema_version", "type", "manifest", "content", "chunks"}
            or data["schema_version"] != CURRICULUM_STORE_EXPORT_VERSION
            or data["type"] != "curriculum-evidence-store-export"
            or not isinstance(data["manifest"], dict)
            or not isinstance(data["content"], list)
            or not isinstance(data["chunks"], list)
        ):
            raise CurriculumStoreError("TMM-STORE-CHUNK-INTEGRITY", "export shape is invalid")
        manifest = data["manifest"]
        run_id = manifest.get("run_id")
        if not isinstance(run_id, str):
            raise CurriculumStoreError("TMM-STORE-CHUNK-INTEGRITY", "run identity is invalid")
        run_root = self._run_root(run_id)
        if run_root.exists():
            raise CurriculumStoreError("TMM-STORE-RUN-CONFLICT", "run already exists")
        for record in data["content"]:
            if not isinstance(record, dict):
                raise CurriculumStoreError("TMM-STORE-CONTENT-COLLISION", "content is invalid")
            reference = self.put_content(record.get("content_type", ""), record.get("payload"))
            if reference.content_digest != record.get(
                "content_digest"
            ) or reference.byte_length != record.get("byte_length"):
                raise CurriculumStoreError(
                    "TMM-STORE-CONTENT-COLLISION",
                    "content digest or byte length differs",
                )
        run_root.mkdir(parents=True, mode=0o700)
        (run_root / "chunks").mkdir(mode=0o700)
        try:
            for encoded_chunk, expected_ref in zip(
                data["chunks"], manifest.get("chunk_refs", []), strict=True
            ):
                compressed = base64.b64decode(
                    encoded_chunk["deterministic_gzip_base64"], validate=True
                )
                if encoded_chunk["chunk_digest"] != expected_ref["chunk_digest"]:
                    raise CurriculumStoreError(
                        "TMM-STORE-CHUNK-INTEGRITY", "chunk reference differs"
                    )
                _atomic_write(run_root / "chunks" / expected_ref["file"], compressed)
            self._write_manifest(run_id, manifest)
            self._verify_run(manifest)
        except (KeyError, ValueError, OSError, gzip.BadGzipFile) as error:
            shutil.rmtree(run_root, ignore_errors=True)
            if isinstance(error, CurriculumStoreError):
                raise
            raise CurriculumStoreError(
                "TMM-STORE-CHUNK-INTEGRITY", "export integrity verification failed"
            ) from error
        self._buffers[run_id] = _RunBuffer([])
        return self.inspect(run_id)

    def delete_run(self, run_id: str) -> None:
        """Delete exactly one owner-selected run; shared immutable content remains."""

        run_root = self._run_root(run_id)
        if not run_root.exists():
            raise CurriculumStoreError("TMM-STORE-REFERENCE-MISSING", "run is absent")
        shutil.rmtree(run_root)
        self._buffers.pop(run_id, None)

    def inspect(self, run_id: str) -> CurriculumStoreInspection:
        """Verify and summarize one run without exposing stored payloads."""

        manifest = self._read_manifest(run_id)
        self._verify_run(manifest)
        return CurriculumStoreInspection(
            run_id=run_id,
            status=str(manifest["status"]),
            chunk_count=len(manifest["chunk_refs"]),
            record_count=int(manifest["record_count"]),
            content_count=len(manifest["content_refs"]),
            used_bytes=int(manifest["used_bytes"]),
            warning_state=str(manifest["warning_state"]),
            last_complete_sequence=int(manifest["last_complete_sequence"]),
            integrity_root=manifest["integrity_root"],
        )

    @staticmethod
    def legacy_migration_report(payload: bytes) -> dict[str, object]:
        """Inspect a historical archive without fabricating DEV-009 semantics."""

        digest = hashlib.sha256(payload).hexdigest()
        try:
            source = json.loads(payload)
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise CurriculumStoreError("TMM-MIGRATION-LOSSY", "legacy JSON is invalid") from error
        if not isinstance(source, dict) or "evidence" not in source:
            raise CurriculumStoreError("TMM-MIGRATION-NOT-FOUND", "legacy archive is unknown")
        return {
            "migration_id": "MIGRATION-EVIDENCE-0.1.0-TO-0.2.0-INSPECTION-ONLY",
            "source_digest": digest,
            "source_version": "0.1.0",
            "target_version": CURRICULUM_STORE_VERSION,
            "preserved": ["original-bytes", "source-digest", "historical-evidence"],
            "defaulted": [],
            "unavailable": [
                "practice-scope",
                "curriculum-graph",
                "learner-projection",
                "retention",
                "transfer",
                "dev009-policy-decision",
            ],
            "status": "inspection-only",
        }

    def _run_root(self, run_id: str) -> Path:
        return self.runs_root / hashlib.sha256(run_id.encode("utf-8")).hexdigest()

    def _read_manifest(self, run_id: str) -> dict[str, Any]:
        path = self._run_root(run_id) / "manifest.json"
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise CurriculumStoreError("TMM-STORE-REFERENCE-MISSING", "run is absent") from error
        if not isinstance(value, dict) or value.get("run_id") != run_id:
            raise CurriculumStoreError("TMM-STORE-CHUNK-INTEGRITY", "manifest is invalid")
        return value

    def _write_manifest(self, run_id: str, manifest: dict[str, Any]) -> None:
        _atomic_write(self._run_root(run_id) / "manifest.json", _canonical_bytes(manifest))

    def _require_content(self, reference: CurriculumContentReference) -> None:
        path = self.content_root / f"{reference.content_digest}.json"
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise CurriculumStoreError(
                "TMM-STORE-REFERENCE-MISSING", "content reference is absent"
            ) from error
        if (
            record.get("content_type") != reference.content_type
            or record.get("content_digest") != reference.content_digest
            or record.get("byte_length") != reference.byte_length
        ):
            raise CurriculumStoreError("TMM-STORE-CONTENT-COLLISION", "content reference differs")

    def _verify_run(self, manifest: dict[str, Any]) -> None:
        previous: str | None = None
        record_count = 0
        last_sequence = -1
        for expected_sequence, reference in enumerate(manifest.get("chunk_refs", [])):
            path = self._run_root(manifest["run_id"]) / "chunks" / reference["file"]
            try:
                encoded = gzip.decompress(path.read_bytes())
                chunk = json.loads(encoded)
            except (OSError, gzip.BadGzipFile, json.JSONDecodeError) as error:
                raise CurriculumStoreError(
                    "TMM-STORE-CHUNK-INTEGRITY", "chunk is unreadable"
                ) from error
            supplied_digest = chunk.pop("chunk_digest", None)
            expected_digest = hashlib.sha256(_canonical_bytes(chunk)).hexdigest()
            if (
                chunk.get("chunk_sequence") != expected_sequence
                or chunk.get("previous_chunk_digest") != previous
                or supplied_digest != expected_digest
                or reference.get("chunk_digest") != expected_digest
            ):
                raise CurriculumStoreError(
                    "TMM-STORE-CHUNK-INTEGRITY", "chunk hash chain is invalid"
                )
            records = chunk.get("records")
            if not isinstance(records, list):
                raise CurriculumStoreError("TMM-STORE-CHUNK-INTEGRITY", "chunk records are invalid")
            expected_event_sequences = list(range(record_count, record_count + len(records)))
            if [item.get("event_sequence") for item in records] != expected_event_sequences:
                raise CurriculumStoreError(
                    "TMM-STORE-CHUNK-INTEGRITY", "event sequence is discontinuous"
                )
            record_count += len(records)
            last_sequence = records[-1]["event_sequence"] if records else last_sequence
            previous = expected_digest
        if (
            record_count != manifest.get("record_count")
            or last_sequence != manifest.get("last_complete_sequence")
            or previous != manifest.get("integrity_root")
        ):
            raise CurriculumStoreError(
                "TMM-STORE-CHUNK-INTEGRITY", "manifest totals differ from the chain"
            )
        for reference in manifest.get("content_refs", []):
            self._require_content(
                CurriculumContentReference(
                    reference["content_type"],
                    reference["content_digest"],
                    reference["byte_length"],
                )
            )

    def _last_offset(self, run_id: str, manifest: dict[str, Any]) -> int | None:
        if not manifest["chunk_refs"]:
            return None
        reference = manifest["chunk_refs"][-1]
        chunk = json.loads(
            gzip.decompress((self._run_root(run_id) / "chunks" / reference["file"]).read_bytes())
        )
        return int(chunk["monotonic_end_us"])

    def _require_store_capacity(self, additional_bytes: int) -> None:
        if _tree_bytes(self.root) + additional_bytes > self.policy.store_limit:
            raise CurriculumStoreError("TMM-STORE-TOTAL-LIMIT", "store limit reached")

    def _warning_state(self, used_bytes: int) -> str:
        return (
            "warning"
            if used_bytes * 100 >= self.policy.run_limit * self.policy.warning_percent
            else "normal"
        )

    def _store_id(self) -> str:
        digest = hashlib.sha256(
            f"teachmemusic-local-evidence-store:{CURRICULUM_STORE_VERSION}".encode()
        ).hexdigest()
        return f"evidence-store:{digest}"

    @staticmethod
    def _require_active(manifest: dict[str, Any]) -> None:
        if manifest.get("status") != "active":
            raise CurriculumStoreError("TMM-STORE-RUN-CLOSED", "run is not active")

    @staticmethod
    def _validate_policy(policy: CurriculumStoragePolicy) -> None:
        values = (
            policy.message_limit,
            policy.byte_limit,
            policy.time_limit_us,
            policy.buffer_limit,
            policy.run_limit,
            policy.store_limit,
        )
        if any(value <= 0 for value in values) or not 1 <= policy.warning_percent <= 100:
            raise ValueError("storage policy limits must be positive and bounded")
        if policy.byte_limit > policy.buffer_limit or policy.run_limit > policy.store_limit:
            raise ValueError("storage policy limits are inconsistent")


def _content_ref_data(reference: CurriculumContentReference) -> dict[str, object]:
    return {
        "content_type": reference.content_type,
        "content_digest": reference.content_digest,
        "byte_length": reference.byte_length,
    }


def _canonical_bytes(value: object) -> bytes:
    _reject_floats(value)
    try:
        return (
            json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
        ).encode("utf-8")
    except (TypeError, ValueError) as error:
        raise CurriculumStoreError("TMM-STORE-SERIALIZATION", "value is not strict JSON") from error


def _reject_floats(value: object) -> None:
    if isinstance(value, float):
        raise CurriculumStoreError("TMM-STORE-SERIALIZATION", "floating-point values are forbidden")
    if isinstance(value, dict):
        for key, item in value.items():
            if not isinstance(key, str):
                raise CurriculumStoreError("TMM-STORE-SERIALIZATION", "object keys must be strings")
            _reject_floats(item)
    elif isinstance(value, (list, tuple)):
        for item in value:
            _reject_floats(item)


def _atomic_write(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    temporary = path.with_suffix(f"{path.suffix}.tmp")
    temporary.write_bytes(payload)
    os.chmod(temporary, 0o600)
    temporary.replace(path)
    os.chmod(path, 0o600)


def _tree_bytes(root: Path) -> int:
    return sum(path.stat().st_size for path in root.rglob("*") if path.is_file())
