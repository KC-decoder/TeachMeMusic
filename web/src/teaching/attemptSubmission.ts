import type { AttemptSubmission } from "../api";
import type { MidiSnapshot } from "../midi/contracts";
import type { MobileAttemptContext } from "../mobile/transport";

function apiCalibration(calibration: NonNullable<MidiSnapshot["calibration"]>) {
  return {
    version: calibration.version,
    device_id: calibration.device_id,
    input_name: calibration.input_name,
    timestamp_origin: calibration.timestamp_origin,
    pitch_numbering_confirmed: calibration.pitch_numbering_confirmed,
    sustain_available: calibration.sustain_available,
    clock_offset_microseconds: calibration.clock_offset_microseconds,
    clock_jitter_microseconds: calibration.clock_jitter_microseconds,
    timing_window_microseconds: calibration.timing_window_microseconds,
    chord_window_microseconds: calibration.chord_window_microseconds,
    limitations: calibration.limitations,
    approved: calibration.approved,
    approved_at_utc: calibration.approved_at_utc,
  };
}

export function buildAttemptSubmission(
  snapshot: MidiSnapshot,
  context: MobileAttemptContext,
): AttemptSubmission {
  if (
    !snapshot.calibration?.approved ||
    snapshot.capture_purpose !== "attempt" ||
    (snapshot.capture !== "stopped" && snapshot.capture !== "aborted") ||
    snapshot.capture_start_microseconds === null ||
    snapshot.capture_started_at_utc === null
  ) {
    throw new Error("The calibrated desktop attempt is not ready for submission.");
  }
  const finalTimestamp = Math.max(
    snapshot.capture_end_microseconds ?? snapshot.capture_start_microseconds,
    snapshot.capture_start_microseconds,
    ...snapshot.raw_messages.map((item) => item.timestamp_microseconds),
    ...snapshot.normalized_events.map((item) => item.timestamp_microseconds),
  );
  const discomfort = snapshot.diagnostics.some(
    (item) => item.code === "LEARNER_DISCOMFORT_SAFE_STOP",
  );
  const { run_id: _runId, ...submissionContext } = context;
  return {
    ...submissionContext,
    started_at_utc: snapshot.capture_started_at_utc,
    start_microseconds: snapshot.capture_start_microseconds,
    end_microseconds: finalTimestamp,
    completion: discomfort ? "safe-stop" : snapshot.capture === "stopped"
      ? "completed"
      : "cancelled",
    calibration: apiCalibration(snapshot.calibration),
    raw_messages: snapshot.raw_messages,
    normalized_events: snapshot.normalized_events,
    diagnostics: snapshot.diagnostics.map((item) => `${item.code}: ${item.message}`),
    ...(discomfort ? { unsafe_condition: "Learner reported discomfort." } : {}),
  };
}
