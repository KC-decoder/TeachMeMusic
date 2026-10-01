import { createHash } from "node:crypto";
import { readFile } from "node:fs/promises";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

import { chromium } from "playwright";

const here = dirname(fileURLToPath(import.meta.url));
const bundlePath = process.argv[2];
if (!bundlePath) {
  throw new Error("usage: node proofs/osmd-render-proof.mjs VIEWER_BUNDLE.json");
}

const bundle = JSON.parse(await readFile(resolve(bundlePath), "utf8"));
if (bundle.contract_id !== "org.teachmemusic.viewer-bundle") {
  throw new Error("unsupported viewer bundle contract");
}
if (bundle.renderer.renderer !== "opensheetmusicdisplay") {
  throw new Error("viewer bundle does not contain an OSMD renderer payload");
}
const musicxml = bundle.renderer.content;
const digest = createHash("sha256").update(musicxml, "utf8").digest("hex");
if (digest !== bundle.renderer.sha256) {
  throw new Error("viewer bundle renderer digest mismatch");
}

const browser = await chromium.launch({ channel: "chrome", headless: true });
try {
  const page = await browser.newPage({ viewport: { width: 1280, height: 900 } });
  const failures = [];
  page.on("console", (message) => {
    if (message.type() === "error") failures.push(`console: ${message.text()}`);
  });
  page.on("pageerror", (error) => failures.push(`page: ${error.message}`));
  await page.route("**/*", async (route) => {
    const url = route.request().url();
    if (url.startsWith("data:") || url.startsWith("about:")) {
      await route.continue();
    } else {
      failures.push(`external request blocked: ${url}`);
      await route.abort();
    }
  });
  await page.setContent(
    '<!doctype html><html><body><main id="score" style="width:1200px"></main></body></html>',
  );
  await page.addScriptTag({
    path: resolve(here, "../node_modules/opensheetmusicdisplay/build/opensheetmusicdisplay.min.js"),
  });
  const result = await page.evaluate(async ({ xml, expectedTitle }) => {
    const api = globalThis.opensheetmusicdisplay;
    if (!api?.OpenSheetMusicDisplay) throw new Error("OSMD browser API is unavailable");
    const osmd = new api.OpenSheetMusicDisplay("score", {
      backend: "svg",
      autoResize: false,
      drawTitle: true,
    });
    await osmd.load(xml, expectedTitle ?? "");
    osmd.render();
    const score = document.querySelector("#score");
    const text = score?.textContent ?? "";
    return {
      svg_count: score?.querySelectorAll("svg").length ?? 0,
      graphical_element_count:
        score?.querySelectorAll("path, line, rect, text, polygon, polyline").length ?? 0,
      title_present: expectedTitle === null || text.includes(expectedTitle),
      rendered_width: score?.getBoundingClientRect().width ?? 0,
    };
  }, { xml: musicxml, expectedTitle: bundle.title });
  if (failures.length) throw new Error(failures.join("; "));
  if (result.svg_count < 1) throw new Error("OSMD produced no SVG notation surface");
  if (result.graphical_element_count < 1) {
    throw new Error("OSMD produced no graphical notation elements");
  }
  if (!result.title_present) throw new Error("OSMD output omitted the canonical title");
  process.stdout.write(`${JSON.stringify({ rendered: true, ...result })}\n`);
} finally {
  await browser.close();
}
