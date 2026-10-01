"""Strict deterministic serialization for teaching and evidence contracts."""

from __future__ import annotations

from teachmemusic._contract_codec import (
    ContractCodecError,
    contract_from_data,
    contract_from_json,
    contract_to_data,
    contract_to_json,
)

from .contracts import EvidenceExport, LessonPlan
from .validation import (
    TeachingValidationError,
    require_valid_evidence_export,
    require_valid_lesson_plan,
)


class TeachingSerializationError(ValueError):
    """Raised when teaching JSON is malformed, unsupported, or invalid."""


def lesson_plan_to_dict(plan: LessonPlan) -> dict[str, object]:
    """Return a strict JSON-ready representation of a valid plan."""

    try:
        require_valid_lesson_plan(plan)
        data = contract_to_data(plan)
    except (ContractCodecError, TeachingValidationError) as error:
        raise TeachingSerializationError(str(error)) from error
    if not isinstance(data, dict):
        raise TeachingSerializationError("lesson plan did not encode as an object")
    return data


def lesson_plan_to_json(plan: LessonPlan) -> str:
    """Serialize one valid lesson plan reproducibly."""

    try:
        require_valid_lesson_plan(plan)
        return contract_to_json(plan)
    except (ContractCodecError, TeachingValidationError) as error:
        raise TeachingSerializationError(str(error)) from error


def lesson_plan_from_dict(data: object) -> LessonPlan:
    """Decode and validate a strict lesson plan."""

    try:
        plan = contract_from_data(data, LessonPlan)
        require_valid_lesson_plan(plan)
    except (ContractCodecError, TeachingValidationError) as error:
        raise TeachingSerializationError(str(error)) from error
    return plan


def lesson_plan_from_json(payload: str) -> LessonPlan:
    """Parse, decode, and validate lesson-plan JSON."""

    try:
        plan = contract_from_json(payload, LessonPlan)
        require_valid_lesson_plan(plan)
    except (ContractCodecError, TeachingValidationError) as error:
        raise TeachingSerializationError(str(error)) from error
    return plan


def evidence_export_to_dict(value: EvidenceExport) -> dict[str, object]:
    """Return strict JSON-ready data for one valid evidence export."""

    try:
        require_valid_evidence_export(value)
        data = contract_to_data(value)
    except (ContractCodecError, TeachingValidationError) as error:
        raise TeachingSerializationError(str(error)) from error
    if not isinstance(data, dict):
        raise TeachingSerializationError("evidence export did not encode as an object")
    return data


def evidence_export_to_json(value: EvidenceExport) -> str:
    """Serialize one valid evidence export reproducibly."""

    try:
        require_valid_evidence_export(value)
        return contract_to_json(value)
    except (ContractCodecError, TeachingValidationError) as error:
        raise TeachingSerializationError(str(error)) from error


def evidence_export_from_dict(data: object) -> EvidenceExport:
    """Decode and validate a strict evidence export."""

    try:
        value = contract_from_data(data, EvidenceExport)
        require_valid_evidence_export(value)
    except (ContractCodecError, TeachingValidationError) as error:
        raise TeachingSerializationError(str(error)) from error
    return value


def evidence_export_from_json(payload: str) -> EvidenceExport:
    """Parse, decode, and validate evidence-export JSON."""

    try:
        value = contract_from_json(payload, EvidenceExport)
        require_valid_evidence_export(value)
    except (ContractCodecError, TeachingValidationError) as error:
        raise TeachingSerializationError(str(error)) from error
    return value
