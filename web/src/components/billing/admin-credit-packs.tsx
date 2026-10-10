"use client";
import { useCallback, useEffect, useState } from "react";
import { apiFetch } from "@/lib/api-request";

interface Offer {
  code: string; name: string; credits: number; price_cents: number; enabled: boolean;
  profitability: { status: string; contribution_before_overhead_cad: string; missing_successful_provider_samples: string[]; limitations: string };
}

export function AdminCreditPacks({ isFr }: { isFr: boolean }) {
  const [offers, setOffers] = useState<Offer[]>([]);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const reload = useCallback(async () => {
    try {
      const response = await apiFetch("/api/v1/admin/credit-packs");
      if (!response.ok) throw new Error("Catalogue unavailable");
      setOffers(await response.json());
      setError("");
    } catch { setError(isFr ? "Catalogue indisponible. Réessayez." : "Catalogue unavailable. Retry."); }
  }, [isFr]);
  useEffect(() => { queueMicrotask(() => { void reload(); }); }, [reload]);
  const activate = async (offer: Offer) => {
    const reference = offer.enabled ? null : window.prompt(isFr
      ? "Référence du rapprochement des coûts fournisseurs, téléphonie et frais fixes :"
      : "Provider, telephony and overhead reconciliation reference:");
    if (!offer.enabled && !reference) return;
    setBusy(true);
    try {
      const response = await apiFetch(`/api/v1/admin/credit-packs/${offer.code}`, {
        method: "PATCH", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ enabled: !offer.enabled, reconciliation_reference: reference }),
      });
      if (!response.ok) throw new Error((await response.json()).detail);
      await reload();
    } catch (failure) { setError(failure instanceof Error ? failure.message : "Unavailable"); }
    finally { setBusy(false); }
  };
  return <section className="rounded-2xl border p-5 space-y-4 bg-white dark:bg-[#0B132B]">
    <h2 className="text-lg font-bold">{isFr ? "Packs de crédits IA · CAD hors taxes" : "AI credit packs · CAD excluding tax"}</h2>
    <p className="text-sm text-slate-500">{isFr ? "Achats volontaires. Aucun dépassement automatique. Les nouvelles versions préservent les achats antérieurs. Enterprise : sur devis." : "Voluntary purchases. No automatic overage. New versions preserve past purchases. Enterprise: custom quote."}</p>
    {error && <p role="alert" className="text-red-600">{error} <button onClick={() => void reload()}>↻</button></p>}
    <div className="grid sm:grid-cols-3 gap-3">{offers.map(offer => <article key={offer.code} className="border rounded-xl p-4 space-y-2">
      <h3 className="font-bold">{offer.name}</h3>
      <p>{offer.credits.toLocaleString()} · {(offer.price_cents / 100).toFixed(2)} CAD</p>
      <p className="text-xs">{isFr ? "Contribution estimée avant frais fixes : " : "Estimated contribution before overhead: "}{offer.profitability.contribution_before_overhead_cad} CAD</p>
      {!!offer.profitability.missing_successful_provider_samples.length && <p className="text-xs text-amber-600">{isFr ? "Coûts réels à valider : " : "Actual costs to validate: "}{offer.profitability.missing_successful_provider_samples.join(", ")}</p>}
      <button type="button" disabled={busy || (!offer.enabled && offer.profitability.status !== "ready_for_review")}
        onClick={() => void activate(offer)} className="border rounded-lg px-3 py-2 disabled:opacity-50">
        {offer.enabled ? (isFr ? "Désactiver" : "Disable") : (isFr ? "Activer après rapprochement" : "Activate after reconciliation")}
      </button>
    </article>)}</div>
    <form className="flex flex-wrap gap-3" onSubmit={async (event) => {
      event.preventDefault(); const form = event.currentTarget; const data = new FormData(form); setBusy(true);
      try {
        const response = await apiFetch("/api/v1/admin/credit-packs", { method: "POST", headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ code: data.get("code"), name: data.get("name"), credits: Number(data.get("credits")), price_cents: Math.round(Number(data.get("price")) * 100) }) });
        if (!response.ok) throw new Error((await response.json()).detail);
        form.reset(); await reload();
      } catch (failure) { setError(failure instanceof Error ? failure.message : "Unavailable"); }
      finally { setBusy(false); }
    }}>
      <input aria-label="Code version" name="code" placeholder="starter_v2" required pattern="[a-z0-9_]{3,64}" className="border rounded p-2" />
      <input aria-label={isFr ? "Nom" : "Name"} name="name" placeholder={isFr ? "Nom du pack" : "Pack name"} required className="border rounded p-2" />
      <input aria-label={isFr ? "Crédits" : "Credits"} name="credits" type="number" min="1" max="100000000" required className="border rounded p-2" />
      <input aria-label="Prix CAD" name="price" type="number" min="0.01" max="1000000" step="0.01" required className="border rounded p-2" />
      <button type="submit" disabled={busy} className="rounded bg-blue-600 text-white px-4 py-2">{isFr ? "Créer une nouvelle version" : "Create new version"}</button>
    </form>
  </section>;
}
