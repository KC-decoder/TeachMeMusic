"""Ephemeral, role-bounded state for the DEV-007 mobile companion bridge."""

from __future__ import annotations

import hashlib
import hmac
import math
import secrets
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from threading import RLock
from typing import Literal

MobileRole = Literal["phone", "midi-bridge"]
BridgeConnection = Literal["connected", "disconnected", "unavailable"]
CompanionAvailability = Literal["live", "stale", "disconnected", "unavailable"]
BridgeCapture = Literal["idle", "recording", "paused", "stopped", "aborted"]
BridgeCapturePurpose = Literal["calibration", "attempt"] | None
MobileCommandKind = Literal[
    "start-attempt",
    "pause-attempt",
    "resume-attempt",
    "finish-attempt",
    "abort-attempt",
    "safe-stop",
    "submit-attempt",
]
MobileCommandStatus = Literal["pending", "processing", "completed", "failed"]


class MobileBridgeError(ValueError):
    """Stable fail-closed error raised by the ephemeral bridge store."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True, slots=True)
class PairingOffer:
    """One owner-created, short-lived, role-specific pairing offer."""

    id: str
    phone_capability: str
    bridge_capability: str
    expires_in_seconds: int


@dataclass(frozen=True, slots=True)
class BridgeMessage:
    """Sanitized transient MIDI state; never raw performance evidence."""

    sequence: int
    sent_at_microseconds: int
    connection: BridgeConnection
    active_notes: tuple[int, ...]
    capture: BridgeCapture = "idle"
    capture_purpose: BridgeCapturePurpose = None
    calibration_approved: bool = False


@dataclass(frozen=True, slots=True)
class CompanionSnapshot:
    """State visible to a paired phone."""

    pairing_id: str
    availability: CompanionAvailability
    sequence: int
    active_notes: tuple[int, ...]
    age_microseconds: int | None
    expires_in_seconds: int
    capture: BridgeCapture
    capture_purpose: BridgeCapturePurpose
    calibration_approved: bool


@dataclass(frozen=True, slots=True)
class MobileCommand:
    """One bounded phone request for the paired desktop MIDI session."""

    sequence: int
    kind: MobileCommandKind
    status: MobileCommandStatus
    context: Mapping[str, object]
    result: Mapping[str, object] | None
    error: str | None


@dataclass(frozen=True, slots=True)
class PairingStatus:
    """Secret-free owner inspection of one pairing."""

    pairing_id: str
    phone_claimed: bool
    bridge_claimed: bool
    revoked: bool
    last_sequence: int
    availability: CompanionAvailability
    expires_in_seconds: int


@dataclass(slots=True)
class _Pairing:
    id: str
    phone_capability_digest: bytes | None
    bridge_capability_digest: bytes | None
    phone_token_digest: bytes | None
    bridge_token_digest: bytes | None
    expires_at: float
    revoked: bool = False
    last_sequence: int = 0
    last_message: BridgeMessage | None = None
    last_received_at: float | None = None
    last_command_sequence: int = 0
    command: MobileCommand | None = None


def _digest(secret: str) -> bytes:
    return hashlib.sha256(secret.encode("utf-8")).digest()


def _matches(secret: str, expected: bytes | None) -> bool:
    return expected is not None and hmac.compare_digest(_digest(secret), expected)


class MobileBridgeStore:
    """Thread-safe, memory-only pairing and sanitized live MIDI state."""

    def __init__(
        self,
        *,
        max_pairings: int = 1,
        maximum_ttl_seconds: int = 10 * 60,
        stale_after_seconds: float = 2.0,
        max_active_notes: int = 16,
        clock: Callable[[], float] = time.monotonic,
        id_factory: Callable[[], str] | None = None,
        secret_factory: Callable[[], str] | None = None,
    ) -> None:
        if max_pairings < 1 or maximum_ttl_seconds < 1 or stale_after_seconds <= 0:
            raise ValueError("mobile bridge limits must be positive")
        if max_active_notes < 1 or max_active_notes > 128:
            raise ValueError("max_active_notes must be between 1 and 128")
        self._max_pairings = max_pairings
        self._maximum_ttl_seconds = maximum_ttl_seconds
        self._stale_after_seconds = stale_after_seconds
        self._max_active_notes = max_active_notes
        self._clock = clock
        self._id_factory = id_factory or (lambda: secrets.token_urlsafe(18))
        self._secret_factory = secret_factory or (lambda: secrets.token_urlsafe(32))
        self._pairings: dict[str, _Pairing] = {}
        self._lock = RLock()

    @property
    def maximum_ttl_seconds(self) -> int:
        return self._maximum_ttl_seconds

    @property
    def max_active_notes(self) -> int:
        return self._max_active_notes

    def create(self, *, ttl_seconds: int) -> PairingOffer:
        """Create one explicit pairing with separate one-time role capabilities."""

        if ttl_seconds < 1 or ttl_seconds > self._maximum_ttl_seconds:
            raise MobileBridgeError(
                "MOBILE_PAIRING_TTL_INVALID",
                "The pairing lifetime is outside the allowed range.",
            )
        with self._lock:
            self._discard_inactive()
            active = sum(1 for item in self._pairings.values() if not item.revoked)
            if active >= self._max_pairings:
                raise MobileBridgeError(
                    "MOBILE_PAIRING_CAPACITY",
                    "The bounded mobile pairing capacity is already in use.",
                )
            pairing_id = self._id_factory()
            if not pairing_id or pairing_id in self._pairings:
                raise MobileBridgeError(
                    "MOBILE_PAIRING_ID_INVALID", "A unique pairing ID could not be created."
                )
            phone_capability = self._new_secret()
            bridge_capability = self._new_secret(exclude={phone_capability})
            self._pairings[pairing_id] = _Pairing(
                id=pairing_id,
                phone_capability_digest=_digest(phone_capability),
                bridge_capability_digest=_digest(bridge_capability),
                phone_token_digest=None,
                bridge_token_digest=None,
                expires_at=self._clock() + ttl_seconds,
            )
            return PairingOffer(
                id=pairing_id,
                phone_capability=phone_capability,
                bridge_capability=bridge_capability,
                expires_in_seconds=ttl_seconds,
            )

    def claim(self, pairing_id: str, *, role: MobileRole, capability: str) -> str:
        """Consume the exact role capability and return one bearer token."""

        if role not in {"phone", "midi-bridge"}:
            raise MobileBridgeError("MOBILE_ROLE_INVALID", "The requested role is invalid.")
        with self._lock:
            pairing = self._require_pairing(pairing_id)
            capability_digest = (
                pairing.phone_capability_digest
                if role == "phone"
                else pairing.bridge_capability_digest
            )
            token_digest = (
                pairing.phone_token_digest if role == "phone" else pairing.bridge_token_digest
            )
            if token_digest is not None:
                raise MobileBridgeError(
                    "MOBILE_ROLE_OCCUPIED", f"The {role} role is already paired."
                )
            if not _matches(capability, capability_digest):
                raise MobileBridgeError(
                    "MOBILE_CAPABILITY_INVALID", "The role pairing capability is invalid."
                )
            token = self._new_secret()
            if role == "phone":
                pairing.phone_capability_digest = None
                pairing.phone_token_digest = _digest(token)
            else:
                pairing.bridge_capability_digest = None
                pairing.bridge_token_digest = _digest(token)
            return token

    def publish(self, pairing_id: str, *, token: str, message: BridgeMessage) -> None:
        """Accept one ordered, sanitized message from the paired MIDI bridge."""

        with self._lock:
            pairing = self._require_pairing(pairing_id)
            if not _matches(token, pairing.bridge_token_digest):
                raise MobileBridgeError(
                    "MOBILE_BRIDGE_TOKEN_INVALID", "The MIDI-bridge token is invalid."
                )
            if message.sequence != pairing.last_sequence + 1:
                raise MobileBridgeError(
                    "MOBILE_SEQUENCE_REJECTED",
                    "The bridge sequence is duplicated, reordered, or incomplete.",
                )
            notes = message.active_notes
            if len(notes) > self._max_active_notes:
                raise MobileBridgeError(
                    "MOBILE_ACTIVE_NOTE_LIMIT", "Too many simultaneously held notes were sent."
                )
            if tuple(sorted(set(notes))) != notes or any(note < 0 or note > 127 for note in notes):
                raise MobileBridgeError(
                    "MOBILE_ACTIVE_NOTES_INVALID",
                    "Active MIDI notes must be unique, sorted integers from 0 through 127.",
                )
            if message.connection != "connected" and notes:
                raise MobileBridgeError(
                    "MOBILE_CONNECTION_STATE_INVALID",
                    "Disconnected or unavailable bridge state cannot retain held notes.",
                )
            if message.connection != "connected" and message.capture in {"recording", "paused"}:
                raise MobileBridgeError(
                    "MOBILE_CAPTURE_STATE_INVALID",
                    "Disconnected bridge state cannot retain an active capture.",
                )
            if message.capture_purpose is None and message.capture != "idle":
                raise MobileBridgeError(
                    "MOBILE_CAPTURE_PURPOSE_INVALID",
                    "A non-idle capture must identify its bounded purpose.",
                )
            if message.capture_purpose == "attempt" and not message.calibration_approved:
                raise MobileBridgeError(
                    "MOBILE_CALIBRATION_REQUIRED",
                    "Attempt capture state requires an approved desktop calibration.",
                )
            pairing.last_sequence = message.sequence
            pairing.last_message = message
            pairing.last_received_at = self._clock()

    def snapshot(self, pairing_id: str, *, phone_token: str) -> CompanionSnapshot:
        """Return the current phone state, clearing notes when stale or disconnected."""

        with self._lock:
            pairing = self._require_pairing(pairing_id)
            if not _matches(phone_token, pairing.phone_token_digest):
                raise MobileBridgeError("MOBILE_PHONE_TOKEN_INVALID", "The phone token is invalid.")
            availability, notes, age, capture, purpose, approved = self._current_state(pairing)
            return CompanionSnapshot(
                pairing_id=pairing.id,
                availability=availability,
                sequence=pairing.last_sequence,
                active_notes=notes,
                age_microseconds=age,
                expires_in_seconds=self._expires_in(pairing),
                capture=capture,
                capture_purpose=purpose,
                calibration_approved=approved,
            )

    def authorize_phone(self, pairing_id: str, *, phone_token: str) -> None:
        """Validate the paired phone capability without exposing bridge state."""

        with self._lock:
            pairing = self._require_pairing(pairing_id)
            if not _matches(phone_token, pairing.phone_token_digest):
                raise MobileBridgeError("MOBILE_PHONE_TOKEN_INVALID", "The phone token is invalid.")

    def request_command(
        self,
        pairing_id: str,
        *,
        phone_token: str,
        kind: MobileCommandKind,
        context: Mapping[str, object] | None = None,
    ) -> MobileCommand:
        """Queue one explicit phone command; concurrent commands fail closed."""

        with self._lock:
            pairing = self._require_pairing(pairing_id)
            if not _matches(phone_token, pairing.phone_token_digest):
                raise MobileBridgeError("MOBILE_PHONE_TOKEN_INVALID", "The phone token is invalid.")
            current = pairing.command
            if current is not None and current.status in {"pending", "processing"}:
                raise MobileBridgeError(
                    "MOBILE_COMMAND_BUSY",
                    "The previous phone command has not completed.",
                )
            sequence = pairing.last_command_sequence + 1
            command = MobileCommand(
                sequence=sequence,
                kind=kind,
                status="pending",
                context=dict(context or {}),
                result=None,
                error=None,
            )
            pairing.last_command_sequence = sequence
            pairing.command = command
            return command

    def bridge_command(self, pairing_id: str, *, bridge_token: str) -> MobileCommand | None:
        """Return the one outstanding command to the paired desktop bridge."""

        with self._lock:
            pairing = self._require_pairing(pairing_id)
            if not _matches(bridge_token, pairing.bridge_token_digest):
                raise MobileBridgeError(
                    "MOBILE_BRIDGE_TOKEN_INVALID", "The MIDI-bridge token is invalid."
                )
            command = pairing.command
            if command is None or command.status in {"completed", "failed"}:
                return None
            if command.status == "pending":
                command = MobileCommand(
                    sequence=command.sequence,
                    kind=command.kind,
                    status="processing",
                    context=dict(command.context),
                    result=None,
                    error=None,
                )
                pairing.command = command
            return command

    def complete_command(
        self,
        pairing_id: str,
        *,
        bridge_token: str,
        sequence: int,
        result: Mapping[str, object] | None = None,
        error: str | None = None,
    ) -> MobileCommand:
        """Complete one relayed command with an authoritative result or explicit failure."""

        with self._lock:
            pairing = self._require_pairing(pairing_id)
            if not _matches(bridge_token, pairing.bridge_token_digest):
                raise MobileBridgeError(
                    "MOBILE_BRIDGE_TOKEN_INVALID", "The MIDI-bridge token is invalid."
                )
            command = pairing.command
            if command is None or command.sequence != sequence:
                raise MobileBridgeError(
                    "MOBILE_COMMAND_SEQUENCE_REJECTED",
                    "The command acknowledgement does not match the outstanding command.",
                )
            if command.status not in {"pending", "processing"}:
                raise MobileBridgeError(
                    "MOBILE_COMMAND_ALREADY_COMPLETED",
                    "The command was already completed.",
                )
            if (result is None) == (error is None):
                raise MobileBridgeError(
                    "MOBILE_COMMAND_RESULT_INVALID",
                    "A command must complete with exactly one result or error.",
                )
            completed = MobileCommand(
                sequence=command.sequence,
                kind=command.kind,
                status="failed" if error is not None else "completed",
                context=dict(command.context),
                result=None if result is None else dict(result),
                error=error,
            )
            pairing.command = completed
            return completed

    def command_status(
        self,
        pairing_id: str,
        *,
        phone_token: str,
        sequence: int,
    ) -> MobileCommand:
        """Return only the requested command's bounded status to the paired phone."""

        with self._lock:
            pairing = self._require_pairing(pairing_id)
            if not _matches(phone_token, pairing.phone_token_digest):
                raise MobileBridgeError("MOBILE_PHONE_TOKEN_INVALID", "The phone token is invalid.")
            command = pairing.command
            if command is None or command.sequence != sequence:
                raise MobileBridgeError(
                    "MOBILE_COMMAND_NOT_FOUND", "The requested mobile command is unavailable."
                )
            return command

    def status(self, pairing_id: str) -> PairingStatus:
        """Return owner-visible state without capabilities or bearer tokens."""

        with self._lock:
            pairing = self._require_pairing(pairing_id, permit_revoked=True)
            availability, _, _, _, _, _ = self._current_state(pairing)
            return PairingStatus(
                pairing_id=pairing.id,
                phone_claimed=pairing.phone_token_digest is not None,
                bridge_claimed=pairing.bridge_token_digest is not None,
                revoked=pairing.revoked,
                last_sequence=pairing.last_sequence,
                availability=availability,
                expires_in_seconds=self._expires_in(pairing),
            )

    def revoke(self, pairing_id: str) -> None:
        """Immediately invalidate both roles and erase transient state."""

        with self._lock:
            pairing = self._require_pairing(pairing_id, permit_revoked=True)
            pairing.revoked = True
            pairing.phone_capability_digest = None
            pairing.bridge_capability_digest = None
            pairing.phone_token_digest = None
            pairing.bridge_token_digest = None
            pairing.last_message = None
            pairing.last_received_at = None
            pairing.command = None

    def clear(self) -> None:
        with self._lock:
            self._pairings.clear()

    def _current_state(
        self, pairing: _Pairing
    ) -> tuple[
        CompanionAvailability,
        tuple[int, ...],
        int | None,
        BridgeCapture,
        BridgeCapturePurpose,
        bool,
    ]:
        if pairing.revoked:
            return "unavailable", (), None, "idle", None, False
        message = pairing.last_message
        received_at = pairing.last_received_at
        if message is None or received_at is None:
            return "unavailable", (), None, "idle", None, False
        age_seconds = max(0.0, self._clock() - received_at)
        age_microseconds = round(age_seconds * 1_000_000)
        if age_seconds > self._stale_after_seconds:
            return "stale", (), age_microseconds, "idle", None, False
        if message.connection == "disconnected":
            return (
                "disconnected",
                (),
                age_microseconds,
                message.capture,
                message.capture_purpose,
                False,
            )
        if message.connection == "unavailable":
            return (
                "unavailable",
                (),
                age_microseconds,
                message.capture,
                message.capture_purpose,
                False,
            )
        return (
            "live",
            message.active_notes,
            age_microseconds,
            message.capture,
            message.capture_purpose,
            message.calibration_approved,
        )

    def _require_pairing(self, pairing_id: str, *, permit_revoked: bool = False) -> _Pairing:
        pairing = self._pairings.get(pairing_id)
        if pairing is None:
            raise MobileBridgeError(
                "MOBILE_PAIRING_NOT_FOUND", "The mobile pairing is unavailable."
            )
        if self._clock() >= pairing.expires_at:
            self._pairings.pop(pairing_id, None)
            raise MobileBridgeError("MOBILE_PAIRING_EXPIRED", "The mobile pairing has expired.")
        if pairing.revoked and not permit_revoked:
            raise MobileBridgeError("MOBILE_PAIRING_REVOKED", "The mobile pairing was revoked.")
        return pairing

    def _discard_inactive(self) -> None:
        now = self._clock()
        self._pairings = {
            pairing_id: pairing
            for pairing_id, pairing in self._pairings.items()
            if not pairing.revoked and now < pairing.expires_at
        }

    def _expires_in(self, pairing: _Pairing) -> int:
        return max(0, math.ceil(pairing.expires_at - self._clock()))

    def _new_secret(self, *, exclude: set[str] | None = None) -> str:
        excluded = exclude or set()
        for _ in range(8):
            value = self._secret_factory()
            if len(value) >= 32 and value not in excluded:
                return value
        raise MobileBridgeError(
            "MOBILE_SECRET_INVALID", "A high-entropy pairing secret could not be created."
        )
