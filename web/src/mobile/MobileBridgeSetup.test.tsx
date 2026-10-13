import { render, screen } from "@testing-library/react";

import { MobilePairingTransfer } from "./MobileBridgeSetup";

test("TEST-APP-MOBILE-020 renders the complete one-time pairing URL as a local QR code", () => {
  const pairingUrl =
    "https://192.168.1.10:8443/?pairing_id=pairing-one#phone_capability=private-capability";

  const { container } = render(<MobilePairingTransfer pairingUrl={pairingUrl} />);

  expect(screen.getByRole("heading", { name: "Scan with the iPhone Camera" }))
    .toBeInTheDocument();
  expect(screen.getByText(/short-lived private credential/)).toBeInTheDocument();
  expect(container.querySelector("svg")).not.toBeNull();
  expect(container.querySelector("a")).toBeNull();
});
