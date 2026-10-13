import { useEffect, useState } from "react";
import { QRCodeSVG } from "qrcode.react";

import type { AppConfig } from "../api";
import { BrowserMidiSession } from "../midi/BrowserMidiSession";
import { MidiCalibrationSurface } from "../midi/MidiCalibrationSurface";
import { DesktopBridgeController } from "./DesktopBridgeController";
import {
  DesktopMidiBridge,
  type MobilePairingOffer,
  type MobilePairingStatus,
  claimDesktopBridge,
  createMobilePairing,
  inspectMobilePairing,
  revokeMobilePairing,
} from "./transport";

interface MobileBridgeSetupProps {
  config: AppConfig;
  session: BrowserMidiSession;
}

export function MobilePairingTransfer({ pairingUrl }: { pairingUrl: string }) {
  return (
    <section className="mobile-pairing-transfer" aria-labelledby="mobile-pairing-transfer-title">
      <div className="mobile-pairing-qr">
        <QRCodeSVG
          value={pairingUrl}
          size={184}
          level="M"
          marginSize={4}
          title="One-time TeachMeMusic phone pairing code"
        />
      </div>
      <div>
        <h3 id="mobile-pairing-transfer-title">Scan with the iPhone Camera</h3>
        <p>
          Open the detected TeachMeMusic link once in Safari. The code contains a
          short-lived private credential; do not photograph or share it.
        </p>
      </div>
    </section>
  );
}

export function MobileBridgeSetup({ config, session }: MobileBridgeSetupProps) {
  const [offer, setOffer] = useState<MobilePairingOffer | null>(null);
  const [status, setStatus] = useState<MobilePairingStatus | null>(null);
  const [controller, setController] = useState<DesktopBridgeController | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!offer) return;
    const timer = setInterval(() => {
      void inspectMobilePairing(config, offer.pairing_id).then(setStatus).catch(() => undefined);
    }, 1_000);
    return () => clearInterval(timer);
  }, [config, offer]);

  useEffect(() => () => controller?.stop(), [controller]);

  async function startPairing() {
    setBusy(true);
    setError(null);
    try {
      const created = await createMobilePairing(config, 10 * 60);
      const bridgeToken = await claimDesktopBridge(
        config,
        created.pairing_id,
        created.bridge_capability,
      );
      const nextController = new DesktopBridgeController(
        new DesktopMidiBridge(created.pairing_id, bridgeToken),
        session,
        config,
        setError,
      );
      nextController.start();
      setController(nextController);
      setOffer(created);
      setStatus(await inspectMobilePairing(config, created.pairing_id));
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "The phone pairing could not start.");
    } finally {
      setBusy(false);
    }
  }

  async function revoke() {
    if (!offer) return;
    setBusy(true);
    setError(null);
    try {
      await revokeMobilePairing(config, offer.pairing_id);
      controller?.stop();
      setController(null);
      setOffer(null);
      setStatus(null);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "The phone pairing could not be revoked.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <details className="mobile-bridge-panel">
      <summary>
        <span>Connect the secure phone companion</span>
        <small>Desktop Chrome retains MIDI capture and calibration</small>
      </summary>
      <div className="mobile-bridge-content">
        <MidiCalibrationSurface session={session} />
        {!offer ? (
          <button type="button" className="midi-primary" disabled={busy} onClick={() => void startPairing()}>
            {busy ? "Creating pairing…" : "Create 10-minute phone pairing"}
          </button>
        ) : (
          <section aria-label="Active phone pairing">
            <p>
              Scan this one-time code on the iPhone. Its phone capability stays in the URL
              fragment and is consumed when Safari pairs.
            </p>
            <MobilePairingTransfer pairingUrl={offer.pairing_url} />
            <dl>
              <div><dt>Phone</dt><dd>{status?.phone_claimed ? "paired" : "waiting"}</dd></div>
              <div><dt>MIDI bridge</dt><dd>{status?.bridge_claimed ? "paired" : "waiting"}</dd></div>
              <div><dt>Live state</dt><dd>{status?.availability ?? "unavailable"}</dd></div>
              <div><dt>Expires</dt><dd>{status?.expires_in_seconds ?? offer.expires_in_seconds}s</dd></div>
            </dl>
            <button type="button" disabled={busy} onClick={() => void revoke()}>
              Revoke phone pairing
            </button>
          </section>
        )}
        {error && <p className="midi-alert" role="alert">{error}</p>}
      </div>
    </details>
  );
}
