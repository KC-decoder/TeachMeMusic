import { fireEvent, render, screen, waitFor } from "@testing-library/react";

import { BrowserMidiSession } from "./BrowserMidiSession";
import type { MidiAccessLike, MidiInputLike, MidiMessageEventLike } from "./contracts";
import { MidiCalibrationSurface } from "./MidiCalibrationSurface";

class UiInput implements MidiInputLike {
  id = "px-770";
  name = "CASIO USB-MIDI";
  manufacturer = "CASIO";
  state = "connected" as const;
  connection: "open" | "closed" | "pending" = "closed";
  type = "input" as const;
  onmidimessage: ((event: MidiMessageEventLike) => void) | null = null;
  async open() { this.connection = "open" as const; return this; }
  async close() { this.connection = "closed" as const; return this; }
  emit(data: number[], timeStamp: number) {
    this.onmidimessage?.({ data: new Uint8Array(data), timeStamp });
  }
}

test("TEST-MIDI-007 UI requires permission and real port before calibration", async () => {
  const input = new UiInput();
  const access: MidiAccessLike = { inputs: new Map([[input.id, input]]), onstatechange: null };
  const session = new BrowserMidiSession(async () => access);
  render(<MidiCalibrationSurface createSession={() => session} />);

  expect(screen.getByText(/never falls back to a simulation/)).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Allow MIDI access" }));
  expect(await screen.findByLabelText("Piano input")).toHaveValue("px-770");
  fireEvent.click(screen.getByRole("button", { name: "Connect piano" }));
  expect(await screen.findByRole("button", { name: "Start calibration" })).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Start calibration" }));
  expect(screen.getByRole("button", { name: "Abort without penalty" })).toBeInTheDocument();

  [[0x90, 60, 40], [0x90, 62, 50], [0x90, 64, 60], [0x90, 65, 70], [0x90, 67, 80]]
    .forEach((message, index) => input.emit(message, performance.now() + index));
  fireEvent.click(screen.getByRole("button", { name: "Stop and review" }));
  await waitFor(() => expect(screen.getByText(/middle C arrived as MIDI 60/)).toBeInTheDocument());
  expect(screen.getByRole("button", { name: "Approve calibration evidence" })).toBeEnabled();
});

test("TEST-MIDI-008 unsupported UI is fail-closed and offers no simulated capture", () => {
  render(<MidiCalibrationSurface createSession={() => new BrowserMidiSession(null)} />);
  expect(screen.getByText(/MIDI_UNSUPPORTED/)).toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "Start calibration" })).not.toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "Allow MIDI access" })).not.toBeInTheDocument();
});
