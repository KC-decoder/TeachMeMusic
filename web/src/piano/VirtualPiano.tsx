import type { CSSProperties } from "react";
import { useEffect, useMemo, useRef } from "react";

import type { ActivePlaybackNote } from "../audio/PlaybackTransport";
import { CLEF_LABELS, buildPianoState, type ClefCategory, type PianoKeyState } from "./model";

interface VirtualPianoProps {
  activeNotes: ActivePlaybackNote[];
  playedMidiPitches?: readonly number[];
  learnerInputStatus?: "unavailable" | "connected" | "capturing";
  showNoteNames?: boolean;
  guidanceMode?: "demonstration" | "practice" | "missed";
}

const CLEF_COLORS: Record<ClefCategory, string> = {
  treble: "#d96f3d",
  bass: "#28735d",
  alto: "#7d5ab5",
  tenor: "#276aa0",
  percussion: "#b28a1f",
  tab: "#a04d78",
  other: "#5f6b66",
  unknown: "#818984",
};

function activeFill(clefs: ClefCategory[]): string | undefined {
  if (clefs.length === 0) return undefined;
  if (clefs.length === 1) return CLEF_COLORS[clefs[0] ?? "unknown"];
  const width = 100 / clefs.length;
  const stops = clefs.flatMap((clef, index) => [
    `${CLEF_COLORS[clef]} ${index * width}%`,
    `${CLEF_COLORS[clef]} ${(index + 1) * width}%`,
  ]);
  return `linear-gradient(90deg, ${stops.join(", ")})`;
}

function keyLabel(key: PianoKeyState): string {
  const expectedDetail = key.active
    ? `expected sounding, ${key.clefs.map((clef) => CLEF_LABELS[clef]).join(" and ")}, ${key.canonicalEventIds.length} canonical ${key.canonicalEventIds.length === 1 ? "event" : "events"}`
    : "not expected";
  if (key.match) return `${key.noteName}, ${expectedDetail}, learner played, match`;
  if (key.differentFromTarget) {
    return `${key.noteName}, learner played, different from current target`;
  }
  if (key.played) return `${key.noteName}, learner played, no current target`;
  return `${key.noteName}, ${expectedDetail}`;
}

function Key({
  keyState,
  left,
  showNoteNames,
}: {
  keyState: PianoKeyState;
  left?: number;
  showNoteNames: boolean;
}) {
  const style = {
    ...(left === undefined ? {} : { left: `${left}px` }),
    ...(keyState.active ? { "--piano-active-fill": activeFill(keyState.clefs) } : {}),
  } as CSSProperties;
  const showLabel = showNoteNames && (
    keyState.active || (!keyState.black && (
      keyState.noteName.startsWith("C") || keyState.midiPitch === 21 || keyState.midiPitch === 108
    ))
  );
  const marker = keyState.match
    ? "✓"
    : keyState.differentFromTarget
      ? "!"
      : keyState.played
        ? "●"
        : keyState.active
          ? "◇"
          : null;
  return (
    <div
      className={`piano-key ${keyState.black ? "piano-key-black" : "piano-key-white"} ${keyState.active ? "is-active is-expected" : ""} ${keyState.played ? "is-played" : ""} ${keyState.match ? "is-match" : ""} ${keyState.differentFromTarget ? "is-different" : ""}`}
      style={style}
      role="img"
      aria-label={keyLabel(keyState)}
      data-midi={keyState.midiPitch}
      data-active={keyState.active}
      data-expected={keyState.active}
      data-played={keyState.played}
      data-match={keyState.match}
      data-different-from-target={keyState.differentFromTarget}
      data-clefs={keyState.clefs.join(",")}
    >
      {showLabel && <span className="piano-note-name" aria-hidden="true">{keyState.noteName}</span>}
      {marker && <span className="piano-input-marker" aria-hidden="true">{marker}</span>}
    </div>
  );
}

export function VirtualPiano({
  activeNotes,
  playedMidiPitches = [],
  learnerInputStatus = "unavailable",
  showNoteNames = true,
  guidanceMode = "demonstration",
}: VirtualPianoProps) {
  const scrollContainer = useRef<HTMLDivElement | null>(null);
  const state = useMemo(
    () => buildPianoState(activeNotes, playedMidiPitches),
    [activeNotes, playedMidiPitches],
  );
  const whiteKeys = state.keys.filter((key) => !key.black);
  const blackKeys: Array<{ key: PianoKeyState; left: number }> = [];
  let whiteCount = 0;
  for (const key of state.keys) {
    if (key.black) {
      blackKeys.push({ key, left: whiteCount * 24 - 7 });
    } else {
      whiteCount += 1;
    }
  }
  const activeKeys = state.keys.filter((key) => key.active);
  const playedKeys = state.keys.filter((key) => key.played);
  const matches = state.keys.filter((key) => key.match);
  const differences = state.keys.filter((key) => key.differentFromTarget);
  const soundingSummary =
    activeKeys.length === 0
      ? "No piano keys sounding"
      : `${activeKeys.length} ${activeKeys.length === 1 ? "key" : "keys"} sounding: ${activeKeys.map((key) => key.noteName).join(", ")}`;
  const learnerSummary = learnerInputStatus === "unavailable"
    ? "Learner input unavailable"
    : playedKeys.length === 0
      ? `Learner input ${learnerInputStatus}; no keys held`
      : `Learner playing: ${playedKeys.map((key) => key.noteName).join(", ")}; ${matches.length} ${matches.length === 1 ? "match" : "matches"}${differences.length > 0 ? `; different from current target: ${differences.map((key) => key.noteName).join(", ")}` : ""}`;

  useEffect(() => {
    const first = activeKeys[0];
    if (!first || !scrollContainer.current) return;
    scrollContainer.current
      .querySelector<HTMLElement>(`[data-midi="${first.midiPitch}"]`)
      ?.scrollIntoView?.({ behavior: "auto", block: "nearest", inline: "center" });
  }, [activeKeys]);

  return (
    <section
      className={`virtual-piano-panel guidance-${guidanceMode}`}
      aria-labelledby="virtual-piano-title"
      data-guidance-mode={guidanceMode}
    >
      <div className="virtual-piano-heading">
        <div>
          <p className="eyebrow">AUDIO-CLOCK KEYBOARD</p>
          <h2 id="virtual-piano-title">Follow the piano</h2>
        </div>
        <p className="piano-live-state" aria-live="polite">{soundingSummary}</p>
      </div>

      <p className="piano-learner-state" aria-live="polite">{learnerSummary}</p>

      <div className="piano-legend" aria-label="Piano state and clef legend">
        {(["treble", "bass", "alto", "tenor", "unknown"] as ClefCategory[]).map((clef) => (
          <span key={clef}>
            <i style={{ background: CLEF_COLORS[clef] }} aria-hidden="true" />
            {CLEF_LABELS[clef]}
          </span>
        ))}
        <span><i className="piano-legend-marker is-expected" aria-hidden="true">◇</i>Expected target</span>
        <span><i className="piano-legend-marker is-match" aria-hidden="true">✓</i>Expected + played</span>
        <span><i className="piano-legend-marker is-different" aria-hidden="true">!</i>Different from target</span>
        <span><i className="piano-legend-marker is-played" aria-hidden="true">●</i>Learner played</span>
      </div>

      <div
        ref={scrollContainer}
        className="piano-scroll"
        tabIndex={0}
        aria-label="Scrollable 88-key piano"
      >
        <div className="piano-keyboard" role="group" aria-label="Standard 88-key piano">
          <div className="piano-white-keys">
            {whiteKeys.map((key) => (
              <Key key={key.midiPitch} keyState={key} showNoteNames={showNoteNames} />
            ))}
          </div>
          {blackKeys.map(({ key, left }) => (
            <Key
              key={key.midiPitch}
              keyState={key}
              left={left}
              showNoteNames={showNoteNames}
            />
          ))}
        </div>
      </div>

      <p className="piano-explanation">
        Colors identify the active written clef—not a guessed left or right hand. A striped key
        carries simultaneous contributions from more than one clef.
      </p>

      {state.outOfRange.length > 0 && (
        <p className="piano-warning" role="status">
          <strong>PIANO_PITCH_OUTSIDE_88_KEYS:</strong> {state.outOfRange.length} sounding
          contribution(s) fall outside A0–C8 and cannot be shown on this keyboard.
        </p>
      )}

      {state.playedOutOfRange.length > 0 && (
        <p className="piano-warning" role="status">
          <strong>LEARNER_PITCH_OUTSIDE_88_KEYS:</strong> MIDI {state.playedOutOfRange.join(", ")}
          {state.playedOutOfRange.length === 1 ? " is" : " are"} outside A0–C8 and cannot be shown on this keyboard.
        </p>
      )}

      {activeKeys.length > 0 && (
        <details className="piano-trace">
          <summary>Active canonical events ({activeKeys.reduce((total, key) => total + key.canonicalEventIds.length, 0)})</summary>
          <ul>
            {activeKeys.flatMap((key) =>
              key.canonicalEventIds.map((eventId) => (
                <li key={`${key.midiPitch}-${eventId}`}>
                  <strong>{key.noteName}</strong> <code>{eventId}</code>
                </li>
              )),
            )}
          </ul>
        </details>
      )}
    </section>
  );
}
