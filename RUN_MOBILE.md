# Run the Secure Mobile Companion

Mobile mode is an experimental local-network test configuration. The Mac
retains score processing, Web MIDI capture, calibration, evaluation, and
evidence authority. The paired phone displays and controls the teaching
workflow.

## Requirements

- the completed setup from [RUN_LOCAL.md](RUN_LOCAL.md);
- the Mac and iPhone on one trusted private network;
- the Mac's explicit private IPv4 address or IPv6 unique-local address;
- a locally trusted TLS certificate and private key covering that address.

The repository does not generate or install certificates and never modifies a
device trust store. Do not commit certificate or key files.

## Start the Bridge

```bash
./scripts/run-mobile.sh \
  --host 192.168.1.44 \
  --port 8443 \
  --certfile /path/to/local-cert.pem \
  --keyfile /path/to/local-key.pem
```

Replace the example address and certificate paths with the trusted private
network values for the Mac. The launcher rejects wildcard, loopback, public,
and unspecified companion addresses.

It prints:

- a loopback-only desktop address for Chrome and Web MIDI;
- a separate HTTPS companion address for the phone.

Open the desktop address in Chrome, connect and calibrate the piano, then open
the secure-phone section and create a ten-minute pairing. Open its one-time
link on the iPhone. The capability is carried in the URL fragment, consumed
during pairing, removed from the visible address, and retained only in memory.

Press `Control-C` to stop both listeners and erase all live pairings.

## Security Boundary

- Use only a trusted private network; this is not an internet deployment.
- Never bind the companion to `0.0.0.0`, `::`, or a public address.
- Phone and MIDI-bridge capabilities are separate, short-lived, and
  role-specific.
- Raw MIDI and calibration evidence remain on the Mac.
- Evaluation occurs through the authoritative local service.
- Expired, revoked, malformed, oversized, reordered, cross-origin, wrong-host,
  and wrong-role traffic fails closed.

## Current Limit

Automated transport, API, layout, piano-guidance, and teaching-loop tests pass.
Real-device acceptance remains incomplete, so mobile mode must not be treated
as a finished public product.
