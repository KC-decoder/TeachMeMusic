import { spawn } from "node:child_process";
import { readFile } from "node:fs/promises";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

import { chromium } from "playwright";

// TEST-APP-TEACHING-006: no-learning browser rehearsal of the closed local loop.
// TEST-APP-MOBILE-029: compact learner feedback remains readable and bounded.
// TEST-APP-MOBILE-030: demonstration hands off to guided practice before evaluation.

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
  page = await browser.newPage({ viewport: { width: 1280, height: 1000 }, acceptDownloads: true });
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
  await page.getByRole("button", { name: "Next exercise" }).click();
  await page.getByText("BEGINNER LESSON · STEP 2 OF 16", { exact: true }).waitFor();
  await page.getByRole("heading", { name: "Measure 1", exact: true }).waitFor();

  await page.getByRole("button", { name: "Open practice screen" }).click();
  await page.getByRole("dialog", { name: "Setup, calibration, and evidence" }).waitFor();
  await page.getByLabel("Demonstration tempo").selectOption("72");
  await page.getByText("72 BPM", { exact: true }).first().waitFor();

  await page.getByLabel(/reviewed the untouched plan/i).check();
  await page.getByLabel(/approve local MIDI/i).check();
  await page.getByLabel(/approve local evidence export/i).check();
  await page.getByRole("button", { name: "Start local teaching run" }).click();
  await page.getByText("Authorized run:").waitFor();
  await page.getByText("60 BPM", { exact: true }).first().waitFor();
  if (await page.locator(".lesson-navigation-primary button").last().isEnabled()) {
    throw new Error("manual next navigation bypassed the active teaching policy");
  }

  await page.getByRole("button", { name: "Allow MIDI access" }).click();
  await page.getByRole("button", { name: "Connect piano" }).click();
  await page.getByRole("button", { name: "Start calibration" }).click();
  await page.evaluate(() => {
    const emit = window.__teachMeMusicProofMidi;
    for (const note of [60, 62, 64, 65, 67]) {
      emit([0x90, note, 72]);
      emit([0x80, note, 0]);
    }
    emit([0xb0, 64, 127]);
    emit([0xb0, 64, 0]);
  });
  await page.getByRole("button", { name: "Stop and review" }).click();
  await page.getByRole("button", { name: "Approve calibration evidence" }).click();
  await page.locator(".lesson-panel").getByText("Calibration evidence approved locally.").waitFor();

  await page.getByRole("button", { name: "Continue to exercise →" }).click();
  await page.setViewportSize({ width: 844, height: 390 });
  const practiceStage = page.getByRole("dialog", { name: "Measure 1" });
  const attemptPanel = practiceStage.locator(".attempt-panel");
  await practiceStage.getByRole("button", { name: "Play", exact: true }).click();
  await practiceStage.getByText("Your turn", { exact: true }).waitFor({ timeout: 20_000 });
  await attemptPanel.getByRole("button", { name: "Abort without penalty" }).waitFor();
  await attemptPanel.getByRole("button", { name: "Stop — discomfort" }).waitFor();
  await attemptPanel.getByRole("button", { name: "Pause" }).click();
  await attemptPanel.getByRole("button", { name: "Resume" }).click();
  await page.evaluate(() => {
    const emit = window.__teachMeMusicProofMidi;
    emit([0x90, 71, 80]);
    emit([0x80, 71, 0]);
  });
  await attemptPanel.getByRole("button", { name: "Finish attempt" }).click();
  await attemptPanel.getByRole("button", { name: "Compare and give feedback" }).click();
  await attemptPanel.getByRole("heading", { name: "Try again" }).waitFor();
  await page.locator("section.practice-stage.has-missed-notes").waitFor();
  const compactResult = await attemptPanel.locator(".learner-result").evaluate((card) => {
    const box = card.getBoundingClientRect();
    const readableNodes = [...card.querySelectorAll("h4, p")];
    return {
      fitsViewport: box.left >= -1 && box.right <= window.innerWidth + 1,
      hasNoHorizontalScroll: card.scrollWidth <= card.clientWidth + 1,
      contentFitsCard: readableNodes.every((node) => {
        const nodeBox = node.getBoundingClientRect();
        return nodeBox.left >= box.left - 1 && nodeBox.right <= box.right + 1;
      }),
      minimumTextSize: Math.min(...readableNodes.map((node) => parseFloat(getComputedStyle(node).fontSize))),
      overflowWraps: readableNodes.every((node) => getComputedStyle(node).overflowWrap === "anywhere"),
    };
  });
  if (!compactResult.fitsViewport || !compactResult.hasNoHorizontalScroll ||
      !compactResult.contentFitsCard || !compactResult.overflowWraps ||
      compactResult.minimumTextSize < 11.5) {
    throw new Error(`compact feedback is not readable: ${JSON.stringify(compactResult)}`);
  }
  await page.setViewportSize({ width: 1280, height: 1000 });
  await page.getByRole("button", { name: "Back to practice setup" }).click();
  await page.getByText(/1 attempts/).waitFor();

  const unnamedControls = await page.locator("button:visible, input:visible, select:visible").evaluateAll(
    (elements) => elements.filter((element) => {
      const control = element;
      return !(
        control.getAttribute("aria-label") ||
        control.getAttribute("title") ||
        control.textContent?.trim() ||
        ("labels" in control && control.labels?.length)
      );
    }).map((element) => element.outerHTML),
  );
  if (unnamedControls.length) {
    throw new Error(`visible controls without accessible names: ${unnamedControls.join("; ")}`);
  }

  const downloadPromise = page.waitForEvent("download");
  await page.getByRole("button", { name: "Export evidence" }).click();
  const download = await downloadPromise;
  const downloadPath = await download.path();
  if (!downloadPath) throw new Error("evidence archive was not downloaded");
  const archiveText = await readFile(downloadPath, "utf8");
  const archive = JSON.parse(archiveText);
  if (archive.evidence.performance.attempts.length !== 1) {
    throw new Error("exported archive does not contain the browser attempt");
  }
  if (archiveText.includes("<score-partwise")) {
    throw new Error("exported evidence leaked original score bytes");
  }

  await page.getByRole("button", { name: "Delete active run" }).click();
  await page.getByText("Authorize the closed teaching loop").waitFor();
  await page.locator(".archive-import input").setInputFiles(downloadPath);
  await page.getByText("Authorized run:").waitFor();
  await page.getByText(/1 attempts/).waitFor();

  if (failures.length) throw new Error(failures.join("; "));
  process.stdout.write(`${JSON.stringify({
    closed_loop: true,
    score: "Hot Cross Buns",
    midi: "deterministic fake port",
    attempts: 1,
    feedback_visible: true,
    compact_feedback_readable: true,
    compact_feedback_message: "Try again",
    missing_notes_visible: true,
    demonstration_to_practice_handoff: true,
    pause_resume_abort_discomfort_controls: true,
    visible_controls_named: true,
    policy_navigation_enforced: true,
    support_tempo_restored_before_capture: true,
    evidence_exported: true,
    exact_resume: true,
    learner_trial: false,
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
