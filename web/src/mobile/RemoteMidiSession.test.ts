import { waitFor } from "@testing-library/react";

import { RemoteMidiSession } from "./RemoteMidiSession";
import { MobileCompanionSession } from "./transport";

function response(value: unknown): Response {
  return new Response(JSON.stringify(value), {
    status: 200,
    headers: { "Content-Type": "application/json" },
  });
}

test("TEST-APP-MOBILE-024 applies the acknowledged capture transition even when state polling is stale", async () => {
  const fetcher: typeof fetch = async (input, init) => {
    const url = String(input);
    if (url.endsWith("/commands") && init?.method === "POST") {
      return response({
        mobile_contract_version: "0.2.0",
        pairing_id: "pairing-one",
        sequence: 1,
        kind: "start-attempt",
        status: "completed",
        result: {
          capture: "recording",
          capture_purpose: "attempt",
          calibration_approved: true,
        },
        error: null,
      });
    }
    if (url.endsWith("/state")) {
      return response({
        mobile_contract_version: "0.2.0",
        pairing_id: "pairing-one",
        availability: "live",
        sequence: 4,
        active_notes: [],
        age_microseconds: 10,
        expires_in_seconds: 300,
        capture: "idle",
        capture_purpose: null,
        calibration_approved: true,
      });
    }
    throw new Error(`Unexpected request: ${url}`);
  };
  const remote = new RemoteMidiSession(
    new MobileCompanionSession("pairing-one", "phone-token", fetcher),
  );

  remote.startAttempt();

  await waitFor(() => expect(remote.current()).toMatchObject({
    capture: "recording",
    capture_purpose: "attempt",
    connection: "connected",
  }));
});

test("TEST-APP-MOBILE-025 exposes a rejected desktop attempt command as a blocking diagnostic", async () => {
  const fetcher: typeof fetch = async () => response({
    mobile_contract_version: "0.2.0",
    pairing_id: "pairing-one",
    sequence: 1,
    kind: "start-attempt",
    status: "failed",
    result: null,
    error: "Connect the approved calibrated input before starting an attempt.",
  });
  const remote = new RemoteMidiSession(
    new MobileCompanionSession("pairing-one", "phone-token", fetcher),
  );

  remote.startAttempt();

  await waitFor(() => expect(remote.current().diagnostics).toEqual([
    expect.objectContaining({
      code: "MOBILE_COMMAND_FAILED",
      blocking: true,
      message: "Connect the approved calibrated input before starting an attempt.",
    }),
  ]));
  expect(remote.current().capture).toBe("idle");
});
