const DARK_TEXT = "#0F172A";
const LIGHT_TEXT = "#F8FAFC";

function channel(value: number): number {
  const normalized = value / 255;
  return normalized <= 0.03928 ? normalized / 12.92 : ((normalized + 0.055) / 1.055) ** 2.4;
}

export function normalizeHex(value: string): string {
  const hex = value.trim().replace("#", "");
  const full = hex.length === 3 ? hex.split("").map((item) => item + item).join("") : hex.slice(0, 6);
  return `#${full.toUpperCase()}`;
}

export function contrastRatio(foreground: string, background: string): number {
  const luminances = [foreground, background].map((color) => {
    const hex = normalizeHex(color).slice(1);
    const red = channel(Number.parseInt(hex.slice(0, 2), 16));
    const green = channel(Number.parseInt(hex.slice(2, 4), 16));
    const blue = channel(Number.parseInt(hex.slice(4, 6), 16));
    return 0.2126 * red + 0.7152 * green + 0.0722 * blue;
  });
  const lighter = Math.max(...luminances);
  const darker = Math.min(...luminances);
  return (lighter + 0.05) / (darker + 0.05);
}

export function readableText(background: string): typeof DARK_TEXT | typeof LIGHT_TEXT {
  return contrastRatio(DARK_TEXT, background) >= contrastRatio(LIGHT_TEXT, background) ? DARK_TEXT : LIGHT_TEXT;
}

function mix(color: string, target: string, amount: number): string {
  const from = normalizeHex(color).slice(1);
  const to = normalizeHex(target).slice(1);
  const mixed = [0, 2, 4].map((index) => {
    const start = Number.parseInt(from.slice(index, index + 2), 16);
    const end = Number.parseInt(to.slice(index, index + 2), 16);
    return Math.round(start + (end - start) * amount).toString(16).padStart(2, "0");
  });
  return `#${mixed.join("")}`.toUpperCase();
}

/** Darken or lighten a brand color until black or white text reaches WCAG AA. */
export function accessibleSurface(color: string): string {
  const text = readableText(color);
  if (contrastRatio(text, color) >= 4.5) return normalizeHex(color);
  const target = text === LIGHT_TEXT ? "#000000" : "#FFFFFF";
  let current = normalizeHex(color);
  for (let step = 0; step < 24; step += 1) {
    current = mix(current, target, 0.08);
    if (contrastRatio(text, current) >= 4.5) return current;
  }
  return text === LIGHT_TEXT ? "#0F172A" : "#F8FAFC";
}
