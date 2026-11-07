"use client";
import { useEffect,useState } from "react";
type Tariff={id:string;country:string;number_type:string;currency:string;monthly_amount:number;approved:boolean};
export function AdminVoiceTariffs({isFr}:{isFr:boolean}){
 const [rows,setRows]=useState<Tariff[]>([]),[busy,setBusy]=useState(false),[message,setMessage]=useState("");
 useEffect(()=>{const c=new AbortController();void fetch("/api/v1/voice/provisioning/tariffs",{signal:c.signal,cache:"no-store"}).then(async r=>{if(r.ok)setRows(await r.json());}).catch(()=>{});return()=>c.abort();},[]);
 return <section className="rounded-2xl border p-5 dark:border-white/10"><h2 className="text-lg font-semibold">{isFr?"Tarifs des numéros Voice":"Voice number tariffs"}</h2>
  <p className="my-3 text-sm">{isFr?"Configurer un tarif ne déclenche aucun achat ni paiement. L’activation commerciale reste séparée.":"Saving a tariff does not purchase a number or charge a customer. Commercial activation is separate."}</p>
  <form className="grid gap-3 sm:grid-cols-3" onSubmit={async e=>{e.preventDefault();const form=e.currentTarget;const d=new FormData(form);setBusy(true);setMessage("");try{
   const monthly=Number(d.get("amount"));if(!Number.isFinite(monthly)||monthly<=0)throw Error();
   const currency=String(d.get("currency")).toUpperCase();const digits=new Intl.NumberFormat("en",{style:"currency",currency}).resolvedOptions().maximumFractionDigits??2;
   const body={country:String(d.get("country")).toUpperCase(),number_type:String(d.get("type")),currency,monthly_amount:Math.round(monthly*(10**digits)),stripe_price_id:String(d.get("price"))||null,
    provider_cost_limits:{monthly:{USD:String(d.get("providerMonthly"))},upfront:{USD:String(d.get("providerUpfront"))}},approved:d.get("approved")==="on"};
   const r=await fetch("/api/v1/voice/provisioning/tariffs",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(body)});if(!r.ok)throw Error();
   const list=await fetch("/api/v1/voice/provisioning/tariffs",{cache:"no-store"});if(list.ok)setRows(await list.json());setMessage(isFr?"Tarif enregistré.":"Tariff saved.");
  }catch{setMessage(isFr?"Le tarif n’a pas été enregistré. Vérifiez les montants et les droits.":"Tariff was not saved. Check amounts and permissions.");}finally{setBusy(false);}}}>
   <label>{isFr?"Pays":"Country"}<input name="country" defaultValue="CA" maxLength={2} pattern="[A-Za-z]{2}" required className="block w-full rounded border bg-transparent p-2"/></label>
   <label>{isFr?"Type":"Type"}<select name="type" className="block w-full rounded border bg-transparent p-2"><option value="local">Local</option><option value="mobile">Mobile</option><option value="toll_free">Toll free</option></select></label>
   <label>{isFr?"Devise client":"Customer currency"}<input name="currency" defaultValue="CAD" maxLength={3} pattern="[A-Za-z]{3}" required className="block w-full rounded border bg-transparent p-2"/></label>
   <label>{isFr?"Prix mensuel hors taxes":"Monthly price before tax"}<input name="amount" type="number" min="0.01" step="0.01" defaultValue="4.99" required className="block w-full rounded border bg-transparent p-2"/></label>
   <label>{isFr?"Coût fournisseur maximal / mois (USD)":"Maximum provider monthly cost (USD)"}<input name="providerMonthly" type="number" min="0" step="0.01" defaultValue="1.00" required className="block w-full rounded border bg-transparent p-2"/></label>
   <label>{isFr?"Coût initial fournisseur maximal (USD)":"Maximum provider initial cost (USD)"}<input name="providerUpfront" type="number" min="0" step="0.01" defaultValue="1.00" required className="block w-full rounded border bg-transparent p-2"/></label>
   <label className="sm:col-span-2">{isFr?"Identifiant du prix Stripe mensuel":"Monthly Stripe price ID"}<input name="price" placeholder="price_…" className="block w-full rounded border bg-transparent p-2"/></label>
   <label className="flex items-center gap-2"><input type="checkbox" name="approved"/>{isFr?"Rentabilité vérifiée, tarif approuvé":"Margin reviewed, tariff approved"}</label>
   <button disabled={busy} className="rounded bg-blue-600 p-2 text-white">{isFr?"Enregistrer":"Save"}</button>
  </form><p role="status" className="mt-3 text-sm">{message}</p>
  <ul className="mt-3 text-sm">{rows.map(x=>{const format=new Intl.NumberFormat(isFr?"fr-CA":"en-CA",{style:"currency",currency:x.currency});return <li key={x.id}>{x.country} · {x.number_type} · {format.format(x.monthly_amount/(10**(format.resolvedOptions().maximumFractionDigits??2)))} · {x.approved?(isFr?"Approuvé":"Approved"):(isFr?"En préparation":"Draft")}</li>;})}</ul>
 </section>;
}
