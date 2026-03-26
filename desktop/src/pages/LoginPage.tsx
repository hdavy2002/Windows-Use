import { useState } from "react";
import { Zap } from "lucide-react";

interface LoginPageProps {
  onLogin: () => void;
}

export function LoginPage({ onLogin }: LoginPageProps) {
  const [apiKey, setApiKey] = useState("");

  const handleLogin = () => {
    if (!apiKey.trim()) return;
    localStorage.setItem("openrouter_key", apiKey.trim());
    onLogin();
  };

  return (
    <div className="min-h-screen flex items-center justify-center bg-[#0a0c10] px-4">
      <div className="w-full max-w-sm text-center">
        <Zap className="w-12 h-12 text-[#4f8ef7] mx-auto mb-4" />
        <h1 className="text-2xl font-bold text-[#e2e8f8] mb-1">Humphi AI</h1>
        <p className="text-sm text-[#6b7899] mb-8">
          AI directly on your local machine.
        </p>

        <div className="bg-[#111318] border border-[#1c2132] rounded-xl p-6 text-left">
          <label className="block text-xs text-[#6b7899] mb-2">OpenRouter API Key</label>
          <input value={apiKey} onChange={(e) => setApiKey(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && handleLogin()}
            type="password" placeholder="sk-or-..."
            className="w-full bg-[#0a0c10] border border-[#1c2132] rounded-lg px-3 py-2.5 text-sm text-[#e2e8f8] outline-none focus:border-[#4f8ef7] mb-4" />
          <button onClick={handleLogin}
            className="w-full py-2.5 rounded-lg bg-[#4f8ef7] text-white text-sm font-semibold hover:bg-[#3d7ae5] transition">
            Get Started
          </button>
        </div>

        <p className="text-xs text-[#6b7899] mt-4">
          Get a key at <a href="https://openrouter.ai" target="_blank" rel="noreferrer"
            className="text-[#4f8ef7] hover:underline">openrouter.ai</a>
        </p>
      </div>
    </div>
  );
}
