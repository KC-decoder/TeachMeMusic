"""Thread-safe, bounded, in-memory canonical package sessions."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from threading import RLock
from time import monotonic
from uuid import uuid4

from teachmemusic.score import CanonicalMusicPackage


class SessionStoreError(LookupError):
    """Stable session storage failure."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


@dataclass(frozen=True, slots=True)
class ScoreSession:
    """The only retained upload state: a validated canonical package."""

    id: str
    package: CanonicalMusicPackage
    created_at: float
    last_accessed_at: float


class SessionStore:
    """Keep a small number of canonical packages for a bounded lifetime."""

    def __init__(
        self,
        *,
        max_sessions: int,
        ttl_seconds: int,
        clock: Callable[[], float] = monotonic,
        id_factory: Callable[[], str] = lambda: uuid4().hex,
    ) -> None:
        self._max_sessions = max_sessions
        self._ttl_seconds = ttl_seconds
        self._clock = clock
        self._id_factory = id_factory
        self._sessions: dict[str, ScoreSession] = {}
        self._lock = RLock()

    def create(self, package: CanonicalMusicPackage) -> ScoreSession:
        with self._lock:
            now = self._clock()
            self._purge_expired(now)
            if len(self._sessions) >= self._max_sessions:
                raise SessionStoreError("APP_SESSION_CAPACITY")
            session_id = self._id_factory()
            if not session_id or session_id in self._sessions:
                raise SessionStoreError("APP_SESSION_ID_FAILURE")
            session = ScoreSession(session_id, package, now, now)
            self._sessions[session_id] = session
            return session

    def get(self, session_id: str) -> ScoreSession:
        with self._lock:
            now = self._clock()
            self._purge_expired(now)
            session = self._sessions.get(session_id)
            if session is None:
                raise SessionStoreError("APP_SESSION_NOT_FOUND")
            touched = ScoreSession(
                session.id,
                session.package,
                session.created_at,
                now,
            )
            self._sessions[session_id] = touched
            return touched

    def delete(self, session_id: str) -> None:
        with self._lock:
            self._sessions.pop(session_id, None)

    def clear(self) -> None:
        with self._lock:
            self._sessions.clear()

    def __len__(self) -> int:
        with self._lock:
            self._purge_expired(self._clock())
            return len(self._sessions)

    def _purge_expired(self, now: float) -> None:
        expired = [
            session_id
            for session_id, session in self._sessions.items()
            if now - session.last_accessed_at >= self._ttl_seconds
        ]
        for session_id in expired:
            del self._sessions[session_id]
