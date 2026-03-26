import { useState } from "react";
import { Sidebar } from "@/components/Sidebar";
import { ChatPage } from "@/pages/ChatPage";
import { SettingsPage } from "@/pages/SettingsPage";
import { FilesPage } from "@/pages/FilesPage";
import { LoginPage } from "@/pages/LoginPage";

export default function App() {
  const [loggedIn, setLoggedIn] = useState(
    () => !!localStorage.getItem("openrouter_key")
  );
  const [page, setPage] = useState("chat");

  if (!loggedIn) {
    return <LoginPage onLogin={() => setLoggedIn(true)} />;
  }

  return (
    <div className="flex h-screen bg-[#0a0c10]">
      <Sidebar active={page} onNavigate={setPage} />
      <main className="flex-1 flex flex-col overflow-hidden">
        {page === "chat" && <ChatPage />}
        {page === "files" && <FilesPage />}
        {page === "settings" && <SettingsPage />}
      </main>
    </div>
  );
}
