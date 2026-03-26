import { NextRequest, NextResponse } from "next/server";
import { db } from "@/db";
import { apiCalls } from "@/db/schema";

export async function POST(req: NextRequest) {
  try {
    const body = await req.json();
    await db.insert(apiCalls).values({
      userId: body.userId,
      sessionId: body.sessionId || null,
      model: body.model,
      intent: body.intent || null,
      promptTokens: body.promptTokens || 0,
      completionTokens: body.completionTokens || 0,
      totalTokens: body.totalTokens || 0,
      memoryTokensInjected: body.memoryTokensInjected || 0,
      systemTokens: body.systemTokens || 0,
      costUsd: body.costUsd?.toString() || "0",
      latencyMs: body.latencyMs || 0,
      wasCacheHit: body.wasCacheHit || false,
      capabilityUsed: body.capabilityUsed || null,
      mcpToolsCalled: body.mcpToolsCalled
        ? JSON.stringify(body.mcpToolsCalled) : null,
    });
    return NextResponse.json({ ok: true });
  } catch (e: any) {
    return NextResponse.json({ error: e.message }, { status: 500 });
  }
}
