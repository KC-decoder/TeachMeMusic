import { spawn } from "node:child_process";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

import { chromium } from "playwright";

// TEST-APP-TEACHING-003: real-browser exact range, aids, and lesson navigation.

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
  page = await browser.newPage({ viewport: { width: 1280, height: 900 } });
  const failures = [];
  page.on("console", (message) => {
    if (message.type() === "error") failures.push(`console: ${message.text()}`);
  });
  page.on("pageerror", (error) => failures.push(`page: ${error.message}`));
  await page.route("**/*", async (route) => {
    try {
      const requestUrl = route.request().url();
      if (requestUrl.startsWith(url) || requestUrl.startsWith("data:") || requestUrl.startsWith("blob:")) {
        await route.continue();
      } else {
        failures.push(`external request blocked: ${requestUrl}`);
        await route.abort();
      }
    } catch (error) {
      if (!String(error).includes("Target page, context or browser has been closed")) throw error;
    }
  });

  await page.goto(url);
  await page.locator('input[type="file"]').setInputFiles(fixture);
  const lesson = page.locator(".lesson-panel");
  await lesson.waitFor({ timeout: 120_000 });
  await page.getByText("BEGINNER LESSON · STEP 1 OF 16", { exact: true }).waitFor();
  await page.getByRole("heading", { name: "Measures 1–8", exact: true }).waitFor();
  const originalDigest = await lesson.getAttribute("data-expected-content");
  if (!originalDigest || originalDigest.length !== 64) {
    throw new Error("expected-content fingerprint is unavailable");
  }
  await page.getByRole("button", { name: "Open practice screen" }).click();
  await page.locator('.notation-panel[data-render-complete="true"]').waitFor({ timeout: 120_000 });
  await page.locator(".virtual-piano-panel").waitFor();
  await page.getByRole("button", { name: "Close practice screen" }).click();
  await page.getByText("Setup, calibration, and evidence", { exact: true }).click();
  for (const label of ["Count in", "Show notation", "Light piano keys"]) {
    await page.getByLabel(label).evaluate((element) => {
      if (!(element instanceof HTMLInputElement)) throw new Error("practice aid is not an input");
      element.click();
    });
  }
  await page.getByRole("button", { name: "Open practice screen" }).click();
  if (await page.locator(".notation-panel").count()) throw new Error("notation aid did not hide");
  if (await page.locator(".virtual-piano-panel").count()) throw new Error("piano aid did not hide");
  if ((await lesson.getAttribute("data-expected-content")) !== originalDigest) {
    throw new Error("presentation aid changed expected musical content");
  }
  await page.getByRole("button", { name: "Close practice screen" }).click();

  await page.getByRole("button", { name: "Next exercise" }).click();
  await page.getByText("BEGINNER LESSON · STEP 2 OF 16", { exact: true }).waitFor();
  await page.getByRole("heading", { name: "Measure 1", exact: true }).waitFor();
  await page.getByRole("button", { name: "Open practice screen" }).click();
  await page.locator('.practice-stage .notation-panel[data-render-complete="true"]').waitFor({ timeout: 120_000 });
  await page.locator(".practice-stage .virtual-piano-panel").waitFor();
  await page.getByRole("button", { name: "Close practice screen" }).click();
  const secondDigest = await lesson.getAttribute("data-expected-content");
  if (!secondDigest || secondDigest === originalDigest) {
    throw new Error("lesson navigation did not select a new expected exercise");
  }

  await page.getByLabel("Demonstration tempo").selectOption("72");
  await page.getByText("72 BPM", { exact: true }).first().waitFor();
  if ((await lesson.getAttribute("data-expected-content")) !== secondDigest) {
    throw new Error("tempo aid changed expected musical content");
  }
  if (failures.length) throw new Error(failures.join("; "));
  process.stdout.write(`${JSON.stringify({
    teaching: true,
    steps: 16,
    first_range: "1-8",
    second_range: "1",
    second_exercise_rendered: true,
    aids_reversible: true,
    expected_content_stable: true,
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
