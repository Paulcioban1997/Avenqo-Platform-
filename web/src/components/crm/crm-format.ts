export function finiteMetric(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

export function metricText(value: unknown, locale: string, unavailable: string, digits = 0): string {
  const number = finiteMetric(value);
  return number === null ? unavailable : new Intl.NumberFormat(locale, { minimumFractionDigits: digits, maximumFractionDigits: digits }).format(number);
}

export function validDate(value: unknown): Date | null {
  if (typeof value !== "string" || !value.trim()) return null;
  const parsed = new Date(value);
  return Number.isFinite(parsed.getTime()) ? parsed : null;
}

export function dateText(value: unknown, locale: string, unavailable: string, options: Intl.DateTimeFormatOptions = {}): string {
  const parsed = validDate(value);
  return parsed ? new Intl.DateTimeFormat(locale, options).format(parsed) : unavailable;
}

export function currencyText(value: unknown, currency: unknown, locale: string, unavailable: string): string {
  const number = finiteMetric(value);
  if (number === null || typeof currency !== "string" || !/^[A-Z]{3}$/.test(currency)) return unavailable;
  return new Intl.NumberFormat(locale, { style: "currency", currency }).format(number);
}