import { beforeEach, describe, expect, it, vi } from "vitest";
import {
  ENTERPRISE_QUOTE_RECIPIENTS,
  QuoteMailError,
  acknowledgmentContent,
  ownerNotificationContent,
  sendResendEmail,
} from "@/lib/enterprise-quote-mailer";
import { POST } from "@/app/api/contact/route";

function jsonRequest(body: unknown, headers?: HeadersInit) {
  return new Request("http://localhost/api/contact", {
    method: "POST",
    headers: { "content-type": "application/json", ...(headers || {}) },
    body: JSON.stringify(body),
  });
}

describe("enterprise quote mailer", () => {
  beforeEach(() => {
    process.env.RESEND_API_KEY = "re_test_key";
    process.env.BACKEND_API_URL = "http://backend.test";
    vi.unstubAllGlobals();
  });

  it("requires a provider message id and both default recipients", async () => {
    const fetchImpl = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      text: async () => JSON.stringify({ id: "msg_1" }),
    });
    const result = await sendResendEmail(
      {
        to: [...ENTERPRISE_QUOTE_RECIPIENTS],
        subject: "test",
        text: "body",
        html: "<p>body</p>",
        idempotencyKey: "eq-test-owner-info",
      },
      fetchImpl as unknown as typeof fetch,
    );
    expect(result.id).toBe("msg_1");
    expect(fetchImpl).toHaveBeenCalledWith(
      "https://api.resend.com/emails",
      expect.objectContaining({
        method: "POST",
        headers: expect.objectContaining({
          Authorization: "Bearer re_test_key",
          "Idempotency-Key": "eq-test-owner-info",
        }),
      }),
    );
  });

  it("treats a negative provider response as a hard failure", async () => {
    const fetchImpl = vi.fn().mockResolvedValue({
      ok: false,
      status: 401,
      text: async () => JSON.stringify({ message: "invalid" }),
    });
    await expect(
      sendResendEmail(
        { to: ["info@avenqo.ca"], subject: "x", text: "x", html: "<p>x</p>", idempotencyKey: "k" },
        fetchImpl as unknown as typeof fetch,
      ),
    ).rejects.toBeInstanceOf(QuoteMailError);
  });

  it("includes the required lead fields in the owner email", () => {
    const content = ownerNotificationContent({
      referenceId: "EQ-TEST",
      name: "Camille Roy",
      company: "Nordic Garage",
      email: "camille@nordicgarage.ca",
      phone: "+1 514 555 0101",
      need: "Voice + CRM",
      message: "Trois ateliers.",
      submittedAt: "2026-10-10T23:00:00Z",
    });
    expect(content.text).toContain("Camille Roy");
    expect(content.text).toContain("Nordic Garage");
    expect(content.text).toContain("camille@nordicgarage.ca");
    expect(content.text).toContain("+1 514 555 0101");
    expect(content.text).toContain("Voice + CRM");
    expect(content.text).toContain("2026-10-10T23:00:00Z");
    expect(acknowledgmentContent({ referenceId: "EQ-TEST", name: "Camille" }).subject).toContain("EQ-TEST");
  });
});

describe("contact route", () => {
  const payload = {
    name: "Camille Roy",
    email: "camille@nordicgarage.ca",
    company: "Nordic Garage",
    phone: "+1 514 555 0101",
    need: "Devis Entreprise",
    message: "Nous voulons un devis Enterprise pour trois ateliers.",
  };

  beforeEach(() => {
    process.env.RESEND_API_KEY = "re_test_key";
    process.env.BACKEND_API_URL = "http://backend.test";
  });

  it("does not claim success when Resend rejects the send", async () => {
    const fetchImpl = vi.fn(async (url: string) => {
      if (String(url).includes("/api/v1/public/enterprise-quote") && !String(url).includes("/deliveries")) {
        return {
          ok: false,
          status: 503,
          json: async () => ({
            detail: { reference_id: "EQ-FAIL1", message: "not confirmed", notification_status: "pending" },
          }),
        };
      }
      return {
        ok: false,
        status: 401,
        text: async () => JSON.stringify({ message: "invalid" }),
        json: async () => ({ message: "invalid" }),
      };
    });
    vi.stubGlobal("fetch", fetchImpl);
    const response = await POST(jsonRequest(payload) as never);
    const body = await response.json();
    expect(response.status).toBeGreaterThanOrEqual(400);
    expect(body.success).not.toBe(true);
  });

  it("sends owner emails to both required recipients after persist", async () => {
    const calls: Array<{ url: string; init?: RequestInit }> = [];
    vi.stubGlobal("fetch", async (url: string, init?: RequestInit) => {
      calls.push({ url: String(url), init });
      if (String(url).includes("/deliveries")) {
        return { ok: true, status: 200, json: async () => ({ notification_status: "sent" }), text: async () => "{}" };
      }
      if (String(url).includes("/api/v1/public/enterprise-quote")) {
        return {
          ok: false,
          status: 503,
          json: async () => ({
            detail: { reference_id: "EQ-OK12", notification_status: "pending", message: "pending" },
          }),
        };
      }
      return { ok: true, status: 200, text: async () => JSON.stringify({ id: `msg_${calls.length}` }) };
    });
    const response = await POST(jsonRequest(payload) as never);
    const body = await response.json();
    expect(response.status).toBe(200);
    expect(body.success).toBe(true);
    expect(body.reference_id).toBe("EQ-OK12");
    const resendBodies = calls
      .filter((item) => item.url.includes("api.resend.com"))
      .map((item) => JSON.parse(String(item.init?.body || "{}")));
    const ownerMail = resendBodies.find((item) => Array.isArray(item.to) && item.to.includes("info@avenqo.ca"));
    expect(ownerMail?.to).toEqual(["info@avenqo.ca", "paulmircea15@gmail.com"]);
    expect(ownerMail?.text).toContain("EQ-OK12");
    expect(ownerMail?.text).toContain("Nordic Garage");
    expect(ownerMail?.text).toContain("Camille Roy");
  });

  it("rejects a honeypot submission before any send", async () => {
    const fetchImpl = vi.fn();
    vi.stubGlobal("fetch", fetchImpl);
    const response = await POST(jsonRequest({ ...payload, website: "http://spam.test" }) as never);
    expect(response.status).toBe(400);
    expect(fetchImpl).not.toHaveBeenCalled();
  });
});
