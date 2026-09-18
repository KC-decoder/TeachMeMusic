# TMM-REF-CANDIDATE-001 — Hot Cross Buns

## Sample Status

| Field | Value |
|-------|-------|
| Overall ground-truth status | ESTABLISHED AND APPROVED |
| DEV-003 part | Parts 1-4 complete |
| Current subtask | None - DEV-003 closed |
| Part 1, Task 1 status | COMPLETE |
| Part 1, Task 2A status | COMPLETE |
| Part 1, Task 2B status | COMPLETE |
| Part 1, Task 2C status | COMPLETE |
| Part 1, Task 2D status | COMPLETE |
| Task 3 status | COMPLETE |
| Part 1 status | COMPLETE |
| Part 2, Task 1 status | COMPLETE |
| Part 2, Task 2 status | COMPLETE |
| Part 2 status | COMPLETE |
| Part 3 status | COMPLETE |
| Part 4 status | COMPLETE |
| DEV-003 lifecycle status | DONE |
| Last updated | 2026-09-17 |
| Last updated by | Codex |
| Next action | Plan DEV-004 Canonical ScoreRepresentation from this evidence; do not implement until its Definition of Ready is satisfied |

## Purpose

This fixture now has an established ground-truth record for TeachMeMusic. Its
stable identifier retains `CANDIDATE` because identifiers are not renamed or
repurposed after creation. The two source files and the consolidated evidence
below form the reference basis for the future canonical `ScoreRepresentation`
and MusicXML parser planned for DEV-004 and DEV-005. Neither implementation
exists yet; this fixture documents evidence and required fidelity, not code.

## Source Files

Files stored in this sample directory:

| File | Role | Size (bytes) | SHA-256 | Inspection status |
|------|------|--------------|---------|-------------------|
| `musicxml-17-hot-cross-buns-final-shelbygtdrew.mxl` | Machine-readable source (compressed MusicXML) | 2,224 | `2e48621ad69af56297fb015cd036e62f582b1f3dd8c48239f1f84c7e17d6471e` | Independently inspected, validated, and compared with PDF, 2026-09-17 |
| `print-full.pdf` | Visual reference (printed score) | 26,850 | `91e66bc30aab933707a64e108e8ea18d7f89ea8a7d455a1e81497e08d90d0594` | Independently inspected, validated, and compared with MusicXML, 2026-09-17 |

The PDF was not rendered during Part 1. Part 2 rendered its complete single
page, recorded its metadata and layout, transcribed all eight measures, and
validated the PDF-derived totals without comparing them to MusicXML. Part 3
subsequently compared the two independent records and found no contradictory
musical content.

## Provenance and Limitations

Established file and provenance facts:

- Filesystem modification times in this working copy: `.mxl` 2026-09-17
  10:30, `print-full.pdf` 2026-09-17 10:48 (local time).
- ZIP entry timestamps recorded inside the archive: both entries carry
  2026-03-30 21:30:22.
- The sample directory and both files are untracked in Git as of
  2026-09-17; no commit references them yet.
- The original source of the score (composer notation, publisher, notation
  software, rights status) is UNKNOWN — no provenance document accompanies
  the fixture.

Current limitations:

- The MusicXML archive, metadata, structure, and all eight measures have been
  inspected and validated, but DTD or XSD validation has not been performed.
- The PDF has been rendered, transcribed measure by measure, and validated.
- The sources have been compared; authoritative ground-truth consolidation
  is complete in Part 4 and was approved by the project owner at DEV-003
  closure.

## Part 1 — MusicXML Observations

### Inspection Progress

| Task | Description | Status |
|------|-------------|--------|
| Task 1 | Archive inventory | COMPLETE (2026-09-17, Qwen) |
| Task 2A | MusicXML metadata and score-level structure | COMPLETE (2026-09-17, Qwen) |
| Task 2B | Measures 1–4 | COMPLETE (2026-09-17, Qwen) |
| Task 2C | Measures 5–8 | COMPLETE (2026-09-17, Codex) |
| Task 2D | Validation, derived totals, absent features, uncertainties | COMPLETE (2026-09-17, Codex) |

### Archive Structure

Direct observations (2026-09-17, Qwen):

- Inspected file:
  `tests/fixtures/scores/TMM-REF-CANDIDATE-001-Hot-Cross-Buns/musicxml-17-hot-cross-buns-final-shelbygtdrew.mxl`
  (2,224 bytes on disk).
- The file is a valid ZIP archive; a CRC integrity check (`testzip()`)
  reported no errors.
- Archive entries and their uncompressed sizes:

| Archive entry | Uncompressed size (bytes) |
|---------------|---------------------------|
| `META-INF/container.xml` | 152 |
| `score.xml` | 15,755 |

- Total uncompressed size of the recorded entries: 15,907 bytes (arithmetic
  sum of the two entries above).
- Container metadata file: `META-INF/container.xml` (152 bytes, XML).
- Declared root MusicXML path: `score.xml` (value of the `full-path`
  attribute of the single `<rootfile>` element).
- Media type: **not** explicitly declared — the `<rootfile>` element carries
  no `media-type` attribute.
- Structural notes observed in `META-INF/container.xml`:
  - The `<container>` root element has no XML namespace declaration.
  - The single `<rootfile>` element is empty (whitespace only between its
    opening and closing tags).
  - Closing tags are indented one level deeper than their matching opening
    tags.
- Structural notes observed in the archive as a whole:
  - Both ZIP entries share the identical entry timestamp
    (2026-03-30 21:30:22).
  - The archive contains exactly the two entries recorded above; there is no
    `mimetype` entry or any other entry.
  - The current MusicXML compressed-file specification recommends an
    uncompressed `mimetype` file as the first ZIP entry, while noting that
    applications may encounter older containers without one. Its absence is
    therefore recorded as a compatibility and conformance limitation, not as
    proof that this archive is invalid.

Interpretation (labeled; not direct observation):

- The `META-INF/container.xml` + rootfile layout follows MusicXML's ZIP-based
  compressed-file structure, which the MusicXML specification describes as
  compatible with Java JAR files and based on the Info-ZIP format. Full
  conformance to the MusicXML compressed-file specification has not been
  verified in Task 1.

### Document Metadata

Task 2A (2026-09-17, Qwen). Values are exactly as encoded in `score.xml`;
items listed as "Absent" do not occur in the document.

Document identification:

| Item | Encoded value |
|------|---------------|
| XML declaration | `<?xml version="1.0" encoding="UTF-8"?>` |
| Character encoding | UTF-8 (declared in the XML declaration) |
| DOCTYPE | `score-partwise` — public ID `-//Recordare//DTD MusicXML 4.0 Partwise//EN`, system ID `http://www.musicxml.org/dtds/partwise.dtd` |
| Root element | `score-partwise` |
| MusicXML version | 4.0 (root element attribute) |
| Score organization | Partwise (one `part` element per score part) |

Formatting note (direct observation): closing tags are indented one level
deeper than their matching opening tags throughout the document (same
pattern as `META-INF/container.xml`, Task 1).

Work and identification:

| Item | Encoded value |
|------|---------------|
| Work title | Hot Cross Buns |
| Creator / composer / arranger | Absent |
| Rights | Absent |
| Movement title | Absent |
| Encoding software | MuseScore Studio 4.6.5 |
| Encoding date | 2026-03-30 |
| Miscellaneous fields | `creationDate` = 2026-03-30; `platform` = Linux |

Declared supported elements (`supports`):

| element | attribute | type | value |
|---------|-----------|------|-------|
| accidental | — | yes | — |
| beam | — | yes | — |
| print | new-page | yes | yes |
| print | new-system | yes | yes |
| stem | — | yes | — |

Document-level absences: no `creator`, `composer`, `arranger`, `rights`,
`movement-title`, `source`, `encoding application`, or `version` element;
no miscellaneous fields beyond the two recorded above.

Credits:

| Item | Encoded value |
|------|---------------|
| Page | 1 |
| Credit type | title |
| Text | Hot Cross Buns |
| Placement | `default-x` 600.241173, `default-y` 1611.208292, `justify` center, `valign` top, `font-size` 22 |

### Score Structure

Task 2A (2026-09-17, Qwen). Directly encoded facts, derived counts, and
implicit/missing information are labeled separately.

Part and instrument (directly encoded):

| Item | Encoded value |
|------|---------------|
| Score parts | 1 — `score-part` id `P1` |
| Part name | Present but empty (explicit empty `part-name` element, no text) |
| Score instruments | 1 — `score-instrument` id `P1-I1` |
| Instrument name | Present but empty (explicit empty `instrument-name` element, no text) |
| Instrument sound | `keyboard.piano.grand` |
| MIDI device | id `P1-I1`, port `1`; device name empty (no text content) |

Interpretation (labeled): with both name elements explicitly empty, the
instrument is identified only by `instrument-sound` and MIDI settings;
"piano" is inferred from `keyboard.piano.grand`, not from an explicit name.

Score-level attributes (directly encoded; the only `attributes` element, in
measure 1):

| Item | Encoded value |
|------|---------------|
| Divisions | 1 |
| Key | fifths 1, mode major |
| Time | 4/4 (`beats` 4, `beat-type` 4) |
| Clef | G, line 2 |
| Tempo | 96 — `sound tempo="96"` in measure 1; no `tempo` element anywhere in the document |
| `attributes` elements | 1 total (measure 1); measures 2–8 contain no `attributes` element, so no divisions, key, meter, clef, or tempo change is encoded |

System breaks (score structure):

- 2 `print` instructions total: measure 1 (`print` with no `new-page` or
  `new-system` attribute) and measure 7 (`print new-system="yes"`).
- The layout values of both prints are engraving metadata; see
  MusicXML-Only and Export Metadata.

Derived counts (calculated by scanning all 8 measures):

- Declared parts: 1 (`P1`).
- Measures: 8, numbered 1–8, sequential with no gaps.
- Distinct voice values: 1 (every note element in measures 1–8 encodes
  `voice` 1).

Missing or implicit information:

- No `staff` element is encoded anywhere; a single staff per part is the
  implicit MusicXML default and is not explicitly encoded.
- The measure 1 `print` encodes no `new-page` attribute; starting a new
  page is implicit (MusicXML 4.0 default), not explicit.
- No `staff` change, `part-group`, or `grouping` elements occur.

### Measure-by-Measure Content

Tasks 2B and 2C (2026-09-17, Qwen and Codex): measures 1–8 documented.
Task 2D subsequently validated the complete record; see the validation summary
below.

Conventions:

- Events are listed in source order; encoded values are copied exactly.
  Derived values appear only in the "Derived verification" blocks.
- `—` means the field is absent from the XML (not encoded). An explicitly
  empty element is noted in the text.
- Durations are encoded `duration` values in divisions; with `divisions` 1
  (declared in measure 1, see Score Structure), 1 division = 1 quarter note.
- Pitches are recorded as encoded `step` + `octave` only. No `alter` is
  encoded on any measure 1–4 pitch, and no accidental is inferred from the
  key signature (fifths +1).
- No `staff` element is encoded on any note; staff 1 is implicit.
- `default-x`/`default-y` are layout positioning values, not musical meaning.
- Lyric lines 1 and 2 are kept separate; text is copied exactly
  (capitalization and punctuation preserved, not normalized).

#### Measure 1 (number 1, width 221.71)

Measure-level (encoded):

- `print`: present, no `new-page`/`new-system` attribute (system-layout
  values: see MusicXML-Only and Export Metadata).
- `attributes`: divisions 1; key fifths 1, mode major; time 4/4; clef G,
  line 2 — the document's only `attributes` element (see Score Structure).
- `sound`: tempo 96 (see Score Structure).
- Barline element: absent.

Events (source order; encoded values):

| # | Element | Step | Alter | Octave | Duration (divisions) | Duration unit | Written type | Dots | Voice | Staff | Stem | Chord | Tie | default-x | default-y |
|---|---------|------|-------|--------|----------------------|---------------|--------------|------|-------|-------|------|-------|-----|-----------|-----------|
| 1 | note | B | — | 4 | 2 | 2 quarter notes | half | none | 1 | — | down | — | — | 97.47 | -20 |
| 2 | note | A | — | 4 | 2 | 2 quarter notes | half | none | 1 | — | up | — | — | 158.69 | -25 |

Lyrics (exact text; two separate lines; not normalized):

| Event | Lyric # | Syllabic | Text | default-x | default-y | relative-y |
|-------|---------|----------|------|-----------|-----------|------------|
| 1 | 1 | single | Hot | 6.5 | -44.92 | -30 |
| 1 | 2 | single | Mi | 6.5 | -68.63 | -30 |
| 2 | 1 | single | cross | 6.5 | -44.92 | -30 |
| 2 | 2 | single | Re | 6.5 | -68.63 | -30 |

All lyrics encode number, syllabic, text, and all three placement
attributes; no expected lyric field is absent.

Derived verification (calculated, not encoded):

- Total encoded duration: 2 + 2 = 4 divisions (= 4 quarter notes).
- Expected measure duration (4/4, divisions 1): 4 divisions.
- Duration total fills the measure: yes (4 = 4).
- Pitched notes: 2; rests: 0; lyric elements: 4.

#### Measure 2 (number 2, width 132.73)

Measure-level (encoded): `print`, `attributes`, `sound`, and barline all
absent. Divisions 1, key fifths 1 major, time 4/4, and clef G line 2 carry
over from measure 1 (implicit carryover; not redeclared).

Events (source order; encoded values):

| # | Element | Step | Alter | Octave | Duration (divisions) | Duration unit | Written type | Dots | Voice | Staff | Stem | Chord | Tie | default-x | default-y |
|---|---------|------|-------|--------|----------------------|---------------|--------------|------|-------|-------|------|-------|-----|-----------|-----------|
| 1 | note | G | — | 4 | 3 | 3 quarter notes (dotted half) | half | 1 dot (`dot` element with `default-x` 30.49, `default-y` -25) | 1 | — | up | — | — | 12.5 | -30 |
| 2 | rest | — | — | — | 1 | 1 quarter note | quarter | none | 1 | — | — | — | — | 90.11 | -20 |

Event 2 encodes an empty `<rest/>` element; no stem, chord, tie, or `staff`
is encoded for it.

Lyrics (exact text; not normalized):

| Event | Lyric # | Syllabic | Text | default-x | default-y | relative-y |
|-------|---------|----------|------|-----------|-----------|------------|
| 1 | 1 | single | buns, | 8.71 | -44.92 | -30 |
| 1 | 2 | single | Do | 6.5 | -68.63 | -30 |

All expected lyric fields present; the comma in "buns," is preserved as
encoded.

Derived verification (calculated, not encoded):

- Total encoded duration: 3 + 1 = 4 divisions (= 4 quarter notes).
- Expected measure duration (4/4, divisions 1): 4 divisions.
- Duration total fills the measure: yes (4 = 4).
- Pitched notes: 1; rests: 1; lyric elements: 2.

#### Measure 3 (number 3, width 136.75)

Measure-level (encoded): `print`, `attributes`, `sound`, and barline all
absent. Divisions 1, key fifths 1 major, time 4/4, and clef G line 2 carry
over from measure 1 (implicit carryover; not redeclared).

Events (source order; encoded values):

| # | Element | Step | Alter | Octave | Duration (divisions) | Duration unit | Written type | Dots | Voice | Staff | Stem | Chord | Tie | default-x | default-y |
|---|---------|------|-------|--------|----------------------|---------------|--------------|------|-------|-------|------|-------|-----|-----------|-----------|
| 1 | note | B | — | 4 | 2 | 2 quarter notes | half | none | 1 | — | down | — | — | 12.5 | -20 |
| 2 | note | A | — | 4 | 2 | 2 quarter notes | half | none | 1 | — | up | — | — | 73.72 | -25 |

Lyrics (exact text; not normalized):

| Event | Lyric # | Syllabic | Text | default-x | default-y | relative-y |
|-------|---------|----------|------|-----------|-----------|------------|
| 1 | 1 | single | hot | 6.5 | -44.92 | -30 |
| 1 | 2 | single | Mi | 6.5 | -68.63 | -30 |
| 2 | 1 | single | cross | 6.5 | -44.92 | -30 |
| 2 | 2 | single | Re | 6.5 | -68.63 | -30 |

All expected lyric fields present.

Derived verification (calculated, not encoded):

- Total encoded duration: 2 + 2 = 4 divisions (= 4 quarter notes).
- Expected measure duration (4/4, divisions 1): 4 divisions.
- Duration total fills the measure: yes (4 = 4).
- Pitched notes: 2; rests: 0; lyric elements: 4.

#### Measure 4 (number 4, width 132.73)

Measure-level (encoded): `print`, `attributes`, `sound`, and barline all
absent. Divisions 1, key fifths 1 major, time 4/4, and clef G line 2 carry
over from measure 1 (implicit carryover; not redeclared).

Events (source order; encoded values):

| # | Element | Step | Alter | Octave | Duration (divisions) | Duration unit | Written type | Dots | Voice | Staff | Stem | Chord | Tie | default-x | default-y |
|---|---------|------|-------|--------|----------------------|---------------|--------------|------|-------|-------|------|-------|-----|-----------|-----------|
| 1 | note | G | — | 4 | 3 | 3 quarter notes (dotted half) | half | 1 dot (`dot` element with `default-x` 30.49, `default-y` -25) | 1 | — | up | — | — | 12.5 | -30 |
| 2 | rest | — | — | — | 1 | 1 quarter note | quarter | none | 1 | — | — | — | — | 90.11 | -20 |

Event 2 encodes an empty `<rest/>` element; no stem, chord, tie, or `staff`
is encoded for it.

Lyrics (exact text; not normalized):

| Event | Lyric # | Syllabic | Text | default-x | default-y | relative-y |
|-------|---------|----------|------|-----------|-----------|------------|
| 1 | 1 | single | buns. | 8.51 | -44.92 | -30 |
| 1 | 2 | single | Do | 6.5 | -68.63 | -30 |

All expected lyric fields present; the period in "buns." is preserved as
encoded.

Derived verification (calculated, not encoded):

- Total encoded duration: 3 + 1 = 4 divisions (= 4 quarter notes).
- Expected measure duration (4/4, divisions 1): 4 divisions.
- Duration total fills the measure: yes (4 = 4).
- Pitched notes: 1; rests: 1; lyric elements: 2.

#### Measure 5 (number 5, width 177.56)

Measure-level (encoded): `print`, `attributes`, `sound`, and barline all
absent. Divisions 1, key fifths 1 major, time 4/4, and clef G line 2 carry
over from measure 1 (implicit carryover; not redeclared).

Events (source order; encoded values):

| # | Element | Step | Alter | Octave | Duration (divisions) | Duration unit | Written type | Dots | Voice | Staff | Stem | Chord | Tie | default-x | default-y |
|---|---------|------|-------|--------|----------------------|---------------|--------------|------|-------|-------|------|-------|-----|-----------|-----------|
| 1 | note | G | — | 4 | 1 | 1 quarter note | quarter | none | 1 | — | up | — | — | 12.5 | -30 |
| 2 | note | G | — | 4 | 1 | 1 quarter note | quarter | none | 1 | — | up | — | — | 53.32 | -30 |
| 3 | note | G | — | 4 | 1 | 1 quarter note | quarter | none | 1 | — | up | — | — | 94.13 | -30 |
| 4 | note | G | — | 4 | 1 | 1 quarter note | quarter | none | 1 | — | up | — | — | 134.95 | -30 |

Lyrics (exact text; two separate lines; not normalized):

| Event | Lyric # | Syllabic | Text | default-x | default-y | relative-y |
|-------|---------|----------|------|-----------|-----------|------------|
| 1 | 1 | single | One | 6.5 | -44.92 | -30 |
| 1 | 2 | single | Do | 6.5 | -68.63 | -30 |
| 2 | 1 | single | a | 6.5 | -44.92 | -30 |
| 2 | 2 | single | Do | 6.5 | -68.63 | -30 |
| 3 | 1 | begin | pen- | 9.88 | -44.92 | -30 |
| 3 | 2 | single | Do | 6.5 | -68.63 | -30 |
| 4 | 1 | end | ny | 6.5 | -44.92 | -30 |
| 4 | 2 | single | Do | 6.5 | -68.63 | -30 |

All lyrics encode number, syllabic, text, and all three placement
attributes. The capitalization of "One" and the hyphen in "pen-" are
preserved exactly.

Derived verification (calculated, not encoded):

- Total encoded duration: 1 + 1 + 1 + 1 = 4 divisions (= 4 quarter notes).
- Expected measure duration (4/4, divisions 1): 4 divisions.
- Duration total fills the measure: yes (4 = 4).
- Pitched notes: 4; rests: 0; lyric elements: 8.

#### Measure 6 (number 6, width 177.56)

Measure-level (encoded): `print`, `attributes`, `sound`, and barline all
absent. Divisions 1, key fifths 1 major, time 4/4, and clef G line 2 carry
over from measure 1 (implicit carryover; not redeclared).

Events (source order; encoded values):

| # | Element | Step | Alter | Octave | Duration (divisions) | Duration unit | Written type | Dots | Voice | Staff | Stem | Chord | Tie | default-x | default-y |
|---|---------|------|-------|--------|----------------------|---------------|--------------|------|-------|-------|------|-------|-----|-----------|-----------|
| 1 | note | A | — | 4 | 1 | 1 quarter note | quarter | none | 1 | — | up | — | — | 12.5 | -25 |
| 2 | note | A | — | 4 | 1 | 1 quarter note | quarter | none | 1 | — | up | — | — | 53.32 | -25 |
| 3 | note | A | — | 4 | 1 | 1 quarter note | quarter | none | 1 | — | up | — | — | 94.13 | -25 |
| 4 | note | A | — | 4 | 1 | 1 quarter note | quarter | none | 1 | — | up | — | — | 134.95 | -25 |

Lyrics (exact text; two separate lines; not normalized):

| Event | Lyric # | Syllabic | Text | default-x | default-y | relative-y |
|-------|---------|----------|------|-----------|-----------|------------|
| 1 | 1 | single | two | 6.5 | -44.92 | -30 |
| 1 | 2 | single | Re | 6.5 | -68.63 | -30 |
| 2 | 1 | single | a | 6.5 | -44.92 | -30 |
| 2 | 2 | single | Re | 6.5 | -68.63 | -30 |
| 3 | 1 | begin | pen- | 9.88 | -44.92 | -30 |
| 3 | 2 | single | Re | 6.5 | -68.63 | -30 |
| 4 | 1 | end | ny | 6.5 | -44.92 | -30 |
| 4 | 2 | single | Re | 6.5 | -68.63 | -30 |

All lyrics encode number, syllabic, text, and all three placement
attributes. The lowercase "two" and the hyphen in "pen-" are preserved
exactly.

Derived verification (calculated, not encoded):

- Total encoded duration: 1 + 1 + 1 + 1 = 4 divisions (= 4 quarter notes).
- Expected measure duration (4/4, divisions 1): 4 divisions.
- Duration total fills the measure: yes (4 = 4).
- Pitched notes: 4; rests: 0; lyric elements: 8.

#### Measure 7 (number 7, width 182.15)

Measure-level (encoded):

- `print new-system="yes"` is present.
- Its `system-layout` encodes system margins left 0 and right 0, plus
  `system-distance` 235.
- `attributes`, `sound`, and barline are absent. Divisions 1, key fifths 1
  major, time 4/4, and clef G line 2 carry over from measure 1 (implicit
  carryover; not redeclared).

Events (source order; encoded values):

| # | Element | Step | Alter | Octave | Duration (divisions) | Duration unit | Written type | Dots | Voice | Staff | Stem | Chord | Tie | default-x | default-y |
|---|---------|------|-------|--------|----------------------|---------------|--------------|------|-------|-------|------|-------|-----|-----------|-----------|
| 1 | note | B | — | 4 | 2 | 2 quarter notes | half | none | 1 | — | down | — | — | 75.35 | -20 |
| 2 | note | A | — | 4 | 2 | 2 quarter notes | half | none | 1 | — | up | — | — | 127.85 | -25 |

Lyrics (exact text; two separate lines; not normalized):

| Event | Lyric # | Syllabic | Text | default-x | default-y | relative-y |
|-------|---------|----------|------|-----------|-----------|------------|
| 1 | 1 | single | hot | 6.5 | -44.92 | -30 |
| 1 | 2 | single | Mi | 6.5 | -68.63 | -30 |
| 2 | 1 | single | cross | 6.5 | -44.92 | -30 |
| 2 | 2 | single | Re | 6.5 | -68.63 | -30 |

All lyrics encode number, syllabic, text, and all three placement
attributes.

Derived verification (calculated, not encoded):

- Total encoded duration: 2 + 2 = 4 divisions (= 4 quarter notes).
- Expected measure duration (4/4, divisions 1): 4 divisions.
- Duration total fills the measure: yes (4 = 4).
- Pitched notes: 2; rests: 0; lyric elements: 4.

#### Measure 8 (number 8, width 125.05)

Measure-level (encoded):

- `print`, `attributes`, and `sound` are absent. Divisions 1, key fifths 1
  major, time 4/4, and clef G line 2 carry over from measure 1 (implicit
  carryover; not redeclared).
- A `barline` is encoded at location `right`, with bar style `light-heavy`.

Events (source order; encoded values):

| # | Element | Step | Alter | Octave | Duration (divisions) | Duration unit | Written type | Dots | Voice | Staff | Stem | Chord | Tie | default-x | default-y |
|---|---------|------|-------|--------|----------------------|---------------|--------------|------|-------|-------|------|-------|-----|-----------|-----------|
| 1 | note | G | — | 4 | 3 | 3 quarter notes (dotted half) | half | 1 dot (`dot` element with `default-x` 30.49, `default-y` -25) | 1 | — | up | — | — | 12.5 | -30 |
| 2 | rest | — | — | — | 1 | 1 quarter note | quarter | none | 1 | — | — | — | — | 79.05 | -20 |

Event 2 encodes an empty `<rest/>` element; no stem, chord, tie, or `staff`
is encoded for it.

Lyrics (exact text; not normalized):

| Event | Lyric # | Syllabic | Text | default-x | default-y | relative-y |
|-------|---------|----------|------|-----------|-----------|------------|
| 1 | 1 | single | buns. | 8.51 | -44.92 | -30 |
| 1 | 2 | single | Do | 6.5 | -68.63 | -30 |

All expected lyric fields are present; the period in "buns." is preserved
exactly.

Derived verification (calculated, not encoded):

- Total encoded duration: 3 + 1 = 4 divisions (= 4 quarter notes).
- Expected measure duration (4/4, divisions 1): 4 divisions.
- Duration total fills the measure: yes (4 = 4).
- Pitched notes: 1; rests: 1; lyric elements: 2.

All eight measures are documented. Task 2D validation, final derived totals,
absent-feature analysis, and consolidated uncertainties are recorded below.

### MusicXML-Only and Export Metadata

Task 2A (2026-09-17, Qwen). Engraving, layout, font, MIDI, playback, and
export-specific metadata, kept separate from musical facts.

Scaling (directly encoded):

| Item | Value |
|------|-------|
| millimeters | 6.99912 |
| tenths | 40 |

Page layout (directly encoded):

| Item | Value |
|------|-------|
| Page height | 1696.93 |
| Page width | 1200.48 |
| Margins (even) | left 85.725, right 85.725, top 85.725, bottom 85.725 |
| Margins (odd) | left 85.725, right 85.725, top 85.725, bottom 85.725 |

Appearance — line widths (directly encoded):

| Type | Width |
|------|-------|
| light barline | 1.8 |
| heavy barline | 5.5 |
| beam | 5 |
| bracket | 4.5 |
| dashes | 1 |
| enclosure | 1 |
| ending | 1.1 |
| extend | 1 |
| leger | 1.6 |
| pedal | 1.1 |
| octave shift | 1.1 |
| slur middle | 2.1 |
| slur tip | 0.5 |
| staff | 1.1 |
| stem | 1 |
| tie middle | 2.1 |
| tie tip | 0.5 |
| tuplet bracket | 1 |
| wedge | 1.2 |

Note sizes (directly encoded): cue 70, grace 70, grace-cue 49.

Fonts (directly encoded):

| Font | Family | Size |
|------|--------|------|
| Music font | Leland | (no size encoded) |
| Word font | Edwin | 10 |
| Lyric font | Edwin | 10 |

System-layout values (directly encoded):

| Location | Values |
|----------|--------|
| Measure 1 `print` | system-margins left 50, right 0; top-system-distance 170 |
| Measure 7 `print` | system-margins left 0, right 0; system-distance 235 |

MIDI / playback (directly encoded, instrument P1-I1):

| Item | Value |
|------|-------|
| MIDI channel | 1 |
| MIDI program | 1 |
| Volume | 78.7402 |
| Pan | 0 |

Export origin (cross-reference, see Document Metadata): MuseScore Studio
4.6.5, encoding date 2026-03-30, platform Linux.

Layout note: every `measure` element carries a `width` attribute
(engraving layout); per-measure layout values are recorded in Tasks 2B/2C.

### Task 2D Validation Summary

Task 2D (2026-09-17, Codex) re-read the complete `score.xml` and independently
recomputed the structural, event, duration, pitch, voice, lyric, system-break,
and barline totals.

| Validation target | Result |
|-------------------|--------|
| Archive identity | Source SHA-256 remains `2e48621ad69af56297fb015cd036e62f582b1f3dd8c48239f1f84c7e17d6471e` |
| Document metadata and score structure | Task 2A record matches the encoded values |
| Measures 1–4 | Task 2B event order, values, lyrics, and duration checks match the XML |
| Measures 5–8 | Task 2C event order, values, lyrics, and duration checks match the XML |
| Measure durations | All 8 measures total 4 divisions under divisions 1 and 4/4 |
| Voices | Every event encodes voice 1; no other voice value occurs |
| Explicit staff assignments | No `staff` element occurs |
| System break | One explicit `new-system="yes"`, at measure 7 |
| Barlines | One `barline` element: measure 8, location right, style light-heavy |
| PDF use | Not rendered or content-inspected during Part 1 |

No measure-level corrections were required during Task 2D. The obsolete
Part 1 limitation stating that the MusicXML content had not been inspected
was corrected.

### Explicitly Absent Features

The following statements mean that the named MusicXML element or structure
does not occur in this document. They do not claim that the corresponding
musical concept could never apply outside this encoding.

| Feature | Validation result |
|---------|-------------------|
| Chords | No `chord` element |
| Ties | No `tie` or `tied` element |
| Slurs | No `slur` element |
| Articulations | No `articulations` element |
| Dynamics | No `dynamics` or `direction` element |
| Ornaments | No `ornaments` element |
| Grace notes | No `grace` element |
| Tuplets | No `time-modification` or `tuplet` element |
| Beams | No `beam` element |
| Fermatas | No `fermata` element |
| Repeats and endings | No `repeat` or `ending` element |
| Accidentals | No `accidental` or pitch `alter` element |
| Transposition | No `transpose` element |
| Explicit staff assignments | No `staff` element |
| Multiple parts | One declared part only (`P1`) |
| Multiple voices | Only voice value 1 occurs |
| Attribute changes | One `attributes` element in measure 1; no later divisions, key, meter, or clef redeclaration |
| Tempo changes | One `sound tempo="96"` in measure 1; no later `sound` or tempo declaration |
| Pickup or incomplete measure | No measure has `implicit="yes"`; each measure totals the full 4 divisions expected in 4/4 |

The `supports` declarations for accidentals, beams, print attributes, and
stems describe exporter capabilities, not occurrences in the score. Likewise,
appearance defaults for ties, slurs, tuplets, wedges, and other symbols do not
mean that those notations occur.

Document-level absences and empty values:

- `work` contains only `work-title`; it contains no `work-number` or `opus`.
- The document contains no movement number or movement title.
- `identification` contains no creator, rights, relation, or source field; it
  contains only the recorded encoding information and two miscellaneous
  fields.
- `part-name` for P1 is present but explicitly empty.
- `instrument-name` for P1-I1 is present but explicitly empty.
- No standalone tempo or direction element occurs; tempo is encoded only as
  the measure 1 `sound` attribute.

### Derived Totals

All values in this section are calculated from the encoded MusicXML rather
than stored as whole-score totals in the source.

Score and event totals:

| Item | Derived total |
|------|---------------|
| Parts | 1 |
| Measures | 8, sequentially numbered 1–8 |
| Total events (`note` elements) | 20 |
| Pitched notes | 17 |
| Rests | 3 |
| Total encoded duration | 32 divisions = 32 quarter-note units |
| Pitched-note duration | 29 divisions |
| Rest duration | 3 divisions |
| Distinct voice values | 1 (`voice` 1) |
| Distinct explicitly encoded staff values | 0 |
| Lyric elements | 34: 17 on lyric line 1 and 17 on lyric line 2 |
| Explicit system breaks | 1, before measure 7 |
| Explicit final barlines | 1, at measure 8 |

Written-duration distribution:

| Written type | Events | Pitched notes | Rests | Dotted events |
|--------------|--------|---------------|-------|---------------|
| Half | 9 | 9 | 0 | 3 |
| Quarter | 11 | 8 | 3 | 0 |

Encoded-duration distribution:

| Duration value | Events | Musical reading under divisions 1 |
|----------------|--------|-----------------------------------|
| 1 | 11 | Quarter-note duration |
| 2 | 6 | Half-note duration |
| 3 | 3 | Dotted-half duration |

Pitch distribution and range:

| Encoded pitch | Count |
|---------------|-------|
| G4 | 7 |
| A4 | 7 |
| B4 | 3 |

- Encoded pitch range: G4 through B4.
- No pitch contains an `alter` element; the range and counts use only the
  encoded step and octave values.

Measure-duration validation:

| Measure | Encoded duration total | Expected in 4/4 | Result |
|---------|------------------------|-----------------|--------|
| 1 | 4 | 4 | Full |
| 2 | 4 | 4 | Full |
| 3 | 4 | 4 | Full |
| 4 | 4 | 4 | Full |
| 5 | 4 | 4 | Full |
| 6 | 4 | 4 | Full |
| 7 | 4 | 4 | Full |
| 8 | 4 | 4 | Full |

Derived lyric reconstructions:

- Lyric line 1, reconstructed from the encoded syllabic sequence: “Hot cross
  buns, hot cross buns. One a penny two a penny hot cross buns.”
- Lyric line 2, preserving encoded token order: “Mi Re Do Mi Re Do Do Do Do
  Do Re Re Re Re Mi Re Do”.
- The source tokens `pen-` (`syllabic` begin) and `ny` (`syllabic` end) are
  joined as “penny” only in the derived line-1 reconstruction; their exact
  encoded forms remain recorded in the measure tables.

### Part 1 Uncertainties and Limitations (Historical Snapshot)

The following records the state at the end of Part 1. Statements about work
not yet performed were later resolved by Parts 2-4 and are retained here only
to preserve the chronological inspection record.

- The original creator, publisher, source, rights status, and acquisition
  provenance are unknown because no accompanying provenance record exists.
- `part-name` and `instrument-name` are explicitly empty. Calling the part a
  piano part is an inference from `instrument-sound`
  (`keyboard.piano.grand`) and MIDI program 1, not an encoded name.
- No `staff` element is encoded. A single-staff reading relies on MusicXML's
  implicit behavior rather than an explicit staff declaration.
- Measures 2–8 contain no `attributes` element. Continued divisions, key,
  meter, and clef values rely on attribute carryover rather than explicit
  redeclaration in each measure.
- Tempo 96 is encoded as a `sound` attribute. There is no tempo direction or
  text marking in the MusicXML, and the PDF has not yet been inspected to
  determine what is visibly printed.
- The measure 1 `print` has no `new-page` or `new-system` attribute. Its page
  start is implicit rather than explicitly encoded by that element.
- The archive contains no `mimetype` entry. This is retained as a compressed-
  MusicXML compatibility and conformance limitation, not proof that the file
  is unusable.
- The DOCTYPE references the MusicXML 4.0 partwise DTD by URL, but DTD or XSD
  validation has not been performed.
- Layout coordinates and exporter defaults have been recorded but not checked
  against a rendered score during Part 1.
- At the completion of Part 1, the PDF had not yet been rendered or inspected.
  Part 2 has since completed that independent inspection, but no
  MusicXML-to-PDF comparison has been made.
- The final sample ground truth remains IN PROGRESS until Part 4 consolidates
  the confirmed comparison results and representation implications.

## Part 2 — PDF Observations

### Inspection Progress

| Task | Description | Status |
|------|-------------|--------|
| Task 1 | PDF source metadata and page-level visual inspection | COMPLETE (2026-09-17, Codex) |
| Task 2 | Measures 1-8, whole-PDF validation, totals, and uncertainties (combines the previously planned Tasks 2A, 2B, and 2C) | COMPLETE (2026-09-17, Codex) |

### Task 1 Inspection Method

Direct observations (2026-09-17, Codex):

- Inspected `print-full.pdf` in this sample directory; its recorded SHA-256
  remains
  `91e66bc30aab933707a64e108e8ea18d7f89ea8a7d455a1e81497e08d90d0594`.
- Confirmed the source is a one-page PDF 1.4 document.
- Rendered every page (one page total) at 200 DPI with Ghostscript 10.06.0 and
  visually inspected the resulting 1653 × 2339 pixel image.
- Used text extraction only as a secondary check for readable text. All layout
  and notation observations below come from the rendered page.
- Did not open or consult the MusicXML while interpreting the PDF. No
  cross-source comparison was performed.

### PDF Source Metadata

| Field | Direct PDF observation |
|-------|------------------------|
| File size | 26,850 bytes |
| Format | PDF 1.4 |
| Page count | 1 |
| Page box | 595 × 842 points (A4 portrait) |
| XMP title | `Hot Cross Buns` |
| XMP creator | Empty |
| PDF author | Empty |
| Creator tool | `MuseScore Studio Version: 4.6.5` |
| Producer | `Qt 6.9.2` |
| Creation and modification dates | XMP date fields are empty; the PDF information dictionary contains unusable zero-value placeholders rather than valid dates |
| XMP document ID | `uuid:42457a4f-255a-41ea-9ee2-4cb1d88dd56a` |
| XMP version ID | `1` |
| Trapped | `False` |

The embedded creator-tool value identifies the software used to produce this
PDF. It does not establish the score's author, publisher, rights holder, or
relationship to the MusicXML source.

### Page-Level Visual Observations

- The centered visible title is **Hot Cross Buns**.
- No composer, arranger, lyricist, publisher, copyright, or other visible
  credit appears on the page.
- The page contains two left-aligned music systems, each with one five-line
  staff. No brace, bracket, instrument label, or additional staff is visible.
- The first system contains six visible measure segments. The second system
  contains two, for eight visible measure segments on the page.
- The second system begins with the printed measure number `7`. No other
  measure number is printed.
- A treble clef, a one-sharp key signature, and a 4/4 time signature appear at
  the start of the first system.
- The second system repeats the treble clef and one-sharp key signature. It
  does not visibly repeat the time signature.
- Pitched notes and rests are visible. The page uses unfilled noteheads for
  the longer values and filled, unbeamed noteheads for the shorter values.
- Two aligned text lines appear below the pitched notes: an English lyric line
  and a movable-do solfège line using `Mi`, `Re`, and `Do`.
- The visible English text reads, in page order, “Hot cross buns, hot cross
  buns. One a pen-ny two a pen-ny hot cross buns.” Capitalization and
  punctuation vary by phrase as printed.
- No tempo text or metronome mark is visibly printed.
- No dynamics, articulations, slurs, ties, chord symbols, fingerings, pedal
  marks, rehearsal marks, repeat signs, or volta endings are visible at this
  page-level inspection.
- The final measure ends with a visible final barline.
- The notation and text are sharp and readable. No clipping, overlap, missing
  glyph, or rendering defect was observed. The second system is much shorter
  than the first, leaving substantial unused space on the lower page; this is
  a layout observation, not a musical discrepancy.

### Task 1 Uncertainties and Limits

- A one-sharp signature is visible, but the printed signature alone does not
  uniquely establish whether the mode is G major, E minor, or another tonal
  interpretation.
- Eight measure segments are visible, but only measure `7` is explicitly
  numbered. The other measure positions are counted from the printed
  barlines, not from printed measure labels.
- Absence from the rendered page establishes only that an item is not visibly
  printed. It does not establish whether hidden or playback-only source data
  exists.
- Embedded metadata does not provide a valid creation date or a named author.
- MuseScore Studio is identified as the PDF creator tool, but Task 1 does not
  determine whether this PDF and the MusicXML were produced from the same
  notation document. That question remains reserved for Part 3.
- Task 1 did not transcribe measure-level content. That work is completed and
  validated in Task 2 below.

### Task 2 Inspection Method and Reading Conventions

Direct PDF observations (2026-09-17, Codex):

- Re-rendered the complete one-page PDF at 400 DPI with Ghostscript 10.06.0
  and inspected the full page plus enlarged crops of both systems.
- Confirmed that the 400 DPI render produced one 3306 x 4678 pixel page and
  that the PDF SHA-256 remained
  `91e66bc30aab933707a64e108e8ea18d7f89ea8a7d455a1e81497e08d90d0594`.
- Read pitches from the visible treble clef using standard staff positions.
  The visible one-sharp signature affects F; all printed pitches in this score
  are G, A, or B and therefore require no key-signature alteration.
- Read beat positions from the visible 4/4 meter. Beat `1` is the start of
  each measure; subsequent onsets are counted in quarter-note beats.
- Counted measures from the left edge of the first system and successive
  barlines. Only measure `7` is explicitly numbered in print; the remaining
  measure numbers below are positional labels used for this transcription.
- Used the rendered PDF as the sole musical source for this transcription and
  validation. MusicXML was not used as an answer key, and no cross-source
  comparison was performed.

### Measure-Level PDF Transcription

| Measure | Printed number | System | Beat | Visible event | Written value | Stem | English lyric | Solfege |
|---------|----------------|--------|------|---------------|---------------|------|---------------|---------|
| 1 | Not printed | 1 | 1 | B4 note | Half note (2 beats) | Down | `Hot` | `Mi` |
| 1 | Not printed | 1 | 3 | A4 note | Half note (2 beats) | Up | `cross` | `Re` |
| 2 | Not printed | 1 | 1 | G4 note | Dotted half note (3 beats) | Up | `buns,` | `Do` |
| 2 | Not printed | 1 | 4 | Rest | Quarter rest (1 beat) | Not applicable | - | - |
| 3 | Not printed | 1 | 1 | B4 note | Half note (2 beats) | Down | `hot` | `Mi` |
| 3 | Not printed | 1 | 3 | A4 note | Half note (2 beats) | Up | `cross` | `Re` |
| 4 | Not printed | 1 | 1 | G4 note | Dotted half note (3 beats) | Up | `buns.` | `Do` |
| 4 | Not printed | 1 | 4 | Rest | Quarter rest (1 beat) | Not applicable | - | - |
| 5 | Not printed | 1 | 1 | G4 note | Quarter note (1 beat) | Up | `One` | `Do` |
| 5 | Not printed | 1 | 2 | G4 note | Quarter note (1 beat) | Up | `a` | `Do` |
| 5 | Not printed | 1 | 3 | G4 note | Quarter note (1 beat) | Up | `pen-` | `Do` |
| 5 | Not printed | 1 | 4 | G4 note | Quarter note (1 beat) | Up | `ny` | `Do` |
| 6 | Not printed | 1 | 1 | A4 note | Quarter note (1 beat) | Up | `two` | `Re` |
| 6 | Not printed | 1 | 2 | A4 note | Quarter note (1 beat) | Up | `a` | `Re` |
| 6 | Not printed | 1 | 3 | A4 note | Quarter note (1 beat) | Up | `pen-` | `Re` |
| 6 | Not printed | 1 | 4 | A4 note | Quarter note (1 beat) | Up | `ny` | `Re` |
| 7 | `7` | 2 | 1 | B4 note | Half note (2 beats) | Down | `hot` | `Mi` |
| 7 | `7` | 2 | 3 | A4 note | Half note (2 beats) | Up | `cross` | `Re` |
| 8 | Not printed | 2 | 1 | G4 note | Dotted half note (3 beats) | Up | `buns.` | `Do` |
| 8 | Not printed | 2 | 4 | Rest | Quarter rest (1 beat) | Not applicable | - | - |

### Measure-Level Checks

| Measure | Visible sequence | Pitched notes | Rests | Duration check | Ending barline |
|---------|------------------|---------------|-------|----------------|----------------|
| 1 | B4 half, A4 half | 2 | 0 | 2 + 2 = 4 beats - PASS | Regular single |
| 2 | G4 dotted half, quarter rest | 1 | 1 | 3 + 1 = 4 beats - PASS | Regular single |
| 3 | B4 half, A4 half | 2 | 0 | 2 + 2 = 4 beats - PASS | Regular single |
| 4 | G4 dotted half, quarter rest | 1 | 1 | 3 + 1 = 4 beats - PASS | Regular single |
| 5 | Four G4 quarter notes | 4 | 0 | 1 + 1 + 1 + 1 = 4 beats - PASS | Regular single |
| 6 | Four A4 quarter notes | 4 | 0 | 1 + 1 + 1 + 1 = 4 beats - PASS | Regular single at system end |
| 7 | B4 half, A4 half | 2 | 0 | 2 + 2 = 4 beats - PASS | Regular single |
| 8 | G4 dotted half, quarter rest | 1 | 1 | 3 + 1 = 4 beats - PASS | Final light-heavy barline |

All eight visible measures contain exactly four quarter-note beats under the
printed 4/4 meter. No pickup or incomplete measure is visible.

### Whole-PDF Derived Totals

| Category | PDF-derived total |
|----------|-------------------|
| Pages | 1 |
| Systems | 2 |
| Staff lines per system | 5 |
| Visible measure segments | 8 |
| Total musical events | 20 |
| Pitched-note events | 17 |
| Rest events | 3 |
| Total duration | 32 quarter-note beats |
| Sounding-note duration | 29 quarter-note beats |
| Rest duration | 3 quarter-note beats |
| English lyric syllabic units | 17 |
| Solfege syllabic units | 17 |
| Total visible lyric-to-note alignments | 34 |

#### Pitches and Sounding Durations

| Pitch | Note count | Written values | Sounding duration |
|-------|------------|----------------|-------------------|
| G4 | 7 | 3 dotted half notes, 4 quarter notes | 13 beats |
| A4 | 7 | 3 half notes, 4 quarter notes | 10 beats |
| B4 | 3 | 3 half notes | 6 beats |
| **Total** | **17** | **17 pitched notes** | **29 beats** |

The visible pitch range is G4 through B4 under the printed treble clef.

#### Written Values

| Written value | Count | Beat contribution |
|---------------|-------|-------------------|
| Half notes | 6 | 12 beats |
| Dotted half notes | 3 | 9 beats |
| Quarter notes | 8 | 8 beats |
| Quarter rests | 3 | 3 beats |
| **Total** | **20 events** | **32 beats** |

#### Lyrics and Solfege

- Every pitched note has one aligned English syllabic unit and one aligned
  solfege syllabic unit; rests carry no text.
- The English sequence is `Hot cross buns, hot cross buns. One a pen-ny two a
  pen-ny hot cross buns.`
- The solfege sequence is `Mi Re Do Mi Re Do Do Do Do Do Re Re Re Re Mi Re
  Do`.
- `pen-ny` is visibly hyphenated in measures 5 and 6. No melisma, lyric
  extension line, or elision is visible.
- Printed capitalization is retained: `Hot` and `One` begin with capitals;
  later English words are lowercase. Every solfege syllable begins with a
  capital letter.

### Whole-PDF Validation

- Measure count: PASS - six measures on system 1 plus two on system 2 equals
  eight.
- Event count: PASS - 17 pitched notes plus 3 rests equals 20 events.
- Duration total: PASS - eight 4/4 measures equal 32 quarter-note beats; the
  transcribed events also total 32 beats.
- Pitch count: PASS - G4 (7) plus A4 (7) plus B4 (3) equals 17 pitched notes.
- Written-value count: PASS - 6 half notes, 3 dotted half notes, 8 quarter
  notes, and 3 quarter rests equal 20 events.
- Lyric alignment: PASS - each of 17 pitched notes carries two aligned text
  entries, producing 34 visible lyric-to-note alignments.
- System continuity: PASS - the first system ends after measure 6; the second
  begins with the printed measure number 7 and continues through the final
  barline after measure 8.
- Rendering: PASS - the 400 DPI page and both enlarged systems are sharp and
  complete, with no clipped notation, overlapping text, missing glyphs, or
  unreadable event.

### Visibly Absent Features

The following are not visibly printed anywhere on the PDF page:

- chords or simultaneous stacked noteheads;
- multiple visible voices or contrapuntal event streams;
- ties, slurs, phrase marks, articulations, ornaments, grace notes, tuplets,
  beams, tremolos, or fermatas;
- dynamics, hairpins, tempo text, metronome marks, expression text, rehearsal
  marks, fingerings, pedal marks, or octave signs;
- chord symbols, figured bass, fretboard diagrams, or harmonic-analysis text;
- accidentals attached to individual notes, ledger lines, clef changes, key
  changes, or meter changes;
- repeat barlines, repeat instructions, first/second endings, codas, segnos,
  or jumps;
- instrument name, part name, staff label, brace, bracket, additional staff,
  or visible MIDI/playback information;
- composer, arranger, lyricist, publisher, rights, copyright, footer, or page
  number text.

These statements describe visible print only. They do not establish whether
non-printing source or playback data exists.

### Task 2 Uncertainties and Limitations

- Only measure `7` has a printed number. Labels 1-6 and 8 are positional
  transcription labels inferred from the visible sequence of barlines.
- Pitch names assume the standard interpretation of the printed treble clef.
  The note positions themselves are clear, and G4, A4, and B4 are unaffected
  by the one-sharp signature.
- The one-sharp key signature does not by itself establish a tonal mode. A
  conclusion such as G major or E minor requires information beyond the
  signature alone.
- The PDF shows one visible monophonic event sequence, but it cannot identify
  an internal voice number or prove how many voices exist in the source file.
- Stem directions are visible engraving facts. Task 2 does not assume they
  carry a separate semantic meaning beyond the printed notation.
- No tempo is visibly printed, so performance speed cannot be established
  from the PDF.
- The PDF contains no valid named author or creation date and provides no
  acquisition or rights provenance.
- PDF inspection alone cannot determine whether this PDF and the MusicXML
  were exported from the same notation document.
- No MusicXML-to-PDF agreement or discrepancy claim is made in Part 2. Those
  conclusions are reserved for Part 3.

### Part 2 Outcome

Part 2 is COMPLETE. PDF metadata, page layout, every visible measure, all
event and lyric alignments, whole-page totals, visible absences, validation
checks, and uncertainties have been recorded independently. Part 3 may now
compare this record against the separately completed MusicXML record.

## Part 3 — MusicXML and PDF Comparison

### Comparison Method

Direct comparison performed 2026-09-17 by Codex:

- Reopened the `.mxl` archive and read its declared root document,
  `score.xml`, directly.
- Re-rendered all of `print-full.pdf` at 400 DPI and visually inspected the
  complete page while comparing it with the MusicXML source.
- Reconfirmed both source SHA-256 digests before comparison.
- Compared score metadata, page geometry, part/staff structure, musical
  attributes, every event at every onset, lyrics, stem directions, system
  layout, barlines, whole-score totals, and absent features.
- Classified each difference as a musical discrepancy, source-specific
  metadata, rendering behavior, or unresolved ambiguity. Missing printed
  playback or internal identifiers were not treated as musical discrepancies.

### Score-Level Comparison

| Topic | MusicXML evidence | PDF evidence | Comparison result |
|-------|-------------------|--------------|-------------------|
| Title | `work-title` and page-1 title credit both read `Hot Cross Buns` | XMP and visible title both read `Hot Cross Buns` | Exact match |
| Export software | `MuseScore Studio 4.6.5` | Creator tool `MuseScore Studio Version: 4.6.5` | Same application and version |
| Named creator | No `creator` element | Empty XMP creator and empty PDF author | Compatible absence; creator remains unknown |
| Rights/publisher | No rights or publisher data | No visible or embedded rights/publisher credit | Compatible absence; provenance remains unknown |
| Page count | Page-1 title credit, no new-page instruction, and layout sized for one page | One PDF page | Compatible intended one-page layout; MusicXML has no PDF-style page object |
| Page size | Scaling and page layout convert to approximately 595.44 x 841.68 points | MediaBox is 595 x 842 points | Match to PDF point rounding; both are A4 portrait |
| Fonts | Leland music font and Edwin word/lyric font families | Embedded Leland and Edwin font families | Family match |
| Part/staff structure | One declared part; one G clef; no explicit `staff` elements | One visible five-line staff continued across two systems | Compatible single-staff presentation |
| Part/instrument label | `part-name` and `instrument-name` are empty | No visible part or instrument label | Exact visible outcome |
| Instrument playback | `keyboard.piano.grand`, MIDI channel 1/program 1 | No playback data is printed | MusicXML-only playback metadata; not a discrepancy |
| Measure count | Measures numbered 1-8 | Eight visible measure segments | Exact match |
| Clef | G clef on line 2 | Treble clef on both systems | Match; second-system clef is normal rendering repetition |
| Key signature | One fifth with encoded mode `major` | One-sharp signature on both systems | Signature matches; major mode is not independently visible in print |
| Meter | 4 beats over beat-type 4 | 4/4 printed on system 1 and continued through all measures | Match |
| Divisions | 1 division per quarter note | No internal duration unit is printed | MusicXML-only representation detail |
| Voice/staff identifiers | Every event has voice `1`; no explicit staff number | One visible monophonic event stream; no voice/staff identifier | Compatible, but internal voice number is not verifiable from PDF |
| Tempo | Playback-only `sound tempo="96"`; no tempo direction or words | No tempo or metronome mark printed | Expected omission; not a discrepancy |
| System layout | Explicit `new-system="yes"` at measure 7; first-system left margin exceeds later-system margin | System 1 contains measures 1-6; measure 7 starts the less-indented second system | Match |
| Measure numbering | All measures carry source number attributes; no explicit print-numbering instruction | Only `7` is visibly printed at the second-system start | Rendering policy/source identifier distinction; not a musical discrepancy |
| Final barline | Measure 8 right barline is `light-heavy` | Measure 8 ends with a visible thin-thick final barline | Exact match |

### Event-by-Event Comparison

Beat positions below use quarter-note beats under the shared 4/4 meter.

| Measure | Beat | MusicXML event | PDF event | English / solfege | Result |
|---------|------|----------------|-----------|--------------------|--------|
| 1 | 1 | B4 half note, stem down | B4 half note, stem down | `Hot` / `Mi` | Exact match |
| 1 | 3 | A4 half note, stem up | A4 half note, stem up | `cross` / `Re` | Exact match |
| 2 | 1 | G4 dotted half note, stem up | G4 dotted half note, stem up | `buns,` / `Do` | Exact match |
| 2 | 4 | Quarter rest | Quarter rest | No lyrics | Exact match |
| 3 | 1 | B4 half note, stem down | B4 half note, stem down | `hot` / `Mi` | Exact match |
| 3 | 3 | A4 half note, stem up | A4 half note, stem up | `cross` / `Re` | Exact match |
| 4 | 1 | G4 dotted half note, stem up | G4 dotted half note, stem up | `buns.` / `Do` | Exact match |
| 4 | 4 | Quarter rest | Quarter rest | No lyrics | Exact match |
| 5 | 1 | G4 quarter note, stem up | G4 quarter note, stem up | `One` / `Do` | Exact match |
| 5 | 2 | G4 quarter note, stem up | G4 quarter note, stem up | `a` / `Do` | Exact match |
| 5 | 3 | G4 quarter note, stem up | G4 quarter note, stem up | `pen-` / `Do` | Exact match |
| 5 | 4 | G4 quarter note, stem up | G4 quarter note, stem up | `ny` / `Do` | Exact match |
| 6 | 1 | A4 quarter note, stem up | A4 quarter note, stem up | `two` / `Re` | Exact match |
| 6 | 2 | A4 quarter note, stem up | A4 quarter note, stem up | `a` / `Re` | Exact match |
| 6 | 3 | A4 quarter note, stem up | A4 quarter note, stem up | `pen-` / `Re` | Exact match |
| 6 | 4 | A4 quarter note, stem up | A4 quarter note, stem up | `ny` / `Re` | Exact match |
| 7 | 1 | B4 half note, stem down | B4 half note, stem down | `hot` / `Mi` | Exact match |
| 7 | 3 | A4 half note, stem up | A4 half note, stem up | `cross` / `Re` | Exact match |
| 8 | 1 | G4 dotted half note, stem up | G4 dotted half note, stem up | `buns.` / `Do` | Exact match |
| 8 | 4 | Quarter rest | Quarter rest | No lyrics | Exact match |

All 20 event positions match in event kind, pitch where applicable, onset,
written value, duration, and visible stem direction. All 34 lyric-to-note
alignments match in text, capitalization, punctuation, order, and note
association. The MusicXML `syllabic` begin/end values for `pen-ny` in measures
5 and 6 agree with the PDF's visible hyphenation.

### Measure-by-Measure Structural Comparison

| Measure | MusicXML structure/layout | PDF structure/layout | Result |
|---------|---------------------------|----------------------|--------|
| 1 | Declares 4/4, one-sharp major key, G clef; B4 half + A4 half | Prints 4/4, one sharp, treble clef; same two notes | Musical and visible-attribute match |
| 2 | G4 dotted half + quarter rest; lyric punctuation `buns,` | Same note/rest sequence and punctuation | Exact match |
| 3 | B4 half + A4 half | Same two notes | Exact match |
| 4 | G4 dotted half + quarter rest; lyric punctuation `buns.` | Same note/rest sequence and punctuation | Exact match |
| 5 | Four G4 quarters; `One a pen-ny`; four `Do` syllables | Same events, text, hyphenation, and solfege | Exact match |
| 6 | Four A4 quarters; `two a pen-ny`; four `Re` syllables | Same events, text, hyphenation, and solfege; ends system 1 | Exact musical match; system endpoint agrees |
| 7 | Explicit new-system instruction; B4 half + A4 half | Begins system 2 with printed number `7`; same notes and text | Exact musical and system-break match |
| 8 | G4 dotted half + quarter rest; right light-heavy barline | Same events and final thin-thick barline | Exact match |

Every measure totals four quarter-note beats in both records. No pickup,
overflow, underfilled measure, reordered event, or changed lyric was found.

### Aggregate Comparison

| Fact | MusicXML | PDF | Result |
|------|----------|-----|--------|
| Measures | 8 | 8 | Match |
| Total events | 20 | 20 | Match |
| Pitched notes | 17 | 17 | Match |
| Rests | 3 | 3 | Match |
| Total duration | 32 quarter-note units | 32 quarter-note beats | Match |
| Pitch counts | G4: 7, A4: 7, B4: 3 | G4: 7, A4: 7, B4: 3 | Match |
| Written values | 6 half, 3 dotted half, 8 quarter notes, 3 quarter rests | Same | Match |
| Pitch range | G4-B4 | G4-B4 | Match |
| English lyric units | 17 | 17 | Match |
| Solfege lyric units | 17 | 17 | Match |
| Total lyric elements/alignments | 34 | 34 | Match |
| Systems | New system at measure 7 | Two systems; second begins at measure 7 | Match |
| Final barline | Light-heavy after measure 8 | Thin-thick final barline after measure 8 | Match |

### Absent-Feature Comparison

| Feature group | MusicXML evidence | PDF evidence | Result |
|---------------|-------------------|--------------|--------|
| Chords | No `chord` elements | No stacked simultaneous noteheads | Match |
| Multiple voices | Only voice `1`; no backup/forward voice interleaving | One visible monophonic event stream | Compatible absence |
| Ties and slurs | No tie, tied, or slur elements | No visible ties or slurs | Match |
| Articulations and ornaments | No articulation or ornament elements | None visible | Match |
| Dynamics and expressive marks | No dynamics, wedge, or expression directions | None visible | Match |
| Grace notes and tuplets | No grace, time-modification, or tuplet elements | None visible | Match |
| Beams, tremolos, and fermatas | No corresponding elements | None visible | Match |
| Repeats and endings | No repeat or ending elements | No repeat barlines or volta endings | Match |
| Note accidentals | No accidental elements; pitches need no displayed accidental under the key signature | No note-attached accidentals | Match |
| Mid-score attribute changes | No later key, meter, or clef declarations | No visible key, meter, or clef change | Match |
| Printed tempo | No direction or tempo text; only non-printing playback tempo | No tempo or metronome mark | Match in printed content |
| Instrument/staff labels | Empty part and instrument names; no staff label text | No visible instrument or staff label | Match |

The PDF cannot prove hidden-source absence by itself. These conclusions are
confirmed for this source pair because the direct MusicXML inspection and the
visible PDF inspection agree.

### Source-Specific Information and Expected Omissions

The following differences concern representation or metadata rather than the
musical score:

- **MusicXML packaging:** the `.mxl` ZIP structure, `score-partwise` 4.0 root,
  DTD reference, divisions, element IDs, voice number, duration integers, and
  measure-width/default-position values have no direct printed equivalent.
- **MusicXML encoding metadata:** encoding date `2026-03-30`, platform
  `Linux`, feature-support declarations, and the archive's missing `mimetype`
  entry are not PDF score content.
- **MusicXML playback metadata:** tempo 96, grand-piano sound, MIDI channel,
  program, volume, pan, device ID, and instrument ID are non-printing data.
- **PDF container metadata:** PDF 1.4, Qt 6.9.2 producer, XMP document/version
  IDs, trapping flag, and unusable PDF date placeholders have no MusicXML
  musical equivalent.
- **Rendered appearance:** the PDF contains final glyph shapes and embedded
  font subsets. MusicXML instead declares Leland/Edwin font families and
  numerical engraving defaults that a renderer interprets.
- **Mode visibility:** MusicXML explicitly says `major`; the PDF prints the
  matching one-sharp signature but cannot independently expose the encoded
  mode.
- **System-start repetition:** the PDF repeats the clef and key signature at
  system 2. MusicXML declares them in measure 1 and carries them forward while
  explicitly starting a new system at measure 7.
- **Measure numbers:** MusicXML uses number attributes for every measure,
  while the PDF visibly prints only the system-start number `7`.

None of these differences changes a note, rest, rhythm, lyric, measure,
signature, system break, or ending barline.

### Discrepancies, Ambiguities, and Source Relationship

#### Confirmed discrepancies

No musical or visible-score discrepancy was found. The comparison found zero
contradictory events, attributes, lyrics, system breaks, or barlines.

#### Remaining ambiguities and limitations

- The PDF cannot independently verify internal MusicXML concepts such as
  divisions, voice number `1`, part/instrument IDs, encoded mode, playback
  tempo, MIDI settings, or exact numerical layout coordinates.
- MusicXML layout coordinates were compared with their visible outcomes, not
  through a pixel-perfect geometric reconstruction of every element.
- Absence of a printed feature does not by itself prove absence of hidden or
  playback-only data; the direct MusicXML inspection supplies that evidence
  only for the inspected source file.
- The MusicXML still has not been validated against its external DTD or an
  XSD, although the archive is intact and the document is well-formed enough
  for direct inspection.
- Original authorship, acquisition provenance, publisher, and rights status
  remain unknown.

#### Same-source inference

The evidence strongly suggests that the MusicXML and PDF were exported from
the same MuseScore notation document, or from musically and visually identical
copies of it:

- both identify MuseScore Studio 4.6.5;
- titles, page geometry, font families, part-label absence, attributes, all 20
  events, all lyrics, stem directions, measure durations, and totals agree;
- the unusual layout details also agree, including the measure 7 system break,
  shorter second system, and measure 8 final barline.

This is a high-confidence inference, not proven provenance. The files do not
share a documented source-project identifier, valid matching export
timestamps, or an acquisition record that conclusively links them.

### Part 3 Validation and Outcome

- Source integrity: PASS - both recorded SHA-256 digests are unchanged; the
  `.mxl` ZIP integrity check reports no errors.
- Score structure: PASS - title, page, staff presentation, clef, signature,
  meter, measure count, system break, and final barline are compatible or
  exact matches.
- Events: PASS - 20 of 20 event positions match.
- Pitches: PASS - 17 of 17 pitched events match.
- Rests: PASS - 3 of 3 rests match.
- Durations: PASS - 8 of 8 measures and all 32 quarter-note units match.
- Lyrics: PASS - 34 of 34 text alignments match.
- Genuine musical discrepancies: 0.
- Source-specific or non-printing differences: documented and classified;
  none changes the printed music.

Part 3 is COMPLETE. The comparison supports a single coherent musical record,
but Part 4 must still consolidate that evidence into the authoritative sample
ground truth and identify the facts a future canonical representation must
preserve.

## Part 4 — Established Ground Truth

### Authority and Evidence Rules

This section is the authoritative ground-truth record for
`TMM-REF-CANDIDATE-001` as of 2026-09-17. It consolidates the separately
inspected MusicXML and PDF evidence and the completed Part 3 comparison.

Evidence classifications used below:

| Classification | Meaning |
|----------------|---------|
| **CONFIRMED - BOTH** | Independently observed in both MusicXML and PDF |
| **CONFIRMED - XML** | Directly encoded in MusicXML but not independently visible in PDF |
| **CONFIRMED - PDF** | Directly present in the rendered PDF but not represented as the same kind of MusicXML fact |
| **INFERRED** | Strongly supported by evidence but not proven directly |
| **UNKNOWN** | Not established by either source or repository provenance |

Rules for using this ground truth:

- Cross-source musical facts take precedence as the strongest evidence.
- XML-only encoding and playback facts remain source facts but are not treated
  as visibly printed notation.
- PDF-only container and rendering facts remain source facts but are not
  treated as abstract musical events.
- An inference must never be silently promoted to a confirmed fact.
- Unknown authorship, rights, and provenance must remain unknown until real
  evidence is added.
- The source files remain the primary evidence. This section is their
  reviewed consolidation, not a replacement for them.

### Authoritative Score-Level Ground Truth

| Fact | Authoritative value | Evidence |
|------|---------------------|----------|
| Fixture ID | `TMM-REF-CANDIDATE-001` | Repository identifier |
| Title | `Hot Cross Buns` | CONFIRMED - BOTH |
| Composer/creator | Unknown; no named creator | CONFIRMED absence in both; identity UNKNOWN |
| Publisher/rights holder | Unknown | UNKNOWN |
| Source relationship | Likely exports of the same MuseScore document or equivalent copies, but not proven | INFERRED |
| Page presentation | One A4 portrait page | CONFIRMED - BOTH-compatible layout and CONFIRMED - PDF page object |
| Systems | Two systems: measures 1-6, then measures 7-8 | CONFIRMED - BOTH |
| Parts | One declared MusicXML part | CONFIRMED - XML; PDF presentation is compatible |
| Visible staves | One five-line staff per system, representing one continuing staff | CONFIRMED - PDF; compatible with XML |
| Part/instrument display name | Empty/not printed | CONFIRMED - BOTH |
| Encoded playback instrument | `keyboard.piano.grand`, MIDI program 1 | CONFIRMED - XML only |
| Clef | Treble clef / G clef on line 2 | CONFIRMED - BOTH |
| Key signature | One sharp | CONFIRMED - BOTH |
| Encoded key mode | Major | CONFIRMED - XML only; not independently visible from the signature |
| Meter | 4/4 throughout | CONFIRMED - BOTH |
| Measures | Eight complete measures, numbered 1-8 in source order | CONFIRMED - BOTH for count/order; numbers 1-8 CONFIRMED - XML, only `7` printed in PDF |
| Musical texture | One monophonic event stream; no chords | CONFIRMED - BOTH |
| Encoded voice | Voice `1` for every event | CONFIRMED - XML only; compatible with PDF |
| Explicit staff number | None encoded | CONFIRMED - XML only |
| Event count | 20 total: 17 pitched notes and 3 rests | CONFIRMED - BOTH |
| Pitch range | G4-B4 | CONFIRMED - BOTH |
| Total duration | 32 quarter-note beats; four beats in every measure | CONFIRMED - BOTH |
| Lyrics | Two aligned lines under every pitched note: English line 1 and solfege line 2 | CONFIRMED - BOTH |
| Printed tempo | None | CONFIRMED - BOTH for printed notation |
| Playback tempo | 96 quarter-note beats per minute | CONFIRMED - XML only |
| System break | Before measure 7 | CONFIRMED - BOTH |
| Ending | Measure 8 ends with a light-heavy/final barline | CONFIRMED - BOTH |

The playback instrument and tempo are not grounds for claiming that a piano
label or tempo mark is printed. The instrument display name is empty, and the
PDF contains no tempo marking.

### Authoritative Measure-Level Ground Truth

Beat positions use quarter-note beats in 4/4. Each event sequence is ordered
by onset. Stems are included because they are explicit in MusicXML and visible
in the PDF; they are engraving facts rather than changes to pitch or duration.

| Measure | System | Ordered events | English lyric | Solfege | Duration | Ending/layout |
|---------|--------|----------------|---------------|---------|----------|---------------|
| 1 | 1 | Beat 1: B4 half, stem down; beat 3: A4 half, stem up | `Hot`, `cross` | `Mi`, `Re` | 4 beats | Regular single barline; opening clef, key, and meter printed |
| 2 | 1 | Beat 1: G4 dotted half, stem up; beat 4: quarter rest | `buns,` | `Do` | 4 beats | Regular single barline |
| 3 | 1 | Beat 1: B4 half, stem down; beat 3: A4 half, stem up | `hot`, `cross` | `Mi`, `Re` | 4 beats | Regular single barline |
| 4 | 1 | Beat 1: G4 dotted half, stem up; beat 4: quarter rest | `buns.` | `Do` | 4 beats | Regular single barline |
| 5 | 1 | Beats 1-4: four G4 quarter notes, stems up | `One`, `a`, `pen-`, `ny` | `Do`, `Do`, `Do`, `Do` | 4 beats | Regular single barline |
| 6 | 1 | Beats 1-4: four A4 quarter notes, stems up | `two`, `a`, `pen-`, `ny` | `Re`, `Re`, `Re`, `Re` | 4 beats | Regular single barline; end of system 1 |
| 7 | 2 | Beat 1: B4 half, stem down; beat 3: A4 half, stem up | `hot`, `cross` | `Mi`, `Re` | 4 beats | Starts system 2; printed measure number `7`; regular single barline |
| 8 | 2 | Beat 1: G4 dotted half, stem up; beat 4: quarter rest | `buns.` | `Do` | 4 beats | Right light-heavy/final barline |

No rest carries lyrics. Every pitched note carries exactly one English unit
and one solfege unit.

### Authoritative Totals and Invariants

| Category | Ground-truth value |
|----------|--------------------|
| Measures | 8 |
| Beats per measure | 4 |
| Total duration | 32 quarter-note beats |
| Events | 20 |
| Pitched notes | 17 |
| Rests | 3 quarter rests |
| G4 notes | 7 |
| A4 notes | 7 |
| B4 notes | 3 |
| Plain half notes | 6 |
| Dotted half notes | 3 |
| Quarter notes | 8 |
| English lyric units | 17 |
| Solfege lyric units | 17 |
| Total lyric-to-note alignments | 34 |
| Voices represented | One encoded voice (`1`) |
| Chords | 0 |
| System breaks | 1, before measure 7 |
| Final barlines | 1, after measure 8 |

Ground-truth invariants:

- Measures remain in source order 1-8.
- Every measure totals exactly four quarter-note beats.
- Pitched-note count plus rest count equals total event count: 17 + 3 = 20.
- Pitch counts total 17: 7 + 7 + 3 = 17.
- Written values total 32 beats: 12 half-note beats + 9 dotted-half beats + 8
  quarter-note beats + 3 rest beats.
- Every pitched note has two text alignments; rests have none.
- The score ends only after the measure 8 quarter rest and final barline.

### Authoritatively Absent Musical Features

The following are absent from the inspected MusicXML and absent from the
rendered PDF where they would normally be visible:

- chords and simultaneous stacked noteheads;
- multiple voices or contrapuntal event streams;
- ties, slurs, phrase marks, articulations, ornaments, grace notes, tuplets,
  tremolos, fermatas, and beams;
- dynamics, hairpins, expression text, rehearsal marks, fingerings, pedal
  marks, and octave signs;
- printed tempo text or metronome marks;
- chord symbols, figured bass, fretboard diagrams, and harmonic-analysis text;
- note-level accidentals, ledger lines, clef changes, key changes, meter
  changes, and transposition;
- repeat signs, repeat instructions, endings, codas, segnos, and jumps;
- additional staves, staff groups, braces, brackets, and printed instrument
  labels.

Absence is authoritative only for this fixture. It demonstrates the fixture's
expected empty/default cases; it does not imply that TeachMeMusic may omit
support for these features in other scores.

### Source-Specific Facts Outside the Musical Ground Truth

These facts remain documented for reproducibility and provenance, but they
must not be confused with the canonical musical event record.

#### MusicXML/MXL source facts

- Compressed archive containing `META-INF/container.xml` and root
  `score.xml`; no `mimetype` entry.
- MusicXML 4.0 `score-partwise` document with a DTD reference.
- Divisions value `1`, part/voice/instrument IDs, measure widths, default
  coordinates, page/scaling values, fonts, line widths, and exporter support
  declarations.
- MuseScore Studio 4.6.5, encoding date `2026-03-30`, platform `Linux`, and
  creation-date miscellaneous metadata.
- Playback-only piano sound, tempo, MIDI channel/program, volume, and pan.

#### PDF source facts

- PDF 1.4, one 595 x 842 point page.
- MuseScore Studio 4.6.5 creator tool and Qt 6.9.2 producer.
- XMP document/version identifiers, empty creator, unusable embedded date
  placeholders, and embedded Leland/Edwin font subsets.
- Final glyph shapes, spacing, and page whitespace produced by the renderer.

### Remaining Limitations and Unknowns

- Composer, arranger, lyricist, publisher, rights holder, licensing status,
  acquisition path, and original notation-project provenance are unknown.
- The same-source conclusion remains a high-confidence inference, not proof;
  no shared notation-project identifier or provenance record links the files.
- The `.mxl` archive is intact and inspectable but has no `mimetype` entry and
  has not been validated against the external MusicXML DTD or an XSD.
- Numerical MusicXML layout data was checked against its visible result, not
  reconstructed and compared pixel by pixel.
- Filesystem and archive timestamps are recorded facts, not proof of original
  authorship or export chronology.

### Evidence-Derived Obligations for DEV-004

DEV-004 must use this ground truth when designing the canonical
`ScoreRepresentation`. This section records required information and
distinctions; it does not prescribe classes, fields, serialization, or parser
implementation.

The future representation must be capable of preserving:

- score identity and textual metadata, including a title and genuinely
  unknown or empty creator fields;
- ordered parts/staves/voices without inventing names or instrument identity;
- the distinction between an empty display name and playback instrument
  metadata;
- ordered measures and stable source measure identifiers;
- clef, key signature, encoded mode, meter, and the scope/carry-forward of
  attributes across later measures;
- ordered events with measure, voice, onset, duration, and note-versus-rest
  identity;
- pitch spelling and octave independently of displayed accidental glyphs;
- written rhythmic value and augmentation dots in addition to normalized
  duration;
- exact lyric text, lyric line/number, syllabic status, punctuation,
  capitalization, and event association;
- explicit barline location/style and score termination;
- explicit notation/layout facts needed for faithful source representation,
  including stem direction and the measure 7 system break, or a deliberate
  documented decision to place such facts in a separate layout layer;
- the distinction between printed directions and playback-only values, such
  as the unprinted tempo 96;
- source/provenance facts separately from musical facts and separately from
  evidence-based inferences;
- empty collections/default states for absent features without fabricating
  events or markings.

DEV-004 must explicitly decide, rather than assume, whether full numerical
layout coordinates, page geometry, fonts, and MIDI/playback settings belong in
the canonical model, a separate source/layout record, or are intentionally
excluded. No `REQ-SCORE-xxx` identifier is assigned here; functional
requirements remain a DEV-004 responsibility under the project governance
rules.

### Future Parser Reference Assertions

When parser verification is introduced in DEV-005 or later, this fixture can
support assertions that parsed output preserves:

- the complete eight-measure event table above;
- all measure, event, pitch, rest, duration, and lyric totals;
- 4/4 completeness for every measure;
- the one-sharp key signature, encoded major mode, G clef, and voice identity;
- exact lyric text and `pen-ny` syllabic begin/end behavior;
- the system break and final light-heavy barline when those facts are within
  the representation contract;
- the absence of chords, ties, dynamics, articulations, repeats, and other
  features listed above.

These are evidence-derived future assertions, not current tests and not
claims that parser functionality exists.

### Part 4 Validation and Outcome

- Evidence basis: PASS - Parts 1-3 are complete and internally consistent.
- Source integrity: PASS - source hashes are unchanged and the `.mxl` archive
  passes its ZIP integrity check.
- Ground-truth arithmetic: PASS - all event, pitch, rest, duration, lyric, and
  measure totals reconcile.
- Evidence boundaries: PASS - cross-source facts, source-specific metadata,
  inference, and unknowns are explicitly separated.
- Representation implications: PASS - required preserved facts and deferred
  DEV-004 design decisions are documented without designing the model.
- Product code, parser, dependencies, and source fixtures: UNCHANGED.

Part 4 is COMPLETE and the authoritative fixture ground truth is ESTABLISHED.
The project owner approved the record after independently studying the XML
and using the PDF to play the score. DEV-003 is DONE with its clean closure
commit under the governance rules.

## Sample History

| Date | Agent | Increment | Part | Change | Next action |
|------|-------|-----------|------|--------|-------------|
| 2026-09-17 | Qwen | DEV-003 | Part 1, Task 1 | Archive inventory and README structure created | Task 2: inspect MusicXML document metadata and score structure |
| 2026-09-17 | Qwen | DEV-003 | Part 1, Task 2A | MusicXML metadata and score-level structure documented | Task 2B: document measures 1–4 |
| 2026-09-17 | Qwen | DEV-003 | Part 1, Task 2B | MusicXML measures 1–4 documented and duration-checked | Task 2C: document measures 5–8 |
| 2026-09-17 | Codex | DEV-003 | Part 1, Task 2C | MusicXML measures 5–8 documented and duration-checked | Task 2D: validate the complete MusicXML record and document derived totals, absent features, uncertainties, and limitations |
| 2026-09-17 | Codex | DEV-003 | Part 1, Task 2D | Complete MusicXML record validated; whole-score totals, absent features, uncertainties, and limitations consolidated | Task 3: summarize the completed MusicXML inspection in project documentation and hand off to PDF inspection |
| 2026-09-17 | Codex | DEV-003 | Task 3 | Part 1 summarized in project documentation and handed off | Part 2, Task 1: render and visually inspect the PDF and record PDF-only observations |
| 2026-09-17 | Codex | DEV-003 | Part 2, Task 1 | Complete PDF rendered; source metadata, page layout, visible notation framework, text, legibility, and uncertainties documented independently | Part 2, Task 2A: inspect and record PDF measures 1–4 without consulting or comparing against MusicXML |
| 2026-09-17 | Codex | DEV-003 | Part 2, Task 2 | Previously planned Tasks 2A-2C combined: all eight PDF measures transcribed and duration-checked; whole-PDF totals, visible absences, validation, and uncertainties completed independently | Part 3: compare the independently recorded MusicXML and PDF evidence measure by measure |
| 2026-09-17 | Codex | DEV-003 | Part 3 | MusicXML and PDF compared at score, measure, event, lyric, layout, and aggregate levels; no musical discrepancies found; source-specific differences and same-source inference documented | Part 4: consolidate the authoritative ground truth and canonical-representation implications |
| 2026-09-17 | Codex | DEV-003 | Part 4 | Authoritative score- and measure-level ground truth established; absences, source metadata, limitations, representation obligations, and future parser assertions documented | Human review DEV-003; after approval, create a clean commit and mark the increment DONE before starting DEV-004 |
| 2026-09-17 | Project owner / Codex | DEV-003 | Closure | Project owner confirmed the XML and PDF represent the same musical score; human review accepted and increment closed as DONE in the documentation/evidence commit | Plan DEV-004 from the approved ground truth; do not implement until its Definition of Ready is satisfied |
