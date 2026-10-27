import React from "react";
import { render,screen,waitFor,fireEvent,cleanup } from "@testing-library/react";
import { describe,it,expect,vi,afterEach } from "vitest";
import { VoiceProvisioningSection } from "../src/components/voice/voice-provisioning-section";
vi.mock("@/lib/i18n/locale-context",()=>({useLocale:()=>({locale:"fr"})}));
vi.mock("next/link",()=>({default:({children,...props}:React.PropsWithChildren<{href:string}>)=><a {...props}>{children}</a>}));
afterEach(()=>{cleanup();vi.unstubAllGlobals();});
describe("commercial Voice consent",()=>{
 it("shows provisional add-on and keeps purchases disabled",async()=>{
  vi.stubGlobal("fetch",vi.fn(async(url:string)=>({ok:true,json:async()=>url.includes("catalog")?{commercial_enabled:false,payments_enabled:false}:[]})));
  render(<VoiceProvisioningSection tenantId="alpha" canManage crmEnabled/>);
  await screen.findByText(/Les achats sont en préparation/);
  expect(screen.getByText(/4,99 CAD/)).toBeTruthy();
  expect(screen.getByRole("button",{name:"Rechercher"})).toBeDisabled();
 });
 it("shows full monthly total and requires amount-bound consent",async()=>{
  const q={id:"order-a",phone_number:"+15145550001",status:"QUOTED",billing:{currency:"CAD",number_monthly_amount:499,monthly_total_before_tax:3498,initial_amount_due:574,initial_tax:75,tax_status:"calculated"},provider_cost:{monthly_cost:"1.00",currency:"USD"}};
  const fetcher=vi.fn(async(url:string,options?:RequestInit)=>({ok:true,json:async()=>url.includes("catalog")?{commercial_enabled:true,payments_enabled:true}:url.endsWith("orders")?[]:url.includes("numbers/search")?{offers:[{phone_number:q.phone_number,number_type:"local",country_code:"CA"}]}:options?.method==="POST"?q:[]}));
  vi.stubGlobal("fetch",fetcher);render(<VoiceProvisioningSection tenantId="alpha" canManage crmEnabled/>);
  await waitFor(()=>expect(screen.getByRole("button",{name:"Rechercher"})).not.toBeDisabled());
  fireEvent.click(screen.getByRole("button",{name:"Rechercher"}));
  fireEvent.click(await screen.findByRole("button",{name:/Voir le prix total/}));
  const pay=await screen.findByRole("button",{name:"Confirmer le paiement"});expect(pay).toBeDisabled();
  expect(screen.getByText(/34,98/)).toBeTruthy();
  fireEvent.click(screen.getByLabelText(/J’autorise ce supplément mensuel/));fireEvent.click(pay);
  await waitFor(()=>expect(fetcher.mock.calls.some(([url])=>url.includes("/confirm"))).toBe(true));
  const body=JSON.parse(fetcher.mock.calls.find(([url])=>url.includes("/confirm"))![1]!.body as string);
  expect(body.max_initial_amount).toBe(574);expect(body.monthly_total).toBe(3498);expect(body.consent).toBe(true);
 });
});
