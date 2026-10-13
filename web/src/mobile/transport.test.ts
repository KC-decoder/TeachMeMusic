import { DesktopMidiBridge, MobileCompanionSession, claimPhonePairing } from "./transport";

test("TEST-APP-MOBILE-009 desktop bridge emits only ordered sanitized live state", async () => {
  const requests: Array<{ input: RequestInfo | URL; init?: RequestInit }> = [];
  const responses = [
    new Response(JSON.stringify({ diagnostics: [{ code: "RETRY", message: "retry" }] }), {
      status: 409,
      headers: { "Content-Type": "application/json" },
    }),
    new Response(null, { status: 204 }),
    new Response(null, { status: 204 }),
  ];
  const fetcher: typeof fetch = async (input, init) => {
    requests.push({ input, init });
    return responses.shift()!;
  };
  const bridge = new DesktopMidiBridge("pairing one", "bridge-token", fetcher);

  await expect(bridge.publish({ connection: "connected", active_notes: [64, 60, 64] }))
    .rejects.toThrow("RETRY");
  await bridge.publish({ connection: "connected", active_notes: [64, 60, 64] });
  await bridge.publish({ connection: "disconnected", active_notes: [67] });

  const firstRetry = JSON.parse(String(requests[0]?.init?.body));
  const accepted = JSON.parse(String(requests[1]?.init?.body));
  const disconnected = JSON.parse(String(requests[2]?.init?.body));
  expect(firstRetry.sequence).toBe(1);
  expect(accepted).toMatchObject({
    sequence: 1,
    connection: "connected",
    active_notes: [60, 64],
  });
  expect(disconnected).toMatchObject({
    sequence: 2,
    connection: "disconnected",
    active_notes: [],
  });
  expect(JSON.stringify(accepted)).not.toContain("raw_messages");
  expect(requests[1]?.input).toBe(
    "/api/v1/mobile-pairings/pairing%20one/bridge-messages",
  );
});

test("TEST-APP-MOBILE-010 phone claim and polling retain role token only in memory", async () => {
  const requests: Array<{ input: RequestInfo | URL; init?: RequestInit }> = [];
  const fetcher: typeof fetch = async (input, init) => {
    requests.push({ input, init });
    if (String(input).endsWith("phone-claims")) {
      return new Response(JSON.stringify({ phone_token: "phone-token" }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      });
    }
    return new Response(JSON.stringify({
      mobile_contract_version: "0.2.0",
      pairing_id: "pairing-one",
      availability: "stale",
      sequence: 4,
      active_notes: [],
      age_microseconds: 3_000_000,
      expires_in_seconds: 20,
      capture: "idle",
      capture_purpose: null,
      calibration_approved: false,
    }), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    });
  };

  const token = await claimPhonePairing("pairing-one", "phone-capability", fetcher);
  const state = await new MobileCompanionSession("pairing-one", token, fetcher).read();
  expect(token).toBe("phone-token");
  expect(state).toMatchObject({ availability: "stale", active_notes: [] });
  expect(requests[1]?.init?.headers).toEqual({ Authorization: "Bearer phone-token" });
  expect(localStorage.length).toBe(0);
});

test("TEST-APP-MOBILE-014 commands retain context and await authoritative desktop results", async () => {
  const requests: Array<{ input: RequestInfo | URL; init?: RequestInit }> = [];
  const responses = [
    {
      mobile_contract_version: "0.2.0",
      pairing_id: "pairing-one",
      sequence: 1,
      kind: "submit-attempt",
      status: "pending",
      result: null,
      error: null,
    },
    {
      mobile_contract_version: "0.2.0",
      pairing_id: "pairing-one",
      sequence: 1,
      kind: "submit-attempt",
      status: "completed",
      result: { attempt_id: "attempt:one", decision: { action: "repeat" } },
      error: null,
    },
  ];
  const fetcher: typeof fetch = async (input, init) => {
    requests.push({ input, init });
    return new Response(JSON.stringify(responses.shift()), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    });
  };
  const session = new MobileCompanionSession("pairing-one", "phone-token", fetcher);
  const completed = await session.requestAndWait("submit-attempt", {
    run_id: "run:one",
    score_id: "score:one",
    plan_id: "plan:one",
    exercise_id: "exercise:one",
    practice_mode: "follow-pitch",
    support_state_id: "support:one",
    tempo_bpm: 60,
    count_in_enabled: true,
  }, { attempts: 2, intervalMilliseconds: 0 });

  expect(completed.status).toBe("completed");
  const submitted = JSON.parse(String(requests[0]?.init?.body));
  expect(submitted).toMatchObject({
    mobile_contract_version: "0.2.0",
    kind: "submit-attempt",
    context: { run_id: "run:one", exercise_id: "exercise:one" },
  });
  expect(requests[1]?.input).toBe(
    "/api/v1/mobile/pairings/pairing-one/commands/1",
  );
});

test("TEST-APP-MOBILE-015 desktop reads and acknowledges one relayed command", async () => {
  const requests: Array<{ input: RequestInfo | URL; init?: RequestInit }> = [];
  const command = {
    mobile_contract_version: "0.2.0",
    pairing_id: "pairing-one",
    sequence: 3,
    kind: "finish-attempt",
    status: "processing",
    context: {},
    result: null,
    error: null,
  };
  const fetcher: typeof fetch = async (input, init) => {
    requests.push({ input, init });
    return new Response(JSON.stringify(command), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    });
  };
  const bridge = new DesktopMidiBridge("pairing-one", "bridge-token", fetcher);
  expect(await bridge.readCommand()).toMatchObject({ sequence: 3, kind: "finish-attempt" });
  await bridge.acknowledge(3, { result: { capture: "stopped" } });
  expect(JSON.parse(String(requests[1]?.init?.body))).toEqual({
    mobile_contract_version: "0.2.0",
    sequence: 3,
    result: { capture: "stopped" },
  });
});

test("TEST-APP-MOBILE-019 retained browser transports preserve the global fetch receiver", async () => {
  const receivers: unknown[] = [];
  const fetcher = function (this: unknown, input: RequestInfo | URL): Promise<Response> {
    receivers.push(this);
    if (String(input).endsWith("/state")) {
      return Promise.resolve(new Response(JSON.stringify({
        mobile_contract_version: "0.2.0",
        pairing_id: "pairing-one",
        availability: "live",
        sequence: 1,
        active_notes: [],
        age_microseconds: 0,
        expires_in_seconds: 30,
        capture: "idle",
        capture_purpose: null,
        calibration_approved: true,
      }), { status: 200, headers: { "Content-Type": "application/json" } }));
    }
    return Promise.resolve(new Response(null, { status: 204 }));
  } as typeof fetch;

  await new DesktopMidiBridge("pairing-one", "bridge-token", fetcher).publish({
    connection: "connected",
    active_notes: [],
  });
  await new MobileCompanionSession("pairing-one", "phone-token", fetcher).read();

  expect(receivers).toEqual([globalThis, globalThis]);
});
