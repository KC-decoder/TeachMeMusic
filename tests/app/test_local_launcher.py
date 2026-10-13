"""Repository-launch contract for the local application."""

from __future__ import annotations

import os
import tomllib
from pathlib import Path

ROOT = Path(__file__).parents[2]


def test_local_launch_scripts_are_executable_and_documented() -> None:
    """TEST-APP-LAUNCH-001: a clone exposes one documented setup/run path."""

    setup = ROOT / "scripts/setup-local.sh"
    run = ROOT / "scripts/run-local.sh"
    guide = (ROOT / "RUN_LOCAL.md").read_text(encoding="utf-8")

    assert setup.is_file() and os.access(setup, os.X_OK)
    assert run.is_file() and os.access(run, os.X_OK)
    assert "./scripts/setup-local.sh" in guide
    assert "./scripts/run-local.sh" in guide
    assert "127.0.0.1" in guide
    assert 'export PYTHONPATH="$PROJECT_ROOT/src${PYTHONPATH:+:$PYTHONPATH}"' in run.read_text(
        encoding="utf-8"
    )

    mobile = ROOT / "scripts/run-mobile.sh"
    assert mobile.is_file() and os.access(mobile, os.X_OK)
    mobile_source = mobile.read_text(encoding="utf-8")
    assert "teachmemusic.app.mobile_server" in mobile_source
    assert 'export PYTHONPATH="$PROJECT_ROOT/src${PYTHONPATH:+:$PYTHONPATH}"' in mobile_source


def test_local_console_entry_point_targets_loopback_server() -> None:
    """TEST-APP-LAUNCH-002: installed clones expose the same bounded launcher."""

    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    assert project["scripts"]["teachmemusic-local"] == "teachmemusic.app.server:main"
    assert project["scripts"]["teachmemusic-mobile"] == "teachmemusic.app.mobile_server:main"


def test_required_plain_pytest_command_has_repository_import_path() -> None:
    """TEST-APP-LAUNCH-003: plain pytest resolves the src-layout package."""

    configuration = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))

    assert configuration["tool"]["pytest"]["ini_options"]["pythonpath"] == ["src"]
    assert ".venv" in (ROOT / "scripts/setup-local.sh").read_text(encoding="utf-8")
