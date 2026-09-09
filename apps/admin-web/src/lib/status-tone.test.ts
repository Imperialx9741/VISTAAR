import { describe, expect, it } from "vitest";
import { toneForStatus } from "./status-tone";

describe("toneForStatus", () => {
  it("maps positive states to success", () => {
    expect(toneForStatus("APPROVED")).toBe("success");
    expect(toneForStatus("ACTIVE")).toBe("success");
    expect(toneForStatus("ACTIVATED")).toBe("success");
    expect(toneForStatus("ONLINE")).toBe("success");
    expect(toneForStatus("PUBLISHED")).toBe("success");
    expect(toneForStatus("RESOLVED")).toBe("success");
    expect(toneForStatus("SENT")).toBe("success");
    expect(toneForStatus("VERIFIED")).toBe("success");
    expect(toneForStatus("PAID")).toBe("success");
    expect(toneForStatus("ACCEPTED")).toBe("success");
    expect(toneForStatus("COMPLETED")).toBe("success");
    expect(toneForStatus("SETTLED")).toBe("success");
    expect(toneForStatus("WAIVED")).toBe("success");
  });

  it("maps negative states to danger", () => {
    expect(toneForStatus("REJECTED")).toBe("danger");
    expect(toneForStatus("SUSPENDED")).toBe("danger");
    expect(toneForStatus("EXPIRED")).toBe("danger");
    expect(toneForStatus("INELIGIBLE")).toBe("danger");
    expect(toneForStatus("FAILED")).toBe("danger");
    expect(toneForStatus("CANCELLED")).toBe("danger");
  });

  it("maps in-progress states to warning", () => {
    expect(toneForStatus("ON_RIDE")).toBe("warning");
    expect(toneForStatus("MANUAL_REVIEW")).toBe("warning");
    expect(toneForStatus("PROCESSING")).toBe("warning");
    expect(toneForStatus("IN_REVIEW")).toBe("warning");
    expect(toneForStatus("IN_PROGRESS")).toBe("warning");
    expect(toneForStatus("WAITING_FOR_USER")).toBe("warning");
    expect(toneForStatus("PAUSED")).toBe("warning");
    expect(toneForStatus("PROOF_SUBMITTED")).toBe("warning");
    expect(toneForStatus("STARTED")).toBe("warning");
  });

  it("maps not-yet-actioned states to info", () => {
    expect(toneForStatus("PENDING")).toBe("info");
    expect(toneForStatus("OPEN")).toBe("info");
    expect(toneForStatus("ASSIGNED")).toBe("info");
    expect(toneForStatus("ACKNOWLEDGED")).toBe("info");
    expect(toneForStatus("SEARCHING")).toBe("info");
    expect(toneForStatus("ARRIVED")).toBe("info");
    expect(toneForStatus("OUTSTANDING")).toBe("info");
    expect(toneForStatus("SCHEDULED")).toBe("info");
  });

  it("falls back to neutral for anything unrecognized", () => {
    expect(toneForStatus("OFFLINE")).toBe("neutral");
    expect(toneForStatus("INACTIVE")).toBe("neutral");
    expect(toneForStatus("SOMETHING_UNKNOWN")).toBe("neutral");
  });

  it("leaves terminal-but-not-bad states unmapped (neutral)", () => {
    // Ad campaigns' ENDED, same deliberate non-mapping already given
    // to Safety incidents' CLOSED — terminal isn't the same as bad.
    expect(toneForStatus("ENDED")).toBe("neutral");
    expect(toneForStatus("CLOSED")).toBe("neutral");
  });
});
