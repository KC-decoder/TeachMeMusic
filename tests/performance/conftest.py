"""Governed canonical package used by performance-alignment tests."""

from pathlib import Path

import pytest

from teachmemusic.score import CanonicalMusicPackage, parse_musicxml_package

_FIXTURES = Path(__file__).parents[1] / "fixtures" / "scores"


@pytest.fixture(scope="session")
def hot_cross_buns_package() -> CanonicalMusicPackage:
    """Return the governed Hot Cross Buns canonical package."""

    path = (
        _FIXTURES
        / "TMM-REF-CANDIDATE-001-Hot-Cross-Buns"
        / "musicxml-17-hot-cross-buns-final-shelbygtdrew.mxl"
    )
    return parse_musicxml_package(path.read_bytes(), logical_name=path.name)
