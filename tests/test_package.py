"""Foundational tests for the TeachMeMusic project.

These tests verify legitimate foundation behavior only: the package imports,
its declared version matches the installed distribution metadata, and the
the core package boundaries exist. Domain behavior is verified in its focused
score, viewer, and application suites.
"""

import importlib.metadata

import teachmemusic


def test_version_matches_distribution_metadata() -> None:
    """The package version must match the installed distribution metadata."""
    assert teachmemusic.__version__ == importlib.metadata.version("teachmemusic")


def test_stage_a_module_boundaries_import() -> None:
    """The Stage A module boundaries must exist and be importable."""
    import teachmemusic.analysis
    import teachmemusic.app
    import teachmemusic.performance
    import teachmemusic.score
    import teachmemusic.score.models
    import teachmemusic.score.parser
    import teachmemusic.score.serializer
    import teachmemusic.score.validation
    import teachmemusic.teaching
    import teachmemusic.viewer

    assert teachmemusic.analysis.__doc__ is not None
    assert teachmemusic.app.__doc__ is not None
    assert teachmemusic.performance.__doc__ is not None
    assert teachmemusic.score.__doc__ is not None
    assert teachmemusic.teaching.__doc__ is not None
    assert teachmemusic.viewer.__doc__ is not None


def test_cli_module_boundaries_import() -> None:
    """The CLI package boundary must exist and be importable."""
    import teachmemusic.cli
    import teachmemusic.cli.main

    assert teachmemusic.cli.__doc__ is not None
