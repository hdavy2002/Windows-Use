import { useState, useRef, useEffect, useCallback } from "react";
import { Send, Radio, Mic, MicOff } from "lucide-react";
import { streamChat, type Message } from "@/lib/ai-engine";
import { executeMcpTool } from "@/lib/mcp-client";

const CHIPS = ["Fix slow PC", "Check WiFi", "Free disk space", "Open Downloads", "Update Windows", "Sound issues"];

interface ChatMsg {
  role: "user" | "assistant" | "system";
  content: string;
  streaming?: boolean;
}

export function ChatPage() {
  const [messages, setMessages] = useState<ChatMsg[]>([]);
  const [input, setInput] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [micOn, setMicOn] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);
  const apiKey = localStorage.getItem("openrouter_key") || "";

  const scrollBottom = () => {
    setTimeout(() => scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" }), 50);
  };

  useEffect(scrollBottom, [messages]);

  const sendMessage = useCallback(async (text: string) => {
    if (!text.trim() || isLoading) return;
    const userMsg: ChatMsg = { role: "user", content: text.trim() };
    setMessages((prev) => [...prev, userMsg]);
    setInput("");
    setIsLoading(true);

    // Add a streaming placeholder
    setMessages((prev) => [...prev, { role: "assistant", content: "", streaming: true }]);

    const history: Message[] = messages
      .concat(userMsg)
      .slice(-6)
      .map((m) => ({ role: m.role, content: m.content }));

    try {
      let accumulated = "";
      await streamChat(
        history, apiKey,
        (token) => {
          accumulated += token;
          setMessages((prev) => {
            const copy = [...prev];
            copy[copy.length - 1] = { role: "assistant", content: accumulated, streaming: true };
            return copy;
          });
        },
        (name, args) => executeMcpTool(name, args),
      );

      // Mark streaming done
      setMessages((prev) => {
        const copy = [...prev];
        copy[copy.length - 1] = { ...copy[copy.length - 1], streaming: false };
        return copy;
      });
    } catch (e: any) {
      setMessages((prev) => {
        const copy = [...prev];
        copy[copy.length - 1] = { role: "assistant", content: `Error: ${e.message}`, streaming: false };
        return copy;
      });
    }
    setIsLoading(false);
  }, [messages, isLoading, apiKey]);

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="flex items-center justify-between px-5 py-3 border-b border-[#1c2132]">
        <h1 className="text-sm font-semibold text-[#e2e8f8]">Chat</h1>
        <div className="flex items-center gap-2">
          <button onClick={() => setMicOn(!micOn)}
            className={`p-2 rounded-lg transition ${micOn ? "bg-[#ef4444]/10 text-[#ef4444]" : "text-[#6b7899] hover:text-[#e2e8f8]"}`}>
            {micOn ? <Mic className="w-4 h-4" /> : <MicOff className="w-4 h-4" />}
          </button>
          <button className="flex items-center gap-2 px-3 py-1.5 rounded-lg bg-[#ef4444] text-white text-xs font-semibold hover:bg-[#dc2626] transition">
            <Radio className="w-3 h-3" /> Go Live
          </button>
        </div>
      </div>

      {/* Messages */}
      <div ref={scrollRef} className="flex-1 overflow-y-auto px-5 py-4 space-y-4">
        {messages.length === 0 && (
          <div className="flex flex-col items-center justify-center h-full text-center">
            <div className="text-4xl mb-4">⚡</div>
            <p className="text-lg font-semibold text-[#e2e8f8] mb-1">Humphi AI</p>
            <p className="text-sm text-[#6b7899] mb-6">Your AI desktop assistant. Ask anything.</p>
            <div className="flex flex-wrap gap-2 justify-center max-w-md">
              {CHIPS.map((c) => (
                <button key={c} onClick={() => sendMessage(c)}
                  className="px-3 py-1.5 rounded-full border border-[#1c2132] text-xs text-[#6b7899] hover:border-[#4f8ef7] hover:text-[#4f8ef7] transition">
                  {c}
                </button>
              ))}
            </div>
          </div>
        )}

        {messages.map((m, i) => (
          <div key={i} className={`flex ${m.role === "user" ? "justify-end" : "justify-start"}`}>
            <div className={`max-w-[80%] px-4 py-2.5 rounded-2xl text-sm leading-relaxed whitespace-pre-wrap ${
              m.role === "user"
                ? "bg-[#4f8ef7] text-white rounded-br-md"
                : "bg-[#111318] text-[#e2e8f8] border border-[#1c2132] rounded-bl-md"
            }`}>
              {m.content}
              {m.streaming && <span className="inline-block w-1.5 h-4 ml-1 bg-[#4f8ef7] rounded-full animate-pulse" />}
            </div>
          </div>
        ))}

        {isLoading && messages[messages.length - 1]?.content === "" && (
          <div className="flex gap-1.5 px-4 py-3">
            <div className="w-2 h-2 rounded-full bg-[#4f8ef7] animate-bounce" style={{ animationDelay: "0ms" }} />
            <div className="w-2 h-2 rounded-full bg-[#4f8ef7] animate-bounce" style={{ animationDelay: "150ms" }} />
            <div className="w-2 h-2 rounded-full bg-[#4f8ef7] animate-bounce" style={{ animationDelay: "300ms" }} />
          </div>
        )}
      </div>

      {/* Input */}
      <div className="px-5 py-3 border-t border-[#1c2132]">
        <div className="flex items-center gap-2 bg-[#111318] rounded-xl border border-[#1c2132] px-4 py-2 focus-within:border-[#4f8ef7] transition">
          <input
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && !e.shiftKey && sendMessage(input)}
            placeholder="Ask Humphi anything..."
            className="flex-1 bg-transparent text-sm text-[#e2e8f8] placeholder-[#6b7899] outline-none"
            disabled={isLoading}
          />
          <button onClick={() => sendMessage(input)} disabled={isLoading || !input.trim()}
            className="p-1.5 rounded-lg text-[#4f8ef7] hover:bg-[#4f8ef7]/10 disabled:opacity-30 transition">
            <Send className="w-4 h-4" />
          </button>
        </div>
      </div>
    </div>
  );
}
