import { waitFor } from "@testing-library/react";

import type { AppConfig } from "../api";
import type { BrowserMidiSession } from "../midi/BrowserMidiSession";
import type { MidiSnapshot } from "../midi/contracts";
import { DesktopBridgeController } from "./DesktopBridgeController";
import type { DesktopMidiBridge, MobileCommand } from "./transport";

function snapshot(): MidiSnapshot {
  return {
    permission: "granted",
    connection: "connected",
    capture: "idle",
    capture_purpose: null,
    capture_started_at_utc: null,
    capture_start_microseconds: null,
    capture_end_microseconds: null,
    inputs: [],
    selected_input_id: "px-770",
    raw_messages: [],
    normalized_events: [],
    diagnostics: [],
    active_notes: [],
    calibration: { approved: true } as MidiSnapshot["calibration"],
  };
}

function startCommand(): MobileCommand {
  return {
    mobile_contract_version: "0.2.0",
    pairing_id: "pairing-one",
    sequence: 1,
    kind: "start-attempt",
    status: "processing",
    result: null,
    error: null,
  };
}

test("TEST-APP-MOBILE-027 acknowledges start only after recording state is published", async () => {
  let current = snapshot();
  const listeners = new Set<() => void>();
  const midi = {
    current: () => current,
    subscribe: (listener: () => void) => {
      listeners.add(listener);
      return () => listeners.delete(listener);
    },
    startAttempt: () => {
      current = { ...current, capture: "recording", capture_purpose: "attempt" };
      for (const listener of listeners) listener();
    },
  } as unknown as BrowserMidiSession;
  const acknowledge = vi.fn(async () => undefined);
  const publish = vi.fn(async () => undefined);
  let pending: MobileCommand | null = startCommand();
  const bridge = {
    publish,
    readCommand: vi.fn(async () => {
      const command = pending;
      pending = null;
      return command;
    }),
    acknowledge,
  } as unknown as DesktopMidiBridge;
  const controller = new DesktopBridgeController(bridge, midi, {} as AppConfig);

  controller.start();
  await waitFor(() => expect(acknowledge).toHaveBeenCalledWith(1, {
    result: {
      capture: "recording",
      capture_purpose: "attempt",
      calibration_approved: true,
    },
  }));
  expect(publish).toHaveBeenCalled();
  expect(publish.mock.invocationCallOrder[0]).toBeLessThan(
    acknowledge.mock.invocationCallOrder[0]!,
  );
  controller.stop();
});

test("TEST-APP-MOBILE-028 rejects a start that leaves desktop capture idle", async () => {
  const current = snapshot();
  current.calibration = null;
  const midi = {
    current: () => current,
    subscribe: () => () => undefined,
    startAttempt: () => {
      current.diagnostics = [{
        code: "MIDI_ATTEMPT_NOT_READY",
        message: "Connect the approved calibrated input before starting an attempt.",
        blocking: true,
        timestamp_microseconds: 1,
      }];
    },
  } as unknown as BrowserMidiSession;
  const acknowledge = vi.fn(async () => undefined);
  let pending: MobileCommand | null = startCommand();
  const bridge = {
    publish: vi.fn(async () => undefined),
    readCommand: vi.fn(async () => {
      const command = pending;
      pending = null;
      return command;
    }),
    acknowledge,
  } as unknown as DesktopMidiBridge;
  const controller = new DesktopBridgeController(bridge, midi, {} as AppConfig);

  controller.start();
  await waitFor(() => expect(acknowledge).toHaveBeenCalledWith(1, {
    error: "Connect the approved calibrated input before starting an attempt.",
  }));
  controller.stop();
});
