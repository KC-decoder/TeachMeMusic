"""Foundational tests for the TeachMeMusic project.

These tests verify legitimate foundation behavior only: the package imports,
its declared version matches the installed distribution metadata, and the
Stage A module boundaries exist. They do not test score parsing — no parsing
functionality exists yet (see docs/score-schema.md).
"""

import importlib.metadata

import teachmemusic


def test_version_matches_distribution_metadata() -> None:
    """The package version must match the installed distribution metadata."""
    assert teachmemusic.__version__ == importlib.metadata.version("teachmemusic")


def test_stage_a_module_boundaries_import() -> None:
    """The Stage A module boundaries must exist and be importable."""
    import teachmemusic.score
    import teachmemusic.score.models
    import teachmemusic.score.parser
    import teachmemusic.score.serializer
    import teachmemusic.score.validation

    assert teachmemusic.score.__doc__ is not None


def test_cli_module_boundaries_import() -> None:
    """The CLI package boundary must exist and be importable."""
    import teachmemusic.cli
    import teachmemusic.cli.main

    assert teachmemusic.cli.__doc__ is not None
