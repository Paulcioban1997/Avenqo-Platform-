export const ENTERPRISE_QUOTE_RECIPIENTS = [
  "info@avenqo.ca",
  "paulmircea15@gmail.com",
] as const;

export const RESEND_EMAIL_API_URL = "https://api.resend.com/emails";

export type QuoteMailPayload = {
  to: string[];
  subject: string;
  text: string;
  html: string;
  idempotencyKey: string;
};

export type QuoteMailResult = {
  id: string;
};

const TEMPORARY_STATUS = new Set([408, 409, 425, 429, 500, 502, 503, 504]);

export class QuoteMailError extends Error {
  readonly status: number;
  readonly temporary: boolean;

  constructor(message: string, status: number, temporary: boolean) {
    super(message);
    this.status = status;
    this.temporary = temporary;
  }
}

export function quoteRecipients(): string[] {
  const configured = (process.env.AVENQO_ENTERPRISE_QUOTE_RECIPIENTS || "")
    .split(",")
    .map((item) => item.trim().toLowerCase())
    .filter(Boolean);
  return configured.length ? configured : [...ENTERPRISE_QUOTE_RECIPIENTS];
}

export function resendApiKey(): string | undefined {
  return process.env.RESEND_API_KEY || process.env.EMAIL_API_KEY || undefined;
}

export async function sendResendEmail(
  payload: QuoteMailPayload,
  fetchImpl: typeof fetch = fetch,
): Promise<QuoteMailResult> {
  const apiKey = resendApiKey();
  if (!apiKey) {
    throw new QuoteMailError("Transactional email API is not configured", 503, false);
  }
  const response = await fetchImpl(RESEND_EMAIL_API_URL, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${apiKey}`,
      "Content-Type": "application/json",
      "Idempotency-Key": payload.idempotencyKey.slice(0, 256),
    },
    body: JSON.stringify({
      from: process.env.EMAIL_FROM_EMAIL
        ? `${process.env.EMAIL_FROM_NAME || "Avenqo"} <${process.env.EMAIL_FROM_EMAIL}>`
        : "Avenqo <noreply@avenqo.ca>",
      to: payload.to,
      subject: payload.subject,
      text: payload.text,
      html: payload.html,
    }),
  });
  const raw = await response.text();
  if (!response.ok) {
    throw new QuoteMailError(
      `Transactional email API rejected the request (${response.status})`,
      response.status,
      TEMPORARY_STATUS.has(response.status),
    );
  }
  let parsed: { id?: string } = {};
  try {
    parsed = raw ? (JSON.parse(raw) as { id?: string }) : {};
  } catch {
    throw new QuoteMailError("Transactional email API returned an invalid payload", 502, false);
  }
  if (!parsed.id) {
    throw new QuoteMailError("Transactional email API did not confirm a message id", 502, false);
  }
  return { id: parsed.id };
}

export function ownerNotificationContent(input: {
  referenceId: string;
  name: string;
  company: string;
  email: string;
  phone?: string;
  need?: string;
  message: string;
  submittedAt: string;
}): { subject: string; text: string; html: string } {
  const text = [
    `Référence : ${input.referenceId}`,
    "Source : landing",
    `Nom : ${input.name}`,
    `Entreprise : ${input.company}`,
    `Courriel : ${input.email}`,
    `Téléphone : ${input.phone || "Non renseigné"}`,
    `Besoins : ${input.need || "Non renseigné"}`,
    `Date de soumission : ${input.submittedAt}`,
    "",
    "Message :",
    input.message,
  ].join("\n");
  return {
    subject: `Nouvelle demande Enterprise ${input.referenceId} — ${input.company}`,
    text,
    html: `<pre>${text}</pre>`,
  };
}

export function acknowledgmentContent(input: { referenceId: string; name: string }): {
  subject: string;
  text: string;
  html: string;
} {
  const text = [
    `Bonjour ${input.name},`,
    "",
    "Nous avons bien reçu votre demande de devis Enterprise.",
    `Référence : ${input.referenceId}`,
    "Notre équipe vous répondra sous 24 heures ouvrées.",
    "",
    "Avenqo",
  ].join("\n");
  return {
    subject: `Avenqo a bien reçu votre demande ${input.referenceId}`,
    text,
    html: `<p>${text.replace(/\n/g, "<br>")}</p>`,
  };
}
