import { useState } from "react";
import { Key, Volume2, Palette } from "lucide-react";

export function SettingsPage() {
  const [apiKey, setApiKey] = useState(localStorage.getItem("openrouter_key") || "");

  const saveKey = () => {
    localStorage.setItem("openrouter_key", apiKey);
    alert("API key saved!");
  };

  return (
    <div className="p-6 max-w-lg mx-auto">
      <h1 className="text-xl font-bold text-[#e2e8f8] mb-6">Settings</h1>

      {/* API Key */}
      <div className="bg-[#111318] border border-[#1c2132] rounded-xl p-4 mb-4">
        <div className="flex items-center gap-2 mb-3">
          <Key className="w-4 h-4 text-[#4f8ef7]" />
          <h2 className="text-sm font-semibold">OpenRouter API Key</h2>
        </div>
        <input value={apiKey} onChange={(e) => setApiKey(e.target.value)}
          type="password" placeholder="sk-or-..."
          className="w-full bg-[#0a0c10] border border-[#1c2132] rounded-lg px-3 py-2 text-sm text-[#e2e8f8] outline-none focus:border-[#4f8ef7] mb-2" />
        <button onClick={saveKey}
          className="px-4 py-1.5 bg-[#4f8ef7] text-white text-xs rounded-lg hover:bg-[#3d7ae5] transition">
          Save
        </button>
      </div>

      {/* Voice */}
      <div className="bg-[#111318] border border-[#1c2132] rounded-xl p-4 mb-4">
        <div className="flex items-center gap-2 mb-2">
          <Volume2 className="w-4 h-4 text-[#4f8ef7]" />
          <h2 className="text-sm font-semibold">AI Voice</h2>
        </div>
        <p className="text-xs text-[#6b7899]">Current: <span className="text-[#e2e8f8]">Aoede</span> (calm, professional)</p>
      </div>

      {/* Theme */}
      <div className="bg-[#111318] border border-[#1c2132] rounded-xl p-4">
        <div className="flex items-center gap-2 mb-2">
          <Palette className="w-4 h-4 text-[#4f8ef7]" />
          <h2 className="text-sm font-semibold">Theme</h2>
        </div>
        <p className="text-xs text-[#6b7899]">Current: <span className="text-[#e2e8f8]">Dark</span></p>
      </div>
    </div>
  );
}
