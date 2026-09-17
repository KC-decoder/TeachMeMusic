# Contributing to TeachMeMusic

TeachMeMusic is a research-first project. This guide covers the development
environment, quality expectations, and the conventions that keep the codebase
architecturally clean as it grows.

## Environment Setup

Python **3.12+** is required (do not use or modify system Python).

```bash
# Create and activate a project-local virtual environment
python3.13 -m venv .venv
source .venv/bin/activate

# Install the project in editable mode with development tools
python -m pip install -e ".[dev]"
```

The project uses plain `pip` and a project-local `.venv/`. Do not introduce
another package manager (Poetry, Hatch, PDM, uv, …) without an architectural
discussion.

## Quality Checks

All of the following must pass before a change is considered complete:

```bash
pytest                  # tests
ruff check .            # lint
ruff format --check .   # formatting
mypy src/teachmemusic   # type checking
```

- Add tests for new functionality. Do not write tests for functionality that
  does not exist.
- Do not silence linter or type-checker categories to produce a green result.

## Documentation Expectations

Every significant development step must leave a development journal entry in
`docs/development/` (see `001-project-foundation.md` for the template)
covering: what changed, why, decisions made, alternatives considered,
commands executed, tests performed, results, limitations, unresolved
questions, and the next intended step.

- Architecture changes require an ADR in `docs/decisions/`
  (see [docs/decisions/README.md](docs/decisions/README.md)).
- `CHANGELOG.md` records only functionality that actually exists.
- Documentation must never describe functionality that does not exist.

## Commit Expectations

- Commit messages use the Conventional Commits style
  (`feat:`, `fix:`, `chore:`, `docs:`, `test:`, …) with a subject and a body
  explaining *why* the change was made.
- One logical change per commit; no partial, broken, or WIP states.
- Never commit secrets, credentials, machine-specific paths, or generated
  output. Check `git status` and `git diff` before committing.

## Architectural Boundary Expectations

TeachMeMusic has strict conceptual layers: **score** (what is written),
**analysis** (what is happening musically/technically), **pedagogy** (how it
should be learned), **curriculum** (lesson sequencing), and **performance**
(learner assessment).

- **Functionality must not cross conceptual layer boundaries without
  deliberate architectural discussion** (documented as an ADR).
- External library objects (e.g. `music21`) must terminate at the
  score-ingestion boundary. Downstream code consumes TeachMeMusic's
  canonical score representation only. See
  [docs/architecture.md](docs/architecture.md).
- Do not create packages or modules for layers that do not exist yet
  (analysis, pedagogy, curriculum, performance are not implemented).
