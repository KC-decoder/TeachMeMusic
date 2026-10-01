# Contributing to TeachMeMusic

TeachMeMusic is a research-first project. This guide covers the development
environment, quality expectations, and the conventions that keep the codebase
architecturally clean as it grows.

## Environment Setup

The verified development matrix is CPython **3.12** and **3.13** on macOS
ARM64 and Linux x86-64. Do not use or modify system Python. Choose the lock
whose filename matches the interpreter and platform; the example below uses
Python 3.13 on macOS ARM64.

```bash
# Create and activate a project-local virtual environment
python3.13 -m venv venv
source venv/bin/activate

# Install the PEP 751-capable bootstrap pip and exact locked environment
python -m pip install "pip==26.2.1"
python -m pip install -r requirements/pylock.macos-arm64-py313.toml

# Install the local project without resolving or replacing locked packages
python -m pip install --no-deps --no-build-isolation -e .
```

Available lock artifacts:

- `pylock.macos-arm64-py312.toml`
- `pylock.macos-arm64-py313.toml`
- `pylock.linux-x86_64-py312.toml`
- `pylock.linux-x86_64-py313.toml`

The locks contain build, runtime, development, and transitive packages as
exact wheel URLs with SHA-256 hashes. Do not substitute a lock from another
environment. Changes to dependencies require regenerating and clean-installing
all four locks, running the full matrix, and repeating the vulnerability and
licence review.

The project uses plain `pip` and a project-local `venv/`. Do not introduce
another package manager (Poetry, Hatch, PDM, uv, …) without an architectural
discussion.

> **Why `venv/` and not `.venv/`:** on the current development machine,
> dot-prefixed paths are automatically given the macOS hidden flag, and
> this Python build's `site.py` skips hidden `.pth` files — which silently
> breaks the editable-install hook. A non-dot `venv/` directory is not
> affected. (Found and recorded in the DEV-002 development record.)

## Local Application

For the supported clone-and-run path, follow [`RUN_LOCAL.md`](RUN_LOCAL.md):

```bash
./scripts/setup-local.sh
./scripts/run-local.sh
```

The setup script installs the exact Python and npm locks and builds the browser
interface. The launcher prints an ephemeral `http://127.0.0.1:<port>/`
address. It does not bind a public interface or persist uploaded scores. The
current application can load MusicXML/MXL, display canonical-derived notation,
play the score with locally bundled piano samples, highlight an accessible
88-key virtual piano by written clef, and capture calibrated Web MIDI input.
Browser audio and MIDI access both require explicit user action.

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

## Development Process

Work proceeds in numbered development increments
(`DEV-xxx`, see [PROJECT_STATUS.md](PROJECT_STATUS.md) for the chronological
log and current handoff). The process rules — increment lifecycle, work-in-progress rule,
Definitions of Ready and Done, commit and Git conventions, versioning,
tooling policy — live in
[docs/governance.md](docs/governance.md). Coding agents follow
[AGENTS.md](AGENTS.md).

## Documentation Expectations

Every significant development step must:

- leave a development journal entry in `docs/development/` (see
  [TEMPLATE.md](docs/development/TEMPLATE.md)) covering: what changed, why,
  decisions made, alternatives considered, commands executed, tests
  performed, results, limitations, unresolved questions, and the next
  intended step;
- append a factual entry to `PROJECT_STATUS.md` after meaningful work or a
  status change; never rewrite earlier entries, and leave the exact next action
  for the next developer or LLM;
- keep the [traceability matrix](docs/traceability/traceability-matrix.md)
  updated when requirements, implementations, or verification evidence
  change;
- respect the artifact responsibilities in
  [docs/README.md](docs/README.md) — link, don't duplicate;
- record architecture changes as ADRs in `docs/decisions/`
  (see [docs/decisions/README.md](docs/decisions/README.md));
- keep `CHANGELOG.md` accurate: it records only what actually exists, and
  documentation must never describe functionality that does not exist.

## Commit Expectations

Commit message conventions (Conventional Commits style, optional
`Increment:`/`Implements:`/`Verifies:`/`Fixes:` metadata) are defined in
[docs/governance.md](docs/governance.md#commit-conventions).

- One logical change per commit; no partial, broken, or WIP states.
- **Human review precedes every commit.** Never commit automatically; never
  push without explicit approval.
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
