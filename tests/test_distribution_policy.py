"""Executable evidence for the DEV-004 Task 7J-R6 distribution policy."""

import json
import tomllib
from hashlib import sha256
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).parents[1]
LOCKS = {
    "macos-arm64-py312": ROOT / "requirements/pylock.macos-arm64-py312.toml",
    "macos-arm64-py313": ROOT / "requirements/pylock.macos-arm64-py313.toml",
    "linux-x86_64-py312": ROOT / "requirements/pylock.linux-x86_64-py312.toml",
    "linux-x86_64-py313": ROOT / "requirements/pylock.linux-x86_64-py313.toml",
}
EXPECTED_PACKAGES = {
    "annotated-doc": "0.0.5",
    "annotated-types": "0.8.0",
    "anyio": "4.15.1",
    "ast-serialize": "0.11.2",
    "certifi": "2026.7.22",
    "click": "8.5.0",
    "fastapi": "0.141.1",
    "h11": "0.16.0",
    "httpcore": "1.0.9",
    "httpx": "0.28.1",
    "idna": "3.20",
    "iniconfig": "2.3.0",
    "librt": "0.15.0",
    "lxml": "6.1.3",
    "lxml-stubs": "0.5.1",
    "mypy": "2.3.1",
    "mypy-extensions": "1.1.0",
    "packaging": "26.3",
    "pathspec": "1.1.1",
    "pluggy": "1.6.0",
    "pydantic": "2.13.5",
    "pydantic-core": "2.46.5",
    "pygments": "2.21.0",
    "pytest": "9.1.1",
    "python-multipart": "0.0.32",
    "ruff": "0.16.9",
    "saxonche": "12.9.0",
    "setuptools": "84.0.0",
    "starlette": "1.7.0",
    "typing-inspection": "0.4.4",
    "typing-extensions": "4.16.0",
    "uvicorn": "0.54.0",
}
PLATFORM_PACKAGES = (
    "ast-serialize",
    "librt",
    "lxml",
    "mypy",
    "pydantic-core",
    "ruff",
    "saxonche",
)
WEB_PACKAGE = ROOT / "web/package.json"
WEB_LOCK = ROOT / "web/package-lock.json"
EXPECTED_WEB_DEPENDENCIES = {
    "opensheetmusicdisplay": "2.1.3",
    "react": "19.3.0",
    "react-dom": "19.3.0",
    "tone": "15.1.22",
}
EXPECTED_WEB_DEV_DEPENDENCIES = {
    "@testing-library/jest-dom": "7.0.1",
    "@testing-library/react": "16.3.3",
    "@types/react": "19.3.0",
    "@types/react-dom": "19.3.0",
    "@vitejs/plugin-react": "6.1.1",
    "jsdom": "30.1.1",
    "playwright": "1.60.0",
    "typescript": "6.0.3",
    "vite": "8.3.1",
    "vitest": "5.0.2",
}


def _read_lock(path: Path) -> dict[str, object]:
    return tomllib.loads(path.read_text(encoding="utf-8"))


def test_r6_lock_matrix_is_complete_and_hash_locked() -> None:
    """TEST-NFR-LOCK-001: every accepted environment has one exact wheel lock."""

    assert {path.name for path in (ROOT / "requirements").glob("pylock.*.toml")} == {
        path.name for path in LOCKS.values()
    }
    for path in LOCKS.values():
        lock = _read_lock(path)
        assert lock["lock-version"] == "1.0"
        assert lock["created-by"] == "pip"
        packages = lock["packages"]
        assert isinstance(packages, list)
        versions = {package["name"]: package["version"] for package in packages}
        assert versions == EXPECTED_PACKAGES
        for package in packages:
            wheels = package["wheels"]
            assert isinstance(wheels, list) and wheels
            for wheel in wheels:
                assert urlparse(wheel["url"]).hostname == "files.pythonhosted.org"
                digest = wheel["hashes"]["sha256"]
                assert len(digest) == sha256().digest_size * 2
                assert all(character in "0123456789abcdef" for character in digest)


def test_r6_lock_wheels_match_the_declared_environment() -> None:
    """TEST-NFR-LOCK-002: compiled wheels target each lock's Python/platform."""

    for environment, path in LOCKS.items():
        packages = _read_lock(path)["packages"]
        assert isinstance(packages, list)
        wheels = {
            package["name"]: tuple(wheel["name"] for wheel in package["wheels"])
            for package in packages
        }
        python_tag = "cp312" if environment.endswith("py312") else "cp313"
        platform_tag = "macosx" if environment.startswith("macos") else "manylinux"
        for package_name in PLATFORM_PACKAGES:
            wheel_names = wheels[package_name]
            assert any(platform_tag in name for name in wheel_names)
            if package_name not in {"ast-serialize", "ruff"}:
                assert any(python_tag in name for name in wheel_names)


def test_project_distribution_declares_mit_license() -> None:
    """TEST-NFR-LICENSE-001: source and package metadata record the owner decision."""

    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    license_text = (ROOT / "LICENSE").read_text(encoding="utf-8")

    assert project["license"] == "MIT"
    assert project["requires-python"] == ">=3.12,<3.14"
    assert license_text.startswith("MIT License\n")
    assert "Copyright (c) 2026 TeachMeMusic Contributors" in license_text
    assert "Permission is hereby granted, free of charge" in license_text


def test_dev005_browser_proof_dependencies_are_exact_and_hash_locked() -> None:
    """TEST-NFR-LOCK-003: browser runtime and proof tools use one complete npm lock."""

    manifest = json.loads(WEB_PACKAGE.read_text(encoding="utf-8"))
    lock = json.loads(WEB_LOCK.read_text(encoding="utf-8"))

    assert manifest["dependencies"] == EXPECTED_WEB_DEPENDENCIES
    assert manifest["devDependencies"] == EXPECTED_WEB_DEV_DEPENDENCIES
    assert lock["lockfileVersion"] == 3
    assert lock["packages"][""]["dependencies"] == manifest["dependencies"]
    assert lock["packages"][""]["devDependencies"] == manifest["devDependencies"]
    assert lock["packages"]["node_modules/opensheetmusicdisplay"]["version"] == "2.1.3"
    assert lock["packages"]["node_modules/opensheetmusicdisplay"]["license"] == ("BSD-3-Clause")
    assert lock["packages"]["node_modules/playwright"]["version"] == "1.60.0"
    assert lock["packages"]["node_modules/playwright"]["license"] == "Apache-2.0"
    assert lock["packages"]["node_modules/tone"]["version"] == "15.1.22"
    assert lock["packages"]["node_modules/tone"]["license"] == "MIT"
    for name, package in lock["packages"].items():
        if not name:
            continue
        assert package["version"]
        assert package["integrity"].startswith("sha512-")
        assert urlparse(package["resolved"]).hostname == "registry.npmjs.org"
        assert package["license"]
