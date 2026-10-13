# Run TeachMeMusic Locally

TeachMeMusic runs as a private local web application. Uploaded scores remain
inside the running local service. Durable learner evidence is written only to
the ignored owner-local `.teachmemusic/` directory.

## Requirements

- macOS on Apple Silicon or Linux on x86-64;
- CPython 3.12 or 3.13;
- Node.js 20 or newer with npm;
- Chrome or Edge for Web MIDI piano input.

Safari can display the application but does not provide the Web MIDI support
needed for a connected digital piano.

## First Run

From a clone of the repository:

```bash
./scripts/setup-local.sh
./scripts/run-local.sh
```

The setup script selects the platform- and Python-specific hash lock, installs
the exact frontend lock, installs the local package without dependency
re-resolution, and builds the browser application.

The launcher prints a private loopback address such as:

```text
TeachMeMusic: http://127.0.0.1:54321/
```

Open the address in Chrome or Edge.

## Run a Score

1. Choose a MusicXML (`.xml` or `.musicxml`) or compressed MXL (`.mxl`) file.
2. Review the generated curriculum and authorize the local teaching run.
3. Connect the digital piano and select **Allow MIDI access**.
4. Select the visible MIDI input and complete calibration.
5. Open an exercise, listen to its demonstration, and start an attempt.
6. Play the requested material and submit the completed attempt.
7. Review the factual feedback and deterministic next action.
8. Export evidence only if an export was explicitly authorized.

The application does not substitute simulated learner input when MIDI is
unavailable.

Press `Control-C` in the terminal to stop the service. Live score sessions are
then discarded; previously authorized durable evidence remains owner-local
until explicitly deleted.

## Later Runs

After setup:

```bash
./scripts/run-local.sh
```

Run `./scripts/setup-local.sh` again after pulling dependency-lock or frontend
dependency changes.

## Verify the Clone

```bash
.venv/bin/pytest -q
.venv/bin/ruff check src tests scripts
.venv/bin/ruff format --check src tests scripts
.venv/bin/mypy src/teachmemusic

cd web
npm test
npm run build
```

## Optional Phone Companion

The experimental phone companion has additional private-network and TLS
requirements. Follow [RUN_MOBILE.md](RUN_MOBILE.md). The normal launcher above
remains loopback-only.

## Current Limits

- This is a local research build, not a hosted service.
- PDF sheet-music recognition is not an accepted input path.
- The active teaching policy is deterministic, not learned or stochastic.
- Human learning effectiveness has not yet been established.
- Mobile mode remains an experimental local-network companion, not a public
  deployment.
