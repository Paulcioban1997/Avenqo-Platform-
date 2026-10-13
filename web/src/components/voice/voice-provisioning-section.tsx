"use client";
import { useEffect, useState, useRef } from "react";
import Link from "next/link";
import { useLocale } from "@/lib/i18n/locale-context";

type Offer={phone_number:string;number_type:string;country_code:string};
type Order={id:string;status:string;phone_number:string;paid:boolean;phone_assigned:boolean;audio_ready:boolean;invoice_url:string|null;billing:{currency:string;number_monthly_amount:number;monthly_total_before_tax:number;monthly_invoice_total?:number;monthly_tax?:number;initial_amount_due:number;initial_tax:number;tax_status:string};provider_cost:{monthly_cost:string;upfront_cost?:string;currency:string}};
const COPY={
 fr:{title:"Votre numéro professionnel",price:"Supplément provisoire : 4,99 CAD/mois hors taxes, sans installation.",disabled:"Les achats sont en préparation. Aucun paiement ni achat de numéro n’est activé.",country:"Pays",region:"Région ou indicatif",type:"Type de numéro",search:"Rechercher",quote:"Voir le prix total",monthly:"Total mensuel avant taxes",due:"Montant initial à payer",tax:"Taxes du paiement initial",supplier:"Coût du numéro chez le fournisseur",consent:"J’autorise ce supplément mensuel et le montant initial affiché.",crm:"J’autorise mon agent à consulter les créneaux et créer des rendez-vous dans mon CRM.",confirm:"Confirmer le paiement",progress:"État de votre service",pending:"En préparation",ready:"Réception audio autorisée",assigned:"Numéro attribué, audio en attente",invoice:"Voir la facture",suspend:"Suspendre",resume:"Réactiver",cancel:"Annuler et libérer le numéro",cancelConfirm:"Confirmez-vous l’annulation et la libération de ce numéro ? Il pourrait ne plus être disponible ensuite.",failed:"Cette opération n’a pas abouti. Aucun statut d’activation n’a été confirmé.",usage:"Les appels et l’IA consomment vos crédits. Aucun dépassement n’est facturé automatiquement.",unknownTax:"La collecte fiscale n’est pas configurée. Aucune taxe n’a été ajoutée à cette estimation.",empty:"Aucun numéro disponible pour cette recherche."},
 en:{title:"Your business number",price:"Provisional add-on: CAD 4.99/month before tax, no setup fee.",disabled:"Purchases are being prepared. Payments and number purchases are disabled.",country:"Country",region:"Region or area code",type:"Number type",search:"Search",quote:"See the total price",monthly:"Monthly total before tax",due:"Initial amount due",tax:"Initial payment taxes",supplier:"Provider number cost",consent:"I authorize this monthly add-on and the displayed initial payment.",crm:"I authorize availability checks and appointment creation in my CRM.",confirm:"Confirm payment",progress:"Service status",pending:"Preparing",ready:"Audio reception authorized",assigned:"Number assigned; audio pending",invoice:"View invoice",suspend:"Suspend",resume:"Reactivate",cancel:"Cancel and release number",cancelConfirm:"Cancel and release this number? It might not be available again.",failed:"This operation did not complete. Activation has not been confirmed.",usage:"Calls and AI consume credits. Overages are never billed automatically.",unknownTax:"Tax collection is not configured. No tax was added to this estimate.",empty:"No numbers available for this search."},
 es:{title:"Su número profesional",price:"Suplemento provisional: 4,99 CAD/mes sin impuestos ni instalación.",disabled:"Las compras están en preparación. Los pagos y compras de números están desactivados.",country:"País",region:"Región o prefijo",type:"Tipo de número",search:"Buscar",quote:"Ver el precio total",monthly:"Total mensual sin impuestos",due:"Pago inicial",tax:"Impuestos del pago inicial",supplier:"Coste del número del proveedor",consent:"Autorizo este suplemento mensual y el pago inicial mostrado.",crm:"Autorizo consultar disponibilidad y crear citas en mi CRM.",confirm:"Confirmar pago",progress:"Estado del servicio",pending:"En preparación",ready:"Recepción de audio autorizada",assigned:"Número asignado; audio pendiente",invoice:"Ver factura",suspend:"Suspender",resume:"Reactivar",cancel:"Cancelar y liberar número",cancelConfirm:"¿Cancelar y liberar este número? Podría no estar disponible después.",failed:"La operación no se completó. La activación no está confirmada.",usage:"Las llamadas y la IA consumen créditos. No se factura automáticamente el exceso.",unknownTax:"La recaudación fiscal no está configurada. Esta estimación no incluye impuestos.",empty:"No hay números disponibles para esta búsqueda."}
};

export function VoiceProvisioningSection({tenantId,canManage,crmEnabled}:{tenantId:string|undefined;canManage:boolean;crmEnabled:boolean}){
 const {locale}=useLocale();const t=COPY[locale==="fr"?"fr":locale==="es"?"es":"en"];
 const activeTenant=useRef(tenantId);activeTenant.current=tenantId;
 const [loadedTenant,setLoadedTenant]=useState<string|undefined>(undefined);
 const [country,setCountry]=useState("CA"),[region,setRegion]=useState(""),[type,setType]=useState("local");
 const [currency,setCurrency]=useState("CAD");
 const [catalog,setCatalog]=useState<{commercial_enabled:boolean;payments_enabled:boolean}|null>(null);
 const [offers,setOffers]=useState<Offer[]>([]),[orders,setOrders]=useState<Order[]>([]),[selected,setSelected]=useState<Order|null>(null);
 const [consent,setConsent]=useState(false),[bookings,setBookings]=useState(false),[busy,setBusy]=useState(false),[message,setMessage]=useState("");
 useEffect(()=>{
  const abort=new AbortController();let current=true;
  queueMicrotask(()=>{if(current){setOffers([]);setOrders([]);setSelected(null);setCatalog(null);setConsent(false);setBookings(false);setMessage("");}});
  if(!tenantId||!canManage)return ()=>abort.abort();
  const load=async()=>{
   try{const responses=await Promise.all([fetch("/api/v1/voice/provisioning/catalog",{signal:abort.signal,cache:"no-store"}),fetch("/api/v1/voice/provisioning/orders",{signal:abort.signal,cache:"no-store"})]);
    if(responses.every(r=>r.ok)){const [c,o]=await Promise.all(responses.map(r=>r.json()));if(current){setCatalog(c);setOrders(o);setLoadedTenant(tenantId);}}
   }catch{/* The account or deployment may not yet have commercial Voice enabled. */}
  };
  void load();const timer=setInterval(()=>void load(),10000);return ()=>{current=false;abort.abort();clearInterval(timer);};
 },[tenantId,canManage]);
 const money=(amount:number,currency="CAD")=>{const f=new Intl.NumberFormat(locale,{style:"currency",currency});return f.format(amount/(10**(f.resolvedOptions().maximumFractionDigits??2)));};
 async function operation(run:()=>Promise<void>){setBusy(true);setMessage("");try{await run();}catch{if(activeTenant.current===tenantId)setMessage(t.failed);}finally{if(activeTenant.current===tenantId)setBusy(false);}}
 async function post(path:string,body:unknown){const r=await fetch(path,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(body)});if(!r.ok||activeTenant.current!==tenantId)throw Error("Operation unavailable");return r.json();}
 if(!canManage)return null;
 return <section className="space-y-4 rounded-2xl border border-slate-200 p-5 dark:border-white/10" aria-label={t.title}>
  <h2 className="text-lg font-semibold">{t.title}</h2><p>{t.price}</p><p className="text-sm text-slate-500">{t.usage}</p>
  {(loadedTenant!==tenantId||!catalog?.commercial_enabled)&&<p role="status" className="rounded-xl bg-amber-50 p-3 text-amber-900 dark:bg-amber-900/20 dark:text-amber-200">{t.disabled}</p>}
  <form className="flex flex-wrap items-end gap-3" onSubmit={e=>{e.preventDefault();void operation(async()=>{
   const params=new URLSearchParams({country_code:country,number_type:type,limit:"20"});if(region)params.set("area_code",region);
   const r=await fetch(`/api/v1/voice/numbers/search?${params}`);if(!r.ok)throw Error();const data=await r.json();if(activeTenant.current!==tenantId)return;setOffers(data.offers||[]);setSelected(null);setConsent(false);if(!data.offers?.length)setMessage(t.empty);
  });}}>
   <label className="space-y-1 text-sm"><span>{t.country}</span><input value={country} onChange={e=>setCountry(e.target.value.toUpperCase())} pattern="[A-Z]{2}" maxLength={2} required className="block rounded-lg border bg-transparent p-2"/></label>
   <label className="space-y-1 text-sm"><span>{locale==="fr"?"Devise de l’abonnement":locale==="es"?"Moneda de la suscripción":"Subscription currency"}</span><input value={currency} onChange={e=>setCurrency(e.target.value.toUpperCase())} pattern="[A-Z]{3}" maxLength={3} required className="block rounded-lg border bg-transparent p-2"/></label>
   <label className="space-y-1 text-sm"><span>{t.region}</span><input value={region} onChange={e=>setRegion(e.target.value)} inputMode="numeric" pattern="[0-9]*" maxLength={8} className="block rounded-lg border bg-transparent p-2"/></label>
   <label className="space-y-1 text-sm"><span>{t.type}</span><select value={type} onChange={e=>setType(e.target.value)} className="block rounded-lg border bg-transparent p-2"><option value="local">Local</option><option value="mobile">Mobile</option><option value="toll_free">Toll free</option></select></label>
   <button disabled={busy||loadedTenant!==tenantId||!catalog?.commercial_enabled} className="rounded-lg bg-blue-600 px-4 py-2 text-white disabled:opacity-40">{t.search}</button>
  </form>
  <div className="grid gap-2 sm:grid-cols-2">{loadedTenant===tenantId&&offers.map(o=><button key={o.phone_number} disabled={busy} className="rounded-xl border p-3 text-left" onClick={()=>void operation(async()=>{const q=await post("/api/v1/voice/provisioning/quote",{phone_number:o.phone_number,country,number_type:o.number_type,currency});setSelected(q);setConsent(false);})}>{o.phone_number}<span className="block text-sm text-blue-600">{t.quote}</span></button>)}</div>
  {loadedTenant===tenantId&&selected&&<div className="space-y-3 rounded-xl bg-slate-50 p-4 dark:bg-white/5"><strong>{selected.phone_number}</strong>
   <p>{t.monthly}: {money(selected.billing.monthly_total_before_tax,selected.billing.currency)}</p><p>{t.due}: {money(selected.billing.initial_amount_due,selected.billing.currency)}</p><p>{t.tax}: {money(selected.billing.initial_tax,selected.billing.currency)}</p>
   {selected.billing.monthly_invoice_total!==undefined&&<p>{locale==="fr"?"Total mensuel taxes comprises":locale==="es"?"Total mensual con impuestos":"Monthly total including taxes"}: {money(selected.billing.monthly_invoice_total,selected.billing.currency)}</p>}
   <p>{locale==="fr"?"Supplément numéro":locale==="es"?"Suplemento del número":"Number add-on"}: {money(selected.billing.number_monthly_amount,selected.billing.currency)}</p>
   <p className="text-sm">{t.supplier}: {selected.provider_cost.monthly_cost} {selected.provider_cost.currency}/month</p>
   {selected.billing.tax_status!=="calculated"&&<p className="text-sm">{t.unknownTax}</p>}
   <label className="flex gap-2 text-sm"><input type="checkbox" checked={consent} onChange={e=>setConsent(e.target.checked)}/>{t.consent}</label>
   {crmEnabled&&<label className="flex gap-2 text-sm"><input type="checkbox" checked={bookings} onChange={e=>setBookings(e.target.checked)}/>{t.crm}</label>}
   <button disabled={!consent||busy||!catalog?.payments_enabled} className="rounded-lg bg-blue-600 px-4 py-2 text-white disabled:opacity-40" onClick={()=>void operation(async()=>{const result=await post(`/api/v1/voice/provisioning/orders/${selected.id}/confirm`,{consent,max_initial_amount:selected.billing.initial_amount_due,monthly_total:selected.billing.monthly_total_before_tax,allow_crm_bookings:bookings});setSelected(result);setOrders(previous=>[result,...previous.filter(x=>x.id!==result.id)]);})}>{t.confirm}</button>
  </div>}
  {message&&<p role="alert">{message}</p>}
  {loadedTenant===tenantId&&orders.length>0&&<div className="space-y-3"><h3 className="font-semibold">{t.progress}</h3>{orders.map(o=><div key={o.id} className="flex flex-wrap items-center justify-between gap-3 rounded-xl border p-3"><div><strong>{o.phone_number}</strong><p>{["CANCELED","REFUNDED"].includes(o.status)?(locale==="fr"?"Annulé":locale==="es"?"Cancelado":"Canceled"):o.status.startsWith("SUSPENDED")?(locale==="fr"?"Suspendu":locale==="es"?"Suspendido":"Suspended"):o.status==="REVIEW_REQUIRED"?t.failed:o.audio_ready?t.ready:o.phone_assigned?t.assigned:t.pending}</p></div>
   <div className="flex flex-wrap gap-3 text-sm">{o.invoice_url&&<a href={o.invoice_url} target="_blank" rel="noopener noreferrer" className="text-blue-600">{t.invoice}</a>}
   {o.phone_assigned&&o.status!=="CANCELED"&&<><button disabled={busy} onClick={()=>void operation(async()=>{await post(`/api/v1/voice/provisioning/orders/${o.id}/action`,{action:o.status==="SUSPENDED_OWNER"?"resume":"suspend",confirmed:true});})}>{o.status==="SUSPENDED_OWNER"?t.resume:t.suspend}</button><button disabled={busy} onClick={()=>{if(window.confirm(t.cancelConfirm))void operation(async()=>{await post(`/api/v1/voice/provisioning/orders/${o.id}/action`,{action:"cancel",confirmed:true});});}}>{t.cancel}</button></>}
  </div></div>)}<Link href="/billing" className="text-sm text-blue-600">{t.invoice}</Link></div>}
 </section>;
}
