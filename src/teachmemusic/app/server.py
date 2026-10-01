"""Loopback-only Uvicorn launcher for the local TeachMeMusic application."""

from __future__ import annotations

import secrets
import socket
from pathlib import Path

import uvicorn

from .api import create_app


def create_loopback_socket() -> socket.socket:
    """Reserve an ephemeral IPv4 loopback port for Uvicorn."""

    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    listener.bind(("127.0.0.1", 0))
    listener.listen(2048)
    return listener


def main() -> None:
    """Run the compiled local application on an ephemeral loopback port."""

    frontend = Path(__file__).resolve().parents[3] / "web" / "dist"
    if not frontend.is_dir():
        raise SystemExit("Frontend build missing: run `npm run build` in web/.")
    token = secrets.token_urlsafe(32)
    listener = create_loopback_socket()
    port = listener.getsockname()[1]
    app = create_app(launch_token=token, static_directory=frontend)
    print(f"TeachMeMusic: http://127.0.0.1:{port}/")
    config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="info")
    try:
        uvicorn.Server(config).run(sockets=[listener])
    except KeyboardInterrupt:
        pass
    finally:
        listener.close()


if __name__ == "__main__":
    main()
