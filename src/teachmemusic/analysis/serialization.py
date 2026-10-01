"""Strict deterministic serialization for analysis contracts."""

from __future__ import annotations

from teachmemusic._contract_codec import (
    ContractCodecError,
    contract_from_data,
    contract_from_json,
    contract_to_data,
    contract_to_json,
)

from .contracts import ScoreAnalysis
from .validation import AnalysisValidationError, require_valid_score_analysis


class AnalysisSerializationError(ValueError):
    """Raised when analysis JSON is malformed, unsupported, or invalid."""


def score_analysis_to_dict(value: ScoreAnalysis) -> dict[str, object]:
    """Return strict JSON-ready analysis data."""

    try:
        require_valid_score_analysis(value)
        data = contract_to_data(value)
    except (ContractCodecError, AnalysisValidationError) as error:
        raise AnalysisSerializationError(str(error)) from error
    if not isinstance(data, dict):
        raise AnalysisSerializationError("analysis did not encode as an object")
    return data


def score_analysis_to_json(value: ScoreAnalysis) -> str:
    """Serialize analysis reproducibly."""

    try:
        require_valid_score_analysis(value)
        return contract_to_json(value)
    except (ContractCodecError, AnalysisValidationError) as error:
        raise AnalysisSerializationError(str(error)) from error


def score_analysis_from_dict(data: object) -> ScoreAnalysis:
    """Decode and validate strict analysis data."""

    try:
        value = contract_from_data(data, ScoreAnalysis)
        require_valid_score_analysis(value)
    except (ContractCodecError, AnalysisValidationError) as error:
        raise AnalysisSerializationError(str(error)) from error
    return value


def score_analysis_from_json(payload: str) -> ScoreAnalysis:
    """Parse, decode, and validate analysis JSON."""

    try:
        value = contract_from_json(payload, ScoreAnalysis)
        require_valid_score_analysis(value)
    except (ContractCodecError, AnalysisValidationError) as error:
        raise AnalysisSerializationError(str(error)) from error
    return value
