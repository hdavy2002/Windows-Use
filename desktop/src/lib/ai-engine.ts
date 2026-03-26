/**
 * ai-engine.ts — Chat engine that calls OpenRouter with MCP tool definitions.
 * The AI decides which DesktopCommander tools to call. No intent router.
 */

export interface Message {
  role: "user" | "assistant" | "system" | "tool";
  content: string;
  toolCalls?: ToolCall[];
  toolCallId?: string;
  name?: string;
}

export interface ToolCall {
  id: string;
  type: "function";
  function: { name: string; arguments: string };
}

// Only the 5-6 most relevant tools injected per turn (lean injection strategy)
export const DC_TOOLS = [
  {
    type: "function" as const,
    function: {
      name: "execute_command",
      description: "Run a terminal command (PowerShell). Returns stdout/stderr.",
      parameters: {
        type: "object",
        properties: {
          command: { type: "string", description: "The command to execute" },
        },
        required: ["command"],
      },
    },
  },
  {
    type: "function" as const,
    function: {
      name: "read_file",
      description: "Read contents of a file at the given path.",
      parameters: {
        type: "object",
        properties: {
          path: { type: "string", description: "Absolute file path" },
        },
        required: ["path"],
      },
    },
  },
  {
    type: "function" as const,
    function: {
      name: "list_directory",
      description: "List files and folders in a directory.",
      parameters: {
        type: "object",
        properties: {
          path: { type: "string", description: "Directory path" },
        },
        required: ["path"],
      },
    },
  },
  {
    type: "function" as const,
    function: {
      name: "write_file",
      description: "Write content to a file (creates or overwrites).",
      parameters: {
        type: "object",
        properties: {
          path: { type: "string", description: "Absolute file path" },
          content: { type: "string", description: "File content" },
        },
        required: ["path", "content"],
      },
    },
  },
  {
    type: "function" as const,
    function: {
      name: "search_files",
      description: "Search for files or content within files.",
      parameters: {
        type: "object",
        properties: {
          path: { type: "string", description: "Directory to search" },
          pattern: { type: "string", description: "Search pattern" },
          searchType: { type: "string", enum: ["files", "content"] },
        },
        required: ["path", "pattern"],
      },
    },
  },
];

const SYSTEM_PROMPT = `You are Humphi, an AI desktop assistant. You have Desktop Commander tools to execute commands, manage files, and control processes on the user's Windows PC.

RULES:
- Use tools to EXECUTE actions, don't just tell the user how.
- For "open X" requests, use execute_command with explorer.exe or Start-Process.
- For system info, run Get-Process, Get-PSDrive, etc.
- Be concise. Show results, not explanations.
- For complex visual tasks, suggest Go Live mode.
- NEVER run destructive commands (del, rm, Remove-Item, format).`;

const CHAT_MODEL = "openai/gpt-4.1";
const CHAT_URL = "https://openrouter.ai/api/v1/chat/completions";

export type OnToken = (token: string) => void;
export type OnToolCall = (name: string, args: Record<string, unknown>) => Promise<string>;

export async function streamChat(
  messages: Message[],
  apiKey: string,
  onToken: OnToken,
  onToolCall: OnToolCall,
): Promise<Message> {
  const payload = {
    model: CHAT_MODEL,
    messages: [{ role: "system", content: SYSTEM_PROMPT }, ...messages],
    tools: DC_TOOLS,
    stream: true,
    temperature: 0.3,
    max_tokens: 1024,
  };

  const res = await fetch(CHAT_URL, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${apiKey}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify(payload),
  });

  if (!res.ok) throw new Error(`AI API ${res.status}: ${await res.text()}`);

  const reader = res.body!.getReader();
  const decoder = new TextDecoder();
  let fullText = "";
  let toolCalls: ToolCall[] = [];
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split("\n");
    buffer = lines.pop() || "";

    for (const line of lines) {
      if (!line.startsWith("data: ")) continue;
      const data = line.slice(6);
      if (data === "[DONE]") break;
      try {
        const chunk = JSON.parse(data);
        const delta = chunk.choices?.[0]?.delta;
        if (!delta) continue;

        // Text content
        if (delta.content) {
          fullText += delta.content;
          onToken(delta.content);
        }

        // Tool calls accumulation
        if (delta.tool_calls) {
          for (const tc of delta.tool_calls) {
            if (tc.index !== undefined) {
              while (toolCalls.length <= tc.index) {
                toolCalls.push({ id: "", type: "function", function: { name: "", arguments: "" } });
              }
              if (tc.id) toolCalls[tc.index].id = tc.id;
              if (tc.function?.name) toolCalls[tc.index].function.name += tc.function.name;
              if (tc.function?.arguments) toolCalls[tc.index].function.arguments += tc.function.arguments;
            }
          }
        }
      } catch { /* skip malformed chunks */ }
    }
  }

  // If AI made tool calls, execute them and recurse
  if (toolCalls.length > 0) {
    const assistantMsg: Message = {
      role: "assistant",
      content: fullText,
      toolCalls,
    };

    const toolResults: Message[] = [];
    for (const tc of toolCalls) {
      const args = JSON.parse(tc.function.arguments || "{}");
      onToken(`\n🔧 ${tc.function.name}(${JSON.stringify(args).slice(0, 80)})\n`);
      const result = await onToolCall(tc.function.name, args);
      onToken(`📋 ${result.slice(0, 200)}\n\n`);
      toolResults.push({
        role: "tool",
        content: result,
        toolCallId: tc.id,
        name: tc.function.name,
      });
    }

    // Recurse: send tool results back to AI for final response
    return streamChat(
      [...messages, assistantMsg, ...toolResults],
      apiKey,
      onToken,
      onToolCall,
    );
  }

  return { role: "assistant", content: fullText };
}
