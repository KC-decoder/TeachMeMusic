"""Narrow HTTPS companion API for one explicitly paired phone."""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Annotated, Literal
from urllib.parse import urlsplit

from fastapi import FastAPI, Header, Request
from fastapi.responses import HTMLResponse, JSONResponse, Response
from pydantic import BaseModel, ConfigDict, Field
from starlette.types import ASGIApp, Receive, Scope, Send

from .mobile_bridge import MobileBridgeError, MobileBridgeStore, MobileCommand

MOBILE_CONTRACT_VERSION = "0.2.0"


@dataclass(frozen=True, slots=True)
class MobileNetworkPolicy:
    """Exact public authority and bounded companion request policy."""

    public_origin: str
    max_message_bytes: int = 4 * 1024
    max_result_bytes: int = 256 * 1024

    def __post_init__(self) -> None:
        parsed = urlsplit(self.public_origin)
        if (
            parsed.scheme != "https"
            or not parsed.hostname
            or not parsed.netloc
            or parsed.path
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError("public_origin must be one exact HTTPS origin")
        if self.max_message_bytes < 256 or self.max_result_bytes < self.max_message_bytes:
            raise ValueError("mobile message budgets are invalid")

    @property
    def allowed_host(self) -> str:
        return urlsplit(self.public_origin).netloc.lower()


class PhoneClaimInput(BaseModel):
    """One-time phone capability submitted to the companion origin."""

    model_config = ConfigDict(extra="forbid")

    capability: str = Field(min_length=32, max_length=256)


class AttemptCommandContext(BaseModel):
    """Facts needed by desktop capture to submit through the existing authority."""

    model_config = ConfigDict(extra="forbid")

    run_id: str = Field(min_length=1, max_length=512)
    score_id: str = Field(min_length=1, max_length=512)
    plan_id: str = Field(min_length=1, max_length=512)
    exercise_id: str = Field(min_length=1, max_length=512)
    practice_mode: str = Field(min_length=1, max_length=120)
    support_state_id: str = Field(min_length=1, max_length=512)
    tempo_bpm: int = Field(ge=1, le=480)
    count_in_enabled: bool


class PhoneCommandInput(BaseModel):
    """One exact phone control request; no learner evidence is accepted here."""

    model_config = ConfigDict(extra="forbid")

    mobile_contract_version: Literal["0.2.0"]
    kind: Literal[
        "start-attempt",
        "pause-attempt",
        "resume-attempt",
        "finish-attempt",
        "abort-attempt",
        "safe-stop",
        "submit-attempt",
    ]
    context: AttemptCommandContext | None = None


class PairedPhoneAuthority:
    """Require a live phone pairing before exposing the companion app authority."""

    def __init__(self, app: ASGIApp, bridge: MobileBridgeStore) -> None:
        self._app = app
        self._bridge = bridge

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or not str(scope.get("path", "")).startswith("/api/v1/"):
            await self._app(scope, receive, send)
            return
        headers = {
            key.decode("latin-1").lower(): value.decode("latin-1")
            for key, value in scope.get("headers", [])
        }
        pairing_id = headers.get("x-teachmemusic-mobile-pairing")
        token = _bearer_token(headers.get("authorization"))
        if not pairing_id or token is None:
            await _send_asgi_error(
                send,
                403,
                "MOBILE_PHONE_AUTH_REQUIRED",
                "A live phone pairing is required for the teaching authority.",
            )
            return
        try:
            self._bridge.authorize_phone(pairing_id, phone_token=token)
        except MobileBridgeError as error:
            response = _mobile_error(error)
            await response(scope, receive, send)
            return
        await self._app(scope, receive, send)


def create_mobile_companion_app(
    *,
    bridge: MobileBridgeStore,
    policy: MobileNetworkPolicy,
    authority_app: ASGIApp | None = None,
) -> FastAPI:
    """Create the paired phone edge and optionally mount the existing authority."""

    app = FastAPI(
        title="TeachMeMusic Mobile Companion",
        version=MOBILE_CONTRACT_VERSION,
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )
    app.state.mobile_bridge_store = bridge
    app.state.mobile_network_policy = policy

    @app.middleware("http")
    async def secure_companion_response(
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        rejected = _network_guard(request, policy, require_origin=False)
        response = rejected if rejected is not None else await call_next(request)
        response.headers["Cache-Control"] = "no-store"
        response.headers["Content-Security-Policy"] = "default-src 'self'; frame-ancestors 'none'"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Strict-Transport-Security"] = "max-age=300"
        return response

    if authority_app is None:

        @app.get("/")
        async def companion_boundary() -> Response:
            return HTMLResponse(
                "<!doctype html><html><head><meta name='viewport' "
                "content='width=device-width,initial-scale=1'></head>"
                "<body><main><h1>TeachMeMusic companion bridge</h1>"
                "<p>The secure phone transport is available.</p></main></body></html>"
            )

    @app.get("/api/v1/mobile/health")
    async def mobile_health(request: Request) -> Response:
        rejected = _network_guard(request, policy, require_origin=False)
        if rejected is not None:
            return rejected
        return _json(
            {
                "status": "ok",
                "mobile_contract_version": MOBILE_CONTRACT_VERSION,
                "roles": ["phone"],
            },
            policy.max_message_bytes,
        )

    @app.post("/api/v1/mobile/pairings/{pairing_id}/phone-claims")
    async def claim_phone(pairing_id: str, request: Request) -> Response:
        rejected = _network_guard(request, policy, require_origin=True)
        if rejected is not None:
            return rejected
        payload = await _read_bounded(request, policy.max_message_bytes)
        if payload is None:
            return _error(
                413, "MOBILE_MESSAGE_TOO_LARGE", "The phone claim exceeds the size limit."
            )
        try:
            body = PhoneClaimInput.model_validate_json(payload)
            phone_token = bridge.claim(
                pairing_id,
                role="phone",
                capability=body.capability,
            )
        except MobileBridgeError as error:
            return _mobile_error(error)
        except (ValueError, TypeError):
            return _error(422, "MOBILE_CLAIM_INVALID", "The phone claim is malformed.")
        return _json(
            {
                "mobile_contract_version": MOBILE_CONTRACT_VERSION,
                "pairing_id": pairing_id,
                "role": "phone",
                "phone_token": phone_token,
            },
            policy.max_message_bytes,
        )

    @app.get("/api/v1/mobile/pairings/{pairing_id}/state")
    async def phone_state(
        pairing_id: str,
        request: Request,
        authorization: Annotated[str | None, Header(alias="Authorization")] = None,
    ) -> Response:
        rejected = _network_guard(request, policy, require_origin=False)
        if rejected is not None:
            return rejected
        token = _bearer_token(authorization)
        if token is None:
            return _error(403, "MOBILE_PHONE_TOKEN_REQUIRED", "A phone token is required.")
        try:
            snapshot = bridge.snapshot(pairing_id, phone_token=token)
        except MobileBridgeError as error:
            return _mobile_error(error)
        return _json(
            {
                "mobile_contract_version": MOBILE_CONTRACT_VERSION,
                "pairing_id": snapshot.pairing_id,
                "availability": snapshot.availability,
                "sequence": snapshot.sequence,
                "active_notes": list(snapshot.active_notes),
                "age_microseconds": snapshot.age_microseconds,
                "expires_in_seconds": snapshot.expires_in_seconds,
                "capture": snapshot.capture,
                "capture_purpose": snapshot.capture_purpose,
                "calibration_approved": snapshot.calibration_approved,
            },
            policy.max_message_bytes,
        )

    @app.post("/api/v1/mobile/pairings/{pairing_id}/commands")
    async def phone_command(
        pairing_id: str,
        request: Request,
        authorization: Annotated[str | None, Header(alias="Authorization")] = None,
    ) -> Response:
        token = _bearer_token(authorization)
        if token is None:
            return _error(403, "MOBILE_PHONE_TOKEN_REQUIRED", "A phone token is required.")
        payload = await _read_bounded(request, policy.max_message_bytes)
        if payload is None:
            return _error(
                413, "MOBILE_MESSAGE_TOO_LARGE", "The phone command exceeds the size limit."
            )
        try:
            body = PhoneCommandInput.model_validate_json(payload)
            if body.kind == "submit-attempt" and body.context is None:
                return _error(
                    422,
                    "MOBILE_COMMAND_CONTEXT_REQUIRED",
                    "Attempt submission requires exact teaching context.",
                )
            if body.kind != "submit-attempt" and body.context is not None:
                return _error(
                    422,
                    "MOBILE_COMMAND_CONTEXT_REJECTED",
                    "Only attempt submission may carry teaching context.",
                )
            command = bridge.request_command(
                pairing_id,
                phone_token=token,
                kind=body.kind,
                context={} if body.context is None else body.context.model_dump(),
            )
        except MobileBridgeError as error:
            return _mobile_error(error)
        except (ValueError, TypeError):
            return _error(422, "MOBILE_COMMAND_INVALID", "The phone command is malformed.")
        return _json(_command_data(pairing_id, command), policy.max_message_bytes)

    @app.get("/api/v1/mobile/pairings/{pairing_id}/commands/{sequence}")
    async def phone_command_status(
        pairing_id: str,
        sequence: int,
        authorization: Annotated[str | None, Header(alias="Authorization")] = None,
    ) -> Response:
        token = _bearer_token(authorization)
        if token is None:
            return _error(403, "MOBILE_PHONE_TOKEN_REQUIRED", "A phone token is required.")
        try:
            command = bridge.command_status(pairing_id, phone_token=token, sequence=sequence)
        except MobileBridgeError as error:
            return _mobile_error(error)
        return _json(_command_data(pairing_id, command), policy.max_result_bytes)

    if authority_app is not None:
        app.mount("/", PairedPhoneAuthority(authority_app, bridge), name="phone-authority")

    return app


def _command_data(pairing_id: str, command: MobileCommand) -> dict[str, object]:
    return {
        "mobile_contract_version": MOBILE_CONTRACT_VERSION,
        "pairing_id": pairing_id,
        "sequence": command.sequence,
        "kind": command.kind,
        "status": command.status,
        "result": command.result,
        "error": command.error,
    }


async def _send_asgi_error(
    send: Send,
    status: int,
    code: str,
    message: str,
) -> None:
    payload = json.dumps(
        {"diagnostics": [{"code": code, "stage": "mobile-bridge", "message": message}]},
        separators=(",", ":"),
    ).encode("utf-8")
    await send(
        {
            "type": "http.response.start",
            "status": status,
            "headers": [(b"content-type", b"application/json"), (b"cache-control", b"no-store")],
        }
    )
    await send({"type": "http.response.body", "body": payload})


def _network_guard(
    request: Request,
    policy: MobileNetworkPolicy,
    *,
    require_origin: bool,
) -> JSONResponse | None:
    host = request.headers.get("host", "").lower()
    if host != policy.allowed_host:
        return _error(403, "MOBILE_HOST_REJECTED", "The companion host is invalid.")
    origin = request.headers.get("origin")
    if require_origin and origin is None:
        return _error(403, "MOBILE_ORIGIN_REQUIRED", "The companion origin is required.")
    if origin is not None and origin != policy.public_origin:
        return _error(403, "MOBILE_ORIGIN_REJECTED", "The companion origin is invalid.")
    if request.headers.get("sec-fetch-site", "same-origin") not in {"same-origin", "none"}:
        return _error(403, "MOBILE_FETCH_SITE_REJECTED", "Cross-site companion access is denied.")
    return None


def _bearer_token(value: str | None) -> str | None:
    if value is None or not value.startswith("Bearer "):
        return None
    token = value.removeprefix("Bearer ")
    if not token or any(character.isspace() for character in token):
        return None
    return token


async def _read_bounded(request: Request, maximum: int) -> bytes | None:
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


def _json(value: object, maximum: int) -> Response:
    encoded = json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    if len(encoded) > maximum:
        return _error(413, "MOBILE_RESPONSE_TOO_LARGE", "The companion response is too large.")
    return Response(encoded, media_type="application/json")


def _error(status: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(
        {"diagnostics": [{"code": code, "stage": "mobile-bridge", "message": message}]},
        status_code=status,
    )


def _mobile_error(error: MobileBridgeError) -> JSONResponse:
    if error.code in {"MOBILE_CAPABILITY_INVALID", "MOBILE_PHONE_TOKEN_INVALID"}:
        status = 403
    elif error.code in {"MOBILE_PAIRING_EXPIRED", "MOBILE_PAIRING_REVOKED"}:
        status = 410
    elif error.code == "MOBILE_PAIRING_NOT_FOUND":
        status = 404
    elif error.code in {
        "MOBILE_ROLE_OCCUPIED",
        "MOBILE_SEQUENCE_REJECTED",
        "MOBILE_COMMAND_BUSY",
        "MOBILE_COMMAND_ALREADY_COMPLETED",
    }:
        status = 409
    elif error.code == "MOBILE_COMMAND_NOT_FOUND":
        status = 404
    else:
        status = 422
    return _error(status, error.code, str(error))
