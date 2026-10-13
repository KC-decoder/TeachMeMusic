"""Explicit dual-listener launcher for the secure local phone companion."""

from __future__ import annotations

import argparse
import asyncio
import ipaddress
import os
import secrets
import socket
from collections.abc import Sequence
from pathlib import Path

import uvicorn

from .api import create_app
from .budgets import DEFAULT_APP_BUDGETS
from .curriculum_runs import default_curriculum_store
from .mobile_api import MobileNetworkPolicy, create_mobile_companion_app
from .mobile_bridge import MobileBridgeStore
from .server import create_loopback_socket
from .sessions import SessionStore
from .teaching_runs import TeachingRunStore

_IPV4_PRIVATE_NETWORKS = tuple(
    ipaddress.ip_network(value) for value in ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16")
)
_IPV6_PRIVATE_NETWORK = ipaddress.ip_network("fc00::/7")


def private_interface_address(value: str) -> ipaddress.IPv4Address | ipaddress.IPv6Address:
    """Require one concrete RFC1918 or IPv6 unique-local interface address."""

    try:
        address = ipaddress.ip_address(value)
    except ValueError as error:
        raise ValueError("--host must be one explicit private IP address") from error
    allowed = (
        any(address in network for network in _IPV4_PRIVATE_NETWORKS)
        if isinstance(address, ipaddress.IPv4Address)
        else address in _IPV6_PRIVATE_NETWORK
    )
    if not allowed:
        raise ValueError("--host must be an RFC1918 or IPv6 unique-local address")
    return address


def create_private_network_socket(host: str, port: int) -> socket.socket:
    """Bind only the selected private interface; wildcard binding is impossible."""

    address = private_interface_address(host)
    if port < 1 or port > 65_535:
        raise ValueError("--port must be between 1 and 65535")
    family = socket.AF_INET6 if isinstance(address, ipaddress.IPv6Address) else socket.AF_INET
    listener = socket.socket(family, socket.SOCK_STREAM)
    listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        listener.bind((host, port))
        listener.listen(64)
    except Exception:
        listener.close()
        raise
    return listener


def require_tls_file(value: str, *, label: str) -> Path:
    """Resolve one explicit existing TLS file without creating credentials."""

    path = Path(value).expanduser().resolve()
    if not path.is_file() or not os.access(path, os.R_OK):
        raise ValueError(f"{label} does not identify a readable file")
    return path


def companion_origin(host: str, port: int) -> str:
    address = private_interface_address(host)
    rendered_host = f"[{address}]" if isinstance(address, ipaddress.IPv6Address) else str(address)
    suffix = "" if port == 443 else f":{port}"
    return f"https://{rendered_host}{suffix}"


async def _serve(
    *,
    host: str,
    port: int,
    certfile: Path,
    keyfile: Path,
) -> None:
    frontend = Path(__file__).resolve().parents[3] / "web" / "dist"
    if not frontend.is_dir():
        raise RuntimeError("Frontend build missing: run `npm run build` in web/.")
    loopback_socket = create_loopback_socket()
    companion_socket = create_private_network_socket(host, port)
    loopback_port = loopback_socket.getsockname()[1]
    origin = companion_origin(host, companion_socket.getsockname()[1])
    launch_token = secrets.token_urlsafe(32)
    companion_launch_token = secrets.token_urlsafe(32)
    bridge = MobileBridgeStore()
    sessions = SessionStore(
        max_sessions=DEFAULT_APP_BUDGETS.max_sessions,
        ttl_seconds=DEFAULT_APP_BUDGETS.session_ttl_seconds,
    )
    teaching_runs = TeachingRunStore(max_runs=DEFAULT_APP_BUDGETS.max_sessions)
    curriculum_runs = default_curriculum_store(
        Path(__file__).resolve().parents[3] / ".teachmemusic" / "evidence"
    )
    loopback_app = create_app(
        launch_token=launch_token,
        store=sessions,
        teaching_store=teaching_runs,
        curriculum_store=curriculum_runs,
        static_directory=frontend,
        mobile_bridge=bridge,
        mobile_companion_origin=origin,
    )
    phone_authority_app = create_app(
        launch_token=companion_launch_token,
        store=sessions,
        teaching_store=teaching_runs,
        curriculum_store=curriculum_runs,
        static_directory=frontend,
    )
    companion_app = create_mobile_companion_app(
        bridge=bridge,
        policy=MobileNetworkPolicy(public_origin=origin),
        authority_app=phone_authority_app,
    )
    loopback_server = uvicorn.Server(
        uvicorn.Config(loopback_app, host="127.0.0.1", port=loopback_port, log_level="info")
    )
    companion_server = uvicorn.Server(
        uvicorn.Config(
            companion_app,
            host=host,
            port=companion_socket.getsockname()[1],
            log_level="info",
            ssl_certfile=str(certfile),
            ssl_keyfile=str(keyfile),
        )
    )
    print(f"TeachMeMusic desktop: http://127.0.0.1:{loopback_port}/")
    print(f"TeachMeMusic companion: {origin}/")
    print("The companion listener is temporary; stop it with Control-C to revoke all state.")
    tasks = {
        asyncio.create_task(loopback_server.serve(sockets=[loopback_socket])),
        asyncio.create_task(companion_server.serve(sockets=[companion_socket])),
    }
    try:
        done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        loopback_server.should_exit = True
        companion_server.should_exit = True
        results = await asyncio.gather(*done, *pending, return_exceptions=True)
        for result in results:
            if isinstance(result, BaseException):
                raise result
    finally:
        bridge.clear()
        loopback_socket.close()
        companion_socket.close()


def main(arguments: Sequence[str] | None = None) -> None:
    """Run the opt-in desktop authority and HTTPS companion listeners."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", required=True, help="Explicit private Mac interface address")
    parser.add_argument("--port", type=int, default=8443, help="HTTPS companion port")
    parser.add_argument("--certfile", required=True, help="Locally trusted TLS certificate")
    parser.add_argument("--keyfile", required=True, help="Private key for the TLS certificate")
    parsed = parser.parse_args(arguments)
    try:
        private_interface_address(parsed.host)
        certfile = require_tls_file(parsed.certfile, label="--certfile")
        keyfile = require_tls_file(parsed.keyfile, label="--keyfile")
        asyncio.run(
            _serve(
                host=parsed.host,
                port=parsed.port,
                certfile=certfile,
                keyfile=keyfile,
            )
        )
    except ValueError as error:
        parser.error(str(error))
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
