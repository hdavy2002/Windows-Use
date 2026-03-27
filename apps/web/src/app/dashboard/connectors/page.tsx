"use client";

import { useEffect, useState, useCallback } from "react";
import { useAuth } from "@clerk/nextjs";
import { useSearchParams } from "next/navigation";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { api } from "@/lib/api-client";

interface Connector {
  id: string;
  name: string;
  icon: string;
  desc: string;
  connected: boolean;
  connectedAt: string | null;
  accountEmail: string | null;
}

export default function ConnectorsPage() {
  const { getToken } = useAuth();
  const searchParams = useSearchParams();
  const [connectors, setConnectors] = useState<Connector[]>([]);
  const [loading, setLoading] = useState(true);
  const [acting, setActing] = useState<string | null>(null);
  const [toast, setToast] = useState<{ msg: string; ok: boolean } | null>(null);

  const showToast = (msg: string, ok = true) => {
    setToast({ msg, ok });
    setTimeout(() => setToast(null), 4000);
  };

  const fetchConnectors = useCallback(async () => {
    const token = await getToken();
    if (!token) return;
    const data = await api.connectors.list(token).catch(() => null);
    if (data) setConnectors(data.connectors);
    setLoading(false);
  }, [getToken]);

  useEffect(() => {
    fetchConnectors();
  }, [fetchConnectors]);

  // Handle OAuth redirect back from Composio
  useEffect(() => {
    const connectedApp = searchParams.get("connected");
    if (!connectedApp) return;

    (async () => {
      const token = await getToken();
      if (!token) return;

      try {
        const res = await fetch(
          `${process.env.NEXT_PUBLIC_API_URL}/connectors/callback`,
          {
            method: "POST",
            headers: {
              Authorization: `Bearer ${token}`,
              "Content-Type": "application/json",
            },
            body: JSON.stringify({ app: connectedApp }),
          }
        );
        const data = await res.json() as { ok: boolean };
        if (data.ok) {
          showToast(`${connectedApp} connected successfully!`);
          await fetchConnectors();
        } else {
          showToast(`Could not verify ${connectedApp} connection.`, false);
        }
      } catch {
        showToast("Connection verification failed.", false);
      }

      // Remove query param without full reload
      window.history.replaceState({}, "", "/dashboard/connectors");
    })();
  }, [searchParams, getToken, fetchConnectors]);

  async function handleConnect(app: string) {
    setActing(app);
    try {
      const token = await getToken();
      if (!token) return;
      const { redirectUrl } = await api.connectors.connect(app, token);
      window.location.href = redirectUrl;
    } catch (e: any) {
      showToast(e.message ?? "Failed to start connection.", false);
      setActing(null);
    }
  }

  async function handleDisconnect(app: string) {
    setActing(app);
    try {
      const token = await getToken();
      if (!token) return;
      await api.connectors.disconnect(app, token);
      showToast(`${app} disconnected.`);
      await fetchConnectors();
    } catch (e: any) {
      showToast(e.message ?? "Failed to disconnect.", false);
    } finally {
      setActing(null);
    }
  }

  return (
    <div>
      <h1 className="text-2xl font-bold mb-2">Connectors</h1>
      <p className="text-[#6b7899] mb-6">
        Connect your apps to Humphi AI via Composio. Your AI can then use these services directly.
      </p>

      {toast && (
        <div
          className={`mb-6 p-4 rounded-lg border text-sm ${
            toast.ok
              ? "bg-[#22d3a5]/10 border-[#22d3a5]/30 text-[#22d3a5]"
              : "bg-[#ef4444]/10 border-[#ef4444]/30 text-[#ef4444]"
          }`}
        >
          {toast.msg}
        </div>
      )}

      {loading ? (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {[...Array(4)].map((_, i) => (
            <div key={i} className="h-36 rounded-lg bg-[#111318] border border-[#1c2132] animate-pulse" />
          ))}
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {connectors.map((c) => (
            <Card
              key={c.id}
              className={`bg-[#111318] border transition ${
                c.connected ? "border-[#22d3a5]/40" : "border-[#1c2132] hover:border-[#4f8ef7]"
              }`}
            >
              <CardHeader className="pb-2">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-3">
                    <span className="text-2xl">{c.icon}</span>
                    <CardTitle className="text-base text-[#e2e8f8]">{c.name}</CardTitle>
                  </div>
                  <span
                    className={`text-xs px-2 py-1 rounded-full ${
                      c.connected
                        ? "bg-[#22d3a5]/10 text-[#22d3a5] border border-[#22d3a5]/30"
                        : "bg-[#1c2132] text-[#6b7899]"
                    }`}
                  >
                    {c.connected ? "Connected" : "Not connected"}
                  </span>
                </div>
              </CardHeader>

              <CardContent>
                <p className="text-sm text-[#6b7899]">{c.desc}</p>

                {c.connected && c.connectedAt && (
                  <p className="text-xs text-[#6b7899] mt-1">
                    Since{" "}
                    {new Date(c.connectedAt).toLocaleDateString("en-GB", {
                      day: "2-digit",
                      month: "short",
                      year: "numeric",
                    })}
                  </p>
                )}

                <div className="mt-3">
                  {c.connected ? (
                    <button
                      onClick={() => handleDisconnect(c.id)}
                      disabled={acting === c.id}
                      className="text-sm text-[#ef4444] hover:underline disabled:opacity-50"
                    >
                      {acting === c.id ? "Disconnecting…" : "Disconnect"}
                    </button>
                  ) : (
                    <button
                      onClick={() => handleConnect(c.id)}
                      disabled={acting === c.id}
                      className="text-sm text-[#4f8ef7] hover:underline disabled:opacity-50"
                    >
                      {acting === c.id ? "Redirecting…" : "Connect →"}
                    </button>
                  )}
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}
