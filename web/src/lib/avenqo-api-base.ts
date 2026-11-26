const PRODUCTION_API_ORIGIN = "https://api.avenqo.ca";
const SANDBOX_API_ORIGIN = "https://avenqo-platform-sandbox.up.railway.app";

function stripApiSuffix(value: string): string {
  return value.replace(/\/$/, "").replace(/\/api\/v1$/i, "");
}

export function resolveAvenqoApiOrigin(
  env: Record<string, string | undefined> = process.env as Record<string, string | undefined>,
): string {
  const explicit = stripApiSuffix(
    env.AVENQO_API_BASE_URL ??
      env.AVENQO_API_URL ??
      env.API_BASE_URL ??
      env.BACKEND_API_URL ??
      "",
  );
  const vercelEnv = (env.VERCEL_ENV ?? "").toLowerCase();
  const gitRef = env.VERCEL_GIT_COMMIT_REF ?? "";
  const appEnv = (
    env.AVENQO_ENVIRONMENT ??
    env.ENVIRONMENT ??
    env.NEXT_PUBLIC_AVENQO_ENVIRONMENT ??
    ""
  ).toLowerCase();

  // Preview and named Sandbox deployments share the same API origin for
  // Next.js rewrites, session refresh, authentication and OAuth relay.
  if (
    vercelEnv === "preview"
    || appEnv === "sandbox"
    || gitRef === "promotion/sandbox"
    || gitRef === "integration/avenqo-sandbox-latest-20261113"
  ) {
    return SANDBOX_API_ORIGIN;
  }
  if (vercelEnv === "production" || appEnv === "production") {
    return PRODUCTION_API_ORIGIN;
  }
  return explicit || "http://127.0.0.1:8000";
}

export function resolveAvenqoApiBase(
  env: Record<string, string | undefined> = process.env as Record<string, string | undefined>,
): string {
  const origin = resolveAvenqoApiOrigin(env);
  return origin.endsWith("/api/v1") ? origin : `${origin}/api/v1`;
}
