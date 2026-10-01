"""Strict deterministic serialization for performance contracts."""

from __future__ import annotations

from teachmemusic._contract_codec import (
    ContractCodecError,
    contract_from_data,
    contract_from_json,
    contract_to_data,
    contract_to_json,
)

from .contracts import PerformanceBundle
from .validation import PerformanceValidationError, require_valid_performance_bundle


class PerformanceSerializationError(ValueError):
    """Raised when performance JSON is malformed, unsupported, or invalid."""


def performance_bundle_to_dict(bundle: PerformanceBundle) -> dict[str, object]:
    """Return a strict JSON-ready representation of a valid bundle."""

    try:
        require_valid_performance_bundle(bundle)
        data = contract_to_data(bundle)
    except (ContractCodecError, PerformanceValidationError) as error:
        raise PerformanceSerializationError(str(error)) from error
    if not isinstance(data, dict):
        raise PerformanceSerializationError("performance bundle did not encode as an object")
    return data


def performance_bundle_to_json(bundle: PerformanceBundle) -> str:
    """Serialize a valid performance bundle reproducibly."""

    try:
        require_valid_performance_bundle(bundle)
        return contract_to_json(bundle)
    except (ContractCodecError, PerformanceValidationError) as error:
        raise PerformanceSerializationError(str(error)) from error


def performance_bundle_from_dict(data: object) -> PerformanceBundle:
    """Decode and validate a strict performance bundle."""

    try:
        bundle = contract_from_data(data, PerformanceBundle)
        require_valid_performance_bundle(bundle)
    except (ContractCodecError, PerformanceValidationError) as error:
        raise PerformanceSerializationError(str(error)) from error
    return bundle


def performance_bundle_from_json(payload: str) -> PerformanceBundle:
    """Parse, decode, and validate performance JSON."""

    try:
        bundle = contract_from_json(payload, PerformanceBundle)
        require_valid_performance_bundle(bundle)
    except (ContractCodecError, PerformanceValidationError) as error:
        raise PerformanceSerializationError(str(error)) from error
    return bundle
