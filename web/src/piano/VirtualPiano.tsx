import type { CSSProperties } from "react";
import { useEffect, useMemo, useRef } from "react";

import type { ActivePlaybackNote } from "../audio/PlaybackTransport";
import { CLEF_LABELS, buildPianoState, type ClefCategory, type PianoKeyState } from "./model";

interface VirtualPianoProps {
  activeNotes: ActivePlaybackNote[];
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
  if (!key.active) return `${key.noteName}, not sounding`;
  const clefs = key.clefs.map((clef) => CLEF_LABELS[clef]).join(" and ");
  return `${key.noteName}, sounding, ${clefs}, ${key.canonicalEventIds.length} canonical ${key.canonicalEventIds.length === 1 ? "event" : "events"}`;
}

function Key({ keyState, left }: { keyState: PianoKeyState; left?: number }) {
  const style = {
    ...(left === undefined ? {} : { left: `${left}px` }),
    ...(keyState.active ? { "--piano-active-fill": activeFill(keyState.clefs) } : {}),
  } as CSSProperties;
  const showLabel = !keyState.black &&
    (keyState.noteName.startsWith("C") || keyState.midiPitch === 21 || keyState.midiPitch === 108);
  return (
    <div
      className={`piano-key ${keyState.black ? "piano-key-black" : "piano-key-white"} ${keyState.active ? "is-active" : ""}`}
      style={style}
      role="img"
      aria-label={keyLabel(keyState)}
      data-midi={keyState.midiPitch}
      data-active={keyState.active}
      data-clefs={keyState.clefs.join(",")}
    >
      {showLabel && <span aria-hidden="true">{keyState.noteName}</span>}
    </div>
  );
}

export function VirtualPiano({ activeNotes }: VirtualPianoProps) {
  const scrollContainer = useRef<HTMLDivElement | null>(null);
  const state = useMemo(() => buildPianoState(activeNotes), [activeNotes]);
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
  const soundingSummary =
    activeKeys.length === 0
      ? "No piano keys sounding"
      : `${activeKeys.length} ${activeKeys.length === 1 ? "key" : "keys"} sounding: ${activeKeys.map((key) => key.noteName).join(", ")}`;

  useEffect(() => {
    const first = activeKeys[0];
    if (!first || !scrollContainer.current) return;
    scrollContainer.current
      .querySelector<HTMLElement>(`[data-midi="${first.midiPitch}"]`)
      ?.scrollIntoView?.({ behavior: "auto", block: "nearest", inline: "center" });
  }, [activeKeys]);

  return (
    <section className="virtual-piano-panel" aria-labelledby="virtual-piano-title">
      <div className="virtual-piano-heading">
        <div>
          <p className="eyebrow">AUDIO-CLOCK KEYBOARD</p>
          <h2 id="virtual-piano-title">Follow the piano</h2>
        </div>
        <p className="piano-live-state" aria-live="polite">{soundingSummary}</p>
      </div>

      <div className="piano-legend" aria-label="Clef color legend">
        {(["treble", "bass", "alto", "tenor", "unknown"] as ClefCategory[]).map((clef) => (
          <span key={clef}>
            <i style={{ background: CLEF_COLORS[clef] }} aria-hidden="true" />
            {CLEF_LABELS[clef]}
          </span>
        ))}
      </div>

      <div
        ref={scrollContainer}
        className="piano-scroll"
        tabIndex={0}
        aria-label="Scrollable 88-key piano"
      >
        <div className="piano-keyboard" role="group" aria-label="Standard 88-key piano">
          <div className="piano-white-keys">
            {whiteKeys.map((key) => <Key key={key.midiPitch} keyState={key} />)}
          </div>
          {blackKeys.map(({ key, left }) => <Key key={key.midiPitch} keyState={key} left={left} />)}
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
