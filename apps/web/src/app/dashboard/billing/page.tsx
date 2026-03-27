"use client";

import { useEffect, useState } from "react";
import { useAuth } from "@clerk/nextjs";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { api } from "@/lib/api-client";

const PLANS = {
  free: {
    name: "Free",
    price: "£0 / mo",
    color: "border-[#6b7899] text-[#6b7899]",
    features: [
      "100 AI calls per day",
      "Chat mode only",
      "Desktop app access",
      "Basic file tools",
    ],
    missing: ["Live AI mode", "Gmail & Outlook connectors", "QuickBooks & Opera PMS"],
  },
  pro: {
    name: "Pro",
    price: "Contact us",
    color: "border-[#4f8ef7] text-[#4f8ef7]",
    features: [
      "Unlimited AI calls",
      "Chat + Live AI mode",
      "All MCP connectors (Gmail, Outlook, QuickBooks)",
      "Priority support",
    ],
    missing: ["Fleet management", "Audit logs"],
  },
  corporate: {
    name: "Corporate",
    price: "Contact us",
    color: "border-[#22d3a5] text-[#22d3a5]",
    features: [
      "Everything in Pro",
      "Fleet management & remote actions",
      "Audit logs",
      "Opera PMS connector",
      "Dedicated support",
    ],
    missing: [],
  },
} as const;

type Plan = keyof typeof PLANS;

export default function BillingPage() {
  const { getToken } = useAuth();
  const [user, setUser] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [upgrading, setUpgrading] = useState<string | null>(null);
  const [toastMsg, setToastMsg] = useState<string | null>(null);

  useEffect(() => {
    (async () => {
      const token = await getToken();
      if (!token) return;
      const data = await api.users.me(token).catch(() => null);
      setUser(data?.user ?? null);
      setLoading(false);
    })();
  }, [getToken]);

  // Show toast from Stripe redirect
  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    if (params.get("success") === "1") setToastMsg("Plan upgraded successfully!");
    if (params.get("cancelled") === "1") setToastMsg("Checkout cancelled.");
  }, []);

  async function handleUpgrade(plan: "pro" | "corporate") {
    setUpgrading(plan);
    try {
      const token = await getToken();
      if (!token) return;
      const { url } = await api.billing.checkout(plan, token);
      if (url) window.location.href = url;
    } catch {
      setToastMsg("Failed to start checkout. Please try again.");
    } finally {
      setUpgrading(null);
    }
  }

  async function handlePortal() {
    setUpgrading("portal");
    try {
      const token = await getToken();
      if (!token) return;
      const { url } = await api.billing.portal(token);
      if (url) window.location.href = url;
    } catch {
      setToastMsg("No billing account found. Subscribe to a plan first.");
    } finally {
      setUpgrading(null);
    }
  }

  if (loading) {
    return (
      <div className="animate-pulse space-y-4">
        <div className="h-8 w-48 bg-[#1c2132] rounded" />
        <div className="h-48 bg-[#1c2132] rounded-lg" />
      </div>
    );
  }

  const currentPlan: Plan = (user?.plan as Plan) ?? "free";
  const planInfo = PLANS[currentPlan];

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold">Billing</h1>
          <p className="text-[#6b7899] mt-1">Manage your plan and subscription.</p>
        </div>
        {currentPlan !== "free" && (
          <button
            onClick={handlePortal}
            disabled={upgrading === "portal"}
            className="px-4 py-2 text-sm rounded-lg border border-[#1c2132] text-[#6b7899] hover:text-[#e2e8f8] hover:border-[#6b7899] transition-colors disabled:opacity-50"
          >
            {upgrading === "portal" ? "Loading…" : "Manage subscription"}
          </button>
        )}
      </div>

      {toastMsg && (
        <div className="mb-6 p-4 rounded-lg bg-[#111318] border border-[#1c2132] text-[#e2e8f8] text-sm">
          {toastMsg}
        </div>
      )}

      {/* Current plan card */}
      <Card className="bg-[#111318] border-[#1c2132] mb-8">
        <CardHeader className="pb-2">
          <div className="flex items-center gap-3">
            <CardTitle className="text-[#e2e8f8]">Current plan</CardTitle>
            <Badge variant="outline" className={planInfo.color}>
              {planInfo.name}
            </Badge>
          </div>
        </CardHeader>
        <CardContent>
          <ul className="space-y-2 mt-2">
            {planInfo.features.map((f) => (
              <li key={f} className="flex items-center gap-2 text-sm text-[#e2e8f8]">
                <span className="text-[#22d3a5]">✓</span> {f}
              </li>
            ))}
            {planInfo.missing.map((f) => (
              <li key={f} className="flex items-center gap-2 text-sm text-[#6b7899]">
                <span>✗</span> {f}
              </li>
            ))}
          </ul>
        </CardContent>
      </Card>

      {/* Upgrade options */}
      {currentPlan === "free" && (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {/* Pro */}
          <Card className="bg-[#111318] border-[#4f8ef7]">
            <CardHeader>
              <CardTitle className="text-[#4f8ef7]">Pro</CardTitle>
              <p className="text-[#6b7899] text-sm">{PLANS.pro.price}</p>
            </CardHeader>
            <CardContent>
              <ul className="space-y-2 mb-4">
                {PLANS.pro.features.map((f) => (
                  <li key={f} className="flex items-center gap-2 text-sm text-[#e2e8f8]">
                    <span className="text-[#4f8ef7]">✓</span> {f}
                  </li>
                ))}
              </ul>
              <button
                onClick={() => handleUpgrade("pro")}
                disabled={upgrading === "pro"}
                className="w-full py-2 rounded-lg bg-[#4f8ef7] text-white text-sm font-medium hover:bg-[#3a7de8] transition-colors disabled:opacity-50"
              >
                {upgrading === "pro" ? "Redirecting…" : "Upgrade to Pro"}
              </button>
            </CardContent>
          </Card>

          {/* Corporate */}
          <Card className="bg-[#111318] border-[#22d3a5]">
            <CardHeader>
              <CardTitle className="text-[#22d3a5]">Corporate</CardTitle>
              <p className="text-[#6b7899] text-sm">{PLANS.corporate.price}</p>
            </CardHeader>
            <CardContent>
              <ul className="space-y-2 mb-4">
                {PLANS.corporate.features.map((f) => (
                  <li key={f} className="flex items-center gap-2 text-sm text-[#e2e8f8]">
                    <span className="text-[#22d3a5]">✓</span> {f}
                  </li>
                ))}
              </ul>
              <button
                onClick={() => handleUpgrade("corporate")}
                disabled={upgrading === "corporate"}
                className="w-full py-2 rounded-lg bg-[#22d3a5] text-[#0a0e1a] text-sm font-medium hover:bg-[#1ab890] transition-colors disabled:opacity-50"
              >
                {upgrading === "corporate" ? "Redirecting…" : "Upgrade to Corporate"}
              </button>
            </CardContent>
          </Card>
        </div>
      )}

      {currentPlan === "pro" && (
        <Card className="bg-[#111318] border-[#22d3a5]">
          <CardHeader>
            <CardTitle className="text-[#22d3a5]">Corporate</CardTitle>
            <p className="text-[#6b7899] text-sm">{PLANS.corporate.price}</p>
          </CardHeader>
          <CardContent>
            <ul className="space-y-2 mb-4">
              {PLANS.corporate.features.map((f) => (
                <li key={f} className="flex items-center gap-2 text-sm text-[#e2e8f8]">
                  <span className="text-[#22d3a5]">✓</span> {f}
                </li>
              ))}
            </ul>
            <button
              onClick={() => handleUpgrade("corporate")}
              disabled={upgrading === "corporate"}
              className="w-full py-2 rounded-lg bg-[#22d3a5] text-[#0a0e1a] text-sm font-medium hover:bg-[#1ab890] transition-colors disabled:opacity-50"
            >
              {upgrading === "corporate" ? "Redirecting…" : "Upgrade to Corporate"}
            </button>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
