import { readFileSync, readdirSync, statSync } from "node:fs";
import { join, relative, resolve } from "node:path";

const repository = resolve(import.meta.dirname, "../..");
const technicalLiteral = /^(https?:\/\/|\/api\/|\/|#[0-9A-Fa-f]{3,8}$|[a-z0-9_./:-]+$)/;
const brandOrProtocol = /^(Avenqo|Stripe|Shopify|WooCommerce|Google Calendar|OpenAI|OAuth|REST|API|CSV|XLSX|JSON|PDF|DOCX|Parquet|CAD|USD|SMTP|Twilio|SKU|LTV)$/i;
const exactTechnicalExclusions = new Map([
  ["web/src/app/privacy/page.tsx", "Legal/privacy text requires approved legal wording."],
  ["web/src/app/terms/page.tsx", "Legal/terms text requires approved legal wording."],
  ["web/src/app/design-system/page.tsx", "Internal design-system showcase, not production application UI."],
]);

function filesUnder(root, extensions) {
  const result = [];
  for (const entry of readdirSync(root, { withFileTypes: true })) {
    if (entry.name === "node_modules" || entry.name.startsWith(".")) continue;
    const absolute = join(root, entry.name);
    if (entry.isDirectory()) result.push(...filesUnder(absolute, extensions));
    else if (extensions.has(entry.name.split(".").pop())) result.push(absolute);
  }
  return result;
}

function keep(value) {
  const text = value.trim();
  return text.length > 2 && /[A-Za-zÀ-ÿ]/u.test(text) && !technicalLiteral.test(text) && !brandOrProtocol.test(text);
}

function scanWeb() {
  const root = join(repository, "web/src");
  const candidates = [];
  for (const file of filesUnder(root, new Set(["ts", "tsx"]))) {
    const normalizedFile = file.replaceAll("\\", "/");
    const relativeFile = relative(repository, file).replaceAll("\\", "/");
    if (normalizedFile.includes("/lib/i18n/") || exactTechnicalExclusions.has(relativeFile)) continue;
    const source = readFileSync(file, "utf8");
    const patterns = [
      />\s*([A-Za-zÀ-ÿ][^<{\n]*?)\s*</gu,
      /(?:placeholder|title|aria-label|alt)\s*=\s*["']([^"']+)["']/gu,
    ];
    for (const pattern of patterns) {
      for (const match of source.matchAll(pattern)) {
        if (keep(match[1])) candidates.push({ file: relative(repository, file), value: match[1].trim() });
      }
    }
  }
  return candidates;
}

function scanFlutter() {
  const root = join(repository, "frontend/lib");
  const candidates = [];
  for (const file of filesUnder(root, new Set(["dart"]))) {
    if (file.endsWith("/i18n/translations.dart")) continue;
    const source = readFileSync(file, "utf8");
    for (const match of source.matchAll(/\b(?:Text|Tooltip|InputDecoration)\s*\(\s*["']([^"']+)["']/gu)) {
      if (/^\s*\$\{|AvenqoLocaleScope|translationsOf\(|(?:^|\W)t\.|creditsT\b|connectorHub\b/u.test(match[1])) continue;
      if (keep(match[1])) candidates.push({ file: relative(repository, file), value: match[1].trim() });
    }
  }
  return candidates;
}

function scanBackend() {
  const root = join(repository, "backend/app");
  const candidates = [];
  for (const file of filesUnder(root, new Set(["py"]))) {
    const source = readFileSync(file, "utf8");
    for (const match of source.matchAll(/(?:detail|message)\s*=\s*["']([^"']+)["']/gu)) {
      if (keep(match[1])) candidates.push({ file: relative(repository, file), value: match[1].trim() });
    }
  }
  return candidates;
}

const report = {
  exclusions: Object.fromEntries(exactTechnicalExclusions),
  web: scanWeb(),
  flutter: scanFlutter(),
  backend: scanBackend(),
};
const unresolved = report.web.length + report.flutter.length + report.backend.length;
console.log(JSON.stringify({ ...report, unresolved }, null, 2));
if (unresolved > 0) process.exitCode = 1;