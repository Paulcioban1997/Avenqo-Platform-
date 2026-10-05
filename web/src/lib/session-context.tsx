"use client";

import { createContext, useCallback, useContext, useEffect, useRef, useState, type ReactNode } from "react";
import { usePathname } from "next/navigation";
import { apiFetch, ApiRequestError } from "./api-request";
import { creditBalanceViewModel, type CreditBalanceViewModel } from "./credit-balance";

export interface OrganizationItem {
  id: string; name: string; slug: string; subscription_plan: string; role: string; is_current: boolean;
}
interface Identity {
  user: { id: string; first_name: string; last_name: string; job_title?: string; role: string; is_platform_admin: boolean };
  company: { id: string; name: string; subscription_plan: string };
  organizations: OrganizationItem[];
}
interface SessionState {
  identity: Identity | null;
  error: ApiRequestError | null;
  loading: boolean;
  credits: CreditBalanceViewModel;
  creditError: ApiRequestError | null;
  activeDataSources: string[];
  sourceError: ApiRequestError | null;
  reload: () => Promise<void>;
  sourceContext: SourceContext | null;
  sourceRevision: number;
  selectSource: (sourceType: string, sourceId: string | null) => Promise<void>;
}
export interface ContextSource { source_type: string; source_id: string; dataset_id: string | null; display_name: string; provider: string | null; status: string; active: boolean; enabled: boolean; }
export interface SourceContext { state: string; source_type: string | null; source_id: string | null; sources: ContextSource[]; }
const namesForContext = (context: SourceContext) => context.state === "READY" ? context.sources.filter(source => context.source_type === "all" ? source.enabled : source.source_type === context.source_type && source.source_id === context.source_id).map(source => source.display_name) : [];
const SessionContext = createContext<SessionState | null>(null);
const unknownCredits = { remaining: null, limit: null, used: null };
const publicRoutes = new Set(["/", "/login", "/register", "/signup", "/forgot-password", "/reset-password", "/pricing", "/contact", "/privacy", "/terms", "/docs"]);
const asError = (error: unknown) => error instanceof ApiRequestError ? error : new ApiRequestError("backend_error");

export function SessionProvider({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const [identity, setIdentity] = useState<Identity | null>(null);
  const [error, setError] = useState<ApiRequestError | null>(null);
  const [loading, setLoading] = useState(true);
  const [credits, setCredits] = useState<CreditBalanceViewModel>(unknownCredits);
  const [creditError, setCreditError] = useState<ApiRequestError | null>(null);
  const [activeDataSources, setActiveDataSources] = useState<string[]>([]);
  const [sourceError, setSourceError] = useState<ApiRequestError | null>(null);
  const [sourceContext, setSourceContext] = useState<SourceContext | null>(null);
  const [sourceRevision, setSourceRevision] = useState(0);
  const pending = useRef<Promise<void> | null>(null);
  const creditPending = useRef<Promise<void> | null>(null);
  const creditVersion = useRef(-1);
  const revision = useRef(0);
  const tenantId = useRef<string | null>(null);
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
    pending.current = (async () => {
      setLoading(true);
      try {
        const response = await apiFetch("/api/v1/auth/me");
        const data: Identity = await response.json();
        if (version !== revision.current) return;
        if (!data.user?.id || !data.company?.id || !data.company.name) throw new ApiRequestError("tenant_unresolved");
        if (tenantId.current !== data.company.id) {
          setCredits(unknownCredits); setActiveDataSources([]); setSourceContext(null);
          tenantId.current = data.company.id;
        }
        setIdentity(data); setError(null);
        await Promise.all([
          refreshCredits(),
          (async () => {
            try {
              const response = await apiFetch("/api/v1/retail/sources");
              const sources: { display_name: string; enabled: boolean }[] = await response.json();
              if (version === revision.current) {
                setActiveDataSources(sources.filter(source => source.enabled).map(source => source.display_name));
                setSourceError(null);
              }
              const contextResponse = await apiFetch("/api/v1/retail/sources/context");
              const context = await contextResponse.json();
              if (version === revision.current && context && !Array.isArray(context) && Array.isArray(context.sources)) { setSourceContext(context); setActiveDataSources(namesForContext(context)); }
            } catch (error) {
              if (version === revision.current) setSourceError(asError(error));
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

  const selectSource = async (sourceType: string, sourceId: string | null) => {
    const version = revision.current;
    await apiFetch("/api/v1/retail/sources/active", { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ source_type: sourceType, source_id: sourceId }) });
    const response = await apiFetch("/api/v1/retail/sources/context");
    const context = await response.json();
    if (version !== revision.current) return;
    setSourceContext(context); setSourceError(null); setSourceRevision(value => value + 1);
    setActiveDataSources(namesForContext(context));
    window.dispatchEvent(new Event("avenqo:sources-changed"));
  };

  useEffect(() => {
    if (protectedPage && !identity && !error) void reload();
  }, [protectedPage, identity, error, reload]);

  useEffect(() => {
    if (!protectedPage) return;
    const expired = () => { revision.current++; setIdentity(null); setCredits(unknownCredits); setActiveDataSources([]); setSourceContext(null); setCreditError(null); setSourceError(null); setError(new ApiRequestError("session_expired")); setLoading(false); };
    const changed = () => {
      revision.current++; tenantId.current = null;
      setIdentity(null); setCredits(unknownCredits); setActiveDataSources([]); setCreditError(null); setSourceError(null); setError(null);
      setSourceContext(null); setSourceRevision(value => value + 1);
      const previous = pending.current;
      if (previous) void previous.finally(() => { void reload(); });
      else void reload();
    };
    const creditUpdated = () => { void refreshCredits(); };
    const channel = typeof BroadcastChannel !== "undefined" ? new BroadcastChannel("avenqo-session") : null;
    if (channel) channel.onmessage = changed;
    window.addEventListener("avenqo:session-expired", expired);
    window.addEventListener("avenqo:ai-credits-updated", creditUpdated);
    const timer = window.setInterval(creditUpdated, 30_000);
    return () => { channel?.close(); window.clearInterval(timer); window.removeEventListener("avenqo:session-expired", expired); window.removeEventListener("avenqo:ai-credits-updated", creditUpdated); };
  }, [protectedPage, reload, refreshCredits]);

  return <SessionContext.Provider value={{ identity, error, loading, credits, creditError, activeDataSources, sourceError, reload, sourceContext, sourceRevision, selectSource }}>{children}</SessionContext.Provider>;
}

export function useSession() {
  const session = useContext(SessionContext);
  if (!session) throw new Error("SessionProvider required");
  return session;
}
