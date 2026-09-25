"""Stable failures for the private MusicXML ingestion boundary."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class DiagnosticStage(StrEnum):
    """Boundary stage that rejected an untrusted source."""

    INPUT = "input"
    ARCHIVE = "archive"
    CONTAINER = "container"
    XML = "xml"
    VERSION = "version"
    VALIDATION = "validation"
    LIMIT = "limit"


@dataclass(frozen=True, slots=True)
class IngestionDiagnostic:
    """One deterministic, machine-readable ingestion failure."""

    code: str
    stage: DiagnosticStage
    message: str
    logical_path: str | None = None
    line: int | None = None
    column: int | None = None


class MusicXmlBoundaryError(ValueError):
    """Raised when untrusted input cannot produce a validated source document."""

    def __init__(self, *diagnostics: IngestionDiagnostic) -> None:
        if not diagnostics:
            raise ValueError("at least one ingestion diagnostic is required")
        self.diagnostics = tuple(diagnostics)
        super().__init__(self._render())

    @property
    def primary(self) -> IngestionDiagnostic:
        """Return the first and most actionable diagnostic."""

        return self.diagnostics[0]

    def _render(self) -> str:
        return "; ".join(
            f"{diagnostic.code}: {diagnostic.message}" for diagnostic in self.diagnostics
        )


def boundary_failure(
    code: str,
    stage: DiagnosticStage,
    message: str,
    *,
    logical_path: str | None = None,
    line: int | None = None,
    column: int | None = None,
) -> MusicXmlBoundaryError:
    """Build a one-diagnostic boundary exception without raising it."""

    return MusicXmlBoundaryError(
        IngestionDiagnostic(
            code=code,
            stage=stage,
            message=message,
            logical_path=logical_path,
            line=line,
            column=column,
        )
    )
