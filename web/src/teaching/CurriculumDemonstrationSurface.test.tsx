import { fireEvent, render, screen } from "@testing-library/react";

import type { ActivePlaybackNote } from "../audio/PlaybackTransport";
import type { PlaybackPlan } from "../contracts/playback";
import type { ViewerBundle } from "../contracts/viewer";
import {
  CurriculumDemonstrationSurface,
  type CurriculumPassageGuidanceView,
  type CurriculumPassagePresentationView,
} from "./CurriculumDemonstrationSurface";

vi.mock("../playback/PlaybackSurface", () => ({
  PlaybackSurface: ({
    onFocusEventIds,
    onActiveNotes,
  }: {
    onFocusEventIds: (ids: string[]) => void;
    onActiveNotes: (notes: ActivePlaybackNote[]) => void;
  }) => (
    <button
      type="button"
      onClick={() => {
        onFocusEventIds(["event:upper"]);
        onActiveNotes([{
          noteId: "note:upper",
          midiPitch: 72,
          contributions: [{
            eventId: "event:upper",
            clefGroupId: "clef:treble",
            clef: { sign: "G", line: 2, octave_change: null },
            staff: "1",
            voice: "1",
          }],
        }]);
      }}
    >
      Emit active layer
    </button>
  ),
}));
vi.mock("../notation/NotationSurface", () => ({
  NotationSurface: ({
    allowedEventIds,
    focusEventIds,
    layerEmphasis,
  }: {
    allowedEventIds: string[];
    focusEventIds: string[];
    layerEmphasis: {
      activeTargets: Array<{ canonical_id: string }>;
      inactiveTargets: Array<{ canonical_id: string }>;
    };
  }) => (
    <div data-testid="curriculum-notation">
      visible {allowedEventIds.join(",")} · active {layerEmphasis.activeTargets.map(
        (item) => item.canonical_id,
      ).join(",")} · context {layerEmphasis.inactiveTargets.map(
        (item) => item.canonical_id,
      ).join(",")} · focus {focusEventIds.join(",")}
    </div>
  ),
}));
vi.mock("../piano/VirtualPiano", () => ({
  VirtualPiano: ({ activeNotes }: { activeNotes: ActivePlaybackNote[] }) => (
    <div data-testid="curriculum-piano">
      {activeNotes.map((note) => `${note.midiPitch}:${note.contributions[0]?.eventId}`).join(",")}
    </div>
  ),
}));

const target = (canonicalId: string, rendererAnchor: string) => ({
  canonical_id: canonicalId,
  canonical_kind: "event" as const,
  renderer_anchor: rendererAnchor,
});

const presentation: CurriculumPassagePresentationView = {
  id: "curriculum-passage-presentation:one",
  semantic_fingerprint: "b".repeat(64),
  analysis_id: "analysis:one",
  package_id: "package:one",
  score_id: "score:one",
  practice_scope_ref: {
    type: "practice-scope-assignment",
    id: "practice-scope-assignment:one",
    semantic_fingerprint: "c".repeat(64),
  },
  notation_condition: "upper-layer",
  visible_event_ids: ["event:upper", "event:lower"],
  active_target_ids: ["event:upper"],
  inactive_context_ids: ["event:lower"],
  active_renderer_targets: [target("event:upper", "part[0]/measure[0]/event[0]")],
  inactive_renderer_targets: [target("event:lower", "part[0]/measure[0]/event[1]")],
  visible_omitted_renderer_targets: [],
  notation_renderer_sha256: "a".repeat(64),
};

const guidance: CurriculumPassageGuidanceView = {
  id: "curriculum-passage-guidance:one",
  semantic_fingerprint: "d".repeat(64),
  analysis_id: "analysis:one",
  package_id: "package:one",
  score_id: "score:one",
  presentation_ref: {
    type: "curriculum-passage-presentation",
    id: presentation.id,
    semantic_fingerprint: presentation.semantic_fingerprint,
  },
  practice_scope_ref: presentation.practice_scope_ref,
  notation_condition: "upper-layer",
  items: [{
    id: "curriculum-guidance-item:one",
    requirement_ref: {
      type: "passage-skill-requirement",
      id: "passage-requirement:one",
      semantic_fingerprint: "e".repeat(64),
    },
    primitive_ref: {
      type: "learning-primitive",
      id: "PRIM-READ-001",
      semantic_fingerprint: "f".repeat(64),
    },
    primitive_family: "score-literacy",
    heading: "Score literacy focus",
    explanation: "Connect the highlighted score event to its key.",
    action_prompt: "Follow the highlighted symbol, then play it.",
    reconnect_prompt: "Return to the surrounding visible score.",
    focus_event_ids: ["event:upper"],
    canonical_evidence_refs: ["event:upper"],
    analysis_evidence_refs: [],
  }],
};

const notation = {
  contract_id: "org.teachmemusic.viewer-bundle",
  contract_version: "0.2.0",
  capabilities: ["notation"],
  package_id: "package:one",
  score_id: "score:one",
  canonical_schema_id: "org.teachmemusic.canonical-music-package",
  canonical_schema_version: "2.0.0",
  title: "Layer study",
  renderer: {
    renderer: "opensheetmusicdisplay",
    media_type: "application/vnd.recordare.musicxml+xml",
    encoding: "utf-8",
    content: "<score-partwise/>",
    sha256: "a".repeat(64),
    anchors: [],
    represented_features: [],
  },
  diagnostics: [],
} as ViewerBundle;

const playback: PlaybackPlan = {
  contract_id: "org.teachmemusic.playback-plan",
  contract_version: "0.2.0",
  package_id: "package:one",
  score_id: "score:one",
  canonical_schema_id: "org.teachmemusic.canonical-music-package",
  canonical_schema_version: "2.0.0",
  duration_microseconds: 1_000_000,
  navigation_section_starts: [0],
  notes: [{
    id: "note:upper",
    start_microseconds: 0,
    end_microseconds: 1_000_000,
    midi_pitch: 72,
    chord_id: null,
    dynamic_percent: null,
    source_events: [{
      event_id: "event:upper",
      part_id: "part:one",
      measure_id: "measure:one",
      staff: "1",
      voice: "1",
      score_onset: { numerator: 0, denominator: 1 },
      clef_group_id: "clef:treble",
      clef: { sign: "G", line: 2, octave_change: null },
    }],
  }],
  tempo_controls: [],
  grace_realizations: [],
  measure_visits: [],
  diagnostics: [],
};

test("TEST-APP-TEACHING-014 synchronizes active notation, sound, and piano keys", () => {
  render(
    <CurriculumDemonstrationSurface
      presentation={presentation}
      guidance={guidance}
      notation={notation}
      playback={playback}
    />,
  );

  expect(screen.getByTestId("curriculum-notation")).toHaveTextContent(
    "visible event:upper,event:lower",
  );
  expect(screen.getByTestId("curriculum-notation")).toHaveTextContent(
    "active event:upper · context event:lower",
  );
  expect(screen.getByTestId("curriculum-piano")).toBeEmptyDOMElement();

  fireEvent.click(screen.getByRole("button", { name: "Emit active layer" }));

  expect(screen.getByTestId("curriculum-notation")).toHaveTextContent("focus event:upper");
  expect(screen.getByTestId("curriculum-piano")).toHaveTextContent("72:event:upper");
});

test("TEST-APP-TEACHING-015 rejects inactive events in sound and expected keys", () => {
  const leaked: PlaybackPlan = {
    ...playback,
    notes: [{
      ...playback.notes[0]!,
      source_events: [{
        ...playback.notes[0]!.source_events[0]!,
        event_id: "event:lower",
      }],
    }],
  };

  render(
    <CurriculumDemonstrationSurface
      presentation={presentation}
      guidance={guidance}
      notation={notation}
      playback={leaked}
    />,
  );

  expect(screen.getByRole("alert")).toHaveTextContent(
    "Expected sound or piano guidance contains inactive notation.",
  );
  expect(screen.queryByTestId("curriculum-notation")).not.toBeInTheDocument();
  expect(screen.queryByTestId("curriculum-piano")).not.toBeInTheDocument();
});

test("TEST-APP-TEACHING-016 shows actionable guidance and focuses exact active evidence", () => {
  render(
    <CurriculumDemonstrationSurface
      presentation={presentation}
      guidance={guidance}
      notation={notation}
      playback={playback}
    />,
  );

  expect(screen.getByRole("heading", { name: "What to notice and do" })).toBeVisible();
  expect(screen.getByText("Connect the highlighted score event to its key.")).toBeVisible();
  expect(screen.getByText(/Follow the highlighted symbol, then play it/)).toBeVisible();

  fireEvent.click(screen.getByRole("button", { name: "Show this target in the score" }));

  expect(screen.getByTestId("curriculum-notation")).toHaveTextContent("focus event:upper");
  expect(screen.getByTestId("curriculum-notation")).toHaveTextContent("context event:lower");
});

test("TEST-APP-TEACHING-017 rejects guidance that targets inactive material", () => {
  const leakedGuidance: CurriculumPassageGuidanceView = {
    ...guidance,
    items: [{
      ...guidance.items[0]!,
      focus_event_ids: ["event:lower"],
    }],
  };

  render(
    <CurriculumDemonstrationSurface
      presentation={presentation}
      guidance={leakedGuidance}
      notation={notation}
      playback={playback}
    />,
  );

  expect(screen.getByRole("alert")).toHaveTextContent(
    "The learner guidance does not belong to this exact active layer.",
  );
  expect(screen.getByRole("alert")).toHaveTextContent("TMM_PRESENTATION_GUIDANCE_MISMATCH");
  expect(screen.queryByTestId("curriculum-notation")).not.toBeInTheDocument();
});
