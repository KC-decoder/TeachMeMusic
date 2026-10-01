"""Governed canonical packages used by planner tests."""

from pathlib import Path

import pytest

from teachmemusic.score import CanonicalMusicPackage, parse_musicxml_package

_FIXTURES = Path(__file__).parents[1] / "fixtures" / "scores"


def _package(directory: str, name: str) -> CanonicalMusicPackage:
    path = _FIXTURES / directory / name
    return parse_musicxml_package(path.read_bytes(), logical_name=path.name)


@pytest.fixture(scope="session")
def hot_cross_buns_package() -> CanonicalMusicPackage:
    """Return the governed Hot Cross Buns canonical package."""

    return _package(
        "TMM-REF-CANDIDATE-001-Hot-Cross-Buns",
        "musicxml-17-hot-cross-buns-final-shelbygtdrew.mxl",
    )


@pytest.fixture(scope="session")
def happy_birthday_package() -> CanonicalMusicPackage:
    """Return the governed Happy Birthday canonical package."""

    return _package(
        "TMM-REF-CANDIDATE-002-Happy-Birthday",
        "happy-birthday-to-you-c-major.mxl",
    )


@pytest.fixture(scope="session")
def moonlight_package() -> CanonicalMusicPackage:
    """Return the governed Moonlight Sonata canonical package."""

    return _package(
        "TMM-REF-CANDIDATE-004-Moonlight-Sonata",
        "beethoven-piano-sonata-no-14-moonlight.mxl",
    )
