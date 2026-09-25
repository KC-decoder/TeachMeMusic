"""Fail-closed invariants for canonical opus and sound-catalog content."""

from __future__ import annotations

from dataclasses import dataclass

from .auxiliary import AuxiliaryDocument, OpusCatalog, OpusItem, SoundCatalog
from .links import ExternalLink


@dataclass(frozen=True, slots=True)
class AuxiliaryValidationIssue:
    code: str
    path: str
    message: str


def _valid_link(value: ExternalLink | None) -> bool:
    return value is not None and bool(value.href) and value.link_type in {None, "simple"}


def _opus_item_issues(item: OpusItem, path: str) -> list[AuxiliaryValidationIssue]:
    issues: list[AuxiliaryValidationIssue] = []
    if item.kind == "opus":
        if item.link is not None or item.new_page is not None:
            issues.append(AuxiliaryValidationIssue("AUX_OPUS_ITEM", path, "invalid nested opus"))
        for index, child in enumerate(item.children):
            issues.extend(_opus_item_issues(child, f"{path}.children[{index}]"))
    elif item.kind == "opus-link":
        if not _valid_link(item.link) or item.new_page is not None or item.children:
            issues.append(AuxiliaryValidationIssue("AUX_OPUS_LINK", path, "invalid opus link"))
    elif item.kind == "score":
        if not _valid_link(item.link) or item.children:
            issues.append(AuxiliaryValidationIssue("AUX_SCORE_LINK", path, "invalid score link"))
    else:
        issues.append(AuxiliaryValidationIssue("AUX_OPUS_KIND", path, "unknown opus item kind"))
    return issues


def validate_auxiliary_document(
    value: AuxiliaryDocument,
) -> tuple[AuxiliaryValidationIssue, ...]:
    """Validate typed auxiliary content without accepting catch-all payloads."""

    issues: list[AuxiliaryValidationIssue] = []
    if isinstance(value, OpusCatalog):
        if not value.version:
            issues.append(AuxiliaryValidationIssue("AUX_VERSION", "opus.version", "empty version"))
        for index, item in enumerate(value.items):
            issues.extend(_opus_item_issues(item, f"opus.items[{index}]"))
        return tuple(issues)
    if not isinstance(value, SoundCatalog):
        return (AuxiliaryValidationIssue("AUX_TYPE", "auxiliary", "unknown document type"),)
    if not value.version:
        issues.append(AuxiliaryValidationIssue("AUX_VERSION", "sounds.version", "empty version"))
    ids: set[str] = set()
    for index, entry in enumerate(value.entries):
        path = f"sounds.entries[{index}]"
        if not entry.id or entry.id in ids:
            issues.append(AuxiliaryValidationIssue("AUX_SOUND_ID", path, "duplicate/empty ID"))
        ids.add(entry.id)
        if any(
            mapping.kind not in {"any", "solo", "ensemble"}
            or not mapping.value
            or mapping.kind != "ensemble"
            and mapping.ensemble_size is not None
            for mapping in entry.mappings
        ):
            issues.append(AuxiliaryValidationIssue("AUX_SOUND_MAPPING", path, "invalid mapping"))
    return tuple(issues)
