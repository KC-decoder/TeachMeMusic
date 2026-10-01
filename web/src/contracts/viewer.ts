export type ViewerDiagnosticSeverity = "info" | "warning" | "error";

export interface ViewerDiagnostic {
  code: string;
  severity: ViewerDiagnosticSeverity;
  message: string;
  canonical_ids: string[];
}

export interface RenderAnchor {
  canonical_id: string;
  canonical_kind: string;
  renderer_anchor: string;
  renderer_part_id: string | null;
  part_index: number | null;
  measure_index: number | null;
  event_index: number | null;
  measure_onset_quarters: string | null;
}

export interface RendererPayload {
  renderer: "opensheetmusicdisplay";
  media_type: "application/vnd.recordare.musicxml+xml";
  encoding: "utf-8";
  content: string;
  sha256: string;
  anchors: RenderAnchor[];
  represented_features: string[];
}

export interface ViewerBundle {
  contract_id: "org.teachmemusic.viewer-bundle";
  contract_version: "0.2.0";
  capabilities: string[];
  package_id: string;
  score_id: string;
  canonical_schema_id: string;
  canonical_schema_version: string;
  title: string | null;
  renderer: RendererPayload;
  diagnostics: ViewerDiagnostic[];
}
