import { useEffect, useMemo, useState } from "react";

import { midiNoteName } from "../piano/model";
import { BrowserMidiSession } from "./BrowserMidiSession";
import type { CalibrationRecord, MidiSnapshot } from "./contracts";

interface MidiCalibrationSurfaceProps {
  createSession?: () => BrowserMidiSession;
  session?: BrowserMidiSession;
  onApproved?: (calibration: CalibrationRecord) => void;
}

function permissionMessage(snapshot: MidiSnapshot): string {
  if (snapshot.permission === "unsupported") {
    return "This browser does not provide Web MIDI. Use desktop Chrome or Edge over a secure or localhost connection.";
  }
  if (snapshot.permission === "denied") {
    return "MIDI permission was denied. Nothing is being captured; allow MIDI access in the browser to continue.";
  }
  if (snapshot.permission === "error") {
    return "The browser could not start Web MIDI. Nothing is being captured.";
  }
  if (snapshot.permission === "requesting") return "Waiting for browser MIDI permission…";
  if (snapshot.permission === "granted" && snapshot.inputs.length === 0) {
    return "MIDI access is allowed, but no input is visible. Connect and switch on the piano, then reconnect.";
  }
  return "Connect your digital piano to receive played notes. Input never falls back to a simulation.";
}

function evidenceFilename(): string {
  return `teachmemusic-midi-calibration-${new Date().toISOString().replaceAll(":", "-")}.json`;
}

export function MidiCalibrationSurface({
  createSession,
  session: suppliedSession,
  onApproved,
}: MidiCalibrationSurfaceProps) {
  const [createdSession] = useState(() => createSession?.() ?? new BrowserMidiSession());
  const session = suppliedSession ?? createdSession;
  const [snapshot, setSnapshot] = useState(() => session.current());
  const [selectedInputId, setSelectedInputId] = useState("");

  useEffect(() => {
    const unsubscribe = session.subscribe(setSnapshot);
    return () => {
      unsubscribe();
      if (!suppliedSession) session.dispose();
    };
  }, [session, suppliedSession]);

  const activeInputId = selectedInputId &&
      snapshot.inputs.some((item) => item.id === selectedInputId && item.state === "connected")
    ? selectedInputId
    : snapshot.inputs.find((item) => item.state === "connected")?.id ?? "";

  const noteOns = useMemo(
    () => snapshot.normalized_events.filter((item) => item.kind === "note-on"),
    [snapshot.normalized_events],
  );
  const sustainObserved = snapshot.normalized_events.some(
    (item) => item.kind === "control-change" && item.controller === 64,
  );
  const firstNote = noteOns[0]?.note ?? null;

  function downloadEvidence() {
    if (!snapshot.calibration?.approved) return;
    const evidence = {
      calibration: snapshot.calibration,
      raw_messages: snapshot.raw_messages,
      normalized_events: snapshot.normalized_events,
      diagnostics: snapshot.diagnostics,
    };
    const url = URL.createObjectURL(new Blob([JSON.stringify(evidence, null, 2)], {
      type: "application/json",
    }));
    const link = document.createElement("a");
    link.href = url;
    link.download = evidenceFilename();
    link.click();
    URL.revokeObjectURL(url);
  }

  const canRequest = snapshot.permission === "idle" || snapshot.permission === "denied" ||
    snapshot.permission === "error";
  const canConnect = snapshot.permission === "granted" && activeInputId !== "" &&
    snapshot.connection === "disconnected";
  const canStart = snapshot.connection === "connected" &&
    snapshot.capture_purpose !== "attempt" && snapshot.capture !== "recording";

  return (
    <section className="midi-panel" aria-labelledby="midi-title">
      <div className="midi-heading">
        <div>
          <p className="eyebrow">LEARNER PIANO INPUT</p>
          <h2 id="midi-title">Connect and calibrate your piano</h2>
        </div>
        <span className={`midi-state state-${snapshot.connection}`}>
          {snapshot.connection}
        </span>
      </div>

      <p className="midi-introduction">{permissionMessage(snapshot)}</p>

      {snapshot.permission === "unsupported" ? (
        <p className="midi-alert" role="status">
          <strong>MIDI_UNSUPPORTED:</strong> calibration is unavailable and no learner result can be inferred.
        </p>
      ) : (
        <div className="midi-controls">
          {canRequest && (
            <button type="button" className="midi-primary" onClick={() => void session.requestPermission()}>
              Allow MIDI access
            </button>
          )}
          {snapshot.permission === "requesting" && <button type="button" disabled>Requesting…</button>}
          {snapshot.permission === "granted" && (
            <>
              <label>
                Piano input
                <select
                  aria-label="Piano input"
                  value={activeInputId}
                  disabled={snapshot.connection !== "disconnected"}
                  onChange={(event) => setSelectedInputId(event.target.value)}
                >
                  <option value="">Choose an input</option>
                  {snapshot.inputs.map((input) => (
                    <option key={input.id} value={input.id} disabled={input.state !== "connected"}>
                      {input.name}{input.manufacturer ? ` · ${input.manufacturer}` : ""}
                      {input.state === "disconnected" ? " · disconnected" : ""}
                    </option>
                  ))}
                </select>
              </label>
              {canConnect && (
                <button type="button" className="midi-primary" onClick={() => void session.connect(activeInputId)}>
                  Connect piano
                </button>
              )}
              {snapshot.connection === "connecting" && <button type="button" disabled>Connecting…</button>}
              {snapshot.connection === "connected" && (
                <button type="button" onClick={() => void session.disconnect()}>Disconnect</button>
              )}
            </>
          )}
        </div>
      )}

      {snapshot.connection === "connected" && (
        <div className="calibration-workflow">
          <div className="calibration-instructions">
            <p className="eyebrow">TECHNICAL CALIBRATION</p>
            <ol>
              <li>Start calibration, then play <strong>middle C (C4)</strong> first.</li>
              <li>Play at least four more keys, softly and firmly, and release each key.</li>
              <li>Press and release the sustain pedal once, if one is connected.</li>
              <li>Stop, review the evidence, and approve only if the first note is shown as C4.</li>
            </ol>
          </div>
          <div className="calibration-actions">
            {canStart && (
              <button type="button" className="midi-primary" onClick={() => session.startCalibration()}>
                {snapshot.capture === "idle" ? "Start calibration" : "Restart calibration"}
              </button>
            )}
            {snapshot.capture_purpose === "calibration" && snapshot.capture === "recording" && (
              <>
                <button type="button" className="midi-primary" onClick={() => session.stopCalibration()}>
                  Stop and review
                </button>
                <button type="button" onClick={() => session.pauseCalibration()}>Pause input</button>
                <button type="button" onClick={() => session.abortCalibration()}>Abort without penalty</button>
                <button type="button" onClick={() => session.stopForDiscomfort()}>Stop — discomfort</button>
              </>
            )}
            {snapshot.capture_purpose === "calibration" && snapshot.capture === "paused" && (
              <>
                <button type="button" className="midi-primary" onClick={() => session.resumeCalibration()}>
                  Resume input
                </button>
                <button type="button" onClick={() => session.stopCalibration()}>Stop and review</button>
                <button type="button" onClick={() => session.abortCalibration()}>Abort without penalty</button>
                <button type="button" onClick={() => session.stopForDiscomfort()}>Stop — discomfort</button>
              </>
            )}
          </div>

          {snapshot.capture_purpose === "calibration" && snapshot.capture !== "idle" && (
            <div className="midi-evidence" aria-live="polite">
              <div><small>Raw messages</small><strong>{snapshot.raw_messages.length}</strong></div>
              <div><small>Played notes</small><strong>{noteOns.length}</strong></div>
              <div>
                <small>First note</small>
                <strong>{firstNote === null ? "Waiting" : `${midiNoteName(firstNote)} · MIDI ${firstNote}`}</strong>
              </div>
              <div><small>Sustain</small><strong>{sustainObserved ? "Observed" : "Not observed"}</strong></div>
            </div>
          )}

          {snapshot.active_notes.length > 0 && (
            <div className="midi-live-notes" aria-label="Keys currently held">
              {snapshot.active_notes.map((note) => <span key={note}>{midiNoteName(note)}</span>)}
            </div>
          )}

          {snapshot.capture_purpose === "calibration" && snapshot.capture === "aborted" && (
            <p className="midi-alert" role="status">Calibration stopped. No learner error or score was recorded.</p>
          )}

          {snapshot.calibration && (
            <div className="calibration-review">
              <h3>Calibration review</h3>
              <ul>
                <li data-result={snapshot.calibration.pitch_numbering_confirmed ? "pass" : "fail"}>
                  Pitch numbering: {snapshot.calibration.pitch_numbering_confirmed
                    ? "confirmed — middle C arrived as MIDI 60"
                    : `not confirmed — first note was ${snapshot.calibration.first_note ?? "not received"}`}
                </li>
                <li>Note-on messages: {snapshot.calibration.note_on_count}</li>
                <li>Sustain evidence: {snapshot.calibration.sustain_available === true ? "available" : "unknown"}</li>
                <li>Browser clock handling spread: {snapshot.calibration.clock_jitter_microseconds ?? "insufficient samples"} µs</li>
                <li>No physical or acoustic latency was measured.</li>
              </ul>
              {!snapshot.calibration.approved ? (
                <button
                  type="button"
                  className="midi-primary"
                  disabled={!snapshot.calibration.pitch_numbering_confirmed || snapshot.calibration.note_on_count < 5}
                  onClick={() => {
                    session.approveCalibration();
                    const approved = session.current().calibration;
                    if (approved?.approved) onApproved?.(approved);
                  }}
                >
                  Approve calibration evidence
                </button>
              ) : (
                <>
                  <p className="midi-approved" role="status">Calibration evidence approved locally.</p>
                  <button type="button" onClick={downloadEvidence}>Download calibration evidence</button>
                </>
              )}
            </div>
          )}
        </div>
      )}

      {snapshot.diagnostics.length > 0 && (
        <details className="midi-diagnostics">
          <summary>Input diagnostics ({snapshot.diagnostics.length})</summary>
          <ul>
            {snapshot.diagnostics.map((item, index) => (
              <li key={`${item.code}-${index}`} data-blocking={item.blocking}>
                <strong>{item.code}</strong>: {item.message}
              </li>
            ))}
          </ul>
        </details>
      )}
    </section>
  );
}
