"""DEV-004 Task 7H page, system, credit, and print-layout evidence."""

from __future__ import annotations

from fractions import Fraction
from pathlib import Path

import pytest

from teachmemusic.score.parser import parse_musicxml_timeline_package
from teachmemusic.score.v2.serialization import (
    CanonicalSerializationError,
    package_from_dict,
    package_from_json,
    package_to_dict,
    package_to_json,
)

FIXTURES = Path(__file__).resolve().parents[2] / "fixtures/scores"


def _fixture(folder: str, name: str) -> bytes:
    return (FIXTURES / folder / name).read_bytes()


def test_happy_birthday_layout_and_credits_are_exact() -> None:
    """TEST-MXML-PRESENTATION-003: score and measure layout map exactly."""

    name = "happy-birthday-to-you-c-major.mxl"
    package = parse_musicxml_timeline_package(
        _fixture("TMM-REF-CANDIDATE-002-Happy-Birthday", name), logical_name=name
    )
    score = package.documents[0].content.score
    layout = score.layout
    assert layout is not None and layout.defaults is not None
    assert layout.defaults.scaling is not None
    assert (layout.defaults.scaling.millimeters, layout.defaults.scaling.tenths) == (
        Fraction(882, 125),
        Fraction(40),
    )
    assert layout.defaults.page is not None
    assert (layout.defaults.page.height, layout.defaults.page.width) == (
        Fraction(168367, 100),
        Fraction(29762, 25),
    )
    assert [item.value for credit in layout.credits for item in credit.items] == [
        "Happy Birthday to You",
        "Patty Hill  Mildred J. Hill",
    ]

    first = score.parts[0].measures[0].layout
    assert first is not None and first.system is not None
    assert first.width == Fraction(5249, 20)
    assert first.system.margins is not None
    assert (first.system.margins.left, first.system.margins.right) == (
        Fraction(8601, 100),
        Fraction(0),
    )
    assert first.system.top_system_distance == Fraction(180)
    assert first.staves[0].number == "2"
    assert first.staves[0].distance == Fraction(65)
    assert sum(measure.layout.new_system is True for measure in score.parts[0].measures) == 1
    assert package_from_json(package_to_json(package)) == package


def test_clair_de_lune_layout_breaks_and_credits_are_complete() -> None:
    """TEST-MXML-PRESENTATION-004: complex fixture layout remains ordered."""

    name = "clair-de-lune-debussy.mxl"
    package = parse_musicxml_timeline_package(
        _fixture("TMM-REF-CANDIDATE-003-Clair-de-Lune", name), logical_name=name
    )
    score = package.documents[0].content.score
    assert score.layout is not None
    assert [(credit.types, len(credit.items)) for credit in score.layout.credits] == [
        (("title",), 1),
        (("subtitle",), 4),
        (("composer",), 2),
    ]
    measures = score.parts[0].measures
    assert len(measures) == 72
    assert sum(measure.layout.new_page is True for measure in measures) == 5
    assert sum(measure.layout.new_system is True for measure in measures) == 23
    assert package_from_json(package_to_json(package)) == package


def test_layout_validation_rejects_invalid_scaling() -> None:
    """TEST-MXML-PRESENTATION-005: malformed canonical layout fails closed."""

    name = "happy-birthday-to-you-c-major.mxl"
    package = parse_musicxml_timeline_package(
        _fixture("TMM-REF-CANDIDATE-002-Happy-Birthday", name), logical_name=name
    )
    modified = package_to_dict(package)
    modified["documents"][0]["content"]["score"]["layout"]["defaults"]["scaling"]["tenths"] = {
        "numerator": 0,
        "denominator": 1,
    }
    with pytest.raises(CanonicalSerializationError, match="TEMPORAL_SCORE_LAYOUT"):
        package_from_dict(modified)
