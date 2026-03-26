import { MessageSquare, FolderOpen, Settings, User, Zap } from "lucide-react";
import { cn } from "@/lib/utils";

interface SidebarProps {
  active: string;
  onNavigate: (page: string) => void;
  userName?: string;
}

const NAV = [
  { id: "chat", label: "Chat", icon: MessageSquare },
  { id: "files", label: "Files", icon: FolderOpen },
  { id: "settings", label: "Settings", icon: Settings },
];

export function Sidebar({ active, onNavigate, userName }: SidebarProps) {
  return (
    <aside className="w-14 hover:w-48 transition-all duration-200 group border-r border-[#1c2132] flex flex-col py-3 bg-[#0a0c10] overflow-hidden">
      {/* Brand */}
      <button onClick={() => onNavigate("chat")} className="flex items-center gap-3 px-4 mb-6">
        <Zap className="w-5 h-5 text-[#4f8ef7] shrink-0" />
        <span className="text-sm font-bold text-[#e2e8f8] opacity-0 group-hover:opacity-100 transition whitespace-nowrap">Humphi AI</span>
      </button>

      {/* Nav */}
      <nav className="flex-1 space-y-1 px-2">
        {NAV.map((n) => (
          <button key={n.id} onClick={() => onNavigate(n.id)}
            className={cn(
              "flex items-center gap-3 w-full px-2 py-2 rounded-lg text-sm transition",
              active === n.id
                ? "bg-[#111318] text-[#4f8ef7]"
                : "text-[#6b7899] hover:text-[#e2e8f8] hover:bg-[#111318]"
            )}>
            <n.icon className="w-4 h-4 shrink-0" />
            <span className="opacity-0 group-hover:opacity-100 transition whitespace-nowrap">{n.label}</span>
          </button>
        ))}
      </nav>

      {/* User */}
      <div className="px-2 pt-3 border-t border-[#1c2132]">
        <button onClick={() => onNavigate("settings")}
          className="flex items-center gap-3 w-full px-2 py-2 rounded-lg text-[#6b7899] hover:text-[#e2e8f8] transition">
          <User className="w-4 h-4 shrink-0" />
          <span className="opacity-0 group-hover:opacity-100 transition whitespace-nowrap text-xs truncate">
            {userName || "Account"}
          </span>
        </button>
      </div>
    </aside>
  );
}
