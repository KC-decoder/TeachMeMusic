"""Task 5C session and launcher unit tests."""

import socket
from typing import Any

import pytest

import teachmemusic.app.server as server_module
from teachmemusic.app.server import create_loopback_socket
from teachmemusic.app.sessions import SessionStore, SessionStoreError


def test_app_008_unknown_session_has_stable_error() -> None:
    """TEST-APP-008: an opaque missing session does not leak internal state."""

    store = SessionStore(max_sessions=1, ttl_seconds=10)
    with pytest.raises(SessionStoreError, match="APP_SESSION_NOT_FOUND"):
        store.get("not-present")


def test_app_009_server_socket_is_ephemeral_loopback_only(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """TEST-APP-009: the launcher never binds a public or fixed address."""

    calls: list[tuple[str, Any]] = []

    class FakeSocket:
        def setsockopt(self, *args: object) -> None:
            calls.append(("setsockopt", args))

        def bind(self, address: tuple[str, int]) -> None:
            calls.append(("bind", address))

        def listen(self, backlog: int) -> None:
            calls.append(("listen", backlog))

    fake = FakeSocket()
    monkeypatch.setattr(socket, "socket", lambda *args: fake)
    assert create_loopback_socket() is fake
    assert ("bind", ("127.0.0.1", 0)) in calls


def test_app_010_normal_interrupt_closes_the_listener(monkeypatch: pytest.MonkeyPatch) -> None:
    """TEST-APP-010: normal local shutdown does not leak a socket or traceback."""

    class FakeSocket:
        closed = False

        def getsockname(self) -> tuple[str, int]:
            return ("127.0.0.1", 12345)

        def close(self) -> None:
            self.closed = True

    class FakeServer:
        def __init__(self, _: object) -> None:
            pass

        def run(self, *, sockets: list[FakeSocket]) -> None:
            assert sockets == [listener]
            raise KeyboardInterrupt

    listener = FakeSocket()
    monkeypatch.setattr(server_module, "create_loopback_socket", lambda: listener)
    monkeypatch.setattr(server_module, "create_app", lambda **_: object())
    monkeypatch.setattr(server_module.uvicorn, "Config", lambda *args, **kwargs: object())
    monkeypatch.setattr(server_module.uvicorn, "Server", FakeServer)
    server_module.main()
    assert listener.closed
