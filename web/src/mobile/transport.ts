import type { AppConfig, Diagnostic } from "../api";
import type { MidiSnapshot } from "../midi/contracts";

export interface MobilePairingOffer {
  app_contract_version: string;
  pairing_id: string;
  phone_capability: string;
  bridge_capability: string;
  expires_in_seconds: number;
  companion_origin: string;
  pairing_url: string;
}

export interface MobilePairingStatus {
  app_contract_version: string;
  pairing_id: string;
  phone_claimed: boolean;
  bridge_claimed: boolean;
  revoked: boolean;
  last_sequence: number;
  availability: "live" | "stale" | "disconnected" | "unavailable";
  expires_in_seconds: number;
}

export interface MobileCompanionState {
  mobile_contract_version: "0.2.0";
  pairing_id: string;
  availability: "live" | "stale" | "disconnected" | "unavailable";
  sequence: number;
  active_notes: number[];
  age_microseconds: number | null;
  expires_in_seconds: number;
  capture: MidiSnapshot["capture"];
  capture_purpose: MidiSnapshot["capture_purpose"];
  calibration_approved: boolean;
}

export type MobileCommandKind =
  | "start-attempt"
  | "pause-attempt"
  | "resume-attempt"
  | "finish-attempt"
  | "abort-attempt"
  | "safe-stop"
  | "submit-attempt";

export interface MobileAttemptContext {
  run_id: string;
  score_id: string;
  plan_id: string;
  exercise_id: string;
  practice_mode: string;
  support_state_id: string;
  tempo_bpm: number;
  count_in_enabled: boolean;
}

export interface MobileCommand {
  mobile_contract_version: "0.2.0";
  pairing_id: string;
  sequence: number;
  kind: MobileCommandKind;
  status: "pending" | "processing" | "completed" | "failed";
  context?: MobileAttemptContext;
  result: unknown | null;
  error: string | null;
}

type Fetch = typeof fetch;

function diagnostic(data: unknown): Diagnostic {
  if (typeof data === "object" && data !== null && "diagnostics" in data) {
    const items = (data as { diagnostics?: unknown }).diagnostics;
    if (Array.isArray(items) && items.length > 0) {
      const first = items[0] as Partial<Diagnostic>;
      if (typeof first.code === "string" && typeof first.message === "string") {
        return {
          code: first.code,
          stage: typeof first.stage === "string" ? first.stage : "mobile-bridge",
          message: first.message,
        };
      }
    }
  }
  return {
    code: "MOBILE_REQUEST_FAILED",
    stage: "mobile-bridge",
    message: "The secure companion request failed.",
  };
}

async function checked<T>(response: Response): Promise<T> {
  const data = response.status === 204 ? null : await response.json();
  if (!response.ok) {
    const failure = diagnostic(data);
    throw new Error(`${failure.code}: ${failure.message}`);
  }
  return data as T;
}

function ownerHeaders(config: AppConfig): Record<string, string> {
  return {
    "Content-Type": "application/json",
    "X-TeachMeMusic-Token": config.launch_token,
  };
}

export async function createMobilePairing(
  config: AppConfig,
  ttlSeconds: number,
  fetcher: Fetch = fetch,
): Promise<MobilePairingOffer> {
  return checked<MobilePairingOffer>(
    await fetcher("/api/v1/mobile-pairings", {
      method: "POST",
      headers: ownerHeaders(config),
      body: JSON.stringify({ ttl_seconds: ttlSeconds }),
    }),
  );
}

export async function claimDesktopBridge(
  config: AppConfig,
  pairingId: string,
  capability: string,
  fetcher: Fetch = fetch,
): Promise<string> {
  const result = await checked<{ bridge_token: string }>(
    await fetcher(
      `/api/v1/mobile-pairings/${encodeURIComponent(pairingId)}/bridge-claims`,
      {
        method: "POST",
        headers: ownerHeaders(config),
        body: JSON.stringify({ capability }),
      },
    ),
  );
  return result.bridge_token;
}

export async function inspectMobilePairing(
  config: AppConfig,
  pairingId: string,
  fetcher: Fetch = fetch,
): Promise<MobilePairingStatus> {
  return checked<MobilePairingStatus>(
    await fetcher(`/api/v1/mobile-pairings/${encodeURIComponent(pairingId)}`, {
      headers: { "X-TeachMeMusic-Token": config.launch_token },
    }),
  );
}

export async function revokeMobilePairing(
  config: AppConfig,
  pairingId: string,
  fetcher: Fetch = fetch,
): Promise<void> {
  await checked<null>(
    await fetcher(`/api/v1/mobile-pairings/${encodeURIComponent(pairingId)}`, {
      method: "DELETE",
      headers: { "X-TeachMeMusic-Token": config.launch_token },
    }),
  );
}

export class DesktopMidiBridge {
  private sequence = 0;
  private readonly fetcher: Fetch;

  constructor(
    private readonly pairingId: string,
    private readonly bridgeToken: string,
    fetcher: Fetch = fetch,
  ) {
    // WebKit and Chromium may reject a native Window.fetch invoked with this
    // class instance as its receiver ("Illegal invocation").  Bind the
    // injected transport to the browser global before retaining it as a
    // method-like field.
    this.fetcher = fetcher.bind(globalThis);
  }

  async publish(
    snapshot: Pick<MidiSnapshot, "connection" | "active_notes"> &
      Partial<Pick<MidiSnapshot, "capture" | "capture_purpose" | "calibration">>,
  ): Promise<void> {
    const connected = snapshot.connection === "connected";
    const activeNotes = connected
      ? [...new Set(snapshot.active_notes)]
          .filter((note) => Number.isInteger(note) && note >= 0 && note <= 127)
          .sort((left, right) => left - right)
          .slice(0, 16)
      : [];
    const nextSequence = this.sequence + 1;
    await checked<null>(
      await this.fetcher(
        `/api/v1/mobile-pairings/${encodeURIComponent(this.pairingId)}/bridge-messages`,
        {
          method: "POST",
          headers: {
            "Authorization": `Bearer ${this.bridgeToken}`,
            "Content-Type": "application/json",
          },
          body: JSON.stringify({
            contract_version: "0.2.0",
            kind: "midi-state",
            sequence: nextSequence,
            sent_at_microseconds: Math.round(performance.now() * 1000),
            connection: connected ? "connected" : "disconnected",
            active_notes: activeNotes,
            capture: snapshot.capture ?? "idle",
            capture_purpose: snapshot.capture_purpose ?? null,
            calibration_approved: snapshot.calibration?.approved === true,
          }),
        },
      ),
    );
    this.sequence = nextSequence;
  }

  async readCommand(): Promise<MobileCommand | null> {
    const response = await this.fetcher(
      `/api/v1/mobile-pairings/${encodeURIComponent(this.pairingId)}/bridge-command`,
      { headers: { Authorization: `Bearer ${this.bridgeToken}` } },
    );
    if (response.status === 204) return null;
    return checked<MobileCommand>(response);
  }

  async acknowledge(
    sequence: number,
    outcome: { result: unknown } | { error: string },
  ): Promise<void> {
    await checked<MobileCommand>(
      await this.fetcher(
        `/api/v1/mobile-pairings/${encodeURIComponent(this.pairingId)}` +
          "/bridge-command-acks",
        {
          method: "POST",
          headers: {
            Authorization: `Bearer ${this.bridgeToken}`,
            "Content-Type": "application/json",
          },
          body: JSON.stringify({
            mobile_contract_version: "0.2.0",
            sequence,
            ...("result" in outcome ? { result: outcome.result } : { error: outcome.error }),
          }),
        },
      ),
    );
  }
}

export async function claimPhonePairing(
  pairingId: string,
  capability: string,
  fetcher: Fetch = fetch,
): Promise<string> {
  const result = await checked<{ phone_token: string }>(
    await fetcher(
      `/api/v1/mobile/pairings/${encodeURIComponent(pairingId)}/phone-claims`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ capability }),
      },
    ),
  );
  return result.phone_token;
}

export class MobileCompanionSession {
  private readonly fetcher: Fetch;

  constructor(
    private readonly pairingId: string,
    private readonly phoneToken: string,
    fetcher: Fetch = fetch,
  ) {
    this.fetcher = fetcher.bind(globalThis);
  }

  async read(): Promise<MobileCompanionState> {
    return checked<MobileCompanionState>(
      await this.fetcher(
        `/api/v1/mobile/pairings/${encodeURIComponent(this.pairingId)}/state`,
        { headers: { "Authorization": `Bearer ${this.phoneToken}` } },
      ),
    );
  }

  authorityHeaders(): Record<string, string> {
    return {
      Authorization: `Bearer ${this.phoneToken}`,
      "X-TeachMeMusic-Mobile-Pairing": this.pairingId,
    };
  }

  async requestCommand(
    kind: MobileCommandKind,
    context?: MobileAttemptContext,
  ): Promise<MobileCommand> {
    return checked<MobileCommand>(
      await this.fetcher(
        `/api/v1/mobile/pairings/${encodeURIComponent(this.pairingId)}/commands`,
        {
          method: "POST",
          headers: {
            Authorization: `Bearer ${this.phoneToken}`,
            "Content-Type": "application/json",
          },
          body: JSON.stringify({
            mobile_contract_version: "0.2.0",
            kind,
            ...(context ? { context } : {}),
          }),
        },
      ),
    );
  }

  async commandStatus(sequence: number): Promise<MobileCommand> {
    return checked<MobileCommand>(
      await this.fetcher(
        `/api/v1/mobile/pairings/${encodeURIComponent(this.pairingId)}` +
          `/commands/${sequence}`,
        { headers: { Authorization: `Bearer ${this.phoneToken}` } },
      ),
    );
  }

  async requestAndWait(
    kind: MobileCommandKind,
    context?: MobileAttemptContext,
    options: { attempts?: number; intervalMilliseconds?: number } = {},
  ): Promise<MobileCommand> {
    let command = await this.requestCommand(kind, context);
    const attempts = options.attempts ?? 60;
    const interval = options.intervalMilliseconds ?? 100;
    for (let index = 0; index < attempts; index += 1) {
      if (command.status === "completed" || command.status === "failed") return command;
      await new Promise((resolve) => setTimeout(resolve, interval));
      command = await this.commandStatus(command.sequence);
    }
    throw new Error("MOBILE_COMMAND_TIMEOUT: The desktop did not complete the phone command.");
  }
}
