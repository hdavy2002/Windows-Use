/**
 * mem0.ts — Per-user memory via Mem0.
 * Fetches relevant memories to inject into the system prompt,
 * and adds new memories after each assistant turn.
 */

import MemoryClient from "mem0ai";

function getClient(apiKey: string) {
  return new MemoryClient({ apiKey });
}

/** Fetch the top-N memories relevant to the current user message. */
export async function searchMemories(
  apiKey: string,
  userId: string,
  query: string,
  limit = 5
): Promise<string> {
  try {
    const client = getClient(apiKey);
    const results = await client.search(query, { user_id: userId, limit });
    if (!results || results.length === 0) return "";
    const lines = (results as Array<{ memory: string }>)
      .map((r) => `- ${r.memory}`)
      .join("\n");
    return `## REMEMBERED CONTEXT FOR THIS USER\n${lines}`;
  } catch {
    // Memory fetch failure should never block the main AI call
    return "";
  }
}

/** Add a new memory from the assistant's response. Fire-and-forget. */
export async function addMemory(
  apiKey: string,
  userId: string,
  userMessage: string,
  assistantMessage: string
): Promise<void> {
  try {
    const client = getClient(apiKey);
    await client.add(
      [
        { role: "user", content: userMessage },
        { role: "assistant", content: assistantMessage },
      ],
      { user_id: userId }
    );
  } catch {
    // Non-critical — do not throw
  }
}
