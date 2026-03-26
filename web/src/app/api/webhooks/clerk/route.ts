import { NextRequest, NextResponse } from "next/server";
import { db } from "@/db";
import { users } from "@/db/schema";

export async function POST(req: NextRequest) {
  try {
    const payload = await req.json();
    const type = payload.type;
    const data = payload.data;

    if (type === "user.created") {
      await db.insert(users).values({
        id: data.id,
        email: data.email_addresses?.[0]?.email_address || "",
        name: `${data.first_name || ""} ${data.last_name || ""}`.trim(),
        plan: "free",
        role: "user",
      }).onConflictDoNothing();
    }

    return NextResponse.json({ ok: true });
  } catch (e: any) {
    return NextResponse.json({ error: e.message }, { status: 500 });
  }
}
