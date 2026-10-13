# TeachMeMusic

TeachMeMusic is a research project and application that transforms the sheet
music selected by a learner into a structured, interactive learning
experience. Given a musical score, TeachMeMusic aims to understand what is
written, what is happening musically and technically, and how the material
should be learned — then to teach the learner that piece.

The initial instrument is **piano**. Learners will select a proficiency level
(`Beginner`, `Intermediate`, or `Advanced`); the same piece is expected to
yield different learning strategies for different levels.

## Current Status

> **Early development - DEV-003 is complete; DEV-004 planning is next.**
>
> The repository contains the project foundation (DEV-001) and the
> development-governance system (DEV-002): package layout, tooling, and
> documentation. DEV-003 established and project-owner approved the
> authoritative Hot Cross Buns fixture ground truth after independent
> MusicXML/PDF inspection and comparison; no musical discrepancies were
> found. DEV-004 has not started. **No music parsing,
> musical analysis, curriculum generation, or other product functionality
> exists yet.**
>
> For the chronological development log and current handoff, see
> [PROJECT_STATUS.md](PROJECT_STATUS.md).

## Product Vision

TeachMeMusic aims to transform music selected by the learner into a structured
learning experience:

```text
Sheet Music
     ↓
Understand the score
     ↓
Understand the musical and technical demands
     ↓
Determine how the material should be learned
     ↓
Generate a structured curriculum
     ↓
Teach the learner interactively
     ↓
Help the learner perform the complete piece
```

## Stage A — Read the Music

Stage A accurately represents **what is written in a musical score**:

```text
MusicXML / MXL
    ↓
Score ingestion (parser)
    ↓
TeachMeMusic canonical score representation
```

Stage A intentionally does **not** determine difficulty, motifs, phrase
structure, learner ability, teaching strategy, lesson boundaries, exercises,
or performance quality - those belong to later stages. DEV-003 first
establishes reference-score ground truth; the canonical score representation
will be designed afterward (see [docs/score-schema.md](docs/score-schema.md)).

## Development Roadmap

| Stage | Question |
|-------|----------|
| **A — Read** | What is written in the music? |
| **B — Understand** | What is happening musically and technically? |
| **C — Plan** | How should someone at a specified level learn it? |
| **D — Evaluate** | Is the generated learning plan pedagogically sensible? |

See [docs/development-roadmap.md](docs/development-roadmap.md) for details.

## Architecture

TeachMeMusic is organized around conceptual layers with strict boundaries:

- **Score ingestion** — read and represent what is written (MusicXML/MXL).
- **Musical analysis** — what is happening musically and technically.
- **Pedagogical reasoning** — how the material should be learned.
- **Curriculum generation** — what sequence of lessons to produce.
- **Learner performance** — how the learner performed and how to adapt.

Only the score-ingestion layer exists in this repository today. The
fundamental architectural rule is that TeachMeMusic **owns its canonical
internal representation of music**: external parsing libraries (eventually
`music21`) terminate at the ingestion boundary, and every downstream
component consumes the TeachMeMusic representation, never external library
objects. See [docs/architecture.md](docs/architecture.md).

## Development Setup

Requires Python 3.12+ (development was verified on Python 3.13).

```bash
# 1. Create and activate a project-local virtual environment
python3.13 -m venv venv
source venv/bin/activate

# 2. Install the project in editable mode with development tools
python -m pip install -e ".[dev]"

# 3. Run the checks
pytest
ruff check .
ruff format --check .
mypy src/teachmemusic
```

See [RUN_LOCAL.md](RUN_LOCAL.md) for local application instructions and
[docs/governance.md](docs/governance.md) for development conventions.

## Repository Structure

```text
TeachMeMusic/
├── README.md               # This file
├── PROJECT_STATUS.md       # Append-only development log and LLM handoff
├── CHANGELOG.md            # Notable changes (currently "Unreleased" only)
├── pyproject.toml          # Project metadata, tooling configuration
├── src/
│   └── teachmemusic/       # Python package
│       ├── score/          # Stage A module boundaries (not implemented)
│       └── cli/            # Future CLI (not implemented)
├── tests/                  # Test suite (foundation tests only, for now)
├── examples/scores/        # Future example MusicXML/MXL scores
├── docs/                   # Project documentation (see below)
└── outputs/                # Generated application output (not committed)
```

## Documentation

- [docs/README.md](docs/README.md) — documentation index and artifact responsibilities
- [docs/governance.md](docs/governance.md) — development governance (lifecycle, Definitions of Ready/Done, commit and Git conventions)
- [docs/architecture.md](docs/architecture.md) — layers, the canonical-representation boundary, modularity principles
- [docs/development-roadmap.md](docs/development-roadmap.md) — stages A–D
- [docs/requirements/](docs/requirements/README.md) — requirement conventions and established requirements
- [docs/traceability/](docs/traceability/README.md) — traceability conventions and matrix
- [docs/experiments/](docs/experiments/README.md) — experiment framework
- [docs/score-schema.md](docs/score-schema.md) — status of the canonical score representation
- [docs/decisions/](docs/decisions/README.md) — architecture decision records
- [docs/development/](docs/development/001-project-foundation.md) — development journal (one record per increment)

## Project Maturity

> **Warning:** TeachMeMusic is experimental and incomplete. This repository
> currently implements no product functionality. Nothing in this repository
> reads, analyzes, or teaches music yet. Do not treat the documented roadmap
> as an availability statement.

Licensing for this project is **pending**; no license has been chosen.
