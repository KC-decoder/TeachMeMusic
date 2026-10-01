import type { PlaybackPlan } from "../contracts/playback";
import {
  PlaybackTransport,
  type PlaybackAudioEngine,
  type PlaybackController,
  type PlaybackSnapshot,
} from "./PlaybackTransport";

const SAMPLE_URLS: Readonly<Record<string, string>> = {
  A0: "A0.mp3",
  C1: "C1.mp3",
  "D#1": "Ds1.mp3",
  "F#1": "Fs1.mp3",
  A1: "A1.mp3",
  C2: "C2.mp3",
  "D#2": "Ds2.mp3",
  "F#2": "Fs2.mp3",
  A2: "A2.mp3",
  C3: "C3.mp3",
  "D#3": "Ds3.mp3",
  "F#3": "Fs3.mp3",
  A3: "A3.mp3",
  C4: "C4.mp3",
  "D#4": "Ds4.mp3",
  "F#4": "Fs4.mp3",
  A4: "A4.mp3",
  C5: "C5.mp3",
  "D#5": "Ds5.mp3",
  "F#5": "Fs5.mp3",
  A5: "A5.mp3",
  C6: "C6.mp3",
  "D#6": "Ds6.mp3",
  "F#6": "Fs6.mp3",
  A6: "A6.mp3",
  C7: "C7.mp3",
  "D#7": "Ds7.mp3",
  "F#7": "Fs7.mp3",
  A7: "A7.mp3",
  C8: "C8.mp3",
};

const PITCH_NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"];

export function midiToScientificPitch(midiPitch: number): string {
  const pitchClass = PITCH_NAMES[midiPitch % 12];
  if (!pitchClass || !Number.isInteger(midiPitch) || midiPitch < 0 || midiPitch > 127) {
    throw new Error("MIDI pitch is outside 0–127");
  }
  return `${pitchClass}${Math.floor(midiPitch / 12) - 1}`;
}

class TonePianoEngine implements PlaybackAudioEngine {
  private sampler: import("tone").Sampler | null = null;
  private tone: typeof import("tone") | null = null;
  private click: import("tone").Synth | null = null;
  private readonly toneReady: Promise<typeof import("tone")>;
  private samplesReady: Promise<void> | null = null;

  constructor() {
    this.toneReady = import("tone").then((tone) => {
      this.tone = tone;
      return tone;
    });
  }

  async activate(): Promise<void> {
    const tone = await this.toneReady;
    await tone.start();
    if (!this.click) {
      this.click = new tone.Synth({
        oscillator: { type: "sine" },
        envelope: { attack: 0.001, decay: 0.03, sustain: 0, release: 0.02 },
        volume: -10,
      }).toDestination();
    }
    if (!this.samplesReady) {
      this.samplesReady = new Promise<void>((resolve, reject) => {
        this.sampler = new tone.Sampler({
          urls: SAMPLE_URLS,
          baseUrl: "/audio/salamander/",
          attack: 0,
          release: 1,
          onload: resolve,
          onerror: reject,
        }).toDestination();
      });
    }
    await this.samplesReady;
  }

  nowSeconds(): number {
    if (!this.tone) throw new Error("Tone.js is not ready");
    return this.tone.getContext().now();
  }

  schedule(
    midiPitch: number,
    atSeconds: number,
    durationSeconds: number,
    velocity: number,
  ): void {
    if (!this.sampler) throw new Error("Piano samples are not ready");
    this.sampler.triggerAttackRelease(
      midiToScientificPitch(midiPitch),
      durationSeconds,
      atSeconds,
      velocity,
    );
  }

  scheduleClick(atSeconds: number, accented: boolean): void {
    this.click?.triggerAttackRelease(accented ? "C6" : "G5", 0.035, atSeconds, 0.55);
  }

  releaseAll(): void {
    this.sampler?.releaseAll();
  }

  dispose(): void {
    this.sampler?.releaseAll();
    this.sampler?.dispose();
    this.sampler = null;
    this.click?.dispose();
    this.click = null;
  }
}

export type PlaybackControllerFactory = (
  plan: PlaybackPlan,
  onSnapshot: (snapshot: PlaybackSnapshot) => void,
  countIn?: import("./PlaybackTransport").CountInSpec | null,
) => PlaybackController;

export const createTonePlaybackController: PlaybackControllerFactory = (plan, onSnapshot, countIn) =>
  new PlaybackTransport(plan, new TonePianoEngine(), onSnapshot, undefined, countIn);
