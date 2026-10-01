# Run TeachMeMusic Locally

TeachMeMusic currently runs as a private local web application. The Python
service listens only on the loopback interface, and uploaded scores are kept
only in the running process.

## Requirements

- macOS on Apple Silicon or Linux on x86-64;
- Python 3.12 or 3.13;
- Node.js 20 or newer with npm; and
- desktop Google Chrome or Microsoft Edge for Web MIDI piano input.

Safari can display the application but does not provide the Web MIDI support
required for a connected piano.

## First run

Clone the repository, enter it, and run:

```bash
./scripts/setup-local.sh
./scripts/run-local.sh
```

The setup command installs the exact platform-specific Python lock, installs
the exact npm lock, and builds the browser interface. The run command prints a
private address such as:

```text
TeachMeMusic: http://127.0.0.1:54321/
```

Open that address in desktop Chrome or Edge. Choose a MusicXML (`.xml` or
`.musicxml`) or compressed MusicXML (`.mxl`) score. To use a digital piano,
connect it before selecting **Allow MIDI access**, approve the browser prompt,
select the visible input, and run the guided calibration.

Press `Control-C` in the terminal to stop TeachMeMusic. The ephemeral score
session is then discarded.

## Later runs

After the first setup, start the application with:

```bash
./scripts/run-local.sh
```

Run `./scripts/setup-local.sh` again after pulling a change to the Python or
browser dependency locks.

## Current limits

- This is a local research build, not a hosted service.
- PDF sheet-music recognition is not an accepted input path.
- MusicXML/MXL ingestion, notation, demonstration playback, beginner exercise
  generation, virtual-piano highlighting, and calibrated Web MIDI capture are
  available.
- Automatic comparison and teaching feedback are planned but not yet present.
