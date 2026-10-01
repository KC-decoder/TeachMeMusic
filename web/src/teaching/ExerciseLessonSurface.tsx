import { useEffect, useMemo, useState } from "react";

import type { ActivePlaybackNote } from "../audio/PlaybackTransport";
import type { ExercisePresentation, TeachingPlan } from "../api";
import type { ViewerBundle } from "../contracts/viewer";
import { MidiCalibrationSurface } from "../midi/MidiCalibrationSurface";
import { NotationSurface } from "../notation/NotationSurface";
import { VirtualPiano } from "../piano/VirtualPiano";
import { PlaybackSurface } from "../playback/PlaybackSurface";

interface ExerciseLessonSurfaceProps {
  plan: TeachingPlan;
  presentation: ExercisePresentation;
  notation: ViewerBundle;
  loading?: boolean;
  onSelectExercise: (exerciseId: string) => void;
  onTempoChange: (tempoBpm: number) => void;
}

function fractionValue(value: { numerator: number; denominator: number }): number {
  return value.numerator / value.denominator;
}

function rangeLabel(presentation: ExercisePresentation): string {
  if (presentation.material_kind === "synthetic-transfer") return "New transfer pattern";
  if (presentation.measure_numbers.length === 1) {
    return `Measure ${presentation.measure_numbers[0]}`;
  }
  return `Measures ${presentation.measure_numbers[0]}–${presentation.measure_numbers.at(-1)}`;
}

function pitchName(midi: number): string {
  const names = ["C", "C♯", "D", "E♭", "E", "F", "F♯", "G", "A♭", "A", "B♭", "B"];
  return `${names[midi % 12]}${Math.floor(midi / 12) - 1}`;
}

export function ExerciseLessonSurface({
  plan,
  presentation,
  notation,
  loading = false,
  onSelectExercise,
  onTempoChange,
}: ExerciseLessonSurfaceProps) {
  const index = plan.exercises.findIndex((item) => item.id === presentation.exercise_id);
  const node = plan.nodes.find((item) => item.exercise_id === presentation.exercise_id);
  const exercise = plan.exercises[index];
  const [showNotation, setShowNotation] = useState(presentation.aid_state.notation_visible);
  const [showKeyboard, setShowKeyboard] = useState(presentation.aid_state.keyboard_visible);
  const [countInEnabled, setCountInEnabled] = useState(presentation.aid_state.count_in_enabled);
  const [focusEventIds, setFocusEventIds] = useState<string[]>([]);
  const [activeNotes, setActiveNotes] = useState<ActivePlaybackNote[]>([]);
  const tempo = fractionValue(presentation.aid_state.tempo_bpm);
  const syntheticPitches = useMemo(
    () => presentation.demonstration.notes.map((note) => pitchName(note.midi_pitch)),
    [presentation.demonstration.notes],
  );

  useEffect(() => {
    setShowNotation(presentation.aid_state.notation_visible);
    setShowKeyboard(presentation.aid_state.keyboard_visible);
    setCountInEnabled(presentation.aid_state.count_in_enabled);
    setFocusEventIds([]);
    setActiveNotes([]);
  }, [presentation.exercise_id, presentation.aid_state]);

  const countIn = useMemo(
    () =>
      countInEnabled && presentation.aid_state.count_in_beats > 0
        ? {
            beats: presentation.aid_state.count_in_beats,
            beatMicroseconds: presentation.aid_state.count_in_beat_microseconds,
          }
        : null,
    [
      countInEnabled,
      presentation.aid_state.count_in_beats,
      presentation.aid_state.count_in_beat_microseconds,
    ],
  );

  if (!exercise || index < 0) return null;

  return (
    <section
      className="lesson-panel"
      aria-labelledby="lesson-title"
      data-expected-content={presentation.expected_content_sha256}
    >
      <div className="lesson-heading">
        <div>
          <p className="eyebrow">
            BEGINNER LESSON · STEP {index + 1} OF {plan.exercises.length}
          </p>
          <h2 id="lesson-title">{rangeLabel(presentation)}</h2>
        </div>
        <span className={`lesson-kind kind-${node?.kind ?? "exercise"}`}>
          {node?.kind ?? "exercise"}
        </span>
      </div>

      <div className="lesson-summary">
        <div><small>Focus</small><strong>{presentation.primary_skill}</strong></div>
        <div><small>Practice</small><strong>{presentation.practice_modes.join(" · ")}</strong></div>
        <div><small>Tempo</small><strong>{tempo} BPM</strong></div>
        <div><small>Expected notes</small><strong>{presentation.demonstration.notes.length}</strong></div>
      </div>

      <p className="lesson-reason">{presentation.boundary_reason}</p>

      <fieldset className="lesson-aids" disabled={loading}>
        <legend>Practice aids</legend>
        <label>
          <input
            type="checkbox"
            checked={countInEnabled}
            onChange={(event) => setCountInEnabled(event.target.checked)}
          />
          Count in
        </label>
        <label>
          <input
            type="checkbox"
            checked={showNotation}
            disabled={presentation.material_kind !== "canonical"}
            onChange={(event) => setShowNotation(event.target.checked)}
          />
          Show notation
        </label>
        <label>
          <input
            type="checkbox"
            checked={showKeyboard}
            onChange={(event) => setShowKeyboard(event.target.checked)}
          />
          Light piano keys
        </label>
        <label>
          Demonstration tempo
          <select
            aria-label="Demonstration tempo"
            value={tempo}
            onChange={(event) => onTempoChange(Number(event.target.value))}
          >
            {[...new Set([48, 60, 72, 84, 96, 120, tempo])]
              .sort((left, right) => left - right)
              .map((value) => (
              <option value={value} key={value}>{value} BPM</option>
              ))}
          </select>
        </label>
      </fieldset>

      <MidiCalibrationSurface />

      {presentation.material_kind === "synthetic-transfer" && (
        <div className="transfer-pattern" aria-label="Expected transfer notes">
          {syntheticPitches.map((pitch, pitchIndex) => (
            <span key={`${pitch}-${pitchIndex}`}>{pitch}</span>
          ))}
        </div>
      )}

      <PlaybackSurface
        key={`${presentation.exercise_id}:${tempo}`}
        plan={presentation.demonstration}
        countIn={countIn}
        eyebrow="EXPECTED PIANO DEMONSTRATION"
        heading="Listen to this exercise"
        onFocusEventIds={setFocusEventIds}
        onActiveNotes={setActiveNotes}
      />
      {showKeyboard && <VirtualPiano activeNotes={activeNotes} />}
      {showNotation && presentation.material_kind === "canonical" && (
        <NotationSurface
          bundle={notation}
          allowedEventIds={presentation.event_ids}
          focusEventIds={focusEventIds}
        />
      )}

      <nav className="lesson-navigation" aria-label="Lesson navigation">
        <button
          type="button"
          disabled={loading || index === 0}
          onClick={() => onSelectExercise(plan.exercises[index - 1]!.id)}
        >
          Previous exercise
        </button>
        <span>{loading ? "Preparing exercise…" : `${index + 1} / ${plan.exercises.length}`}</span>
        <button
          type="button"
          disabled={loading || index + 1 >= plan.exercises.length}
          onClick={() => onSelectExercise(plan.exercises[index + 1]!.id)}
        >
          Next exercise
        </button>
      </nav>

      <details className="lesson-trace">
        <summary>Why this exercise is traceable</summary>
        <p>Expected-content fingerprint: <code>{presentation.expected_content_sha256}</code></p>
        <p>{presentation.event_ids.length} exact expected event identities.</p>
        {presentation.diagnostics.map((item) => <p key={item}>{item}</p>)}
      </details>
    </section>
  );
}
