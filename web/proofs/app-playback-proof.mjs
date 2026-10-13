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
  await page.locator('input[type="file"]').first().setInputFiles(fixture);
  await page.getByRole("heading", { name: "Hot Cross Buns", exact: true }).first().waitFor();
  await page.getByRole("button", { name: "Open practice screen" }).click();
  await page.locator('.notation-panel[data-render-complete="true"]').waitFor({ timeout: 120_000 });
  const initialLocation = await page.locator(".notation-location").textContent();
  if (await page.locator("[data-midi]").count() !== 88) {
    throw new Error("virtual piano did not expose the standard 88-key range");
  }
  if (await page.locator('[data-active="true"]').count() !== 0) {
    throw new Error("virtual piano was active before audio started");
  }

  await clickButton("Play");
  await page.waitForFunction(
    () => document.querySelector(".playback-state")?.textContent?.startsWith("Playing ·"),
    undefined,
    { timeout: 120_000 },
  );
  await page.waitForFunction(() => {
    const slider = document.querySelector('#playback-position');
    return slider instanceof HTMLInputElement && Number(slider.value) > 100_000;
  });
  await page.locator('[data-active="true"]').first().waitFor();
  const hotCrossBunsActiveKeys = await page.locator('[data-active="true"]').count();
  await page.locator('[data-teachmemusic-current-note="true"]').first().waitFor();
  const hotCrossBunsHighlightedNotes = await page
    .locator('[data-teachmemusic-current-note="true"]')
    .count();
  const hotCrossBunsHighlightPaint = await page
    .locator('[data-teachmemusic-current-note="true"]')
    .evaluateAll((notes) => notes.map((note) => {
      const elements = [note, ...note.querySelectorAll("*")];
      return {
        tag: note.tagName,
        outer_html: note.outerHTML.slice(0, 500),
        painted: elements.map((element) => ({
          tag: element.tagName,
          fill: getComputedStyle(element).fill,
          stroke: getComputedStyle(element).stroke,
        })),
      };
    }));
  if (!hotCrossBunsHighlightPaint.some((note) =>
    note.painted.some((element) =>
      element.tag.toLowerCase() === "path" &&
      (element.fill === "rgb(217, 79, 31)" || element.stroke === "rgb(217, 79, 31)")
    ))) {
    throw new Error(
      `current notation notehead was tagged but not visibly painted: ${JSON.stringify(hotCrossBunsHighlightPaint)}`,
    );
  }
  if (screenshotDirectory) {
    await mkdir(screenshotDirectory, { recursive: true });
    await page.locator(".practice-stage").screenshot({
      path: resolve(screenshotDirectory, "hot-cross-buns-practice-stage.png"),
    });
  }
  const cursorGeometry = await page.locator('.notation-panel [id^="cursorImg"]').evaluateAll(
    (cursors) => cursors.map((cursor) => {
      const box = cursor.getBoundingClientRect();
      const style = getComputedStyle(cursor);
      return {
        id: cursor.id,
        left: box.left,
        top: box.top,
        right: box.right,
        bottom: box.bottom,
        width: box.width,
        height: box.height,
        display: style.display,
        visibility: style.visibility,
        opacity: style.opacity,
        position: style.position,
        zIndex: style.zIndex,
      };
    }),
  );
  const notationBox = await page.locator(".practice-stage-score").boundingBox();
  if (!notationBox || cursorGeometry.length !== 2) {
    throw new Error(`notation cursor geometry unavailable: ${JSON.stringify(cursorGeometry)}`);
  }
  if (!cursorGeometry.some((cursor) =>
    cursor.display !== "none" && cursor.visibility !== "hidden" && Number(cursor.opacity) > 0 &&
    Number(cursor.zIndex) > 0 &&
    cursor.right > notationBox.x && cursor.left < notationBox.x + notationBox.width &&
    cursor.bottom > notationBox.y && cursor.top < notationBox.y + notationBox.height)) {
    throw new Error(
      `no notation cursor intersects the practice score: ${JSON.stringify({ cursorGeometry, notationBox })}`,
    );
  }
  await clickButton("Pause");
  await page.waitForFunction(
    () => document.querySelector(".playback-state")?.textContent === "Paused",
  );
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
  await page.waitForFunction(
    () => document.querySelector(".playback-state")?.textContent?.startsWith("Playing ·"),
  );
  await clickButton("Stop");
  await page.waitForFunction(
    () => document.querySelector(".playback-state")?.textContent === "Ready to play",
  );
  if (await page.locator('[data-active="true"]').count() !== 0) {
    throw new Error("virtual piano did not clear on stop");
  }

  await page.getByRole("button", { name: "Close practice screen" }).click();
  await page.locator('input[type="file"]').first().setInputFiles(happyBirthdayFixture);
  await page.getByRole("heading", { name: "Happy Birthday to You", exact: true }).first().waitFor();
  await page.getByRole("button", { name: "Open practice screen" }).click();
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
  await page.locator('[data-teachmemusic-current-note="true"]').first().waitFor();
  const happyBirthdayHighlightedNotes = await page
    .locator('[data-teachmemusic-current-note="true"]')
    .count();
  if (happyBirthdayHighlightedNotes < happyBirthdayActiveKeys) {
    throw new Error(
      `Happy Birthday chord highlighting was incomplete: ${happyBirthdayHighlightedNotes} score notes for ${happyBirthdayActiveKeys} active keys`,
    );
  }
  const bassChordClefs = await Promise.all(
    [48, 52, 55].map((midi) =>
      page.locator(`[data-midi="${midi}"]`).getAttribute("data-clefs"),
    ),
  );
  if (bassChordClefs.some((clefs) => clefs !== "bass")) {
    throw new Error(`Happy Birthday accompaniment clefs were not retained: ${bassChordClefs}`);
  }
  await page.locator(".piano-trace").waitFor({ state: "attached" });
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

  await page.evaluate(() => {
    globalThis.__teachMeMusicPianoAudit = [];
    globalThis.__teachMeMusicPianoAuditTimer = globalThis.setInterval(() => {
      const slider = document.querySelector("#playback-position");
      const state = document.querySelector(".playback-state")?.textContent ?? "";
      const keys = [...document.querySelectorAll('[data-active="true"]')].map((key) => {
        const style = getComputedStyle(key);
        const defaultColor = key.classList.contains("piano-key-black")
          ? "rgb(32, 49, 44)"
          : "rgb(255, 255, 255)";
        return {
          midi: Number(key.getAttribute("data-midi")),
          backgroundColor: style.backgroundColor,
          backgroundImage: style.backgroundImage,
          visiblyHighlighted:
            style.backgroundImage !== "none" || style.backgroundColor !== defaultColor,
        };
      });
      if (keys.length > 0) {
        globalThis.__teachMeMusicPianoAudit.push({
          position: slider instanceof HTMLInputElement ? Number(slider.value) : -1,
          state,
          keys,
          highlightedScoreNotes: document.querySelectorAll(
            '[data-teachmemusic-current-note="true"]',
          ).length,
        });
      }
    }, 10);
  });
  await clickButton("Play");
  await page.waitForFunction(
    () => document.querySelector(".playback-state")?.textContent === "Playback complete",
    undefined,
    { timeout: 30_000 },
  );
  const happyBirthdayPianoAudit = await page.evaluate(() => {
    globalThis.clearInterval(globalThis.__teachMeMusicPianoAuditTimer);
    return globalThis.__teachMeMusicPianoAudit;
  });
  const missingHappyBirthdayHighlights = happyBirthdayPianoAudit.filter((sample) =>
    sample.keys.some((key) => !key.visiblyHighlighted)
  );
  if (missingHappyBirthdayHighlights.length > 0) {
    throw new Error(
      `Happy Birthday active keys lacked visible highlighting: ${JSON.stringify(missingHappyBirthdayHighlights.slice(0, 10))}`,
    );
  }
  const incompleteNotationRuns = [];
  let incompleteRun = [];
  for (const sample of happyBirthdayPianoAudit) {
    const signature = sample.keys.map((key) => key.midi).join(",");
    const priorSignature = incompleteRun.at(-1)?.keys.map((key) => key.midi).join(",");
    if (sample.highlightedScoreNotes < sample.keys.length) {
      if (incompleteRun.length > 0 && signature !== priorSignature) {
        if (incompleteRun.length >= 3) incompleteNotationRuns.push(incompleteRun);
        incompleteRun = [];
      }
      incompleteRun.push(sample);
    } else {
      if (incompleteRun.length >= 3) incompleteNotationRuns.push(incompleteRun);
      incompleteRun = [];
    }
  }
  if (incompleteRun.length >= 3) incompleteNotationRuns.push(incompleteRun);
  if (incompleteNotationRuns.length > 0) {
    throw new Error(
      `Happy Birthday score-note highlighting was incomplete: ${JSON.stringify(incompleteNotationRuns.slice(0, 3).map((run) => run.slice(0, 3)))}`,
    );
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
    hot_cross_buns_highlighted_notes: hotCrossBunsHighlightedNotes,
    hot_cross_buns_highlight_paint: hotCrossBunsHighlightPaint,
    hot_cross_buns_notation_cursors: cursorGeometry,
    happy_birthday_active_keys: happyBirthdayActiveKeys,
    happy_birthday_highlighted_notes: happyBirthdayHighlightedNotes,
    happy_birthday_audited_frames: happyBirthdayPianoAudit.length,
    happy_birthday_missing_key_highlights: missingHappyBirthdayHighlights.length,
    happy_birthday_incomplete_notation_runs: incompleteNotationRuns.length,
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
