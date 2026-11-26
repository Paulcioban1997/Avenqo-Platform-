"use client";

import { createContext, useCallback, useContext, useEffect, useRef, useState, type ReactNode } from "react";
import { usePathname } from "next/navigation";
import { apiFetch, ApiRequestError } from "./api-request";
import { creditBalanceViewModel, type CreditBalanceViewModel, type CreditBalancePayload } from "./credit-balance";

export interface OrganizationItem {
  id: string; name: string; slug: string; subscription_plan: string; role: string; is_current: boolean;
}
interface Identity {
  user: { id: string; first_name: string; last_name: string; job_title?: string; role: string; permissions?: string[]; is_platform_admin: boolean };
  company: { id: string; name: string; subscription_plan: string; preferred_language?: string | null; logo_url?: string | null; brand_color?: string | null };
  organizations: OrganizationItem[];
}
interface SessionState {
  identity: Identity | null;
  error: ApiRequestError | null;
  loading: boolean;
  credits: CreditBalanceViewModel;
  creditBalance: CreditBalancePayload | null;
  creditError: ApiRequestError | null;
  activeDataSources: string[];
  sourceError: ApiRequestError | null;
  reload: () => Promise<void>;
  sourceContext: SourceContext | null;
  sourceRevision: number;
  sourceChoices: ContextSource[];
  sourceSelectionState: "pending" | "unconfirmed" | null;
  selectSource: (sourceType: string, sourceId: string | null) => Promise<void>;
}
export interface ContextSource { source_type: string; source_id: string; dataset_id: string | null; display_name: string; provider: string | null; status: string; active: boolean; enabled: boolean; }
export interface SourceContext { state: string; source_type: string | null; source_id: string | null; sources: ContextSource[]; }
const namesForContext = (context: SourceContext) => context.state === "READY" ? context.sources.filter(source => context.source_type === "all" ? source.enabled : source.source_type === context.source_type && source.source_id === context.source_id).map(source => source.display_name) : [];
const sourceApiFor = (permissions: string[] | undefined) => {
  if (permissions?.includes("data:read") || permissions?.includes("data:manage")) return "/api/v1/datasets/sources";
  if (permissions?.includes("retail:read")) return "/api/v1/retail/sources";
  return null;
};
const SessionContext = createContext<SessionState | null>(null);
const unknownCredits = { remaining: null, limit: null, used: null };
const publicRoutes = new Set(["/", "/login", "/register", "/signup", "/forgot-password", "/reset-password", "/pricing", "/contact", "/privacy", "/terms", "/docs", "/trust", "/join", "/confirm-email"]);
const asError = (error: unknown) => error instanceof ApiRequestError ? error : new ApiRequestError("backend_error");

export function SessionProvider({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const [identity, setIdentity] = useState<Identity | null>(null);
  const [error, setError] = useState<ApiRequestError | null>(null);
  const [loading, setLoading] = useState(true);
  const [credits, setCredits] = useState<CreditBalanceViewModel>(unknownCredits);
  const [creditBalance, setCreditBalance] = useState<CreditBalancePayload | null>(null);
  const [creditError, setCreditError] = useState<ApiRequestError | null>(null);
  const [activeDataSources, setActiveDataSources] = useState<string[]>([]);
  const [sourceError, setSourceError] = useState<ApiRequestError | null>(null);
  const [sourceContext, setSourceContext] = useState<SourceContext | null>(null);
  const [sourceChoices, setSourceChoices] = useState<ContextSource[]>([]);
  const [sourceRevision, setSourceRevision] = useState(0);
  const [sourceSelectionState, setSourceSelectionState] = useState<SessionState["sourceSelectionState"]>(null);
  const sourceRequest = useRef(0);
  const sourceWrite = useRef(Promise.resolve());
  const sourceWritePending = useRef(false);
  const sourceNeedsConfirmation = useRef(false);
  const pending = useRef<Promise<void> | null>(null);
  const creditPending = useRef<Promise<void> | null>(null);
  const creditVersion = useRef(-1);
  const revision = useRef(0);
  const tenantId = useRef<string | null>(null);
  const sourceApi = useRef<string | null>(null);
  const protectedPage = !publicRoutes.has(pathname) && !pathname.startsWith("/modules/") && !pathname.startsWith("/docs/");

  const refreshCredits = useCallback(function refreshCredits(): Promise<void> {
    if (creditPending.current) {
      if (creditVersion.current === revision.current) return creditPending.current;
      return creditPending.current.then(() => refreshCredits());
    }
    const version = revision.current;
    creditVersion.current = version;
    creditPending.current = (async () => {
      try {
        const response = await apiFetch("/api/v1/billing/ai-credits");
        const payload = await response.json();
        if (version !== revision.current) return;
        setCredits(creditBalanceViewModel(payload));
        setCreditBalance(payload);
        setCreditError(null);
      } catch (error) {
        if (version === revision.current) setCreditError(asError(error));
      } finally { creditPending.current = null; }
    })();
    return creditPending.current;
  }, []);

  const reload = useCallback(() => {
    if (pending.current) return pending.current;
    const version = revision.current;
    const sourceVersion = sourceRequest.current;
    const canConfirmSource = () => version === revision.current && sourceVersion === sourceRequest.current && !sourceWritePending.current;
    pending.current = (async () => {
      setLoading(true);
      try {
        const response = await apiFetch("/api/v1/auth/me");
        const data: Identity = await response.json();
        if (version !== revision.current) return;
        if (!data.user?.id || !data.company?.id || !data.company.name) throw new ApiRequestError("tenant_unresolved");
        if (tenantId.current !== data.company.id) {
          setSourceChoices([]);
          setCredits(unknownCredits); setCreditBalance(null); setActiveDataSources([]); setSourceContext(null);
          tenantId.current = data.company.id;
        }
        setIdentity(data); setError(null);
        sourceApi.current = sourceApiFor(data.user.permissions);
        if (typeof window !== "undefined" && data.company.preferred_language) {
          window.dispatchEvent(new CustomEvent("avenqo:company-preferred-language", { detail: data.company.preferred_language }));
        }
        await Promise.all([
          refreshCredits(),
          (async () => {
            if (!sourceApi.current) {
              if (canConfirmSource()) {
                setSourceChoices([]);
                setActiveDataSources([]);
                setSourceContext(null);
                setSourceError(null);
              }
              return;
            }
            try {
              const response = await apiFetch(sourceApi.current);
              const sources: { display_name: string; enabled: boolean }[] = await response.json();
              if (canConfirmSource()) {
                setActiveDataSources(sources.filter(source => source.enabled).map(source => source.display_name));
                setSourceError(null);
              }
              try {
                const contextResponse = await apiFetch(`${sourceApi.current}/context`);
                const context = await contextResponse.json();
                if (canConfirmSource() && context && !Array.isArray(context) && Array.isArray(context.sources)) {
                  setSourceContext(context);
                  setSourceChoices(context.sources);
                  setActiveDataSources(namesForContext(context));
                  setSourceSelectionState(null);
                  if (sourceNeedsConfirmation.current) {
                    sourceNeedsConfirmation.current = false;
                    setSourceRevision(value => value + 1);
                  }
                }
              } catch {
                if (canConfirmSource()) setSourceContext(null);
              }
            } catch (error) {
              if (canConfirmSource()) setSourceError(asError(error));
            }
          })(),
        ]);
      } catch (error) {
        if (version === revision.current) setError(asError(error));
      } finally {
        if (version === revision.current) setLoading(false);
        pending.current = null;
      }
    })();
    return pending.current;
  }, [refreshCredits]);

  const selectSource = (sourceType: string, sourceId: string | null) => {
    const version = revision.current;
    const base = sourceApi.current;
    if (!base) return Promise.reject(new Error("Source selection is unavailable"));

    const request = ++sourceRequest.current;
    const isCurrent = () => version === revision.current && request === sourceRequest.current;
    sourceWritePending.current = true;
    sourceNeedsConfirmation.current = true;
    setSourceSelectionState("pending");
    setSourceContext(null);
    setActiveDataSources([]);
    setSourceError(null);
    setSourceRevision(value => value + 1);

    const work = sourceWrite.current.then(async () => {
      if (!isCurrent()) return;
      try {
        await apiFetch(`${base}/active`, {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ source_type: sourceType, source_id: sourceId }),
        });
        if (!isCurrent()) return;
        const response = await apiFetch(`${base}/context`);
        const context: SourceContext = await response.json();
        if (!isCurrent()) return;
        if (!Array.isArray(context?.sources) || context.source_type !== sourceType || context.source_id !== sourceId) {
          throw new Error("Requested source could not be confirmed");
        }
        setSourceContext(context);
        setSourceChoices(context.sources);
        setActiveDataSources(namesForContext(context));
        setSourceSelectionState(null);
        sourceNeedsConfirmation.current = false;
        setSourceRevision(value => value + 1);
        window.dispatchEvent(new Event("avenqo:sources-changed"));
      } catch (error) {
        if (!isCurrent()) return;
        setSourceSelectionState("unconfirmed");
        setSourceError(asError(error));
        throw error;
      } finally {
        if (isCurrent()) sourceWritePending.current = false;
      }
    });
    sourceWrite.current = work.catch(() => {});
    return work;
  };

  useEffect(() => {
    if (protectedPage && !identity && !error) void reload();
  }, [protectedPage, identity, error, reload]);

  useEffect(() => {
    if (!protectedPage) return;
    const expired = () => { revision.current++; sourceWritePending.current = false; sourceNeedsConfirmation.current = false; setSourceSelectionState(null); setSourceChoices([]); tenantId.current = null; setIdentity(null); setCredits(unknownCredits); setCreditBalance(null); setActiveDataSources([]); setSourceContext(null); setCreditError(null); setSourceError(null); setError(new ApiRequestError("session_expired")); setLoading(false); };
    const changed = () => {
      revision.current++; sourceWritePending.current = false; sourceNeedsConfirmation.current = false; setSourceSelectionState(null); setSourceChoices([]); tenantId.current = null;
      setIdentity(null); setCredits(unknownCredits); setCreditBalance(null); setActiveDataSources([]); setCreditError(null); setSourceError(null); setError(null);
      setSourceContext(null); setSourceRevision(value => value + 1);
      const previous = pending.current;
      if (previous) void previous.finally(() => { void reload(); });
      else void reload();
    };
    const creditUpdated = () => { if (document.visibilityState !== "hidden" && tenantId.current) void refreshCredits(); };
    const channel = typeof BroadcastChannel !== "undefined" ? new BroadcastChannel("avenqo-session") : null;
    if (channel) channel.onmessage = changed;
    window.addEventListener("avenqo:session-expired", expired);
    window.addEventListener("avenqo:ai-credits-updated", creditUpdated);
    window.addEventListener("focus", creditUpdated);
    document.addEventListener("visibilitychange", creditUpdated);
    const timer = window.setInterval(creditUpdated, 5_000);
    return () => { channel?.close(); window.clearInterval(timer); window.removeEventListener("focus", creditUpdated); document.removeEventListener("visibilitychange", creditUpdated); window.removeEventListener("avenqo:session-expired", expired); window.removeEventListener("avenqo:ai-credits-updated", creditUpdated); };
  }, [protectedPage, reload, refreshCredits]);

  return <SessionContext.Provider value={{ identity, error, loading, credits, creditBalance, creditError, activeDataSources, sourceError, reload, sourceContext, sourceRevision, sourceChoices, sourceSelectionState, selectSource }}>{children}</SessionContext.Provider>;
}

export function useSession() {
  const session = useContext(SessionContext);
  if (!session) throw new Error("SessionProvider required");
  return session;
}

export function useOptionalSession() {
  return useContext(SessionContext);
}
