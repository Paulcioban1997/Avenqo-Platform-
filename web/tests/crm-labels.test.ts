import { describe, expect, it } from "vitest";

import { attendanceLabel, currencyText } from "@/components/crm/crm-format";

describe("attendanceLabel", () => {
  it("says there are no appointments this month when the count is zero", () => {
    expect(attendanceLabel({
      appointments_this_month: 0,
      attendance_rate_percent: null,
      attendance_tracked_count: 0,
    }, "fr")).toBe("Aucun rendez-vous ce mois-ci.");
  });

  it("does not call a zero month an unavailable analysis", () => {
    const label = attendanceLabel({
      appointments_this_month: 0,
      attendance_rate_percent: null,
      attendance_tracked_count: 0,
    }, "fr-CA");
    expect(label).not.toContain("n’est pas disponible");
    expect(label).not.toContain("n'est pas disponible");
  });

  it("formats a real attendance rate", () => {
    expect(attendanceLabel({
      appointments_this_month: 4,
      attendance_rate_percent: 75,
      attendance_tracked_count: 4,
    }, "en")).toBe("75.0%");
  });
});

describe("currencyText", () => {
  it("prints the ISO currency code instead of a locale symbol", () => {
    expect(currencyText(0, "CAD", "fr-CA", "unavailable")).toBe("0,00 CAD");
    expect(currencyText(73000, "CAD", "fr-CA", "unavailable")).toContain("CAD");
    expect(currencyText(73000, "CAD", "fr-CA", "unavailable")).not.toContain("$");
  });
});
