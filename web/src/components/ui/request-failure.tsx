"use client";
import Link from "next/link";
import { ApiRequestError } from "@/lib/api-request";
import { useLocale } from "@/lib/i18n/locale-context";
import { getApplicationCatalog } from "@/lib/i18n/generated-app-catalogs";

export function RequestFailure({ error, retry }: { error: ApiRequestError; retry: () => void }) {
  const { locale } = useLocale();
  const catalog = getApplicationCatalog(locale);
  return <div role="alert" data-error-category={error.category} className="rounded-xl border border-red-300 p-4 space-x-3">
    <span>{error.publicMessage ?? catalog.auth.genericError}</span>
    {error.category === "session_expired"
      ? <Link href="/login?session_expired=1">{catalog.auth.backToLogin}</Link>
      : <button type="button" onClick={retry}>{catalog.assistant.retry}</button>}
  </div>;
}
