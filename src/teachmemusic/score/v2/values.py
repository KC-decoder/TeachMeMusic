"""Exact and source-state-aware values for canonical schema version 2."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum
from fractions import Fraction


class ValueState(StrEnum):
    """How a canonical value relates to its source expression."""

    EXPLICIT_VALUE = "explicit-value"
    EXPLICIT_EMPTY = "explicit-empty"
    DEFAULTED = "defaulted"
    INHERITED = "inherited"
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class SpecifiedValue[T]:
    """A resolved value paired with its source-presence state."""

    state: ValueState
    value: T | None = None

    @classmethod
    def explicit(cls, value: T) -> SpecifiedValue[T]:
        """Construct a source-explicit non-empty value."""

        return cls(ValueState.EXPLICIT_VALUE, value)

    @classmethod
    def explicit_empty(cls) -> SpecifiedValue[T]:
        """Construct a source-explicit empty value."""

        return cls(ValueState.EXPLICIT_EMPTY)

    @classmethod
    def defaulted(cls, value: T) -> SpecifiedValue[T]:
        """Construct a value supplied by a standard default."""

        return cls(ValueState.DEFAULTED, value)

    @classmethod
    def inherited(cls, value: T) -> SpecifiedValue[T]:
        """Construct a value inherited from an earlier scope."""

        return cls(ValueState.INHERITED, value)

    @classmethod
    def unknown(cls) -> SpecifiedValue[T]:
        """Construct a value unavailable from existing evidence."""

        return cls(ValueState.UNKNOWN)


@dataclass(frozen=True, slots=True)
class ExactInteger:
    """An exact integral standard value."""

    value: int


@dataclass(frozen=True, slots=True)
class ExactDecimal:
    """An exact base-10 standard value without binary-float conversion."""

    value: Decimal


@dataclass(frozen=True, slots=True)
class ExactRational:
    """An exact reduced rational value."""

    numerator: int
    denominator: int

    @classmethod
    def from_fraction(cls, value: Fraction) -> ExactRational:
        """Construct a normalized exact rational from ``Fraction``."""

        return cls(value.numerator, value.denominator)

    def as_fraction(self) -> Fraction:
        """Return the standard-library exact value."""

        return Fraction(self.numerator, self.denominator)


type ExactNumber = ExactInteger | ExactDecimal | ExactRational


class CanonicalUnit(StrEnum):
    """Reusable units needed by the declared canonical architecture."""

    QUARTER_NOTE = "quarter-note"
    TENTHS = "tenths"
    MILLIMETRES = "millimetres"
    BEATS_PER_MINUTE = "beats-per-minute"
    SEMITONES = "semitones"
    DEGREES = "degrees"
    PERCENT = "percent"


@dataclass(frozen=True, slots=True)
class MeasuredValue:
    """An exact number carrying an explicit canonical unit."""

    number: ExactNumber
    unit: CanonicalUnit
