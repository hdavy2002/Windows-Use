import { auth } from "@clerk/nextjs/server";
import { api } from "@/lib/api-client";
import { Badge } from "@/components/ui/badge";

function formatDuration(startedAt: string, endedAt: string | null) {
  if (!endedAt) return "Active";
  const ms = new Date(endedAt).getTime() - new Date(startedAt).getTime();
  const mins = Math.floor(ms / 60000);
  return mins < 1 ? "<1 min" : `${mins} min`;
}

export default async function HistoryPage() {
  const { getToken } = await auth();
  const token = await getToken();

  let sessions: any[] = [];

  if (token) {
    const data = await api.sessions.list(token).catch(() => null);
    if (data) sessions = data.sessions;
  }

  return (
    <div>
      <h1 className="text-2xl font-bold mb-2">Session History</h1>
      <p className="text-[#6b7899] mb-6">Your past conversations and live sessions.</p>

      {sessions.length === 0 ? (
        <div className="rounded-lg border border-[#1c2132] bg-[#111318] p-8 text-center text-[#6b7899]">
          No sessions yet. Start chatting in the desktop app!
        </div>
      ) : (
        <div className="rounded-lg border border-[#1c2132] overflow-hidden">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-[#1c2132] bg-[#111318]">
                <th className="text-left px-4 py-3 text-[#6b7899] font-medium">Date</th>
                <th className="text-left px-4 py-3 text-[#6b7899] font-medium">Mode</th>
                <th className="text-left px-4 py-3 text-[#6b7899] font-medium">Source</th>
                <th className="text-left px-4 py-3 text-[#6b7899] font-medium">Duration</th>
                <th className="text-left px-4 py-3 text-[#6b7899] font-medium">Status</th>
              </tr>
            </thead>
            <tbody>
              {sessions.map((s: any) => (
                <tr key={s.id} className="border-b border-[#1c2132] hover:bg-[#111318] transition-colors">
                  <td className="px-4 py-3 text-[#e2e8f8]">
                    {new Date(s.startedAt).toLocaleDateString("en-GB", {
                      day: "2-digit", month: "short", year: "numeric",
                      hour: "2-digit", minute: "2-digit",
                    })}
                  </td>
                  <td className="px-4 py-3">
                    <Badge variant="outline" className="border-[#4f8ef7] text-[#4f8ef7] capitalize">
                      {s.mode}
                    </Badge>
                  </td>
                  <td className="px-4 py-3 text-[#6b7899] capitalize">{s.source ?? "desktop"}</td>
                  <td className="px-4 py-3 text-[#e2e8f8]">
                    {formatDuration(s.startedAt, s.endedAt)}
                  </td>
                  <td className="px-4 py-3">
                    {s.endedAt ? (
                      <span className="text-[#6b7899]">Ended</span>
                    ) : (
                      <span className="text-[#22d3a5]">Active</span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
