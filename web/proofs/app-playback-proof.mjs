import { spawn } from "node:child_process";
import { mkdir } from "node:fs/promises";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

import { chromium } from "playwright";

// TEST-APP-PLAYBACK-007 / TEST-APP-PIANO-006: real-browser audio and piano sync.

const here = dirname(fileURLToPath(import.meta.url));
const root = resolve(here, "../..");
const python = resolve(root, ".venv/bin/python");
const screenshotDirectory = process.env.TMM_SCREENSHOT_DIR;
const fixture = resolve(
  root,
  "tests/fixtures/scores/TMM-REF-CANDIDATE-001-Hot-Cross-Buns/musicxml-17-hot-cross-buns-final-shelbygtdrew.mxl",
);
const happyBirthdayFixture = resolve(
  root,
  "tests/fixtures/scores/TMM-REF-CANDIDATE-002-Happy-Birthday/happy-birthday-to-you-c-major.mxl",
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
    server.once("exit", (code) => {
      clearTimeout(timeout);
      reject(new Error(`local application exited early (${code})`));
    });
  });
}

let browser;
try {
  const url = await serverUrl();
  browser = await chromium.launch({ channel: "chrome", headless: true });
  const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
  const failures = [];
  const sampleRequests = new Set();
  page.on("console", (message) => {
    if (message.type() === "error") failures.push(`console: ${message.text()}`);
  });
  page.on("pageerror", (error) => failures.push(`page: ${error.message}`));
  page.on("requestfinished", (request) => {
    if (request.url().includes("/audio/salamander/") && request.url().endsWith(".mp3")) {
      sampleRequests.add(request.url());
    }
  });
  await page.route("**/*", async (route) => {
    const requestUrl = route.request().url();
    if (requestUrl.startsWith(url) || requestUrl.startsWith("data:") || requestUrl.startsWith("blob:")) {
      await route.continue();
    } else {
      failures.push(`external request blocked: ${requestUrl}`);
      await route.abort();
    }
  });
  const clickButton = async (name) => {
    const button = page.getByRole("button", { name, exact: true });
    await button.focus();
    await page.keyboard.press("Enter");
  };

  await page.goto(url);
  await page.locator('input[type="file"]').setInputFiles(fixture);
  await page.getByRole("heading", { name: "Hot Cross Buns", exact: true }).first().waitFor();
  await page.locator('.notation-panel[data-render-complete="true"]').waitFor({ timeout: 120_000 });
  const initialLocation = await page.locator(".notation-location").textContent();
  if (await page.locator("[data-midi]").count() !== 88) {
    throw new Error("virtual piano did not expose the standard 88-key range");
  }
  if (await page.locator('[data-active="true"]').count() !== 0) {
    throw new Error("virtual piano was active before audio started");
  }

  await clickButton("Play");
  await page.getByText(/^Playing ·/).waitFor({ timeout: 120_000 });
  await page.waitForFunction(() => {
    const slider = document.querySelector('#playback-position');
    return slider instanceof HTMLInputElement && Number(slider.value) > 100_000;
  });
  await page.locator('[data-active="true"]').first().waitFor();
  const hotCrossBunsActiveKeys = await page.locator('[data-active="true"]').count();
  await clickButton("Pause");
  await page.getByText("Paused", { exact: true }).waitFor();
  if (await page.locator('[data-active="true"]').count() !== 0) {
    throw new Error("virtual piano did not clear on pause");
  }

  await page.locator("#playback-position").evaluate((element) => {
    if (!(element instanceof HTMLInputElement)) throw new Error("playback slider missing");
    const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value")?.set;
    if (!setter) throw new Error("playback slider setter missing");
    setter.call(element, "10000000");
    element.dispatchEvent(new Event("input", { bubbles: true }));
    element.dispatchEvent(new Event("change", { bubbles: true }));
  });
  await page.waitForFunction(
    (first) => document.querySelector(".notation-location")?.textContent !== first,
    initialLocation,
  );
  const seekLocation = await page.locator(".notation-location").textContent();

  await clickButton("Resume");
  await page.getByText(/^Playing ·/).waitFor();
  await clickButton("Stop");
  await page.getByText("Ready to play", { exact: true }).waitFor();
  if (await page.locator('[data-active="true"]').count() !== 0) {
    throw new Error("virtual piano did not clear on stop");
  }

  await page.locator('input[type="file"]').setInputFiles(happyBirthdayFixture);
  await page.getByRole("heading", { name: "Happy Birthday to You", exact: true }).first().waitFor();
  await page.locator('.notation-panel[data-render-complete="true"]').waitFor({ timeout: 120_000 });
  await page.locator("#playback-position").evaluate((element) => {
    if (!(element instanceof HTMLInputElement)) throw new Error("playback slider missing");
    const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value")?.set;
    if (!setter) throw new Error("playback slider setter missing");
    setter.call(element, "500000");
    element.dispatchEvent(new Event("input", { bubbles: true }));
    element.dispatchEvent(new Event("change", { bubbles: true }));
  });
  await clickButton("Resume");
  for (const midi of [48, 52, 55]) {
    await page.locator(`[data-midi="${midi}"][data-active="true"]`).waitFor({ timeout: 30_000 });
  }
  const happyBirthdayActiveKeys = await page.locator('[data-active="true"]').count();
  const bassChordClefs = await Promise.all(
    [48, 52, 55].map((midi) =>
      page.locator(`[data-midi="${midi}"]`).getAttribute("data-clefs"),
    ),
  );
  if (bassChordClefs.some((clefs) => clefs !== "bass")) {
    throw new Error(`Happy Birthday accompaniment clefs were not retained: ${bassChordClefs}`);
  }
  await page.getByText(/Active canonical events/).waitFor();
  if (screenshotDirectory) {
    await mkdir(screenshotDirectory, { recursive: true });
    await page.locator(".virtual-piano-panel").screenshot({
      path: resolve(screenshotDirectory, "happy-birthday-virtual-piano.png"),
    });
  }
  await clickButton("Stop");
  if (await page.locator('[data-active="true"]').count() !== 0) {
    throw new Error("virtual piano did not clear after Happy Birthday");
  }

  if (sampleRequests.size !== 30) {
    throw new Error(`expected 30 local piano samples, received ${sampleRequests.size}`);
  }
  if (failures.length) throw new Error(failures.join("; "));
  process.stdout.write(`${JSON.stringify({
    playback: true,
    local_sample_requests: sampleRequests.size,
    initial_location: initialLocation,
    seek_location: seekLocation,
    piano_keys: 88,
    hot_cross_buns_active_keys: hotCrossBunsActiveKeys,
    happy_birthday_active_keys: happyBirthdayActiveKeys,
    happy_birthday_bass_chord: [48, 52, 55],
    controls: ["play", "pause", "seek", "resume", "stop"],
  })}\n`);
} finally {
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
