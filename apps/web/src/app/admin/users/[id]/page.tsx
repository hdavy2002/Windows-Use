import Link from "next/link";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";

// TODO: Replace with Neon query by params.id
const mockCalls = [
  { id: "call_1", timestamp: "2026-03-26 10:15:02", model: "minimax-01", intent: "network", totalTokens: 340, costUsd: 0.0012, latencyMs: 1200 },
  { id: "call_2", timestamp: "2026-03-26 10:15:45", model: "llama-3.3-70b", intent: "general", totalTokens: 180, costUsd: 0.0004, latencyMs: 800 },
];

export default async function UserDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return (
    <div>
      <h1 className="text-2xl font-bold mb-2">User: {id}</h1>
      <p className="text-[#6b7899] mb-6">Detailed analytics and call history</p>

      <div className="grid grid-cols-3 gap-4 mb-8">
        <Card className="bg-[#111318] border-[#1c2132]">
          <CardHeader className="pb-2"><CardTitle className="text-sm text-[#6b7899]">Total Calls</CardTitle></CardHeader>
          <CardContent><div className="text-2xl font-bold text-[#e2e8f8]">142</div></CardContent>
        </Card>
        <Card className="bg-[#111318] border-[#1c2132]">
          <CardHeader className="pb-2"><CardTitle className="text-sm text-[#6b7899]">Total Tokens</CardTitle></CardHeader>
          <CardContent><div className="text-2xl font-bold text-[#e2e8f8]">48,320</div></CardContent>
        </Card>
        <Card className="bg-[#111318] border-[#1c2132]">
          <CardHeader className="pb-2"><CardTitle className="text-sm text-[#6b7899]">Total Cost</CardTitle></CardHeader>
          <CardContent><div className="text-2xl font-bold text-[#22d3a5]">$0.38</div></CardContent>
        </Card>
      </div>

      <h2 className="text-lg font-semibold mb-4">API Calls</h2>
      <div className="rounded-lg border border-[#1c2132] overflow-hidden">
        <Table>
          <TableHeader>
            <TableRow className="border-[#1c2132] bg-[#111318]">
              <TableHead className="text-[#6b7899]">Time</TableHead>
              <TableHead className="text-[#6b7899]">Model</TableHead>
              <TableHead className="text-[#6b7899]">Intent</TableHead>
              <TableHead className="text-[#6b7899]">Tokens</TableHead>
              <TableHead className="text-[#6b7899]">Cost</TableHead>
              <TableHead className="text-[#6b7899]">Latency</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {mockCalls.map((c) => (
              <TableRow key={c.id} className="border-[#1c2132] hover:bg-[#111318] cursor-pointer">
                <TableCell className="text-[#6b7899]">{c.timestamp}</TableCell>
                <TableCell className="text-[#e2e8f8] font-mono text-xs">{c.model}</TableCell>
                <TableCell><span className="text-[#4f8ef7]">{c.intent}</span></TableCell>
                <TableCell className="text-[#e2e8f8]">{c.totalTokens}</TableCell>
                <TableCell className="text-[#22d3a5]">${c.costUsd.toFixed(4)}</TableCell>
                <TableCell className="text-[#6b7899]">{c.latencyMs}ms</TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>
    </div>
  );
}
