"""Measured resource budgets at the DEV-005 application boundary."""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class AppBudgets:
    """Hard limits for one local viewer process."""

    max_upload_bytes: int = 8 * 1024 * 1024
    max_request_bytes: int = 9 * 1024 * 1024
    max_response_bytes: int = 16 * 1024 * 1024
    max_filename_bytes: int = 255
    max_score_documents: int = 16
    max_sessions: int = 4
    session_ttl_seconds: int = 30 * 60
    max_notes: int = 20_000
    max_anchors: int = 20_000
    max_navigation_sections: int = 128


DEFAULT_APP_BUDGETS = AppBudgets()
