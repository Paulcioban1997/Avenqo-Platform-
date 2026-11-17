import { describe, expect, it } from "vitest";
import { ALL_30_THEMES } from "@/lib/themes/theme-catalog";
import { accessibleSurface, contrastRatio, readableText } from "@/lib/themes/theme-contrast";

describe("theme shell contrast", () => {
  it.each(ALL_30_THEMES.map((theme) => [theme.id, theme.secondary_color, theme.primary_color]))(
    "%s keeps readable shell and button text",
    (_id, secondary, primary) => {
      expect(contrastRatio(readableText(secondary), secondary)).toBeGreaterThanOrEqual(4.5);
      const surface = accessibleSurface(primary);
      expect(contrastRatio(readableText(surface), surface)).toBeGreaterThanOrEqual(4.5);
    },
  );
});
