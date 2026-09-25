"""Executable evidence for the DEV-004 Task 7J-R6 distribution policy."""

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
    "ast-serialize": "0.11.2",
    "iniconfig": "2.3.0",
    "librt": "0.15.0",
    "lxml": "6.1.3",
    "lxml-stubs": "0.5.1",
    "mypy": "2.3.1",
    "mypy-extensions": "1.1.0",
    "packaging": "26.3",
    "pathspec": "1.1.1",
    "pluggy": "1.6.0",
    "pygments": "2.21.0",
    "pytest": "9.1.1",
    "ruff": "0.16.9",
    "saxonche": "12.9.0",
    "setuptools": "84.0.0",
    "typing-extensions": "4.16.0",
}
PLATFORM_PACKAGES = ("ast-serialize", "librt", "lxml", "mypy", "ruff", "saxonche")


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
