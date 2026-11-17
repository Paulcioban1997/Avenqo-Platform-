export function formatMoney(amount: number, currency: string, locale: string, digits = 2) {
  try {
    return new Intl.NumberFormat(locale, {
      style: "currency",
      currency,
      maximumFractionDigits: digits,
    }).format(amount);
  } catch {
    return `${amount.toLocaleString(locale, { maximumFractionDigits: digits })} ${currency}`;
  }
}
