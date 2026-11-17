const PRODUCTION_SITE = "https://avenqo.ca";

type Env = Record<string, string | undefined>;

export function isSandboxFrontend(
  env: Env = process.env as Env,
): boolean {
  const value = (
    env.AVENQO_ENVIRONMENT ??
    env.NEXT_PUBLIC_AVENQO_ENVIRONMENT ??
    ""
  ).toLowerCase();
  return value === "sandbox";
}

/** Public site origin. Sandbox never canonicalizes to avenqo.ca. */
export function resolvePublicSiteUrl(env: Env = process.env as Env): string {
  if (!isSandboxFrontend(env)) return PRODUCTION_SITE;
  const candidate = (env.AVENQO_PUBLIC_URL ?? env.RENDER_EXTERNAL_URL ?? "")
    .trim()
    .replace(/\/$/, "");
  try {
    const url = new URL(candidate);
    const host = url.hostname.toLowerCase();
    if (
      url.protocol === "https:" &&
      host !== "avenqo.ca" &&
      !host.endsWith(".avenqo.ca") &&
      host !== "api.avenqo.ca"
    ) {
      return url.origin;
    }
  } catch {
    // No public sandbox URL yet. Keep metadata off the production domain.
  }
  return "http://127.0.0.1:3000";
}
