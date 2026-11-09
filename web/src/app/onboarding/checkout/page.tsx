"use client";

import React, { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import {
  Lock,
  CreditCard,
  ShieldCheck,
  CheckCircle2,
  ExternalLink,
  RefreshCw,
  AlertCircle,
  Sparkles,
} from "lucide-react";
import { OnboardingWizardLayout } from "@/components/onboarding/onboarding-wizard-layout";
import { getAuthHeaders } from "@/lib/api-headers";
import { apiFetch } from "@/lib/api-request";
import { useLocale } from "@/lib/i18n/locale-context";
import { getOnboardingCopy } from "@/lib/i18n/onboarding-multistep-copy";

export default function OnboardingCheckoutPage() {
  const router = useRouter();
  const { locale } = useLocale();
  const copy = getOnboardingCopy(locale);

  const [isLoading, setIsLoading] = useState(true);
  const [isRedirecting, setIsRedirecting] = useState(false);
  const [state, setState] = useState<any>(null);
  const [isSubscriptionVerified, setIsSubscriptionVerified] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const checkState = async () => {
    try {
      const headers = getAuthHeaders();
      const res = await apiFetch("/api/v1/onboarding/state", { headers });
      if (res.ok) {
        const data = await res.json();
        setState(data);
        const subStatus = data.subscription?.status;
        if (subStatus === "active" || subStatus === "trialing" || subStatus === "verified_test") {
          setIsSubscriptionVerified(true);
        }
      }
    } catch (err) {
      console.error("Erreur de vérification statut:", err);
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    void checkState();
  }, []);

  const handleCreateStripeCheckout = async () => {
    setIsRedirecting(true);
    setErrorMessage(null);
    try {
      const planCode = state?.subscription?.selected_plan || "professional";
      const headers = getAuthHeaders();
      const res = await apiFetch("/api/v1/billing/checkout", {
        method: "POST",
        headers,
        body: JSON.stringify({ plan_code: planCode }),
      });

      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail || "Impossible de générer la session de paiement sécurisée.");
      }

      const data = await res.json();
      if (data.url) {
        // Redirection vers la page sécurisée Stripe Checkout
        window.location.href = data.url;
      } else {
        // En mode test sans URL directe, re-vérifier le statut
        await checkState();
      }
    } catch (err: any) {
      setErrorMessage(err.message || "Erreur de connexion avec le service Stripe.");
      setIsRedirecting(false);
    }
  };

  const handleContinueToActivation = () => {
    router.push("/onboarding/complete");
  };

  if (isLoading || !state) {
    return (
      <div className="min-h-screen bg-[#060B13] flex items-center justify-center text-slate-400">
        Vérification sécurisée du compte…
      </div>
    );
  }

  const selectedPlanCode = state.subscription?.selected_plan || "professional";
  const planName = selectedPlanCode === "base" ? "Base" : "Professional";
  const planPrice = selectedPlanCode === "base" ? "29,99 $ CAD" : "49,99 $ CAD";

  return (
    <OnboardingWizardLayout
      currentStepIndex={7}
      title={copy.checkout.title}
      subtitle={copy.checkout.subtitle}
      onNext={isSubscriptionVerified ? handleContinueToActivation : () => void handleCreateStripeCheckout()}
      nextLabel={isSubscriptionVerified ? "Finaliser l'Activation de l'Espace" : "Payer avec Stripe"}
      isSubmitting={isRedirecting}
    >
      <div className="max-w-2xl mx-auto space-y-6">
        {/* Order Summary Card */}
        <div className="p-6 rounded-2xl bg-[#0B132B]/80 border border-white/[0.08] space-y-5 shadow-xl">
          <div className="flex items-center justify-between border-b border-white/[0.08] pb-4">
            <div>
              <span className="text-[10px] font-bold uppercase tracking-wider text-slate-400">
                Abonnement sélectionné
              </span>
              <h3 className="text-xl font-bold text-white mt-0.5">Avenqo {planName}</h3>
            </div>
            <div className="text-right">
              <span className="text-2xl font-extrabold text-white">{planPrice}</span>
              <span className="text-xs text-slate-400 block">par mois</span>
            </div>
          </div>

          <div className="space-y-2 text-xs text-slate-300">
            <div className="flex items-center justify-between">
              <span>Sous-total mensuel</span>
              <span className="font-mono text-white">{planPrice}</span>
            </div>
            <div className="flex items-center justify-between text-slate-400">
              <span>Taxes applicables (TPS/TVQ ou selon juridiction)</span>
              <span>Calculées au paiement</span>
            </div>
            <div className="flex items-center justify-between text-slate-400">
              <span>Renouvellement</span>
              <span>Mensuel automatique · Résiliable à tout moment</span>
            </div>
          </div>

          {/* Status Badge */}
          <div className="pt-4 border-t border-white/[0.08] flex items-center justify-between">
            <span className="text-xs font-semibold text-slate-300">Statut de l'abonnement :</span>
            {isSubscriptionVerified ? (
              <span className="px-3 py-1 rounded-full bg-emerald-500/20 text-emerald-400 border border-emerald-500/30 text-xs font-bold flex items-center gap-1.5">
                <CheckCircle2 className="w-3.5 h-3.5" />
                Vérifié & Actif
              </span>
            ) : (
              <span className="px-3 py-1 rounded-full bg-amber-500/20 text-amber-300 border border-amber-500/30 text-xs font-bold">
                En attente de règlement
              </span>
            )}
          </div>
        </div>

        {/* Security and Stripe Guarantee Box */}
        <div className="p-5 rounded-2xl bg-[#0B132B]/50 border border-white/[0.06] flex items-start gap-3.5">
          <Lock className="w-5 h-5 text-emerald-400 shrink-0 mt-0.5" />
          <div className="text-xs text-slate-300 space-y-1">
            <span className="font-bold text-white block">Paiement Garanti et Sécurisé par Stripe</span>
            <p className="leading-relaxed text-slate-400">
              {copy.checkout.secureStripeNotice} Avenqo ne stocke aucun numéro de carte bancaire
              sur ses serveurs. L'accès est conditionné à la confirmation cryptographique du paiement.
            </p>
          </div>
        </div>

        {errorMessage && (
          <div className="p-4 rounded-xl bg-rose-500/10 border border-rose-500/25 text-xs text-rose-300 flex items-center gap-2">
            <AlertCircle className="w-4 h-4 shrink-0" />
            <span>{errorMessage}</span>
          </div>
        )}

        {/* Action Button */}
        {!isSubscriptionVerified && (
          <div className="text-center pt-2">
            <button
              type="button"
              onClick={() => void handleCreateStripeCheckout()}
              disabled={isRedirecting}
              className="w-full py-3.5 rounded-xl bg-gradient-to-r from-blue-600 to-[#0076FF] hover:opacity-95 text-sm font-bold text-white shadow-lg shadow-blue-500/25 transition-all flex items-center justify-center gap-2 cursor-pointer disabled:opacity-50"
            >
              <CreditCard className="w-4 h-4" />
              <span>{isRedirecting ? "Redirection vers Stripe Checkout…" : copy.checkout.payWithStripe}</span>
              <ExternalLink className="w-4 h-4" />
            </button>
            <p className="text-[11px] text-slate-500 mt-2">
              {copy.checkout.simulatedSuccessNotice}
            </p>
          </div>
        )}

        {isSubscriptionVerified && (
          <div className="p-4 rounded-xl bg-emerald-500/10 border border-emerald-500/30 text-xs text-emerald-300 text-center flex items-center justify-center gap-2">
            <CheckCircle2 className="w-4 h-4" />
            <span>Abonnement confirmé. Vous pouvez passer à l'activation finale.</span>
          </div>
        )}
      </div>
    </OnboardingWizardLayout>
  );
}
