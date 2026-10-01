"""Strict standard-library codec shared by TeachMeMusic-owned contracts."""

from __future__ import annotations

import json
import types
from dataclasses import fields, is_dataclass
from enum import StrEnum
from fractions import Fraction
from typing import Union, get_args, get_origin, get_type_hints


class ContractCodecError(ValueError):
    """Raised when a contract cannot be encoded or decoded without ambiguity."""


def contract_to_data(value: object) -> object:
    """Encode one registered-shape contract into strict JSON-compatible data."""

    return _encode(value)


def contract_from_data[T](data: object, expected_type: type[T]) -> T:
    """Decode one contract using its declared type graph."""

    value = _decode(data, expected_type, expected_type.__name__)
    if not isinstance(value, expected_type):
        raise ContractCodecError(f"{expected_type.__name__}: decoded unexpected type")
    return value


def contract_to_json(value: object) -> str:
    """Encode one contract reproducibly with a terminating newline."""

    return (
        json.dumps(
            contract_to_data(value),
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
            allow_nan=False,
        )
        + "\n"
    )


def contract_json_data(payload: str) -> object:
    """Parse strict JSON while rejecting duplicate keys and non-finite numbers."""

    try:
        return json.loads(
            payload,
            object_pairs_hook=_unique_object,
            parse_constant=_reject_nonfinite,
        )
    except ContractCodecError:
        raise
    except (TypeError, ValueError, json.JSONDecodeError) as error:
        raise ContractCodecError(f"invalid contract JSON: {error}") from error


def contract_from_json[T](payload: str, expected_type: type[T]) -> T:
    """Parse and decode one strict contract document."""

    return contract_from_data(contract_json_data(payload), expected_type)


def _encode(value: object) -> object:
    if isinstance(value, StrEnum):
        return value.value
    if isinstance(value, Fraction):
        return {"denominator": value.denominator, "numerator": value.numerator}
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, tuple):
        return [_encode(item) for item in value]
    if is_dataclass(value) and not isinstance(value, type):
        return {
            "type": type(value).__name__,
            **{field.name: _encode(getattr(value, field.name)) for field in fields(value)},
        }
    raise ContractCodecError(f"unsupported contract value {type(value).__name__}")


def _decode(data: object, expected: object, path: str) -> object:
    origin = get_origin(expected)
    args = get_args(expected)
    if origin in {Union, types.UnionType}:
        if data is None and type(None) in args:
            return None
        candidates = tuple(item for item in args if item is not type(None))
        errors: list[str] = []
        for candidate in candidates:
            try:
                return _decode(data, candidate, path)
            except ContractCodecError as error:
                errors.append(str(error))
        detail = errors[0] if errors else "no matching union member"
        raise ContractCodecError(f"{path}: value does not match declared union: {detail}")
    if origin is tuple:
        if not isinstance(data, list):
            raise ContractCodecError(f"{path}: expected array")
        if len(args) != 2 or args[1] is not Ellipsis:
            raise ContractCodecError(f"{path}: only homogeneous tuples are supported")
        return tuple(_decode(item, args[0], f"{path}[{index}]") for index, item in enumerate(data))
    if expected is Fraction:
        root = _mapping(data, path)
        _expect_keys(root, {"denominator", "numerator"}, path)
        numerator = _integer(root["numerator"], f"{path}.numerator")
        denominator = _integer(root["denominator"], f"{path}.denominator")
        if denominator <= 0:
            raise ContractCodecError(f"{path}.denominator: expected positive integer")
        return Fraction(numerator, denominator)
    if isinstance(expected, type) and issubclass(expected, StrEnum):
        text = _string(data, path)
        try:
            return expected(text)
        except ValueError as error:
            raise ContractCodecError(f"{path}: unsupported {expected.__name__} {text!r}") from error
    if expected is str:
        return _string(data, path)
    if expected is bool:
        if not isinstance(data, bool):
            raise ContractCodecError(f"{path}: expected boolean")
        return data
    if expected is int:
        return _integer(data, path)
    if expected is type(None):
        if data is not None:
            raise ContractCodecError(f"{path}: expected null")
        return None
    if isinstance(expected, type) and is_dataclass(expected):
        root = _mapping(data, path)
        declared_fields = fields(expected)
        expected_keys = {"type", *(field.name for field in declared_fields)}
        _expect_keys(root, expected_keys, path)
        type_name = _string(root["type"], f"{path}.type")
        if type_name != expected.__name__:
            raise ContractCodecError(
                f"{path}.type: expected {expected.__name__!r}, received {type_name!r}"
            )
        hints = get_type_hints(expected)
        values = {
            field.name: _decode(root[field.name], hints[field.name], f"{path}.{field.name}")
            for field in declared_fields
        }
        try:
            return expected(**values)
        except (TypeError, ValueError) as error:
            raise ContractCodecError(
                f"{path}: cannot construct {expected.__name__}: {error}"
            ) from error
    raise ContractCodecError(f"{path}: unsupported declared type {expected!r}")


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ContractCodecError(f"duplicate JSON key {key!r}")
        result[key] = value
    return result


def _reject_nonfinite(value: str) -> object:
    raise ContractCodecError(f"non-finite JSON number {value!r}")


def _mapping(data: object, path: str) -> dict[str, object]:
    if not isinstance(data, dict) or not all(isinstance(key, str) for key in data):
        raise ContractCodecError(f"{path}: expected object")
    return data


def _expect_keys(data: dict[str, object], expected: set[str], path: str) -> None:
    actual = set(data)
    if actual != expected:
        missing = sorted(expected - actual)
        unexpected = sorted(actual - expected)
        raise ContractCodecError(
            f"{path}: key mismatch; missing={missing!r}; unexpected={unexpected!r}"
        )


def _string(data: object, path: str) -> str:
    if not isinstance(data, str):
        raise ContractCodecError(f"{path}: expected string")
    return data


def _integer(data: object, path: str) -> int:
    if not isinstance(data, int) or isinstance(data, bool):
        raise ContractCodecError(f"{path}: expected integer")
    return data
