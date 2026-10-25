const PRODUCTION_API_ORIGIN = "https://api.avenqo.ca";
const SANDBOX_API_ORIGIN = "https://avenqo-platform-sandbox.up.railway.app";

function stripApiSuffix(value: string): string {
  return value.replace(/\/$/, "").replace(/\/api\/v1$/i, "");
}

function isLocalhostOrigin(value: string): boolean {
  return /^https?:\/\/(localhost|127\.0\.0\.1)(:\d+)?$/i.test(stripApiSuffix(value));
}

function isProductionApiOrigin(value: string): boolean {
  return stripApiSuffix(value) === PRODUCTION_API_ORIGIN;
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

  if (vercelEnv === "production" || appEnv === "production") {
    return PRODUCTION_API_ORIGIN;
  }
  if (vercelEnv === "preview" || gitRef === "promotion/sandbox" || appEnv === "sandbox") {
    if (explicit && !isLocalhostOrigin(explicit) && !isProductionApiOrigin(explicit)) {
      return explicit;
    }
    return SANDBOX_API_ORIGIN;
  }
  return explicit || "http://127.0.0.1:8000";
}

export function resolveAvenqoApiBase(
  env: Record<string, string | undefined> = process.env as Record<string, string | undefined>,
): string {
  const origin = resolveAvenqoApiOrigin(env);
  return origin.endsWith("/api/v1") ? origin : `${origin}/api/v1`;
}
