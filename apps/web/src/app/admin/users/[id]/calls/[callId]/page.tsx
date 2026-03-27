import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";

// TODO: Replace with real Neon query
const mockCall = {
  id: "call_1",
  timestamp: "2026-03-26 10:15:02",
  model: "minimax/minimax-01",
  intent: "network",
  promptTokens: 210,
  completionTokens: 85,
  totalTokens: 340,
  memoryTokensInjected: 45,
  systemTokens: 80,
  costUsd: 0.0012,
  latencyMs: 1200,
  wasCacheHit: false,
  capabilityUsed: "network",
  mcpToolsCalled: ["execute_command", "read_file"],
};

export default async function CallDetailPage({ params }: { params: Promise<{ id: string; callId: string }> }) {
  const { id, callId } = await params;
  const c = mockCall;
  return (
    <div>
      <p className="text-[#6b7899] mb-1 text-sm">User: {id} → Call: {callId}</p>
      <h1 className="text-2xl font-bold mb-6">Call Detail</h1>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-8">
        <Card className="bg-[#111318] border-[#1c2132]">
          <CardHeader className="pb-1"><CardTitle className="text-xs text-[#6b7899]">Model</CardTitle></CardHeader>
          <CardContent><div className="text-sm font-mono text-[#e2e8f8]">{c.model}</div></CardContent>
        </Card>
        <Card className="bg-[#111318] border-[#1c2132]">
          <CardHeader className="pb-1"><CardTitle className="text-xs text-[#6b7899]">Intent</CardTitle></CardHeader>
          <CardContent><Badge className="bg-[#4f8ef7]/10 text-[#4f8ef7] border-[#4f8ef7]/30">{c.intent}</Badge></CardContent>
        </Card>
        <Card className="bg-[#111318] border-[#1c2132]">
          <CardHeader className="pb-1"><CardTitle className="text-xs text-[#6b7899]">Cost</CardTitle></CardHeader>
          <CardContent><div className="text-lg font-bold text-[#22d3a5]">${c.costUsd.toFixed(4)}</div></CardContent>
        </Card>
        <Card className="bg-[#111318] border-[#1c2132]">
          <CardHeader className="pb-1"><CardTitle className="text-xs text-[#6b7899]">Latency</CardTitle></CardHeader>
          <CardContent><div className="text-lg font-bold text-[#e2e8f8]">{c.latencyMs}ms</div></CardContent>
        </Card>
      </div>

      {/* Token Breakdown */}
      <h2 className="text-lg font-semibold mb-4">Token Breakdown</h2>
      <div className="grid grid-cols-5 gap-3 mb-8">
        {[
          { label: "Prompt", val: c.promptTokens, color: "#4f8ef7" },
          { label: "Completion", val: c.completionTokens, color: "#22d3a5" },
          { label: "System", val: c.systemTokens, color: "#f5c542" },
          { label: "Memory Injected", val: c.memoryTokensInjected, color: "#7c5cfc" },
          { label: "Total", val: c.totalTokens, color: "#e2e8f8" },
        ].map((t) => (
          <Card key={t.label} className="bg-[#111318] border-[#1c2132]">
            <CardHeader className="pb-1"><CardTitle className="text-xs text-[#6b7899]">{t.label}</CardTitle></CardHeader>
            <CardContent><div className="text-xl font-bold" style={{ color: t.color }}>{t.val}</div></CardContent>
          </Card>
        ))}
      </div>

      {/* Metadata */}
      <h2 className="text-lg font-semibold mb-4">Metadata</h2>
      <div className="rounded-lg border border-[#1c2132] bg-[#111318] p-5 space-y-3 text-sm">
        <div className="flex justify-between"><span className="text-[#6b7899]">Timestamp</span><span>{c.timestamp}</span></div>
        <div className="flex justify-between"><span className="text-[#6b7899]">Cache Hit</span><span>{c.wasCacheHit ? "✅ Yes" : "❌ No"}</span></div>
        <div className="flex justify-between"><span className="text-[#6b7899]">Capability</span><span className="text-[#4f8ef7]">{c.capabilityUsed || "—"}</span></div>
        <div className="flex justify-between">
          <span className="text-[#6b7899]">MCP Tools Called</span>
          <span className="font-mono text-xs">{c.mcpToolsCalled.join(", ")}</span>
        </div>
      </div>
    </div>
  );
}
