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

export function attendanceLabel(
  kpis: {
    appointments_this_month?: number | null;
    attendance_rate_percent?: number | null;
    attendance_tracked_count?: number | null;
  },
  locale: string,
): string | null {
  const appointments = finiteMetric(kpis.appointments_this_month);
  const tracked = finiteMetric(kpis.attendance_tracked_count);
  const rate = finiteMetric(kpis.attendance_rate_percent);
  const french = locale.startsWith("fr");
  if (appointments === 0) {
    return french ? "Aucun rendez-vous ce mois-ci." : "No appointments this month.";
  }
  if (appointments === null || rate === null) return null;
  if (tracked === 0) {
    return french ? "Aucune présence n’est encore enregistrée." : "No attendance has been recorded yet.";
  }
  return `${new Intl.NumberFormat(locale, { minimumFractionDigits: 1, maximumFractionDigits: 1 }).format(rate)}%`;
}

export function currencyText(value: unknown, currency: unknown, locale: string, unavailable: string): string {
  const number = finiteMetric(value);
  if (number === null || typeof currency !== "string" || !/^[A-Z]{3}$/.test(currency)) return unavailable;
  const amount = new Intl.NumberFormat(locale, { minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(number);
  return `${amount} ${currency}`;
}