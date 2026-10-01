import { CursorType, OpenSheetMusicDisplay } from "opensheetmusicdisplay";

import type { RendererPayload } from "../contracts/viewer";
import type { HighlightPosition } from "./navigation";

export interface NotationSystem {
  index: number;
  pageIndex: number;
  measureIndexes: number[];
}

export interface NotationLayout {
  pageCount: number;
  systems: NotationSystem[];
  complete: boolean;
  renderedMeasures: number;
  totalMeasures: number;
  diagnostics: { code: string; message: string }[];
}

export interface NotationRenderCallbacks {
  title?: string | null;
  measureRange?: { fromMeasureIndex: number; toMeasureIndex: number };
  onLayout?: (layout: NotationLayout) => void;
  onError?: (error: NotationAdapterError) => void;
}

export interface NotationAdapter {
  load(payload: RendererPayload, callbacks?: NotationRenderCallbacks): Promise<NotationLayout>;
  highlight(position: HighlightPosition): boolean;
  dispose(): void;
}

export class NotationAdapterError extends Error {
  constructor(readonly code: string, message: string) {
    super(message);
  }
}

async function sha256(value: string): Promise<string> {
  if (!globalThis.crypto?.subtle) {
    throw new NotationAdapterError(
      "VIEWER_DIGEST_UNAVAILABLE",
      "This browser cannot verify the notation payload.",
    );
  }
  const digest = await globalThis.crypto.subtle.digest(
    "SHA-256",
    new TextEncoder().encode(value),
  );
  return [...new Uint8Array(digest)]
    .map((byte) => byte.toString(16).padStart(2, "0"))
    .join("");
}

function normalizeInlineDynamicSymbols(source: string): { content: string; count: number } {
  const symbols: Readonly<Record<string, string>> = {
    dynamicPiano: "p",
    dynamicForte: "f",
    dynamicMezzo: "m",
    dynamicSforzando: "s",
    dynamicRinforzando: "r",
    dynamicNiente: "n",
    dynamicZ: "z",
  };
  let count = 0;
  const content = source.replace(
    /&lt;sym&gt;(dynamic(?:Piano|Forte|Mezzo|Sforzando|Rinforzando|Niente|Z))&lt;\/sym&gt;/g,
    (_match, name: string) => {
      count += 1;
      return symbols[name] ?? name;
    },
  );
  return { content, count };
}

export class OsmdNotationAdapter implements NotationAdapter {
  private osmd: OpenSheetMusicDisplay | null = null;
  private anchorLimit = 0;
  private batchTimer: number | null = null;
  private lastHighlight: HighlightPosition | null = null;
  private inlineSymbolNormalizationCount = 0;

  constructor(private readonly container: HTMLElement) {}

  async load(
    payload: RendererPayload,
    callbacks: NotationRenderCallbacks = {},
  ): Promise<NotationLayout> {
    if (
      payload.renderer !== "opensheetmusicdisplay" ||
      payload.media_type !== "application/vnd.recordare.musicxml+xml" ||
      payload.encoding.toLowerCase() !== "utf-8" ||
      !payload.content.startsWith("<?xml")
    ) {
      throw new NotationAdapterError(
        "VIEWER_RENDERER_CONTRACT",
        "The notation renderer payload is not supported.",
      );
    }
    if ((await sha256(payload.content)) !== payload.sha256) {
      throw new NotationAdapterError(
        "VIEWER_RENDERER_DIGEST",
        "The notation payload failed its integrity check.",
      );
    }

    this.dispose();
    const displayPayload = normalizeInlineDynamicSymbols(payload.content);
    this.inlineSymbolNormalizationCount = displayPayload.count;
    const progressive = payload.anchors.length > 1_000;
    const osmd = new OpenSheetMusicDisplay(this.container, {
      backend: "svg",
      autoResize: true,
      drawTitle: callbacks.title !== null,
      drawSubtitle: true,
      drawComposer: true,
      drawLyricist: true,
      drawCredits: true,
      drawLyrics: true,
      drawMeasureNumbers: true,
      pageFormat: progressive ? "Endless" : "A4_P",
      newSystemFromXML: true,
      newPageFromXML: !progressive,
      followCursor: true,
      drawFromMeasureNumber: callbacks.measureRange
        ? callbacks.measureRange.fromMeasureIndex + 1
        : 1,
      drawUpToMeasureNumber: callbacks.measureRange
        ? callbacks.measureRange.toMeasureIndex + 1
        : Number.MAX_SAFE_INTEGER,
      cursorsOptions: [
        { type: CursorType.Standard, color: "#c85f2c", alpha: 0.55, follow: true },
        { type: CursorType.CurrentArea, color: "#2d6f5b", alpha: 0.12, follow: false },
      ],
    });
    this.osmd = osmd;
    this.anchorLimit = payload.anchors.length + 1;
    try {
      await osmd.load(displayPayload.content, callbacks.title ?? "");
      if (!progressive) {
        osmd.render();
        for (const cursor of osmd.cursors) {
          cursor.reset();
          cursor.show();
        }
        const totalMeasures = osmd.GraphicSheet.MeasureList.length;
        const layout = this.readLayout(true, totalMeasures, totalMeasures, false);
        callbacks.onLayout?.(layout);
        return layout;
      }
      const progress = osmd.renderNext({ systems: 4 });
      for (const cursor of osmd.cursors) {
        cursor.reset();
        cursor.show();
      }
      const initialLayout = this.readLayout(
        progress.done,
        progress.renderedMeasures,
        progress.totalMeasures,
        true,
      );
      callbacks.onLayout?.(initialLayout);
      if (!progress.done) this.scheduleNextBatch(callbacks);
      return initialLayout;
    } catch {
      this.dispose();
      throw new NotationAdapterError(
        "VIEWER_OSMD_RENDER_FAILED",
        "The notation renderer could not display this canonical score.",
      );
    }

  }

  private readLayout(
    complete: boolean,
    renderedMeasures: number,
    totalMeasures: number,
    progressive: boolean,
  ): NotationLayout {
    const osmd = this.osmd;
    if (!osmd) {
      throw new NotationAdapterError("VIEWER_OSMD_DISPOSED", "The notation renderer is unavailable.");
    }
    const systems: NotationSystem[] = [];
    for (const [pageIndex, page] of osmd.GraphicSheet.MusicPages.entries()) {
      for (const system of page.MusicSystems) {
        const measureIndexes = [
          ...new Set(
            system.GraphicalMeasures.flat()
              .map((measure) => measure?.parentSourceMeasure?.measureListIndex)
              .filter((index): index is number => Number.isInteger(index)),
          ),
        ].sort((left, right) => left - right);
        systems.push({ index: systems.length, pageIndex, measureIndexes });
      }
    }
    if (systems.length === 0 || this.container.querySelector("svg") === null) {
      this.dispose();
      throw new NotationAdapterError(
        "VIEWER_OSMD_EMPTY",
        "The notation renderer produced no visible score.",
      );
    }
    return {
      pageCount: osmd.GraphicSheet.MusicPages.length,
      systems,
      complete,
      renderedMeasures,
      totalMeasures,
      diagnostics: progressive
        ? [
            {
              code: "VIEWER_CONTINUOUS_PAGE_NORMALIZATION",
              message:
                "This large score uses a continuous reading page while it is engraved. " +
                "Canonical system breaks are retained; compare the fixture PDF for original pagination.",
            },
            ...(this.inlineSymbolNormalizationCount > 0
              ? [
                  {
                    code: "VIEWER_INLINE_DYNAMIC_SYMBOL_NORMALIZED",
                    message:
                      `${this.inlineSymbolNormalizationCount} exporter-specific inline ` +
                      "dynamic symbol token(s) were converted to standard visible letters; " +
                      "the canonical source text remains unchanged.",
                  },
                ]
              : []),
          ]
        : this.inlineSymbolNormalizationCount > 0
          ? [
              {
                code: "VIEWER_INLINE_DYNAMIC_SYMBOL_NORMALIZED",
                message:
                  `${this.inlineSymbolNormalizationCount} exporter-specific inline ` +
                  "dynamic symbol token(s) were converted to standard visible letters; " +
                  "the canonical source text remains unchanged.",
              },
            ]
          : [],
    };
  }

  private scheduleNextBatch(callbacks: NotationRenderCallbacks): void {
    this.batchTimer = globalThis.setTimeout(() => {
      this.batchTimer = null;
      const osmd = this.osmd;
      if (!osmd) return;
      try {
        const progress = osmd.renderNext({ systems: 8 });
        callbacks.onLayout?.(
          this.readLayout(
            progress.done,
            progress.renderedMeasures,
            progress.totalMeasures,
            true,
          ),
        );
        if (progress.done && this.lastHighlight) this.highlight(this.lastHighlight);
        if (!progress.done) this.scheduleNextBatch(callbacks);
      } catch {
        callbacks.onError?.(
          new NotationAdapterError(
            "VIEWER_OSMD_RENDER_FAILED",
            "The notation renderer stopped before the complete score was displayed.",
          ),
        );
      }
    }, 0);
  }

  highlight(position: HighlightPosition): boolean {
    const osmd = this.osmd;
    if (!osmd) return false;
    this.lastHighlight = position;
    const onset =
      position.onsetQuarters.numerator / position.onsetQuarters.denominator / 4;
    let matched = true;
    for (const cursor of osmd.cursors) {
      cursor.reset();
      let steps = 0;
      while (!cursor.Iterator.EndReached && steps <= this.anchorLimit) {
        const measure = cursor.Iterator.CurrentMeasureIndex;
        const current = cursor.Iterator.CurrentRelativeInMeasureTimestamp.RealValue;
        if (measure > position.measureIndex || (measure === position.measureIndex && current >= onset)) {
          break;
        }
        cursor.next();
        steps += 1;
      }
      const measure = cursor.Iterator.CurrentMeasureIndex;
      const current = cursor.Iterator.CurrentRelativeInMeasureTimestamp.RealValue;
      cursor.show();
      matched = matched && measure === position.measureIndex && Math.abs(current - onset) < 1e-9;
    }
    const cursorElement = osmd.cursor.cursorElement;
    cursorElement.scrollIntoView?.({ block: "center", inline: "nearest" });
    return matched;
  }

  dispose(): void {
    if (this.batchTimer !== null) globalThis.clearTimeout(this.batchTimer);
    this.batchTimer = null;
    this.lastHighlight = null;
    this.inlineSymbolNormalizationCount = 0;
    if (this.osmd) {
      for (const cursor of this.osmd.cursors) cursor.Dispose();
      this.osmd.clear();
    }
    this.osmd = null;
    this.container.replaceChildren();
  }
}

export function createOsmdNotationAdapter(container: HTMLElement): NotationAdapter {
  return new OsmdNotationAdapter(container);
}
