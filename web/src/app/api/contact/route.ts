import { NextRequest, NextResponse } from "next/server";

export async function POST(request: NextRequest) {
  try {
    const body = await request.json();
    const { name, email, company, phone, need, message } = body;

    if (!name || !email || !message) {
      return NextResponse.json(
        { detail: "Le nom, l'email et le message sont requis." },
        { status: 400 }
      );
    }

    // Basic email validation
    const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
    if (!emailRegex.test(email)) {
      return NextResponse.json(
        { detail: "L'adresse email fournie n'est pas valide." },
        { status: 400 }
      );
    }

    // Forward lead notification if email API is configured
    const resendApiKey = process.env.RESEND_API_KEY || process.env.EMAIL_API_KEY;
    const recipientEmail =
      process.env.AVENQO_OWNER_NOTIFICATION_EMAIL ||
      process.env.NOTIFICATION_EMAIL ||
      "info@avenqo.ca";

    if (resendApiKey) {
      try {
        await fetch("https://api.resend.com/emails", {
          method: "POST",
          headers: {
            Authorization: `Bearer ${resendApiKey}`,
            "Content-Type": "application/json",
          },
          body: JSON.stringify({
            from: "Avenqo Leads <noreply@avenqo.ca>",
            to: [recipientEmail],
            subject: `Nouveau lead Avenqo — ${company || name} (${need || "Contact général"})`,
            text: `Nom: ${name}\nEmail: ${email}\nEntreprise: ${company || "Non renseignée"}\nTéléphone: ${phone || "Non renseigné"}\nBesoin: ${need || "Général"}\n\nMessage:\n${message}`,
          }),
        });
      } catch (err) {
        console.error("Lead email forwarding error:", err);
      }
    }

    console.log(`[LEAD_CAPTURED] Name: ${name}, Email: ${email}, Company: ${company}, Need: ${need}`);

    return NextResponse.json({
      success: true,
      message: "Votre demande a été transmise avec succès. Notre équipe vous répondra sous 24h ouvrées.",
    });
  } catch (error) {
    console.error("Contact API error:", error);
    return NextResponse.json(
      { detail: "Une erreur est survenue lors de l'envoi de votre message." },
      { status: 500 }
    );
  }
}
