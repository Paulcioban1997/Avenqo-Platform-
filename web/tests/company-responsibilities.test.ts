import { describe, expect, it } from "vitest";
import {
  ACCESS_SUMMARY,
  COMPANY_RESPONSIBILITIES,
  COMPANY_SIZES,
  invitationFromResponsibility,
} from "../src/lib/workspace/company-responsibilities";

const ACCESS = new Set(["admin", "manager", "analyst", "user", "viewer"]);

describe("company responsibilities", () => {
  it("covers small, mid-size and large companies without a duplicate position", () => {
    for (const size of COMPANY_SIZES) {
      const rows = COMPANY_RESPONSIBILITIES.filter((item) => item.size === size.id);
      expect(rows.length).toBeGreaterThanOrEqual(10);
      const titles = rows.map((item) => item.title.fr);
      expect(new Set(titles).size).toBe(titles.length);
    }
  });

  it("maps each responsibility to one existing access, a title and a department", () => {
    const ids = new Set<string>();
    for (const item of COMPANY_RESPONSIBILITIES) {
      expect(ids.has(item.id)).toBe(false);
      ids.add(item.id);
      expect(ACCESS.has(item.access)).toBe(true);
      expect(item.access).not.toBe("owner");
      expect(item.title.fr.length).toBeGreaterThan(2);
      expect(item.title.en.length).toBeGreaterThan(2);
      expect(item.title.fr.length).toBeLessThanOrEqual(120);
      expect(item.department.fr.length).toBeGreaterThan(1);
      expect(ACCESS_SUMMARY[item.access].fr.length).toBeGreaterThan(5);
    }
  });

  it("sends the chosen responsibility once, as title, department and access", () => {
    const invitation = invitationFromResponsibility("comptable-pme", "fr");
    expect(invitation).toEqual({
      role: "analyst",
      job_title: "Comptable",
      department: "Finance",
    });
    expect(invitationFromResponsibility("inconnu", "fr").job_title).toBe("Adjoint administratif");
  });
});
