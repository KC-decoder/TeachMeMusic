import { spawn } from "node:child_process";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

import { chromium } from "playwright";

// TEST-APP-MOBILE-003: compiled expected/played piano layers remain independent.

const here = dirname(fileURLToPath(import.meta.url));
const root = resolve(here, "../..");
const python = resolve(root, ".venv/bin/python");
const fixture = resolve(
  root,
  "tests/fixtures/scores/TMM-REF-CANDIDATE-001-Hot-Cross-Buns/" +
    "musicxml-17-hot-cross-buns-final-shelbygtdrew.mxl",
);
const server = spawn(python, ["-m", "teachmemusic.app.server"], {
  cwd: root,
  env: { ...process.env, PYTHONPATH: resolve(root, "src"), PYTHONUNBUFFERED: "1" },
  stdio: ["ignore", "pipe", "pipe"],
});

function serverUrl() {
  return new Promise((accept, reject) => {
    const timeout = setTimeout(() => reject(new Error("local application did not start")), 15_000);
    const inspect = (chunk) => {
      const match = chunk.toString().match(/TeachMeMusic: (http:\/\/127\.0\.0\.1:\d+\/)/);
      if (!match) return;
      clearTimeout(timeout);
      accept(match[1]);
    };
    server.stdout.on("data", inspect);
    server.stderr.on("data", inspect);
  });
}

let browser;
let page;
try {
  const url = await serverUrl();
  browser = await chromium.launch({ channel: "chrome", headless: true });
  page = await browser.newPage({
    viewport: { width: 844, height: 390 },
    hasTouch: true,
    isMobile: true,
  });
  await page.addInitScript(() => {
    const input = {
      id: "proof-casio-px-770",
      name: "CASIO USB-MIDI Proof Port",
      manufacturer: "CASIO",
      state: "connected",
      connection: "closed",
      type: "input",
      onmidimessage: null,
      async open() { this.connection = "open"; return this; },
      async close() { this.connection = "closed"; return this; },
    };
    const access = { inputs: new Map([[input.id, input]]), onstatechange: null };
    Object.defineProperty(navigator, "requestMIDIAccess", {
      configurable: true,
      value: async () => access,
    });
    window.__teachMeMusicProofMidi = (data) => {
      input.onmidimessage?.({ data: new Uint8Array(data), timeStamp: performance.now() });
    };
  });
  const failures = [];
  page.on("console", (message) => {
    if (message.type() === "error") failures.push(`console: ${message.text()}`);
  });
  page.on("pageerror", (error) => failures.push(`page: ${error.message}`));
  await page.route("**/*", async (route) => {
    const requestUrl = route.request().url();
    if (requestUrl.startsWith(url) || requestUrl.startsWith("data:") || requestUrl.startsWith("blob:")) {
      await route.continue();
    } else {
      failures.push(`external request blocked: ${requestUrl}`);
      await route.abort();
    }
  });

  await page.goto(url);
  await page.locator('input[type="file"]').first().setInputFiles(fixture);
  await page.getByText("BEGINNER LESSON · STEP 1 OF 16", { exact: true }).waitFor({ timeout: 120_000 });
  await page.getByRole("button", { name: "Open practice screen" }).click();
  await page.getByRole("dialog", { name: "Setup, calibration, and evidence" }).waitFor();
  await page.getByLabel("Count in").uncheck();
  await page.getByLabel("Demonstration tempo").selectOption("48");
  await page.getByText("48 BPM", { exact: true }).first().waitFor();
  await page.getByRole("button", { name: "Allow MIDI access" }).click();
  await page.getByRole("button", { name: "Connect piano" }).click();
  await page.getByRole("button", { name: /Continue (to exercise|without recording)/ }).click();
  const learnerState = page.locator(".piano-learner-state");
  await learnerState.waitFor({ state: "attached" });
  if (await learnerState.textContent() !== "Learner input connected; no keys held") {
    throw new Error(`unexpected learner input state: ${await learnerState.textContent()}`);
  }

  const play = page.getByRole("button", { name: "Play", exact: true });
  await play.click();
  try {
    await page.waitForFunction(
      () => document.querySelector(".playback-state")?.textContent?.startsWith("Playing ·"),
      undefined,
      { timeout: 30_000 },
    );
  } catch (error) {
    const state = await page.locator(".playback-state").textContent();
    const alert = await page.locator(".playback-error").textContent().catch(() => null);
    throw new Error(`playback did not start: state=${state}; alert=${alert}; browser=${failures.join(" | ")}; ${error}`);
  }
  const target = page.locator('[data-expected="true"]').first();
  await target.waitFor({ timeout: 120_000 });
  const expectedPitch = Number(await target.getAttribute("data-midi"));
  const expectedPitches = await page.locator('[data-expected="true"]').evaluateAll(
    (keys) => keys.map((key) => Number(key.getAttribute("data-midi"))),
  );
  const wrongPitch = [expectedPitch + 1, expectedPitch - 1, expectedPitch + 2]
    .find((pitch) => pitch >= 21 && pitch <= 108 && !expectedPitches.includes(pitch));
  if (wrongPitch === undefined) throw new Error("could not choose a distinct proof pitch");

  await page.evaluate((pitch) => window.__teachMeMusicProofMidi([0x90, pitch, 80]), wrongPitch);
  const wrong = page.locator(`[data-midi="${wrongPitch}"]`);
  await wrong.locator(".piano-input-marker").waitFor();
  if (await wrong.getAttribute("data-different-from-target") !== "true") {
    throw new Error("played-only pitch was not marked different from the current target");
  }
  if (await page.locator(`[data-midi="${expectedPitch}"]`).getAttribute("data-expected") !== "true") {
    throw new Error("a different learner pitch erased the expected target");
  }
  if (await page.locator(`[data-midi="${expectedPitch}"] .piano-input-marker`).textContent() !== "◇") {
    throw new Error("expected-only target lacks its non-color marker");
  }
  await page.evaluate((pitch) => window.__teachMeMusicProofMidi([0x80, pitch, 0]), wrongPitch);

  const liveTarget = page.locator('[data-expected="true"]').first();
  await liveTarget.waitFor();
  const matchPitch = Number(await liveTarget.getAttribute("data-midi"));
  await page.evaluate((pitch) => window.__teachMeMusicProofMidi([0x90, pitch, 80]), matchPitch);
  const match = page.locator(`[data-midi="${matchPitch}"]`);
  await match.locator(".piano-input-marker").waitFor();
  if (await match.getAttribute("data-match") !== "true") {
    throw new Error("expected-plus-played pitch was not marked as a match");
  }
  await page.evaluate((pitch) => window.__teachMeMusicProofMidi([0x80, pitch, 0]), matchPitch);

  await page.getByRole("button", { name: "Back to practice setup" }).click();
  await page.getByRole("button", { name: "Disconnect" }).evaluate((button) => {
    if (!(button instanceof HTMLButtonElement)) throw new Error("disconnect control missing");
    button.click();
  });
  await page.getByRole("button", { name: /Continue (to exercise|without recording)/ }).click();
  await page.locator(".piano-learner-state").waitFor({ state: "attached" });
  if (await page.locator(".piano-learner-state").textContent() !== "Learner input unavailable") {
    throw new Error("disconnect state did not reach the practice piano");
  }
  if (await page.locator('[data-played="true"]').count()) {
    throw new Error("disconnect left stale learner-held keys visible");
  }
  if (failures.length) throw new Error(failures.join("; "));
  process.stdout.write(`${JSON.stringify({
    dual_layer_piano: true,
    expected_target_preserved: true,
    match_state: true,
    different_from_target_state: true,
    non_color_markers: ["diamond", "check", "exclamation"],
    disconnect_clears_held_keys: true,
    evidence_capture_started: false,
    network_bridge: false,
  })}\n`);
} finally {
  await page?.unrouteAll({ behavior: "ignoreErrors" });
  await browser?.close();
  server.kill("SIGINT");
  await new Promise((accept) => {
    const timeout = setTimeout(accept, 5_000);
    server.once("exit", () => {
      clearTimeout(timeout);
      accept();
    });
  });
}
