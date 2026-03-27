import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

const CONNECTORS = [
  { id: "gmail", name: "Gmail", icon: "📧", desc: "Read, send, and organize emails", connected: false },
  { id: "gdrive", name: "Google Drive", icon: "📁", desc: "Search, read, and upload files", connected: false },
  { id: "gcalendar", name: "Google Calendar", icon: "📅", desc: "View and create events", connected: false },
  { id: "slack", name: "Slack", icon: "💬", desc: "Send messages and search channels", connected: false },
  { id: "notion", name: "Notion", icon: "📝", desc: "Read and edit pages and databases", connected: false },
  { id: "github", name: "GitHub", icon: "🐙", desc: "Manage repos, issues, and PRs", connected: false },
];

export default function ConnectorsPage() {
  return (
    <div>
      <h1 className="text-2xl font-bold mb-2">Connectors</h1>
      <p className="text-[#6b7899] mb-6">
        Connect your apps to Humphi AI via Composio. Your AI can then access these services.
      </p>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {CONNECTORS.map((c) => (
          <Card key={c.id} className="bg-[#111318] border-[#1c2132] hover:border-[#4f8ef7] transition cursor-pointer">
            <CardHeader className="pb-2">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-3">
                  <span className="text-2xl">{c.icon}</span>
                  <CardTitle className="text-base">{c.name}</CardTitle>
                </div>
                <span className={`text-xs px-2 py-1 rounded-full ${
                  c.connected
                    ? "bg-[#22d3a5]/10 text-[#22d3a5] border border-[#22d3a5]/30"
                    : "bg-[#1c2132] text-[#6b7899]"
                }`}>
                  {c.connected ? "Connected" : "Not connected"}
                </span>
              </div>
            </CardHeader>
            <CardContent>
              <p className="text-sm text-[#6b7899]">{c.desc}</p>
              <button className="mt-3 text-sm text-[#4f8ef7] hover:underline">
                {c.connected ? "Disconnect" : "Connect →"}
              </button>
            </CardContent>
          </Card>
        ))}
      </div>
    </div>
  );
}
