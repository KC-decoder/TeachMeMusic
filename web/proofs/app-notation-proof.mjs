import { spawn } from "node:child_process";
import { mkdir } from "node:fs/promises";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

import { chromium } from "playwright";

// TEST-APP-NOTATION-005: real-browser canonical notation and navigation proof.

const here = dirname(fileURLToPath(import.meta.url));
const root = resolve(here, "../..");
const screenshotDirectory = process.env.TMM_SCREENSHOT_DIR;
const python = resolve(root, ".venv/bin/python");
const fixtures = [
  {
    path: resolve(
      root,
      "tests/fixtures/scores/TMM-REF-CANDIDATE-001-Hot-Cross-Buns/musicxml-17-hot-cross-buns-final-shelbygtdrew.mxl",
    ),
    label: "Hot Cross Buns",
    displayTitle: "Hot Cross Buns",
    ariaTitle: "Hot Cross Buns",
  },
  {
    path: resolve(
      root,
      "tests/fixtures/scores/TMM-REF-CANDIDATE-002-Happy-Birthday/happy-birthday-to-you-c-major.mxl",
    ),
    label: "Happy Birthday",
    displayTitle: "Happy Birthday to You",
    ariaTitle: "Happy Birthday to You",
  },
  {
    path: resolve(
      root,
      "tests/fixtures/scores/TMM-REF-CANDIDATE-003-Clair-de-Lune/clair-de-lune-debussy.mxl",
    ),
    label: "Clair de Lune",
    displayTitle: "Clair de Lune",
    ariaTitle: "Clair de Lune",
  },
  {
    path: resolve(
      root,
      "tests/fixtures/scores/TMM-REF-CANDIDATE-004-Moonlight-Sonata/beethoven-piano-sonata-no-14-moonlight.mxl",
    ),
    label: "Moonlight Sonata",
    displayTitle: "Piano Sonata No. 14 in C♯ minor (“Moonlight”)",
    ariaTitle: "Piano Sonata No. 14 in C♯ minor (“Moonlight”)",
    expectedDiagnostic: "VIEWER_INLINE_DYNAMIC_SYMBOL_NORMALIZED",
  },
  {
    path: resolve(
      root,
      "tests/fixtures/scores/TMM-REF-CANDIDATE-005-Deux-Arabesques/debussy-deux-arabesques.mxl",
    ),
    label: "Deux arabesques",
    displayTitle: "Deux arabesques",
    ariaTitle: "Deux arabesques",
  },
];

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
  page.on("console", (message) => {
    if (message.type() === "error") failures.push(`console: ${message.text()}`);
  });
  page.on("pageerror", (error) => failures.push(`page: ${error.message}`));
  await page.route("**/*", async (route) => {
    const requestUrl = route.request().url();
    if (requestUrl.startsWith(url) || requestUrl.startsWith("data:")) {
      await route.continue();
    } else {
      failures.push(`external request blocked: ${requestUrl}`);
      await route.abort();
    }
  });
  await page.goto(url);

  const results = [];
  for (const fixture of fixtures) {
    process.stderr.write(`checking ${fixture.label}\n`);
    await page.locator('input[type="file"]').setInputFiles(fixture.path);
    await page.getByRole("heading", { name: fixture.displayTitle, exact: true }).first().waitFor();
    const canvas = page.getByRole("img", {
      name: `Rendered notation for ${fixture.ariaTitle}`,
    });
    await canvas.locator("svg").first().waitFor({ timeout: 120_000 });
    await page.locator('.notation-panel[data-render-complete="true"]').waitFor({ timeout: 120_000 });
    if (screenshotDirectory) {
      await mkdir(screenshotDirectory, { recursive: true });
      await page.locator(".notation-panel").scrollIntoViewIfNeeded();
      await page.screenshot({
        path: resolve(
          screenshotDirectory,
          `${fixture.label.toLowerCase().replaceAll(/[^a-z0-9]+/g, "-")}.png`,
        ),
      });
    }
    const nextEvent = page.getByRole("button", { name: "Next event" });
    try {
      await nextEvent.click({ timeout: 30_000 });
    } catch (error) {
      const visibleState = await page.locator(".notation-status, .notation-error").allTextContents();
      throw new Error(`${fixture.label}: navigation unavailable (${visibleState.join(" | ")}; ${failures.join(" | ")})`, {
        cause: error,
      });
    }
    await page.getByText(/Measure \d+ · offset .* quarters/).waitFor();
    await page.getByRole("button", { name: "Next system" }).click();
    await page.getByText(/System 2 of \d+/).waitFor();
    const pageLabel = await page.getByText(/Page \d+ of \d+/).textContent();
    const systemLabel = await page.getByText(/System \d+ of \d+/).textContent();
    const result = await canvas.evaluate((element) => ({
      svg_count: element.querySelectorAll("svg").length,
      graphical_element_count: element.querySelectorAll(
        "path, line, rect, text, polygon, polyline",
      ).length,
      cursor_count: element.querySelectorAll('img[id^="cursorImg"]').length,
      raw_inline_symbol_count: (element.textContent?.match(/<sym>/g) ?? []).length,
    }));
    if (result.svg_count < 1 || result.graphical_element_count < 1) {
      throw new Error(`${fixture.label}: no engraved notation was produced`);
    }
    if (result.cursor_count !== 2) {
      throw new Error(`${fixture.label}: expected two canonical highlight cursors`);
    }
    if (result.raw_inline_symbol_count !== 0) {
      throw new Error(`${fixture.label}: raw exporter inline-symbol text remained visible`);
    }
    if (fixture.expectedDiagnostic) {
      await page.getByText(new RegExp(`^${fixture.expectedDiagnostic}:`)).waitFor();
    }
    results.push({ title: fixture.label, page_label: pageLabel, system_label: systemLabel, ...result });
  }
  if (failures.length) throw new Error(failures.join("; "));
  process.stdout.write(`${JSON.stringify({ rendered: true, fixtures: results })}\n`);
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
