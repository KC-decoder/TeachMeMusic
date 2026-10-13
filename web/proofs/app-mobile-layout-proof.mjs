import { spawn } from "node:child_process";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

import { chromium } from "playwright";

// TEST-APP-MOBILE-002: the accepted landscape viewport preserves the exercise-first layout.
// TEST-APP-MOBILE-018: portrait blocks practice and directs the learner to rotate.
// TEST-APP-MOBILE-022: practice uses a viewport-locked score-and-piano stage.

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
    viewport: { width: 390, height: 844 },
    hasTouch: true,
    isMobile: true,
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
  const orientationGate = page.getByRole("dialog", { name: "Rotate your iPhone" });
  await orientationGate.waitFor();
  const portraitState = await page.evaluate(() => ({
    gateDisplay: getComputedStyle(document.querySelector(".landscape-orientation-gate")).display,
    appDisplay: getComputedStyle(document.querySelector(".app-shell")).display,
  }));
  if (portraitState.gateDisplay === "none" || portraitState.appDisplay !== "none") {
    throw new Error(`portrait gate failed: ${JSON.stringify(portraitState)}`);
  }

  await page.setViewportSize({ width: 844, height: 390 });
  await orientationGate.waitFor({ state: "hidden" });
  await page.locator(".app-shell").waitFor({ state: "visible" });
  await page.locator('input[type="file"]').first().setInputFiles(fixture);
  await page.getByText("BEGINNER LESSON · STEP 1 OF 16", { exact: true }).waitFor({ timeout: 120_000 });
  await page.getByRole("button", { name: "Next exercise" }).click();
  await page.getByText("BEGINNER LESSON · STEP 2 OF 16", { exact: true }).waitFor();
  await page.getByRole("button", { name: "Open practice screen" }).click();
  await page.getByRole("dialog", { name: "Setup, calibration, and evidence" }).waitFor();
  await page.getByLabel(/reviewed the untouched plan/i).check();
  await page.getByLabel(/approve local MIDI/i).check();
  await page.getByLabel(/approve local evidence export/i).check();
  await page.getByRole("button", { name: "Start local teaching run" }).click();
  await page.getByText("Authorized run:").waitFor();
  if (await page.locator(".notation-panel").count()) {
    throw new Error("bounded notation rendered before the dedicated exercise stage opened");
  }
  await page.getByRole("button", { name: /Continue (to exercise|without recording)/ }).click();
  await page.locator('.notation-panel[data-render-complete="true"]').waitFor({ timeout: 120_000 });

  const structure = await page.locator(".practice-stage").evaluate((stage) => {
    const notation = stage.querySelector('[data-mobile-region="notation"]');
    const controls = stage.querySelector('[data-mobile-region="controls"]');
    const attempt = stage.querySelector('[data-mobile-region="attempt"]');
    const piano = stage.querySelector('[data-mobile-region="piano"]');
    const setup = document.querySelector(".practice-setup-stage");
    if (!notation || !controls || !attempt || !piano) {
      throw new Error("dedicated practice-stage regions are incomplete");
    }
    const stageBox = stage.getBoundingClientRect();
    const pianoBox = piano.getBoundingClientRect();
    const scoreBox = notation.getBoundingClientRect();
    const keyboardBox = stage.querySelector(".piano-keyboard")?.getBoundingClientRect();
    return {
      controlsBeforeNotation: Boolean(controls.compareDocumentPosition(notation) & Node.DOCUMENT_POSITION_FOLLOWING),
      controlsBeforeAttempt: Boolean(controls.compareDocumentPosition(attempt) & Node.DOCUMENT_POSITION_FOLLOWING),
      attemptBeforeNotation: Boolean(attempt.compareDocumentPosition(notation) & Node.DOCUMENT_POSITION_FOLLOWING),
      notationBeforePiano: Boolean(notation.compareDocumentPosition(piano) & Node.DOCUMENT_POSITION_FOLLOWING),
      setupOutsideStage: !setup || !stage.contains(setup),
      setupClosed: setup === null,
      bodyLocked: document.body.classList.contains("practice-stage-open"),
      stagePosition: getComputedStyle(stage).position,
      stageOverflow: getComputedStyle(stage).overflow,
      stageFitsViewport:
        stageBox.left >= -1 && stageBox.top >= -1 &&
        stageBox.right <= window.innerWidth + 1 && stageBox.bottom <= window.innerHeight + 1,
      stageDoesNotScroll: stage.scrollHeight <= stage.clientHeight + 1,
      pianoAnchoredAtBottom: Math.abs(pianoBox.bottom - stageBox.bottom) <= 1,
      scoreHeight: scoreBox.height,
      keyboardHeight: keyboardBox?.height ?? 0,
      pageFitsViewport: document.documentElement.scrollWidth <= document.documentElement.clientWidth,
      pageWidth: `${document.documentElement.scrollWidth}/${document.documentElement.clientWidth}`,
      containerWidths: [
        ".practice-stage",
        ".practice-stage-header",
        ".practice-stage-attempt",
        ".practice-stage-score",
        ".practice-piano-dock",
        ".virtual-piano-panel",
        ".piano-scroll",
      ].map((selector) => {
        const element = document.querySelector(selector);
        const box = element.getBoundingClientRect();
        return `${selector}:${box.left}/${box.right}/${box.width};scroll=${element.scrollWidth};overflow=${getComputedStyle(element).overflowX}`;
      }),
      overflowElements: [...document.querySelectorAll("body *")]
        .map((element) => ({
          element,
          box: element.getBoundingClientRect(),
          scrollWidth: element.scrollWidth,
        }))
        .filter(({ box }) => box.right > document.documentElement.clientWidth + 1)
        .sort((left, right) => right.box.right - left.box.right)
        .slice(0, 12)
        .map(({ element, box, scrollWidth }) =>
          `${element.tagName.toLowerCase()}.${element.className}:${box.left}/${box.right}/${box.width};scroll=${scrollWidth}`),
      notationMaxHeight: getComputedStyle(stage.querySelector(".notation-canvas")).maxHeight,
      pianoPosition: getComputedStyle(piano).position,
    };
  });
  if (!structure.controlsBeforeNotation || !structure.controlsBeforeAttempt ||
      !structure.attemptBeforeNotation || !structure.notationBeforePiano ||
      !structure.setupOutsideStage || !structure.setupClosed || !structure.bodyLocked ||
      !structure.stageFitsViewport || !structure.stageDoesNotScroll ||
      !structure.pianoAnchoredAtBottom || !structure.pageFitsViewport) {
    throw new Error(`invalid mobile structure: ${JSON.stringify(structure)}`);
  }
  if (structure.stagePosition !== "fixed" || structure.stageOverflow !== "hidden") {
    throw new Error(`practice stage is not viewport locked: ${JSON.stringify(structure)}`);
  }
  if (structure.keyboardHeight > 72.5 || structure.scoreHeight < 180) {
    throw new Error(`score/piano landscape allocation is invalid: ${JSON.stringify(structure)}`);
  }

  const undersizedControls = await page.locator(".practice-stage button:visible").evaluateAll(
    (buttons) => buttons
      .map((button) => ({ name: button.textContent?.trim(), box: button.getBoundingClientRect() }))
      .filter(({ box }) => box.width < 44 || box.height < 44)
      .map(({ name, box }) => `${name}: ${box.width}x${box.height}`),
  );
  if (undersizedControls.length) {
    throw new Error(`undersized touch controls: ${undersizedControls.join("; ")}`);
  }

  const dock = page.locator(".practice-piano-dock");
  const dockBox = await dock.boundingBox();
  if (!dockBox || dockBox.y < 0 || dockBox.y + dockBox.height > 391) {
    throw new Error(`piano dock is outside the phone viewport: ${JSON.stringify(dockBox)}`);
  }

  if (failures.length) throw new Error(failures.join("; "));
  process.stdout.write(`${JSON.stringify({
    mobile_layout: true,
    viewport: "844x390",
    landscape_only: true,
    portrait_rotate_gate: true,
    dedicated_practice_stage: true,
    active_run_attempt_controls: true,
    viewport_locked: true,
    bounded_exercise_only: true,
    notation_visible: true,
    controls_touch_sized: true,
    piano_fixed_to_stage_bottom: true,
    score_height: structure.scoreHeight,
    keyboard_height: structure.keyboardHeight,
    setup_is_separate_stage: true,
    page_horizontal_overflow: false,
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
