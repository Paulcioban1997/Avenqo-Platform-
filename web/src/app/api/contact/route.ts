import { NextRequest, NextResponse } from "next/server";
import {
  acknowledgmentContent,
  ownerNotificationContent,
  quoteRecipients,
  resendApiKey,
  sendResendEmail,
  QuoteMailError,
} from "@/lib/enterprise-quote-mailer";

const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
const rateBuckets = new Map<string, { count: number; window: number }>();

type ContactBody = {
  name?: string;
  email?: string;
  company?: string;
  phone?: string;
  need?: string;
  message?: string;
  website?: string;
};

function clientKey(request: NextRequest): string {
  return request.headers.get("x-forwarded-for")?.split(",")[0]?.trim() || "local";
}

function allowRequest(key: string): boolean {
  const window = Math.floor(Date.now() / 60_000);
  const current = rateBuckets.get(key);
  if (!current || current.window !== window) {
    rateBuckets.set(key, { count: 1, window });
    return true;
  }
  current.count += 1;
  return current.count <= 5;
}

function backendUrl(): string {
  return (process.env.BACKEND_API_URL || process.env.BACKEND_URL || "http://127.0.0.1:8000").replace(/\/$/, "");
}

export async function POST(request: NextRequest) {
  try {
    const body = (await request.json()) as ContactBody;
    const name = String(body.name || "").trim();
    const email = String(body.email || "").trim();
    const company = String(body.company || "").trim();
    const phone = String(body.phone || "").trim();
    const need = String(body.need || "").trim();
    const message = String(body.message || "").trim();
    const website = String(body.website || "").trim();

    if (website) {
      return NextResponse.json({ detail: "La demande n'a pas pu être acceptée." }, { status: 400 });
    }
    if (!allowRequest(clientKey(request))) {
      return NextResponse.json({ detail: "Trop de demandes, veuillez réessayer plus tard." }, { status: 429 });
    }
    if (name.length < 2 || !email || !company || message.length < 10) {
      return NextResponse.json(
        { detail: "Le nom, l'entreprise, l'email et un message d'au moins 10 caractères sont requis." },
        { status: 400 },
      );
    }
    if (!EMAIL_RE.test(email)) {
      return NextResponse.json({ detail: "L'adresse email fournie n'est pas valide." }, { status: 400 });
    }

    const persist = await fetch(`${backendUrl()}/api/v1/public/enterprise-quote`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "Accept-Language": request.headers.get("accept-language") || "fr",
        "X-Forwarded-For": clientKey(request),
      },
      body: JSON.stringify({ name, email, company, phone, need, message, website }),
    });
    const persistBody = (await persist.json().catch(() => ({}))) as {
      reference_id?: string;
      notification_status?: string;
      acknowledgment_status?: string;
      detail?: string | { message?: string; reference_id?: string; notification_status?: string };
      message?: string;
    };
    const persistDetail = typeof persistBody.detail === "object" && persistBody.detail
      ? persistBody.detail
      : undefined;
    const referenceId = persistBody.reference_id || persistDetail?.reference_id;
    const notificationStatus = persistBody.notification_status || persistDetail?.notification_status;
    const persistMessage = persistDetail?.message
      || (typeof persistBody.detail === "string" ? persistBody.detail : persistBody.message);

    if (persist.ok && notificationStatus === "sent") {
      return NextResponse.json({
        success: true,
        reference_id: referenceId,
        message: persistBody.message || "Votre demande a été transmise avec succès.",
      });
    }

    if (!referenceId) {
      return NextResponse.json(
        { detail: persistMessage || "La demande n'a pas pu être enregistrée." },
        { status: persist.status === 429 ? 429 : persist.status >= 400 ? persist.status : 503 },
      );
    }

    const apiKey = resendApiKey();
    if (!apiKey) {
      return NextResponse.json(
        {
          detail:
            persistMessage ||
            "La demande a été enregistrée, mais l'envoi n'a pas été confirmé. Réessayez plus tard.",
        },
        { status: 503 },
      );
    }

    const submittedAt = new Date().toISOString();
    const recipients = quoteRecipients();
    const owner = ownerNotificationContent({
      referenceId,
      name,
      company,
      email,
      phone,
      need,
      message,
      submittedAt,
    });
    const deliveries: Array<{ kind: string; recipient: string; provider_message_id: string }> = [];
    try {
      const sent = await sendResendEmail({
        to: recipients,
        subject: owner.subject,
        text: owner.text,
        html: owner.html,
        idempotencyKey: `eq-${referenceId}-owner`,
      });
      for (const recipient of recipients) {
        deliveries.push({ kind: "owner", recipient, provider_message_id: sent.id });
      }
    } catch (error) {
      const status = error instanceof QuoteMailError && error.temporary ? 503 : 502;
      return NextResponse.json(
        { detail: "L'envoi de la demande n'a pas été confirmé par le fournisseur. Réessayez plus tard." },
        { status },
      );
    }

    const report = await fetch(
      `${backendUrl()}/api/v1/public/enterprise-quote/${referenceId}/deliveries`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ deliveries }),
      },
    );
    if (!report.ok) {
      return NextResponse.json(
        { detail: "L'envoi n'a pas pu être confirmé dans l'administration. Réessayez plus tard." },
        { status: 503 },
      );
    }

    const ack = acknowledgmentContent({ referenceId, name });
    try {
      const ackSent = await sendResendEmail({
        to: [email],
        subject: ack.subject,
        text: ack.text,
        html: ack.html,
        idempotencyKey: `eq-${referenceId}-acknowledgment-${email.toLowerCase()}`,
      });
      await fetch(`${backendUrl()}/api/v1/public/enterprise-quote/${referenceId}/deliveries`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          deliveries: [{ kind: "acknowledgment", recipient: email, provider_message_id: ackSent.id }],
        }),
      });
    } catch {
      // The request is already accepted and owner emails are confirmed.
    }

    return NextResponse.json({
      success: true,
      reference_id: referenceId,
      message: "Votre demande a été transmise avec succès. Notre équipe vous répondra sous 24h ouvrées.",
    });
  } catch {
    return NextResponse.json(
      { detail: "Une erreur est survenue lors de l'envoi de votre message." },
      { status: 500 },
    );
  }
}
