"""FastAPI edge for bounded canonical score ingestion and projection."""

from __future__ import annotations

import hmac
import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from fractions import Fraction
from pathlib import Path, PurePath
from threading import BoundedSemaphore
from typing import Annotated, Literal
from urllib.parse import urlsplit

from fastapi import FastAPI, Header, Request
from fastapi.responses import JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict
from starlette.datastructures import UploadFile

from teachmemusic.analysis import AnalysisError, analyze_canonical_score
from teachmemusic.score import (
    CanonicalMusicPackage,
    CanonicalScoreContent,
    ScoreDocument,
    parse_musicxml_package,
)
from teachmemusic.teaching import (
    ExercisePresentationError,
    LearnerContextSnapshot,
    LearnerTrack,
    LessonPlan,
    PlannerError,
    build_exercise_presentation,
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
from .sessions import SessionStore, SessionStoreError

APP_CONTRACT_VERSION = "0.2.0"
_SUPPORTED_SUFFIXES = frozenset({".xml", ".musicxml", ".mxl"})


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


def create_app(
    *,
    launch_token: str,
    budgets: AppBudgets = DEFAULT_APP_BUDGETS,
    store: SessionStore | None = None,
    static_directory: Path | None = None,
) -> FastAPI:
    """Create one same-origin, token-protected local application."""

    if not launch_token:
        raise ValueError("launch_token must not be empty")
    sessions = (
        store
        if store is not None
        else SessionStore(
            max_sessions=budgets.max_sessions,
            ttl_seconds=budgets.session_ttl_seconds,
        )
    )
    projection_slot = BoundedSemaphore(1)

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        yield
        sessions.clear()

    app = FastAPI(title="TeachMeMusic", version="0.0.0", lifespan=lifespan)
    app.state.session_store = sessions

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

    @app.delete("/api/v1/viewer-sessions/{session_id}", status_code=204)
    async def delete_session(
        session_id: str,
        request: Request,
        token: Annotated[str | None, Header(alias="X-TeachMeMusic-Token")] = None,
    ) -> Response:
        rejected = _authorize(request, token, launch_token)
        if rejected is not None:
            return rejected
        sessions.delete(session_id)
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
        run_id=f"run:{session_id}",
        generated_at_utc=datetime.now(UTC).isoformat(),
    )


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
