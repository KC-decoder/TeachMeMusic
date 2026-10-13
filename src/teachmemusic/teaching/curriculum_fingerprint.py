"""Deterministic semantic identities for DEV-009 curriculum artifacts."""

from __future__ import annotations

import hashlib
import json
from dataclasses import fields, is_dataclass
from enum import StrEnum
from fractions import Fraction
from typing import Any


def semantic_fingerprint(value: object) -> str:
    """Return SHA-256 over the artifact's deterministic semantic projection."""

    payload = json.dumps(
        _semantic_value(value, root=True),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def derived_id(kind: str, value: object) -> str:
    """Return the accepted full-digest derived-ID shape."""

    return f"{kind}:{semantic_fingerprint(value)}"


def _semantic_value(value: object, *, root: bool = False) -> Any:
    if isinstance(value, StrEnum):
        return value.value
    if isinstance(value, Fraction):
        return {"denominator": value.denominator, "numerator": value.numerator}
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, tuple):
        return [_semantic_value(item) for item in value]
    if isinstance(value, list):
        return [_semantic_value(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _semantic_value(item) for key, item in value.items()}
    if is_dataclass(value) and not isinstance(value, type):
        return {
            field.name: _semantic_value(getattr(value, field.name))
            for field in fields(value)
            if not root or field.name not in {"id", "semantic_fingerprint"}
        }
    raise TypeError(f"unsupported semantic value {type(value).__name__}")
