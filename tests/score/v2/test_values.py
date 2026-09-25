"""Tests for exact and source-state-aware schema-v2 values."""

from decimal import Decimal
from fractions import Fraction

import pytest

from teachmemusic.score.v2.serialization import (
    CanonicalSerializationError,
    exact_number_from_dict,
    exact_number_to_dict,
    measured_value_from_dict,
    measured_value_to_dict,
)
from teachmemusic.score.v2.validation import (
    validate_exact_number,
    validate_specified_value,
)
from teachmemusic.score.v2.values import (
    CanonicalUnit,
    ExactDecimal,
    ExactInteger,
    ExactRational,
    MeasuredValue,
    SpecifiedValue,
    ValueState,
)


def test_exact_numbers_round_trip_without_binary_float() -> None:
    """TEST-MXML-INVARIANT-001: exact integer, decimal, and rational values survive JSON."""

    values = (
        ExactInteger(42),
        ExactDecimal(Decimal("1.2300")),
        ExactRational.from_fraction(Fraction(7, 12)),
    )

    assert tuple(exact_number_from_dict(exact_number_to_dict(value)) for value in values) == values
    assert exact_number_to_dict(values[1]) == {"kind": "decimal", "value": "1.2300"}
    assert not validate_exact_number(values[2], "value")

    measured = MeasuredValue(values[2], CanonicalUnit.QUARTER_NOTE)
    assert measured_value_from_dict(measured_value_to_dict(measured)) == measured


def test_noncanonical_exact_numbers_fail_closed() -> None:
    """TEST-MXML-INVARIANT-002: invalid or unreduced exact numbers cannot serialize."""

    assert validate_exact_number(ExactRational(2, 4), "value")[0].code == (
        "V2_EXACT_RATIONAL_NOT_REDUCED"
    )
    with pytest.raises(CanonicalSerializationError, match="reduced form"):
        exact_number_to_dict(ExactRational(2, 4))
    with pytest.raises(CanonicalSerializationError, match="finite Decimal"):
        exact_number_to_dict(ExactDecimal(Decimal("NaN")))


def test_specified_values_keep_source_state_distinct() -> None:
    """TEST-MXML-INVARIANT-003: explicit, empty, default, inherited, and unknown differ."""

    values = (
        SpecifiedValue.explicit("major"),
        SpecifiedValue[str].explicit_empty(),
        SpecifiedValue.defaulted("major"),
        SpecifiedValue.inherited("major"),
        SpecifiedValue[str].unknown(),
    )

    assert tuple(value.state for value in values) == tuple(ValueState)
    assert all(not validate_specified_value(value, "value") for value in values)
    invalid = SpecifiedValue(ValueState.UNKNOWN, "invented")
    assert validate_specified_value(invalid, "value")[0].code == "V2_VALUE_UNEXPECTED"
