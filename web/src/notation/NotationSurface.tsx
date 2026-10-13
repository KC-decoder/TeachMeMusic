import { useEffect, useMemo, useRef, useState } from "react";

import type { ViewerBundle } from "../contracts/viewer";
import {
  NotationAdapter,
  NotationAdapterError,
  NotationLayout,
  createOsmdNotationAdapter,
} from "./OsmdNotationAdapter";
import { HighlightPosition, buildHighlightPositions } from "./navigation";
import {
  NotationLayerEmphasis,
  NotationLayerEmphasisError,
  resolveNotationLayerEmphasis,
} from "./layerEmphasis";

type AdapterFactory = (container: HTMLElement) => NotationAdapter;

interface NotationSurfaceProps {
  bundle: ViewerBundle;
  focusEventIds?: readonly string[];
  allowedEventIds?: readonly string[];
  layerEmphasis?: NotationLayerEmphasis;
  adapterFactory?: AdapterFactory;
}

interface SurfaceError {
  code: string;
  message: string;
}

function firstPositionInSystem(
  positions: HighlightPosition[],
  layout: NotationLayout,
  systemIndex: number,
): number {
  const measures = new Set(layout.systems[systemIndex]?.measureIndexes ?? []);
  const index = positions.findIndex((position) => measures.has(position.measureIndex));
  return index < 0 ? 0 : index;
}

export function NotationSurface({
  bundle,
  focusEventIds = [],
  allowedEventIds,
  layerEmphasis,
  adapterFactory = createOsmdNotationAdapter,
}: NotationSurfaceProps) {
  const container = useRef<HTMLDivElement | null>(null);
  const adapter = useRef<NotationAdapter | null>(null);
  const positions = useMemo(() => {
    const allowed = allowedEventIds ? new Set(allowedEventIds) : null;
    return buildHighlightPositions(
      allowed
        ? bundle.renderer.anchors.filter(
            (anchor) => anchor.canonical_kind !== "event" || allowed.has(anchor.canonical_id),
          )
        : bundle.renderer.anchors,
    );
  }, [allowedEventIds, bundle.renderer.anchors]);
  const resolvedLayerEmphasis = useMemo(() => {
    if (!layerEmphasis) return { value: null, error: null };
    try {
      return {
        value: resolveNotationLayerEmphasis(
          bundle.renderer.anchors,
          layerEmphasis,
          allowedEventIds,
        ),
        error: null,
      };
    } catch (reason: unknown) {
      const error =
        reason instanceof NotationLayerEmphasisError
          ? reason
          : new NotationLayerEmphasisError(
              "TMM_PRESENTATION_LAYER_INVALID",
              "The active notation layer could not be verified.",
            );
      return { value: null, error };
    }
  }, [allowedEventIds, bundle.renderer.anchors, layerEmphasis]);
  const [layout, setLayout] = useState<NotationLayout | null>(null);
  const [positionIndex, setPositionIndex] = useState(0);
  const [rendering, setRendering] = useState(true);
  const [error, setError] = useState<SurfaceError | null>(null);
  const [highlightWarning, setHighlightWarning] = useState(false);
  const [layerWarning, setLayerWarning] = useState(false);

  useEffect(() => {
    const target = container.current;
    if (!target) return;
    if (resolvedLayerEmphasis.error) {
      setLayout(null);
      setRendering(false);
      setError({
        code: resolvedLayerEmphasis.error.code,
        message: resolvedLayerEmphasis.error.message,
      });
      return;
    }
    let cancelled = false;
    const nextAdapter = adapterFactory(target);
    adapter.current = nextAdapter;
    setRendering(true);
    setError(null);
    setHighlightWarning(false);
    setLayerWarning(false);
    setPositionIndex(0);
    void nextAdapter
      .load(bundle.renderer, {
        title: bundle.title,
        measureRange:
          allowedEventIds && positions.length > 0
            ? {
                fromMeasureIndex: Math.min(...positions.map((item) => item.measureIndex)),
                toMeasureIndex: Math.max(...positions.map((item) => item.measureIndex)),
              }
            : undefined,
        onLayout: (nextLayout) => {
          if (!cancelled) setLayout(nextLayout);
        },
        onError: (nextError) => {
          if (!cancelled) {
            setError({ code: nextError.code, message: nextError.message });
          }
        },
      })
      .then((nextLayout) => {
        if (cancelled) return;
        if (positions.length === 0) {
          throw new NotationAdapterError(
            "VIEWER_ANCHOR_UNAVAILABLE",
            "This score has no canonical event positions to highlight.",
          );
        }
        setLayout(nextLayout);
        if (resolvedLayerEmphasis.value) {
          setLayerWarning(
            !nextAdapter.emphasizeLayers(
              positions,
              resolvedLayerEmphasis.value.activeEventIds,
              resolvedLayerEmphasis.value.inactiveEventIds,
            ),
          );
        }
        setHighlightWarning(!nextAdapter.highlight([positions[0]]));
        setRendering(false);
      })
      .catch((reason: unknown) => {
        if (cancelled) return;
        const surfaceError =
          reason instanceof NotationAdapterError
            ? reason
            : new NotationAdapterError(
                "VIEWER_OSMD_RENDER_FAILED",
                "The notation renderer could not display this canonical score.",
              );
        setError({ code: surfaceError.code, message: surfaceError.message });
        setRendering(false);
      });
    return () => {
      cancelled = true;
      nextAdapter.dispose();
      if (adapter.current === nextAdapter) adapter.current = null;
    };
  }, [adapterFactory, bundle.renderer, positions, resolvedLayerEmphasis]);

  useEffect(() => {
    if (rendering || focusEventIds.length === 0 || !adapter.current) return;
    const requested = new Set(focusEventIds);
    const focusedPositions = positions.filter((position) =>
      position.canonicalIds.some((id) => requested.has(id)),
    );
    if (focusedPositions.length === 0) return;
    const position = focusedPositions.at(-1);
    if (!position) return;
    const nextIndex = positions.indexOf(position);
    setPositionIndex(nextIndex);
    setHighlightWarning(!adapter.current.highlight(focusedPositions, focusEventIds));
  }, [focusEventIds, positions, rendering]);

  const current = positions[positionIndex] ?? null;
  const systemIndex =
    current && layout
      ? Math.max(
          0,
          layout.systems.findIndex((system) =>
            system.measureIndexes.includes(current.measureIndex),
          ),
        )
      : 0;
  const pageIndex = layout?.systems[systemIndex]?.pageIndex ?? 0;

  function showPosition(nextIndex: number) {
    const position = positions[nextIndex];
    if (!position || !adapter.current) return;
    setPositionIndex(nextIndex);
    setHighlightWarning(!adapter.current.highlight([position]));
  }

  function showSystem(nextSystem: number) {
    if (!layout || nextSystem < 0 || nextSystem >= layout.systems.length) return;
    showPosition(firstPositionInSystem(positions, layout, nextSystem));
  }

  function showPage(nextPage: number) {
    if (!layout || nextPage < 0 || nextPage >= layout.pageCount) return;
    const nextSystem = layout.systems.findIndex((system) => system.pageIndex === nextPage);
    if (nextSystem >= 0) showSystem(nextSystem);
  }

  return (
    <section
      className="notation-panel"
      aria-labelledby="notation-title"
      data-render-complete={layout?.complete ?? false}
      data-layer-emphasis={resolvedLayerEmphasis.value ? "verified" : "none"}
    >
      <div className="notation-heading">
        <div>
          <p className="eyebrow">CANONICAL NOTATION</p>
          <h2 id="notation-title">{bundle.title ?? "Untitled score"}</h2>
        </div>
        {layout && current && (
          <p className="notation-location" aria-live="polite">
            Measure {current.measureIndex + 1} · offset {current.onsetLabel} quarters
          </p>
        )}
      </div>

      {rendering && <p className="notation-status">Engraving the canonical score…</p>}
      {!rendering && layout && !layout.complete && !error && (
        <p className="notation-status" role="status">
          Showing {layout.renderedMeasures} of {layout.totalMeasures} measures while the rest
          of the score is engraved…
        </p>
      )}
      {error && (
        <div className="notation-error" role="alert">
          <strong>Notation could not be displayed.</strong>
          <p>{error.message}</p>
          <code>{error.code}</code>
        </div>
      )}

      {resolvedLayerEmphasis.value && !error && (
        <div className="notation-layer-legend" aria-label="Notation layer emphasis">
          <strong>{resolvedLayerEmphasis.value.label}</strong>
          <span><i data-layer-swatch="active" />Active material ({resolvedLayerEmphasis.value.activeEventIds.length})</span>
          {resolvedLayerEmphasis.value.inactiveEventIds.length > 0 && (
            <span><i data-layer-swatch="inactive" />Visible context ({resolvedLayerEmphasis.value.inactiveEventIds.length})</span>
          )}
        </div>
      )}

      {layout && current && !error && (
        <>
          <nav className="notation-navigation" aria-label="Score navigation">
            <div className="navigation-group" aria-label="Page navigation">
              <button type="button" onClick={() => showPage(pageIndex - 1)} disabled={pageIndex === 0}>
                Previous page
              </button>
              <span>Page {pageIndex + 1} of {layout.pageCount}</span>
              <button
                type="button"
                onClick={() => showPage(pageIndex + 1)}
                disabled={pageIndex + 1 >= layout.pageCount}
              >
                Next page
              </button>
            </div>
            <div className="navigation-group" aria-label="System navigation">
              <button type="button" onClick={() => showSystem(systemIndex - 1)} disabled={systemIndex === 0}>
                Previous system
              </button>
              <span>System {systemIndex + 1} of {layout.systems.length}</span>
              <button
                type="button"
                onClick={() => showSystem(systemIndex + 1)}
                disabled={systemIndex + 1 >= layout.systems.length}
              >
                Next system
              </button>
            </div>
            <div className="navigation-group" aria-label="Event navigation">
              <button type="button" onClick={() => showPosition(positionIndex - 1)} disabled={positionIndex === 0}>
                Previous event
              </button>
              <span>Position {positionIndex + 1} of {positions.length}</span>
              <button
                type="button"
                onClick={() => showPosition(positionIndex + 1)}
                disabled={positionIndex + 1 >= positions.length}
              >
                Next event
              </button>
            </div>
          </nav>
          <details className="trace-details">
            <summary>{current.canonicalIds.length} canonical event {current.canonicalIds.length === 1 ? "ID" : "IDs"}</summary>
            <ul>{current.canonicalIds.map((id) => <li key={id}><code>{id}</code></li>)}</ul>
          </details>
        </>
      )}

      {highlightWarning && (
        <p className="renderer-warning" role="status">
          <strong>VIEWER_CURSOR_POSITION_UNAVAILABLE:</strong> the canonical position is identified,
          but OSMD could not place its visual cursor exactly there.
        </p>
      )}

      {layerWarning && (
        <p className="renderer-warning" role="status">
          <strong>TMM_PRESENTATION_LAYER_RENDER_UNAVAILABLE:</strong> the active and context
          identities are verified, but the renderer could not style every target exactly.
        </p>
      )}

      {layout?.diagnostics.map((diagnostic) => (
        <p className="renderer-warning" role="status" key={diagnostic.code}>
          <strong>{diagnostic.code}:</strong> {diagnostic.message}
        </p>
      ))}

      {bundle.diagnostics
        .filter((diagnostic) => diagnostic.severity === "warning")
        .map((diagnostic, index) => (
          <p className="renderer-warning" role="status" key={`${diagnostic.code}-${index}`}>
            <strong>{diagnostic.code}:</strong> {diagnostic.message}
          </p>
        ))}

      {bundle.diagnostics.length > 0 && (
        <details className="renderer-diagnostics">
          <summary>Renderer notes ({bundle.diagnostics.length})</summary>
          <ul>
            {bundle.diagnostics.map((diagnostic, index) => (
              <li key={`${diagnostic.code}-${index}`} data-severity={diagnostic.severity}>
                <code>{diagnostic.code}</code> — {diagnostic.message}
              </li>
            ))}
          </ul>
        </details>
      )}

      <div
        ref={container}
        className="notation-canvas"
        role="img"
        aria-label={`Rendered notation for ${bundle.title ?? "untitled score"}`}
      />
    </section>
  );
}
