/**
 * mcp-client.ts — Connects to DesktopCommanderMCP via stdio.
 * For now, executes commands via a local HTTP proxy or direct child_process.
 * In Tauri, this will use Rust's Command API for native performance.
 *
 * Browser fallback: uses a WebSocket bridge or fetch to a local server.
 */

export interface McpToolResult {
  success: boolean;
  output: string;
}

/**
 * Execute a tool call from the AI engine.
 * Routes to the appropriate handler based on tool name.
 *
 * In Tauri: calls invoke("execute_command", { command }) via @tauri-apps/api
 * In browser dev: falls back to a mock or local proxy
 */
export async function executeMcpTool(
  name: string,
  args: Record<string, unknown>,
): Promise<string> {
  // Check if running inside Tauri
  const isTauri = "__TAURI__" in window;

  if (isTauri) {
    return executeTauri(name, args);
  }
  return executeMock(name, args);
}

async function executeTauri(name: string, args: Record<string, unknown>): Promise<string> {
  try {
    // Use global Tauri API injected by Tauri runtime (no import needed)
    const invoke = (window as any).__TAURI__?.core?.invoke;
    if (!invoke) return executeMock(name, args);
    const result = await invoke("mcp_tool_call", { tool: name, args: JSON.stringify(args) });
    return String(result);
  } catch (e: any) {
    return `Error: ${e.message || e}`;
  }
}

/** Dev fallback — simulates basic tool results */
function executeMock(name: string, args: Record<string, unknown>): Promise<string> {
  const cmd = args.command || args.path || args.pattern || "";
  return Promise.resolve(
    `[Mock MCP] ${name}(${JSON.stringify(args).slice(0, 100)})\n` +
    `→ This would execute on your PC via DesktopCommander.\n` +
    `→ Install Tauri + Rust to enable real execution.`
  );
}
