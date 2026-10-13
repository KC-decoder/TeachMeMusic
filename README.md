# TeachMeMusic

TeachMeMusic is a local research application that turns a MusicXML score into
a deterministic, traceable piano-learning sequence.

The current system reads MusicXML or compressed MXL, converts it into a
TeachMeMusic-owned canonical representation, displays and plays the score,
generates bounded beginner exercises, receives calibrated MIDI performances,
and records the evidence used for feedback and progression.

## Current Development Status

**Active increment:** DEV-009 — Generalizable Deterministic Piano Teaching
Methodology.

- Tasks 9A–9N are complete. They establish the teaching-methodology contracts,
  hierarchical curriculum graph, deterministic policy, functional fundamental
  exercises, evidence model, replay boundary, metrics, and the rehearsed Happy
  Birthday curriculum path.
- Tasks 9O.1–9O.4 audited the complete production and research path and closed
  the identified integration, evidence-storage, local-setup, privacy, and
  repository-hygiene defects in the audited candidate.
- Task 9O.5's clean technical readiness audit passed: the reproducible setup,
  Python and frontend suites, production build, focused defect regressions,
  launcher smoke test, dependency audit, and privacy checks all succeeded.
- The current deterministic baseline is connected from score upload through
  curriculum generation, MIDI-attempt evaluation, policy decisions,
  content-addressed evidence, export, reconciliation, and exact replay.
- The remaining DEV-009 administrative action is to commit and push the
  audited public reproducibility update before formally closing Task 9O.

No adaptive or reinforcement-learning policy is active in the application;
those remain later experimental work.

## What Works Today

- MusicXML and compressed MXL ingestion through a validated canonical schema.
- Conventional score display, sampled-piano playback, synchronized note
  highlighting, and an 88-key virtual piano.
- Deterministic curriculum generation from score content rather than filename
  or title.
- Layer-aware exercises for single-line and polyphonic piano music.
- Demonstration, supported practice, remediation, support fading,
  learned-to-date practice, and tempo-development stages.
- Calibrated Web MIDI capture and expected-versus-played comparison.
- Factual learner observations, deterministic policy decisions, concise
  feedback, progression, and content-addressed local evidence.
- Exact export, reconciliation, and replay of deterministic curriculum runs.
- Optional de-identified metrics through an explicitly enabled tracker
  boundary.
- An experimental secure local-network phone companion while MIDI remains on
  the Mac.

The teaching policy is a deterministic research baseline. It is not yet a
claim that the curriculum is optimal or that it improves learning across
different learners.

## Input Boundary

The supported application input is:

- `.musicxml` or `.xml` MusicXML;
- `.mxl` compressed MusicXML.

PDF sheet music is not currently an accepted application input. PDFs in the
research fixtures are human comparison evidence only; optical music
recognition remains separate future work.

## Quick Start

Requirements:

- macOS on Apple Silicon or Linux on x86-64;
- CPython 3.12 or 3.13;
- Node.js 20 or newer with npm;
- Chrome or Edge for Web MIDI input.

Clone and start the local application:

```bash
git clone https://github.com/KC-decoder/TeachMeMusic.git
cd TeachMeMusic
./scripts/setup-local.sh
./scripts/run-local.sh
```

The setup script selects the matching hash-locked Python environment, installs
the exact npm lock, installs TeachMeMusic without re-resolving dependencies,
and builds the browser interface. The launcher prints a private loopback URL,
for example:

```text
TeachMeMusic: http://127.0.0.1:54321/
```

Open that address in Chrome or Edge, choose a MusicXML/MXL score, and follow
the application workflow. Browser audio and MIDI access require explicit user
action.

See [RUN_LOCAL.md](RUN_LOCAL.md) for the complete local workflow. The optional
phone companion is documented in [RUN_MOBILE.md](RUN_MOBILE.md).

## Verification

Run the Python verification from the repository root:

```bash
.venv/bin/pytest -q
.venv/bin/ruff check src tests scripts
.venv/bin/ruff format --check src tests scripts
.venv/bin/mypy src/teachmemusic
```

Run the frontend verification:

```bash
cd web
npm test
npm run build
```

The repository includes the source fixtures, dependency locks, deterministic
golden trajectories, and upstream licence needed by the executable test suite.
Generated evidence, W&B output, credentials, build products, and personal
files are excluded from source control.

## Architecture

TeachMeMusic separates these boundaries:

1. score ingestion and canonical representation;
2. musical and technical analysis;
3. deterministic pedagogical requirements;
4. curriculum assembly and presentation;
5. learner-performance capture and factual comparison;
6. policy decisions, evidence storage, replay, and metrics.

External parsing-library objects terminate at the score-ingestion boundary.
Every downstream component consumes TeachMeMusic contracts rather than an
external library's object model.

See:

- [Architecture](docs/architecture.md)
- [Canonical score schema](docs/score-schema.md)
- [Development roadmap](docs/development-roadmap.md)
- [Requirements](docs/requirements/README.md)
- [Traceability matrix](docs/traceability/traceability-matrix.md)
- [Architecture decisions](docs/decisions/README.md)

## Evidence and Privacy

Uploaded score sessions remain local to the running service. Durable learner
evidence is stored under the ignored `.teachmemusic/` owner-local directory.
MIDI capture, optional self-report capture, and evidence export use separate
authorizations. Export and optional external metrics are disabled unless the
owner explicitly enables them.

Do not commit certificates, private keys, learner evidence, W&B run output, or
personal files.

## Current Research Boundary

The repository establishes a deterministic teaching testbed and its
reproducible evidence pipeline. Full human validation still requires a real
end-to-end learner run followed by evidence export, reconciliation, and replay.
Adaptive or reinforcement-learning policies are future experiments and are
not active in the current teaching path.

TeachMeMusic is experimental research software, not a clinical, educational,
or performance-certification product.

## Licence

TeachMeMusic is licensed under the [MIT License](LICENSE). Dependency licence
information is recorded in [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
