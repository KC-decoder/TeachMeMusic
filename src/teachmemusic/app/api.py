"""FastAPI edge for bounded canonical score ingestion and projection."""

from __future__ import annotations

import hashlib
import hmac
import json
import tempfile
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from fractions import Fraction
from pathlib import Path, PurePath
from threading import BoundedSemaphore
from typing import Annotated, Any, Literal
from urllib.parse import urlsplit

from fastapi import FastAPI, Header, Request
from fastapi.responses import JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field
from starlette.datastructures import UploadFile

from teachmemusic._contract_codec import ContractCodecError, contract_to_data
from teachmemusic.analysis import AnalysisError, analyze_canonical_score
from teachmemusic.performance import (
    AttemptCompletion,
    CalibrationProfile,
    LearnerAttempt,
    MidiEventKind,
    NormalizedMidiEvent,
    RawMidiMessage,
)
from teachmemusic.score import (
    CanonicalMusicPackage,
    CanonicalScoreContent,
    ScoreDocument,
    parse_musicxml_package,
)
from teachmemusic.teaching import (
    DataAuthorization,
    EvidenceExport,
    ExercisePresentationError,
    LearnerContextSnapshot,
    LearnerTrack,
    LessonPlan,
    PlanAudit,
    PlanAuditOutcome,
    PlannerError,
    build_exercise_presentation,
    evidence_archive_from_json,
    evidence_archive_to_json,
    exercise_presentation_to_dict,
    generate_beginner_lesson_plan,
    lesson_plan_to_dict,
)
from teachmemusic.viewer import (
    PLAYBACK_CONTRACT_VERSION,
    VIEWER_CONTRACT_VERSION,
    NotationProjectionError,
    PlaybackProjectionError,
    build_notation_bundle,
    build_playback_plan,
    playback_plan_to_dict,
    viewer_bundle_to_dict,
)

from .budgets import DEFAULT_APP_BUDGETS, AppBudgets
from .curriculum_runs import (
    CurriculumAttemptCycle,
    CurriculumDeliveryPlan,
    CurriculumRunStore,
    CurriculumRunStoreError,
    CurriculumStageProjection,
    assemble_curriculum_delivery,
    curriculum_plan_to_dict,
    curriculum_presentation_to_dict,
    default_curriculum_store,
    project_curriculum_stage,
)
from .mobile_bridge import BridgeMessage, MobileBridgeError, MobileBridgeStore, MobileCommand
from .sessions import SessionStore, SessionStoreError
from .teaching_runs import TeachingRunStore, TeachingRunStoreError

APP_CONTRACT_VERSION = "0.3.0"
_SUPPORTED_SUFFIXES = frozenset({".xml", ".musicxml", ".mxl"})
_MOBILE_RESULT_FORBIDDEN_KEYS = frozenset(
    {"raw_messages", "normalized_events", "calibration", "score_bytes", "launch_token"}
)


class BundleRequest(BaseModel):
    """Caller-controlled policies required for deterministic projection."""

    model_config = ConfigDict(extra="forbid")

    score_id: str
    fallback_tempo_qpm: str | int | None = None
    grace_fallback_percent: str | int | None = None
    navigation_section_starts: list[int] | None = None


class TeachingPlanRequest(BaseModel):
    """Select the score used by the approved Beginner planner."""

    model_config = ConfigDict(extra="forbid")

    score_id: str


class ExercisePresentationRequest(BaseModel):
    """Reversible learner-controlled presentation aids for one exercise."""

    model_config = ConfigDict(extra="forbid")

    score_id: str
    tempo_bpm: str | int | None = None
    count_in_enabled: bool = True


class TeachingRunRequest(BaseModel):
    """Explicit owner authorization and untouched-plan audit."""

    model_config = ConfigDict(extra="forbid")

    score_id: str
    plan_id: str
    authorization_approved: bool
    capture_midi: bool
    capture_self_report: bool = True
    allow_export: bool
    audit_outcome: Literal["pass-no-change"]
    source_faithful: bool
    musically_coherent: bool
    safe: bool
    executable: bool
    reviewer: str = Field(min_length=1, max_length=120)


class CalibrationInput(BaseModel):
    """Strict browser calibration evidence admitted to the pure boundary."""

    model_config = ConfigDict(extra="forbid")

    version: str
    device_id: str
    input_name: str
    timestamp_origin: str
    pitch_numbering_confirmed: bool
    sustain_available: bool | None
    clock_offset_microseconds: int | None
    clock_jitter_microseconds: int | None
    timing_window_microseconds: int | None
    chord_window_microseconds: int | None
    limitations: list[str] = Field(default_factory=list)
    approved: bool
    approved_at_utc: str | None


class RawMidiInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    sequence_number: int
    timestamp_microseconds: int
    data: list[int]


class NormalizedMidiInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    raw_message_id: str | None
    kind: Literal["note-on", "note-off", "control-change", "connection", "diagnostic"]
    timestamp_microseconds: int
    channel: int | None
    note: int | None
    velocity: int | None
    controller: int | None
    value: int | None
    detail: str | None


class AttemptSubmissionRequest(BaseModel):
    """One complete browser capture submitted for authoritative reconstruction."""

    model_config = ConfigDict(extra="forbid")

    score_id: str
    plan_id: str
    exercise_id: str
    practice_mode: str
    support_state_id: str
    tempo_bpm: str | int | None = None
    count_in_enabled: bool = True
    started_at_utc: str
    start_microseconds: int
    end_microseconds: int
    completion: Literal["completed", "interrupted", "cancelled", "input-failure", "safe-stop"]
    calibration: CalibrationInput
    raw_messages: list[RawMidiInput]
    normalized_events: list[NormalizedMidiInput]
    diagnostics: list[str] = Field(default_factory=list)
    unsafe_condition: str | None = None


class EvidenceImportRequest(BaseModel):
    """One owner-selected local archive reattached to an exact score session."""

    model_config = ConfigDict(extra="forbid")

    score_id: str
    archive: dict[str, Any]


class MobilePairingRequest(BaseModel):
    """Owner-selected lifetime for one explicit local-network pairing."""

    model_config = ConfigDict(extra="forbid")

    ttl_seconds: int = Field(ge=30, le=10 * 60)


class MobileBridgeClaimRequest(BaseModel):
    """One-time capability consumed by the desktop MIDI bridge role."""

    model_config = ConfigDict(extra="forbid")

    capability: str = Field(min_length=32, max_length=256)


class MobileBridgeMessageInput(BaseModel):
    """Sanitized transient bridge message; raw MIDI is not admitted here."""

    model_config = ConfigDict(extra="forbid")

    contract_version: Literal["0.2.0"]
    kind: Literal["midi-state"]
    sequence: int = Field(ge=1, le=9_007_199_254_740_991)
    sent_at_microseconds: int = Field(ge=0)
    connection: Literal["connected", "disconnected", "unavailable"]
    active_notes: list[int] = Field(max_length=16)
    capture: Literal["idle", "recording", "paused", "stopped", "aborted"]
    capture_purpose: Literal["calibration", "attempt"] | None
    calibration_approved: bool


class MobileCommandAckInput(BaseModel):
    """Desktop acknowledgement carrying no raw MIDI or locally derived grading."""

    model_config = ConfigDict(extra="forbid")

    mobile_contract_version: Literal["0.2.0"]
    sequence: int = Field(ge=1, le=9_007_199_254_740_991)
    result: dict[str, Any] | None = None
    error: str | None = Field(default=None, min_length=1, max_length=1_000)


def create_app(
    *,
    launch_token: str,
    budgets: AppBudgets = DEFAULT_APP_BUDGETS,
    store: SessionStore | None = None,
    teaching_store: TeachingRunStore | None = None,
    curriculum_store: CurriculumRunStore | None = None,
    static_directory: Path | None = None,
    mobile_bridge: MobileBridgeStore | None = None,
    mobile_companion_origin: str | None = None,
) -> FastAPI:
    """Create one same-origin, token-protected local application."""

    if not launch_token:
        raise ValueError("launch_token must not be empty")
    if (mobile_bridge is None) != (mobile_companion_origin is None):
        raise ValueError("mobile bridge and companion origin must be configured together")
    sessions = (
        store
        if store is not None
        else SessionStore(
            max_sessions=budgets.max_sessions,
            ttl_seconds=budgets.session_ttl_seconds,
        )
    )
    teaching_runs = (
        teaching_store
        if teaching_store is not None
        else TeachingRunStore(max_runs=budgets.max_sessions)
    )
    curriculum_temporary_directory: tempfile.TemporaryDirectory[str] | None = None
    if curriculum_store is None:
        curriculum_temporary_directory = tempfile.TemporaryDirectory(
            prefix="teachmemusic-curriculum-"
        )
        curriculum_runs = default_curriculum_store(curriculum_temporary_directory.name)
    else:
        curriculum_runs = curriculum_store
    projection_slot = BoundedSemaphore(1)

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        yield
        sessions.clear()
        teaching_runs.clear()
        curriculum_runs.clear()
        if curriculum_temporary_directory is not None:
            curriculum_temporary_directory.cleanup()
        if mobile_bridge is not None:
            mobile_bridge.clear()

    app = FastAPI(title="TeachMeMusic", version="0.0.0", lifespan=lifespan)
    app.state.session_store = sessions
    app.state.teaching_run_store = teaching_runs
    app.state.curriculum_run_store = curriculum_runs
    app.state.mobile_bridge_store = mobile_bridge

    @app.get("/api/v1/health")
    async def health() -> dict[str, object]:
        return {
            "status": "ok",
            "app_contract_version": APP_CONTRACT_VERSION,
            "viewer_contract_version": VIEWER_CONTRACT_VERSION,
            "playback_contract_version": PLAYBACK_CONTRACT_VERSION,
        }

    @app.get("/api/v1/config")
    async def config() -> dict[str, object]:
        return {
            "app_contract_version": APP_CONTRACT_VERSION,
            "launch_token": launch_token,
            "accepted_extensions": sorted(_SUPPORTED_SUFFIXES),
            "max_upload_bytes": budgets.max_upload_bytes,
        }

    @app.post("/api/v1/viewer-sessions")
    async def upload_score(
        request: Request,
        token: Annotated[str | None, Header(alias="X-TeachMeMusic-Token")] = None,
    ) -> JSONResponse:
        rejected = _authorize(request, token, launch_token)
        if rejected is not None:
            return rejected
        too_large = _reject_content_length(request, budgets.max_request_bytes)
        if too_large is not None:
            return too_large
        try:
            form = await request.form(
                max_files=1,
                max_fields=0,
                max_part_size=budgets.max_request_bytes,
            )
        except Exception:
            return _error(400, "APP_MULTIPART_INVALID", "The upload form is invalid.")
        upload = form.get("score")
        if not isinstance(upload, UploadFile):
            return _error(400, "APP_SCORE_REQUIRED", "One score file is required.")
        filename = str(getattr(upload, "filename", "") or "")
        filename_error = _validate_filename(filename, budgets.max_filename_bytes)
        if filename_error is not None:
            return filename_error
        payload = await _read_bounded(upload, budgets.max_upload_bytes)
        await upload.close()
        if payload is None:
            return _error(413, "APP_UPLOAD_TOO_LARGE", "The score exceeds the upload limit.")
        try:
            package = parse_musicxml_package(payload, logical_name=filename)
        except (ValueError, TypeError):
            return _error(
                422,
                "APP_SCORE_INGESTION_REJECTED",
                "The file is not a supported, valid MusicXML score.",
            )
        score_documents = _score_documents(package)
        if not score_documents:
            return _error(422, "APP_NO_SCORE_DOCUMENT", "The package contains no score.")
        if len(score_documents) > budgets.max_score_documents:
            return _error(
                413,
                "APP_SCORE_DOCUMENT_LIMIT",
                "The package contains too many score documents.",
            )
        try:
            session = sessions.create(package)
        except SessionStoreError as error:
            status = 429 if error.code == "APP_SESSION_CAPACITY" else 500
            return _error(status, error.code, "No additional score session is available.")
        return JSONResponse(
            {
                "session_id": session.id,
                "package_id": package.id.value,
                "expires_in_seconds": budgets.session_ttl_seconds,
                "scores": [_score_manifest(document) for document in score_documents],
                "diagnostics": [],
            },
            status_code=201,
        )

    @app.post("/api/v1/viewer-sessions/{session_id}/bundles")
    async def project_bundle(
        session_id: str,
        body: BundleRequest,
        request: Request,
        token: Annotated[str | None, Header(alias="X-TeachMeMusic-Token")] = None,
    ) -> Response:
        rejected = _authorize(request, token, launch_token)
        if rejected is not None:
            return rejected
        if body.navigation_section_starts is not None and (
            len(body.navigation_section_starts) > budgets.max_navigation_sections
        ):
            return _error(413, "APP_NAVIGATION_LIMIT", "Too many navigation sections.")
        try:
            session = sessions.get(session_id)
        except SessionStoreError:
            return _error(404, "APP_SESSION_NOT_FOUND", "The score session is unavailable.")
        if not projection_slot.acquire(blocking=False):
            return _error(429, "APP_PROJECTION_BUSY", "Another score is being prepared.")
        try:
            try:
                notation = build_notation_bundle(session.package, score_id=body.score_id)
                playback = build_playback_plan(
                    session.package,
                    score_id=body.score_id,
                    fallback_tempo_qpm=_fraction(body.fallback_tempo_qpm),
                    grace_fallback_percent=_fraction(body.grace_fallback_percent),
                    navigation_section_starts=(
                        tuple(body.navigation_section_starts)
                        if body.navigation_section_starts is not None
                        else None
                    ),
                )
            except (NotationProjectionError, PlaybackProjectionError) as error:
                return _error(422, error.code, "This score output is not currently supported.")
            except (ValueError, ZeroDivisionError):
                return _error(422, "APP_PROJECTION_REJECTED", "The score output is invalid.")
            if len(notation.renderer.anchors) > budgets.max_anchors:
                return _error(413, "APP_ANCHOR_LIMIT", "The notation exceeds the anchor limit.")
            if len(playback.notes) > budgets.max_notes:
                return _error(413, "APP_NOTE_LIMIT", "The playback exceeds the note limit.")
            result = {
                "app_contract_version": APP_CONTRACT_VERSION,
                "notation": viewer_bundle_to_dict(notation),
                "playback": playback_plan_to_dict(playback),
            }
            encoded = json.dumps(result, ensure_ascii=False, separators=(",", ":")).encode()
            if len(encoded) > budgets.max_response_bytes:
                return _error(413, "APP_RESPONSE_LIMIT", "The prepared score is too large.")
            return Response(encoded, media_type="application/json")
        finally:
            projection_slot.release()

    @app.post("/api/v1/viewer-sessions/{session_id}/curriculum-plans")
    async def create_curriculum_plan(
        session_id: str,
        body: TeachingPlanRequest,
        request: Request,
        token: Annotated[str | None, Header(alias="X-TeachMeMusic-Token")] = None,
    ) -> Response:
        """Assemble the production DEV-009 deterministic curriculum."""

        rejected = _authorize(request, token, launch_token)
        if rejected is not None:
            return rejected
        try:
            session = sessions.get(session_id)
            plan = assemble_curriculum_delivery(
                session.package,
                score_id=body.score_id,
                session_id=session_id,
            )
            return _bounded_json(
                {
                    "app_contract_version": APP_CONTRACT_VERSION,
                    "plan": curriculum_plan_to_dict(plan),
                },
                budgets.max_response_bytes,
            )
        except SessionStoreError:
            return _error(404, "APP_SESSION_NOT_FOUND", "The score session is unavailable.")
        except (AnalysisError, ValueError, ContractCodecError) as error:
            code = getattr(error, "code", "APP_CURRICULUM_PLAN_REJECTED")
            return _error(422, code, "A safe deterministic curriculum could not be generated.")

    @app.post(
        "/api/v1/viewer-sessions/{session_id}/curriculum-plans/{plan_id}/exercises/{exercise_id}"
    )
    async def project_curriculum_exercise(
        session_id: str,
        plan_id: str,
        exercise_id: str,
        body: ExercisePresentationRequest,
        request: Request,
        token: Annotated[str | None, Header(alias="X-TeachMeMusic-Token")] = None,
    ) -> Response:
        """Project one exact curriculum stage for notation and demonstration."""

        rejected = _authorize(request, token, launch_token)
        if rejected is not None:
            return rejected
        if not projection_slot.acquire(blocking=False):
            return _error(429, "APP_PROJECTION_BUSY", "Another score is being prepared.")
        try:
            try:
                session = sessions.get(session_id)
                plan = assemble_curriculum_delivery(
                    session.package,
                    score_id=body.score_id,
                    session_id=session_id,
                )
                if plan.id != plan_id:
                    return _error(
                        409,
                        "APP_CURRICULUM_PLAN_CHANGED",
                        "The curriculum no longer matches this score session.",
                    )
                projection = _curriculum_projection_for_exercise(plan, exercise_id)
                return _bounded_json(
                    {
                        "app_contract_version": APP_CONTRACT_VERSION,
                        "presentation": curriculum_presentation_to_dict(plan, projection),
                    },
                    budgets.max_response_bytes,
                )
            except SessionStoreError:
                return _error(404, "APP_SESSION_NOT_FOUND", "The score session is unavailable.")
            except (AnalysisError, ValueError, ContractCodecError) as error:
                code = getattr(error, "code", "APP_CURRICULUM_EXERCISE_REJECTED")
                return _error(422, code, "This curriculum exercise cannot be projected safely.")
        finally:
            projection_slot.release()

    @app.post("/api/v1/viewer-sessions/{session_id}/curriculum-runs")
    async def create_curriculum_run(
        session_id: str,
        body: TeachingRunRequest,
        request: Request,
        token: Annotated[str | None, Header(alias="X-TeachMeMusic-Token")] = None,
    ) -> Response:
        """Start one real DEV-009 run with granular local authorization."""

        rejected = _authorize(request, token, launch_token)
        if rejected is not None:
            return rejected
        try:
            session = sessions.get(session_id)
            plan = assemble_curriculum_delivery(
                session.package,
                score_id=body.score_id,
                session_id=session_id,
            )
            if plan.id != body.plan_id:
                return _error(
                    409,
                    "APP_CURRICULUM_PLAN_CHANGED",
                    "The curriculum no longer matches this score session.",
                )
            if not (
                body.authorization_approved
                and body.capture_midi
                and body.source_faithful
                and body.musically_coherent
                and body.safe
                and body.executable
            ):
                return _error(
                    422,
                    "APP_GATE_ZERO_PRECONDITION",
                    "MIDI capture approval and the untouched-plan audit must pass before capture.",
                )
            identity = _identity_token(plan.run_id)
            inspection = curriculum_runs.create(
                plan,
                authorization={
                    "approved": True,
                    "capture_midi": True,
                    "capture_self_report": body.capture_self_report,
                    "allow_export": body.allow_export,
                },
                learner_context_id=f"learner-context:{identity}",
            )
            return _bounded_json(
                {
                    "app_contract_version": APP_CONTRACT_VERSION,
                    "run_id": plan.run_id,
                    "inspection": _curriculum_inspection_view(inspection),
                },
                budgets.max_response_bytes,
            )
        except SessionStoreError:
            return _error(404, "APP_SESSION_NOT_FOUND", "The score session is unavailable.")
        except (AnalysisError, ValueError, ContractCodecError) as error:
            code = getattr(error, "code", "APP_CURRICULUM_RUN_REJECTED")
            return _error(422, code, "The deterministic curriculum run could not be started.")

    @app.post("/api/v1/curriculum-runs/{run_id}/attempts")
    async def submit_curriculum_attempt(
        run_id: str,
        body: AttemptSubmissionRequest,
        request: Request,
        token: Annotated[str | None, Header(alias="X-TeachMeMusic-Token")] = None,
    ) -> Response:
        """Evaluate one real attempt through DEV-009 evidence and policy contracts."""

        rejected = _authorize(request, token, launch_token)
        if rejected is not None:
            return rejected
        if (
            len(body.raw_messages) > budgets.max_attempt_messages
            or len(body.normalized_events) > budgets.max_attempt_messages
        ):
            return _error(413, "APP_ATTEMPT_EVENT_LIMIT", "The attempt has too many events.")
        try:
            plan = curriculum_runs.plan(run_id)
            if plan.score_id != body.score_id or plan.id != body.plan_id:
                return _error(
                    409,
                    "APP_CURRICULUM_RUN_REFERENCE",
                    "The attempt does not match the active curriculum.",
                )
            curriculum_runs.projection(run_id, body.exercise_id)
            calibration = _calibration(run_id, body.calibration)
            inspection = curriculum_runs.inspect(run_id)
            attempt_count = inspection.get("attempt_count")
            if not isinstance(attempt_count, int):
                raise CurriculumRunStoreError(
                    "APP_CURRICULUM_INSPECTION", "attempt count is invalid"
                )
            attempt = _curriculum_attempt(
                run_id,
                body,
                calibration.id,
                attempt_count,
            )
            cycle = curriculum_runs.submit_attempt(
                run_id,
                calibration=calibration,
                attempt=attempt,
            )
            next_presentation = curriculum_presentation_to_dict(
                cycle.plan,
                cycle.projection,
            )
            return _bounded_json(
                _curriculum_cycle_view(cycle, attempt.id, next_presentation),
                budgets.max_response_bytes,
            )
        except (ValueError, CurriculumRunStoreError, ContractCodecError) as error:
            code = getattr(error, "code", "APP_CURRICULUM_ATTEMPT_REJECTED")
            return _error(422, code, "The curriculum attempt could not be evaluated safely.")

    @app.post("/api/v1/curriculum-runs/{run_id}/exercises/{exercise_id}")
    async def project_active_curriculum_exercise(
        run_id: str,
        exercise_id: str,
        body: ExercisePresentationRequest,
        request: Request,
        token: Annotated[str | None, Header(alias="X-TeachMeMusic-Token")] = None,
    ) -> Response:
        """Project only the policy-authorized active exercise of a live run."""

        rejected = _authorize(request, token, launch_token)
        if rejected is not None:
            return rejected
        try:
            plan = curriculum_runs.plan(run_id)
            if plan.score_id != body.score_id:
                return _error(
                    409,
                    "APP_CURRICULUM_RUN_REFERENCE",
                    "The exercise does not match the active score.",
                )
            projection = curriculum_runs.projection(run_id, exercise_id)
            return _bounded_json(
                {
                    "app_contract_version": APP_CONTRACT_VERSION,
                    "presentation": curriculum_presentation_to_dict(plan, projection),
                },
                budgets.max_response_bytes,
            )
        except (ValueError, CurriculumRunStoreError, ContractCodecError) as error:
            code = getattr(error, "code", "APP_CURRICULUM_EXERCISE_REJECTED")
            return _error(422, code, "This curriculum exercise is not currently available.")

    @app.post("/api/v1/curriculum-runs/{run_id}/exports")
    async def export_curriculum_run(
        run_id: str,
        request: Request,
        token: Annotated[str | None, Header(alias="X-TeachMeMusic-Token")] = None,
    ) -> Response:
        rejected = _authorize(request, token, launch_token)
        if rejected is not None:
            return rejected
        try:
            payload = curriculum_runs.export(run_id)
            if len(payload) > budgets.max_evidence_bytes:
                return _error(413, "APP_EVIDENCE_LIMIT", "The evidence archive is too large.")
            return Response(
                payload,
                media_type="application/json",
                headers={
                    "Content-Disposition": (
                        'attachment; filename="teachmemusic-curriculum-'
                        f'{_identity_token(run_id)}.json"'
                    )
                },
            )
        except (ValueError, CurriculumRunStoreError) as error:
            code = getattr(error, "code", "APP_CURRICULUM_EXPORT_REJECTED")
            return _error(422, code, "The curriculum evidence could not be exported.")

    @app.delete("/api/v1/curriculum-runs/{run_id}", status_code=204)
    async def delete_curriculum_run(
        run_id: str,
        request: Request,
        token: Annotated[str | None, Header(alias="X-TeachMeMusic-Token")] = None,
    ) -> Response:
        rejected = _authorize(request, token, launch_token)
        if rejected is not None:
            return rejected
        curriculum_runs.delete(run_id)
        return Response(status_code=204)

    @app.post("/api/v1/viewer-sessions/{session_id}/teaching-plans")
    async def create_teaching_plan(
        session_id: str,
        body: TeachingPlanRequest,
        request: Request,
        token: Annotated[str | None, Header(alias="X-TeachMeMusic-Token")] = None,
    ) -> Response:
        rejected = _authorize(request, token, launch_token)
        if rejected is not None:
            return rejected
        too_large = _reject_content_length(request, budgets.max_request_bytes)
        if too_large is not None:
            return too_large
        try:
            session = sessions.get(session_id)
            plan = _beginner_plan(session.package, body.score_id, session_id)
            result = {
                "app_contract_version": APP_CONTRACT_VERSION,
                "plan": lesson_plan_to_dict(plan),
            }
            encoded = json.dumps(result, ensure_ascii=False, separators=(",", ":")).encode()
            if len(encoded) > budgets.max_response_bytes:
                return _error(413, "APP_RESPONSE_LIMIT", "The lesson plan is too large.")
            return Response(encoded, media_type="application/json")
        except SessionStoreError:
            return _error(404, "APP_SESSION_NOT_FOUND", "The score session is unavailable.")
        except (AnalysisError, PlannerError, ValueError):
            return _error(
                422,
                "APP_TEACHING_PLAN_REJECTED",
                "A safe Beginner lesson plan could not be generated for this score.",
            )

    @app.post(
        "/api/v1/viewer-sessions/{session_id}/teaching-plans/{plan_id}/exercises/{exercise_id}"
    )
    async def project_exercise(
        session_id: str,
        plan_id: str,
        exercise_id: str,
        body: ExercisePresentationRequest,
        request: Request,
        token: Annotated[str | None, Header(alias="X-TeachMeMusic-Token")] = None,
    ) -> Response:
        rejected = _authorize(request, token, launch_token)
        if rejected is not None:
            return rejected
        if not projection_slot.acquire(blocking=False):
            return _error(429, "APP_PROJECTION_BUSY", "Another score is being prepared.")
        try:
            try:
                session = sessions.get(session_id)
                plan = _beginner_plan(session.package, body.score_id, session_id)
                if plan.id != plan_id:
                    return _error(
                        409,
                        "APP_TEACHING_PLAN_CHANGED",
                        "The lesson plan no longer matches this score session.",
                    )
                presentation = build_exercise_presentation(
                    session.package,
                    plan,
                    exercise_id,
                    tempo_bpm=_fraction(body.tempo_bpm),
                    count_in_enabled=body.count_in_enabled,
                )
                result = {
                    "app_contract_version": APP_CONTRACT_VERSION,
                    "presentation": exercise_presentation_to_dict(presentation),
                }
                encoded = json.dumps(result, ensure_ascii=False, separators=(",", ":")).encode()
                if len(encoded) > budgets.max_response_bytes:
                    return _error(413, "APP_RESPONSE_LIMIT", "The exercise output is too large.")
                return Response(encoded, media_type="application/json")
            except SessionStoreError:
                return _error(404, "APP_SESSION_NOT_FOUND", "The score session is unavailable.")
            except (AnalysisError, PlannerError, ExercisePresentationError, ValueError):
                return _error(
                    422,
                    "APP_EXERCISE_PROJECTION_REJECTED",
                    "This exercise cannot be displayed and demonstrated safely.",
                )
        finally:
            projection_slot.release()

    @app.post("/api/v1/viewer-sessions/{session_id}/teaching-runs")
    async def create_teaching_run(
        session_id: str,
        body: TeachingRunRequest,
        request: Request,
        token: Annotated[str | None, Header(alias="X-TeachMeMusic-Token")] = None,
    ) -> Response:
        rejected = _authorize(request, token, launch_token)
        if rejected is not None:
            return rejected
        too_large = _reject_content_length(request, budgets.max_request_bytes)
        if too_large is not None:
            return too_large
        try:
            session = sessions.get(session_id)
            plan = _beginner_plan(session.package, body.score_id, session_id)
            if plan.id != body.plan_id:
                return _error(
                    409,
                    "APP_TEACHING_PLAN_CHANGED",
                    "The lesson plan no longer matches this score session.",
                )
            if not (
                body.authorization_approved
                and body.capture_midi
                and body.source_faithful
                and body.musically_coherent
                and body.safe
                and body.executable
            ):
                return _error(
                    422,
                    "APP_GATE_ZERO_PRECONDITION",
                    "MIDI capture approval and the untouched-plan audit must pass before capture.",
                )
            now = datetime.now(UTC).isoformat()
            identity = _identity_token(plan.run_id)
            learner = LearnerContextSnapshot(
                id=f"learner-context:{identity}",
                track=LearnerTrack.BEGINNER,
                goals=("Learn the selected score accurately and transferably.",),
            )
            authorization = DataAuthorization(
                id=f"data-authorization:{identity}",
                approved=True,
                approved_at_utc=now,
                capture_midi=body.capture_midi,
                capture_self_report=body.capture_self_report,
                capture_environment=False,
                allow_export=body.allow_export,
            )
            audit = PlanAudit(
                id=f"plan-audit:{identity}",
                plan_id=plan.id,
                reviewer=body.reviewer,
                reviewed_at_utc=now,
                outcome=PlanAuditOutcome.PASS_NO_CHANGE,
                source_faithful=body.source_faithful,
                musically_coherent=body.musically_coherent,
                safe=body.safe,
                executable=body.executable,
                notes=("Owner-confirmed no-learning Gate 0 plan audit.",),
            )
            inspection = teaching_runs.create(
                session_id=session_id,
                package=session.package,
                score_id=body.score_id,
                plan=plan,
                learner=learner,
                authorization=authorization,
                audit=audit,
                created_at_utc=now,
            )
            return _bounded_json(
                {
                    "app_contract_version": APP_CONTRACT_VERSION,
                    "run_id": plan.run_id,
                    "inspection": _contract_data(inspection),
                },
                budgets.max_response_bytes,
            )
        except SessionStoreError:
            return _error(404, "APP_SESSION_NOT_FOUND", "The score session is unavailable.")
        except (AnalysisError, PlannerError, TeachingRunStoreError, ContractCodecError) as error:
            code = getattr(error, "code", "APP_TEACHING_RUN_REJECTED")
            return _error(422, code, "The local teaching run could not be started safely.")

    @app.post("/api/v1/teaching-runs/{run_id}/attempts")
    async def submit_teaching_attempt(
        run_id: str,
        body: AttemptSubmissionRequest,
        request: Request,
        token: Annotated[str | None, Header(alias="X-TeachMeMusic-Token")] = None,
    ) -> Response:
        rejected = _authorize(request, token, launch_token)
        if rejected is not None:
            return rejected
        too_large = _reject_content_length(request, budgets.max_request_bytes)
        if too_large is not None:
            return too_large
        if (
            len(body.raw_messages) > budgets.max_attempt_messages
            or len(body.normalized_events) > budgets.max_attempt_messages
        ):
            return _error(413, "APP_ATTEMPT_EVENT_LIMIT", "The attempt has too many events.")
        if len(body.diagnostics) > budgets.max_attempt_diagnostics:
            return _error(
                413, "APP_ATTEMPT_DIAGNOSTIC_LIMIT", "The attempt has too many diagnostics."
            )
        try:
            evidence = teaching_runs.evidence(run_id)
            if evidence.manifest.score_id != body.score_id or evidence.plans[0].id != body.plan_id:
                return _error(
                    409,
                    "APP_TEACHING_RUN_REFERENCE",
                    "The attempt does not match the active score and plan.",
                )
            session = sessions.get(teaching_runs.session_id(run_id))
            plan = evidence.plans[0]
            presentation = build_exercise_presentation(
                session.package,
                plan,
                body.exercise_id,
                tempo_bpm=_fraction(body.tempo_bpm),
                count_in_enabled=body.count_in_enabled,
            )
            support = teaching_runs.support(run_id, body.exercise_id, body.support_state_id)
            calibration = _calibration(run_id, body.calibration)
            attempt = _attempt(run_id, body, calibration.id, evidence)
            cycle = teaching_runs.submit_attempt(
                run_id=run_id,
                presentation=presentation,
                calibration=calibration,
                attempt=attempt,
                support=support,
                created_at_utc=datetime.now(UTC).isoformat(),
                unsafe_condition=body.unsafe_condition,
            )
            return _bounded_json(
                {
                    "app_contract_version": APP_CONTRACT_VERSION,
                    "attempt_id": attempt.id,
                    "observations": _contract_data(cycle.result.observations),
                    "evidence_records": _contract_data(cycle.result.evidence_records),
                    "feedback": _contract_data(cycle.result.feedback),
                    "decision": _contract_data(cycle.result.decision),
                    "mastery": (
                        _contract_data(cycle.result.mastery)
                        if cycle.result.mastery is not None
                        else None
                    ),
                    "next_support": (
                        _contract_data(cycle.result.next_support)
                        if cycle.result.next_support is not None
                        else None
                    ),
                    "inspection": _contract_data(cycle.inspection),
                },
                budgets.max_response_bytes,
            )
        except SessionStoreError:
            return _error(404, "APP_SESSION_NOT_FOUND", "The score session is unavailable.")
        except (ValueError, TeachingRunStoreError, ContractCodecError) as error:
            code = getattr(error, "code", "APP_ATTEMPT_REJECTED")
            return _error(422, code, "The learner attempt could not be evaluated safely.")

    @app.post("/api/v1/teaching-runs/{run_id}/exports")
    async def export_teaching_run(
        run_id: str,
        request: Request,
        token: Annotated[str | None, Header(alias="X-TeachMeMusic-Token")] = None,
    ) -> Response:
        rejected = _authorize(request, token, launch_token)
        if rejected is not None:
            return rejected
        try:
            archive = teaching_runs.archive(run_id, exported_at_utc=datetime.now(UTC).isoformat())
            payload = evidence_archive_to_json(archive).encode("utf-8")
            if len(payload) > budgets.max_evidence_bytes:
                return _error(413, "APP_EVIDENCE_LIMIT", "The evidence archive is too large.")
            return Response(
                payload,
                media_type="application/json",
                headers={
                    "Content-Disposition": (
                        f'attachment; filename="teachmemusic-{_identity_token(run_id)}.json"'
                    )
                },
            )
        except (ValueError, TeachingRunStoreError) as error:
            code = getattr(error, "code", "APP_EVIDENCE_EXPORT_REJECTED")
            return _error(422, code, "The local evidence archive could not be exported.")

    @app.post("/api/v1/viewer-sessions/{session_id}/teaching-runs/import")
    async def import_teaching_run(
        session_id: str,
        body: EvidenceImportRequest,
        request: Request,
        token: Annotated[str | None, Header(alias="X-TeachMeMusic-Token")] = None,
    ) -> Response:
        rejected = _authorize(request, token, launch_token)
        if rejected is not None:
            return rejected
        too_large = _reject_content_length(request, budgets.max_evidence_bytes)
        if too_large is not None:
            return too_large
        try:
            session = sessions.get(session_id)
            archive = evidence_archive_from_json(
                json.dumps(body.archive, ensure_ascii=False, separators=(",", ":"))
            )
            inspection = teaching_runs.resume(
                session_id=session_id,
                package=session.package,
                score_id=body.score_id,
                archive=archive,
            )
            return _bounded_json(
                {
                    "app_contract_version": APP_CONTRACT_VERSION,
                    "run_id": archive.evidence.manifest.id,
                    "inspection": _contract_data(inspection),
                },
                budgets.max_response_bytes,
            )
        except SessionStoreError:
            return _error(404, "APP_SESSION_NOT_FOUND", "The score session is unavailable.")
        except (ValueError, TeachingRunStoreError, ContractCodecError) as error:
            code = getattr(error, "code", "APP_EVIDENCE_IMPORT_REJECTED")
            return _error(422, code, "The local evidence archive could not be resumed.")

    @app.get("/api/v1/teaching-runs/{run_id}")
    async def inspect_teaching_run(
        run_id: str,
        request: Request,
        token: Annotated[str | None, Header(alias="X-TeachMeMusic-Token")] = None,
    ) -> Response:
        rejected = _authorize(request, token, launch_token)
        if rejected is not None:
            return rejected
        try:
            return _bounded_json(
                {
                    "app_contract_version": APP_CONTRACT_VERSION,
                    "inspection": _contract_data(teaching_runs.inspect(run_id)),
                },
                budgets.max_response_bytes,
            )
        except (TeachingRunStoreError, ContractCodecError) as error:
            code = getattr(error, "code", "APP_TEACHING_RUN_NOT_FOUND")
            return _error(404, code, "The local teaching run is unavailable.")

    @app.delete("/api/v1/teaching-runs/{run_id}", status_code=204)
    async def delete_teaching_run(
        run_id: str,
        request: Request,
        token: Annotated[str | None, Header(alias="X-TeachMeMusic-Token")] = None,
    ) -> Response:
        rejected = _authorize(request, token, launch_token)
        if rejected is not None:
            return rejected
        teaching_runs.delete(run_id)
        return Response(status_code=204)

    @app.delete("/api/v1/viewer-sessions/{session_id}", status_code=204)
    async def delete_session(
        session_id: str,
        request: Request,
        token: Annotated[str | None, Header(alias="X-TeachMeMusic-Token")] = None,
    ) -> Response:
        rejected = _authorize(request, token, launch_token)
        if rejected is not None:
            return rejected
        teaching_runs.delete_session(session_id)
        curriculum_runs.delete_session(session_id)
        sessions.delete(session_id)
        return Response(status_code=204)

    if mobile_bridge is not None and mobile_companion_origin is not None:

        @app.post("/api/v1/mobile-pairings")
        async def create_mobile_pairing(
            body: MobilePairingRequest,
            request: Request,
            token: Annotated[str | None, Header(alias="X-TeachMeMusic-Token")] = None,
        ) -> Response:
            rejected = _authorize(request, token, launch_token)
            if rejected is not None:
                return rejected
            try:
                offer = mobile_bridge.create(ttl_seconds=body.ttl_seconds)
            except MobileBridgeError as error:
                return _mobile_error(error)
            return _bounded_json(
                {
                    "app_contract_version": APP_CONTRACT_VERSION,
                    "pairing_id": offer.id,
                    "phone_capability": offer.phone_capability,
                    "bridge_capability": offer.bridge_capability,
                    "expires_in_seconds": offer.expires_in_seconds,
                    "companion_origin": mobile_companion_origin,
                    "pairing_url": (
                        f"{mobile_companion_origin}/?pairing_id={offer.id}"
                        f"#phone_capability={offer.phone_capability}"
                    ),
                },
                budgets.max_mobile_message_bytes,
            )

        @app.post("/api/v1/mobile-pairings/{pairing_id}/bridge-claims")
        async def claim_mobile_bridge(
            pairing_id: str,
            body: MobileBridgeClaimRequest,
            request: Request,
            token: Annotated[str | None, Header(alias="X-TeachMeMusic-Token")] = None,
        ) -> Response:
            rejected = _authorize(request, token, launch_token)
            if rejected is not None:
                return rejected
            try:
                bridge_token = mobile_bridge.claim(
                    pairing_id, role="midi-bridge", capability=body.capability
                )
            except MobileBridgeError as error:
                return _mobile_error(error)
            return _bounded_json(
                {
                    "app_contract_version": APP_CONTRACT_VERSION,
                    "pairing_id": pairing_id,
                    "role": "midi-bridge",
                    "bridge_token": bridge_token,
                },
                budgets.max_mobile_message_bytes,
            )

        @app.post("/api/v1/mobile-pairings/{pairing_id}/bridge-messages", status_code=204)
        async def publish_mobile_bridge_message(
            pairing_id: str,
            request: Request,
            authorization: Annotated[str | None, Header(alias="Authorization")] = None,
        ) -> Response:
            origin_rejection = _authorize_same_origin_request(request)
            if origin_rejection is not None:
                return origin_rejection
            bridge_token = _bearer_token(authorization)
            if bridge_token is None:
                return _error(403, "MOBILE_BRIDGE_TOKEN_REQUIRED", "A bridge token is required.")
            payload = await _read_request_bounded(request, budgets.max_mobile_message_bytes)
            if payload is None:
                return _error(
                    413, "MOBILE_MESSAGE_TOO_LARGE", "The bridge message exceeds the size limit."
                )
            try:
                body = MobileBridgeMessageInput.model_validate_json(payload)
                mobile_bridge.publish(
                    pairing_id,
                    token=bridge_token,
                    message=BridgeMessage(
                        sequence=body.sequence,
                        sent_at_microseconds=body.sent_at_microseconds,
                        connection=body.connection,
                        active_notes=tuple(body.active_notes),
                        capture=body.capture,
                        capture_purpose=body.capture_purpose,
                        calibration_approved=body.calibration_approved,
                    ),
                )
            except MobileBridgeError as error:
                return _mobile_error(error)
            except (ValueError, TypeError):
                return _error(422, "MOBILE_MESSAGE_INVALID", "The bridge message is malformed.")
            return Response(status_code=204)

        @app.get("/api/v1/mobile-pairings/{pairing_id}/bridge-command")
        async def read_mobile_bridge_command(
            pairing_id: str,
            request: Request,
            authorization: Annotated[str | None, Header(alias="Authorization")] = None,
        ) -> Response:
            origin_rejection = _authorize_same_origin_request(request)
            if origin_rejection is not None:
                return origin_rejection
            bridge_token = _bearer_token(authorization)
            if bridge_token is None:
                return _error(403, "MOBILE_BRIDGE_TOKEN_REQUIRED", "A bridge token is required.")
            try:
                command = mobile_bridge.bridge_command(pairing_id, bridge_token=bridge_token)
            except MobileBridgeError as error:
                return _mobile_error(error)
            if command is None:
                return Response(status_code=204)
            return _bounded_json(
                _mobile_command_data(pairing_id, command),
                budgets.max_mobile_message_bytes,
            )

        @app.post("/api/v1/mobile-pairings/{pairing_id}/bridge-command-acks")
        async def acknowledge_mobile_bridge_command(
            pairing_id: str,
            request: Request,
            authorization: Annotated[str | None, Header(alias="Authorization")] = None,
        ) -> Response:
            origin_rejection = _authorize_same_origin_request(request)
            if origin_rejection is not None:
                return origin_rejection
            bridge_token = _bearer_token(authorization)
            if bridge_token is None:
                return _error(403, "MOBILE_BRIDGE_TOKEN_REQUIRED", "A bridge token is required.")
            payload = await _read_request_bounded(request, budgets.max_mobile_result_bytes)
            if payload is None:
                return _error(
                    413,
                    "MOBILE_RESULT_TOO_LARGE",
                    "The command acknowledgement exceeds the size limit.",
                )
            try:
                body = MobileCommandAckInput.model_validate_json(payload)
                if body.result is not None and _contains_forbidden_mobile_result(body.result):
                    return _error(
                        422,
                        "MOBILE_RESULT_CONTENT_REJECTED",
                        "The phone result contains evidence or authority-only content.",
                    )
                command = mobile_bridge.complete_command(
                    pairing_id,
                    bridge_token=bridge_token,
                    sequence=body.sequence,
                    result=body.result,
                    error=body.error,
                )
            except MobileBridgeError as error:
                return _mobile_error(error)
            except (ValueError, TypeError):
                return _error(
                    422,
                    "MOBILE_COMMAND_ACK_INVALID",
                    "The command acknowledgement is malformed.",
                )
            return _bounded_json(
                _mobile_command_data(pairing_id, command),
                budgets.max_mobile_result_bytes,
            )

        @app.get("/api/v1/mobile-pairings/{pairing_id}")
        async def inspect_mobile_pairing(
            pairing_id: str,
            request: Request,
            token: Annotated[str | None, Header(alias="X-TeachMeMusic-Token")] = None,
        ) -> Response:
            rejected = _authorize(request, token, launch_token)
            if rejected is not None:
                return rejected
            try:
                status = mobile_bridge.status(pairing_id)
            except MobileBridgeError as error:
                return _mobile_error(error)
            return _bounded_json(
                {
                    "app_contract_version": APP_CONTRACT_VERSION,
                    "pairing_id": status.pairing_id,
                    "phone_claimed": status.phone_claimed,
                    "bridge_claimed": status.bridge_claimed,
                    "revoked": status.revoked,
                    "last_sequence": status.last_sequence,
                    "availability": status.availability,
                    "expires_in_seconds": status.expires_in_seconds,
                },
                budgets.max_mobile_message_bytes,
            )

        @app.delete("/api/v1/mobile-pairings/{pairing_id}", status_code=204)
        async def revoke_mobile_pairing(
            pairing_id: str,
            request: Request,
            token: Annotated[str | None, Header(alias="X-TeachMeMusic-Token")] = None,
        ) -> Response:
            rejected = _authorize(request, token, launch_token)
            if rejected is not None:
                return rejected
            try:
                mobile_bridge.revoke(pairing_id)
            except MobileBridgeError as error:
                return _mobile_error(error)
            return Response(status_code=204)

    if static_directory is not None:
        app.mount("/", StaticFiles(directory=static_directory, html=True), name="frontend")
    return app


def _authorize(request: Request, token: str | None, expected: str) -> JSONResponse | None:
    if token is None or not hmac.compare_digest(token, expected):
        return _error(403, "APP_TOKEN_REQUIRED", "The launch token is invalid.")
    origin = request.headers.get("origin")
    if origin is not None:
        parsed = urlsplit(origin)
        expected_origin = f"{request.url.scheme}://{request.url.netloc}"
        actual = f"{parsed.scheme}://{parsed.netloc}"
        if actual != expected_origin:
            return _error(403, "APP_ORIGIN_REJECTED", "The request origin is invalid.")
    return None


def _authorize_same_origin_request(request: Request) -> JSONResponse | None:
    origin = request.headers.get("origin")
    if origin is None:
        return None
    parsed = urlsplit(origin)
    expected_origin = f"{request.url.scheme}://{request.url.netloc}"
    actual = f"{parsed.scheme}://{parsed.netloc}"
    if actual != expected_origin:
        return _error(403, "APP_ORIGIN_REJECTED", "The request origin is invalid.")
    return None


def _bearer_token(value: str | None) -> str | None:
    if value is None or not value.startswith("Bearer "):
        return None
    token = value.removeprefix("Bearer ")
    if not token or any(character.isspace() for character in token):
        return None
    return token


def _reject_content_length(request: Request, maximum: int) -> JSONResponse | None:
    raw = request.headers.get("content-length")
    if raw is None:
        return None
    try:
        length = int(raw)
    except ValueError:
        return _error(400, "APP_CONTENT_LENGTH_INVALID", "Content-Length is invalid.")
    if length > maximum:
        return _error(413, "APP_REQUEST_TOO_LARGE", "The request exceeds the size limit.")
    return None


def _validate_filename(filename: str, maximum: int) -> JSONResponse | None:
    if not filename or PurePath(filename).name != filename or "/" in filename or "\\" in filename:
        return _error(400, "APP_FILENAME_INVALID", "The filename is invalid.")
    if len(filename.encode("utf-8")) > maximum:
        return _error(413, "APP_FILENAME_TOO_LONG", "The filename is too long.")
    if Path(filename).suffix.lower() not in _SUPPORTED_SUFFIXES:
        return _error(415, "APP_FILE_TYPE_UNSUPPORTED", "Choose an XML, MusicXML, or MXL file.")
    return None


async def _read_bounded(upload: UploadFile, maximum: int) -> bytes | None:
    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = await upload.read(min(64 * 1024, maximum + 1 - total))
        if not chunk:
            return b"".join(chunks)
        total += len(chunk)
        if total > maximum:
            return None
        chunks.append(chunk)


async def _read_request_bounded(request: Request, maximum: int) -> bytes | None:
    raw_length = request.headers.get("content-length")
    if raw_length is not None:
        try:
            if int(raw_length) > maximum:
                return None
        except ValueError:
            return None
    chunks: list[bytes] = []
    total = 0
    async for chunk in request.stream():
        total += len(chunk)
        if total > maximum:
            return None
        chunks.append(chunk)
    return b"".join(chunks)


def _score_documents(package: CanonicalMusicPackage) -> list[ScoreDocument]:
    return [item for item in package.documents if isinstance(item, ScoreDocument)]


def _score_manifest(document: ScoreDocument) -> dict[str, str | None]:
    title: str | None = None
    if isinstance(document.content, CanonicalScoreContent):
        score = document.content.score
        title = score.work_title or score.movement_title
    return {"score_id": document.id.value, "title": title}


def _fraction(value: str | int | None) -> Fraction | None:
    if value is None:
        return None
    result = Fraction(value)
    if result <= 0:
        raise ValueError("policy value must be positive")
    return result


def _curriculum_projection_for_exercise(
    plan: CurriculumDeliveryPlan,
    exercise_id: str,
) -> CurriculumStageProjection:
    for stage in plan.practice.acquisition.stages:
        projection = project_curriculum_stage(plan, stage.node_id)
        if projection.expected.exercise_id == exercise_id:
            return projection
    raise CurriculumRunStoreError(
        "APP_CURRICULUM_EXERCISE", "the exercise is absent from this curriculum"
    )


def _curriculum_inspection_view(value: dict[str, object]) -> dict[str, object]:
    storage = value.get("storage")
    durable = storage if isinstance(storage, dict) else {}
    raw_attempt_count = value.get("attempt_count", 0)
    attempt_count = raw_attempt_count if isinstance(raw_attempt_count, int) else 0
    return {
        "run_id": value["run_id"],
        "score_digest_sha256": "",
        "evidence_sha256": durable.get("integrity_root") or "",
        "plan_count": 1,
        "audit_count": 1,
        "support_count": 1,
        "calibration_count": attempt_count,
        "attempt_count": attempt_count,
        "observation_count": int(durable.get("record_count", 0)),
        "evidence_record_count": int(durable.get("record_count", 0)),
        "feedback_count": 0,
        "policy_decision_count": attempt_count,
        "journal_entry_count": 0,
        "gate_decision_count": 0,
        "event_count": int(durable.get("record_count", 0)),
        "latest_sequence_number": durable.get("last_complete_sequence"),
        "has_pedagogical_intervention": False,
        "omissions": [
            "No microphone audio, video, biometric, cloud, posture, fingering, "
            "acoustic-tone, or interpretive inference is captured."
        ],
        "curriculum": value,
    }


def _curriculum_cycle_view(
    cycle: CurriculumAttemptCycle,
    attempt_id: str,
    presentation: dict[str, object],
) -> dict[str, object]:
    observations = tuple(cycle.observations)
    pitch = tuple(item for item in observations if item.dimension.value == "pitch")
    matched = sum(item.status.value == "match" for item in pitch)
    expected = len(pitch)
    percent = round((matched / expected) * 100) if expected else 0
    decision_data = contract_to_data(cycle.policy_decision)
    if not isinstance(decision_data, dict):
        raise ContractCodecError("curriculum decision did not encode as an object")
    action = str(decision_data.get("action", "retry"))
    if action in {"progress", "remove-tempo-constraint", "increase-tempo", "maintain-tempo"}:
        mastery_action = "exercise-complete"
        heading = "Exercise complete"
        feedback_action = "Continue with the next curriculum target."
    elif action in {"decrease-tempo", "strengthen-support", "slow-down"}:
        mastery_action = "slow-down"
        heading = "Let’s slow it down"
        feedback_action = "Repeat at the new supported tempo."
    elif action == "fade-support":
        mastery_action = "return-to-normal"
        heading = "Now use less help"
        feedback_action = "Repeat once more with the reduced support."
    else:
        mastery_action = "retry"
        heading = "Try again"
        feedback_action = "Repeat the same target under the recorded support condition."
    next_support = contract_to_data(cycle.projection.support)
    if not isinstance(next_support, dict):
        raise ContractCodecError("curriculum support did not encode as an object")
    return {
        "app_contract_version": APP_CONTRACT_VERSION,
        "attempt_id": attempt_id,
        "observations": contract_to_data(cycle.observations),
        "evidence_records": contract_to_data(cycle.evidence_records),
        "feedback": {
            "id": f"curriculum-feedback:{_identity_token(attempt_id)}",
            "timing": "end-of-attempt",
            "target": cycle.projection.expected.exercise_id,
            "observation": f"{heading}: {percent}% of compared pitch observations matched.",
            "boundary": None,
            "action": feedback_action,
            "reason": str(decision_data.get("reason_code", "DEV009_POLICY")),
        },
        "decision": {
            "id": str(decision_data.get("id", f"tempo-transition:{_identity_token(attempt_id)}")),
            "action": action,
            "next_node_id": cycle.projection.node.id,
            "reason": str(decision_data.get("reason_code", "DEV009_POLICY")),
        },
        "mastery": {
            "correct_note_count": matched,
            "expected_note_count": expected,
            "extra_note_count": sum(
                item.status.value == "discrepancy" and item.observed_value == "extra"
                for item in pitch
            ),
            "green_percent": percent,
            "threshold_percent": 95,
            "action": mastery_action,
            "next_node_id": cycle.projection.node.id,
            "reduced_tempo": cycle.projection.support.tempo_percent < 100,
        },
        "next_support": next_support,
        "inspection": _curriculum_inspection_view(cycle.inspection),
        "plan": curriculum_plan_to_dict(cycle.plan),
        "presentation": presentation,
        "curriculum": {
            "mastery": contract_to_data(cycle.mastery),
            "unlock": contract_to_data(cycle.unlock),
            "outcome": contract_to_data(cycle.outcome),
            "research_reward": contract_to_data(cycle.research_reward),
            "policy_decision": decision_data,
        },
    }


def _beginner_plan(
    package: CanonicalMusicPackage,
    score_id: str,
    session_id: str,
) -> LessonPlan:
    analysis = analyze_canonical_score(package, score_id=score_id)
    learner = LearnerContextSnapshot(
        id="learner-context:local-beginner",
        track=LearnerTrack.BEGINNER,
        goals=("Learn the selected score accurately and transferably.",),
    )
    return generate_beginner_lesson_plan(
        package,
        analysis,
        learner,
        run_id=_run_id(session_id, score_id),
        generated_at_utc=datetime.now(UTC).isoformat(),
    )


def _run_id(session_id: str, score_id: str) -> str:
    return f"run:{session_id}:{_identity_token(score_id)}"


def _identity_token(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:20]


def _calibration(run_id: str, value: CalibrationInput) -> CalibrationProfile:
    identity = _identity_token(
        "|".join(
            (
                run_id,
                value.version,
                value.device_id,
                value.approved_at_utc or "unapproved",
            )
        )
    )
    return CalibrationProfile(
        id=f"calibration:{identity}",
        version=value.version,
        device_id=value.device_id,
        input_name=value.input_name,
        timestamp_origin=value.timestamp_origin,
        pitch_numbering_confirmed=value.pitch_numbering_confirmed,
        sustain_available=value.sustain_available,
        clock_offset_microseconds=value.clock_offset_microseconds,
        clock_jitter_microseconds=value.clock_jitter_microseconds,
        timing_window_microseconds=value.timing_window_microseconds,
        chord_window_microseconds=value.chord_window_microseconds,
        limitations=tuple(value.limitations),
        approved=value.approved,
        approved_at_utc=value.approved_at_utc,
    )


def _attempt(
    run_id: str,
    value: AttemptSubmissionRequest,
    calibration_id: str,
    evidence: EvidenceExport,
) -> LearnerAttempt:
    attempt_count = len(evidence.performance.attempts)
    attempt_id = f"attempt:{_identity_token(run_id)}:{attempt_count + 1}"
    raw = tuple(
        RawMidiMessage(
            id=item.id,
            sequence_number=item.sequence_number,
            timestamp_microseconds=item.timestamp_microseconds,
            data=tuple(item.data),
        )
        for item in value.raw_messages
    )
    normalized = tuple(
        NormalizedMidiEvent(
            id=item.id,
            raw_message_id=item.raw_message_id,
            kind=MidiEventKind(item.kind),
            timestamp_microseconds=item.timestamp_microseconds,
            channel=item.channel,
            note=item.note,
            velocity=item.velocity,
            controller=item.controller,
            value=item.value,
            detail=item.detail,
        )
        for item in value.normalized_events
    )
    return LearnerAttempt(
        id=attempt_id,
        run_id=run_id,
        exercise_id=value.exercise_id,
        calibration_id=calibration_id,
        practice_mode=value.practice_mode,
        support_state_id=value.support_state_id,
        started_at_utc=value.started_at_utc,
        start_microseconds=value.start_microseconds,
        end_microseconds=value.end_microseconds,
        completion=AttemptCompletion(value.completion),
        raw_messages=raw,
        normalized_events=normalized,
        diagnostics=tuple(value.diagnostics),
    )


def _curriculum_attempt(
    run_id: str,
    value: AttemptSubmissionRequest,
    calibration_id: str,
    attempt_count: int,
) -> LearnerAttempt:
    """Build one bounded real attempt for the DEV-009 run store."""

    attempt_id = f"attempt:{_identity_token(run_id)}:{attempt_count + 1}"
    raw = tuple(
        RawMidiMessage(
            id=item.id,
            sequence_number=item.sequence_number,
            timestamp_microseconds=item.timestamp_microseconds,
            data=tuple(item.data),
        )
        for item in value.raw_messages
    )
    normalized = tuple(
        NormalizedMidiEvent(
            id=item.id,
            raw_message_id=item.raw_message_id,
            kind=MidiEventKind(item.kind),
            timestamp_microseconds=item.timestamp_microseconds,
            channel=item.channel,
            note=item.note,
            velocity=item.velocity,
            controller=item.controller,
            value=item.value,
            detail=item.detail,
        )
        for item in value.normalized_events
    )
    return LearnerAttempt(
        id=attempt_id,
        run_id=run_id,
        exercise_id=value.exercise_id,
        calibration_id=calibration_id,
        practice_mode=value.practice_mode,
        support_state_id=value.support_state_id,
        started_at_utc=value.started_at_utc,
        start_microseconds=value.start_microseconds,
        end_microseconds=value.end_microseconds,
        completion=AttemptCompletion(value.completion),
        raw_messages=raw,
        normalized_events=normalized,
        diagnostics=tuple(value.diagnostics),
    )


def _contract_data(value: object) -> object:
    return contract_to_data(value)


def _contains_forbidden_mobile_result(value: object) -> bool:
    if isinstance(value, dict):
        return any(
            key in _MOBILE_RESULT_FORBIDDEN_KEYS or _contains_forbidden_mobile_result(item)
            for key, item in value.items()
        )
    if isinstance(value, list):
        return any(_contains_forbidden_mobile_result(item) for item in value)
    return False


def _mobile_command_data(pairing_id: str, command: MobileCommand) -> dict[str, object]:
    return {
        "mobile_contract_version": "0.2.0",
        "pairing_id": pairing_id,
        "sequence": command.sequence,
        "kind": command.kind,
        "status": command.status,
        "context": command.context,
        "result": command.result,
        "error": command.error,
    }


def _bounded_json(value: object, maximum: int) -> Response:
    encoded = json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    if len(encoded) > maximum:
        return _error(413, "APP_RESPONSE_LIMIT", "The response is too large.")
    return Response(encoded, media_type="application/json")


def _error(
    status: int,
    code: str,
    message: str,
    *,
    stage: Literal["application"] = "application",
) -> JSONResponse:
    return JSONResponse(
        {"diagnostics": [{"code": code, "stage": stage, "message": message}]},
        status_code=status,
    )


def _mobile_error(error: MobileBridgeError) -> JSONResponse:
    if error.code in {"MOBILE_CAPABILITY_INVALID", "MOBILE_BRIDGE_TOKEN_INVALID"}:
        status = 403
    elif error.code in {"MOBILE_PAIRING_EXPIRED", "MOBILE_PAIRING_REVOKED"}:
        status = 410
    elif error.code in {"MOBILE_PAIRING_NOT_FOUND"}:
        status = 404
    elif error.code in {"MOBILE_PAIRING_CAPACITY"}:
        status = 429
    elif error.code in {
        "MOBILE_ROLE_OCCUPIED",
        "MOBILE_SEQUENCE_REJECTED",
        "MOBILE_COMMAND_ALREADY_COMPLETED",
        "MOBILE_COMMAND_SEQUENCE_REJECTED",
    }:
        status = 409
    else:
        status = 422
    return _error(status, error.code, str(error))
