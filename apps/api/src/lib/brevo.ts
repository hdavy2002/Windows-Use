import type { Env } from "../types";

export const EMAIL_TEMPLATES = {
  WELCOME:             1,
  USAGE_80_PERCENT:    2,
  USAGE_LIMIT_REACHED: 3,
  PLAN_UPGRADED:       4,
  PLAN_DOWNGRADED:     5,
  PAYMENT_FAILED:      6,
  WEEKLY_REPORT:       7,
  BILLING_REMINDER:    8,
} as const;

export async function sendEmail(
  env: Env,
  to: { email: string; name: string },
  templateId: number,
  params: Record<string, string | number>
) {
  const res = await fetch("https://api.brevo.com/v3/smtp/email", {
    method: "POST",
    headers: {
      "api-key": env.BREVO_API_KEY,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      to: [to],
      templateId,
      params,
    }),
  });

  if (!res.ok) {
    console.error("Brevo send failed", await res.text());
  }
}
