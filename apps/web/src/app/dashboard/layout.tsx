"use client";
import { Suspense } from "react";
import { UserButton } from "@clerk/nextjs";
import Link from "next/link";
import { usePathname } from "next/navigation";

const NAV = [
  { href: "/dashboard", label: "Overview", icon: "📊" },
  { href: "/dashboard/history", label: "History", icon: "📋" },
  { href: "/dashboard/connectors", label: "Connectors", icon: "🔗" },
  { href: "/dashboard/settings", label: "Settings", icon: "⚙️" },
];

export default function DashboardLayout({ children }: { children: React.ReactNode }) {
  const path = usePathname();
  return (
    <div className="flex min-h-screen bg-[#0a0c10]">
      {/* Sidebar */}
      <aside className="w-56 border-r border-[#1c2132] flex flex-col py-4 px-3">
        <Link href="/dashboard" className="flex items-center gap-2 px-3 mb-8">
          <span className="text-xl">⚡</span>
          <span className="font-bold text-[#e2e8f8]">Humphi AI</span>
        </Link>

        <nav className="flex-1 space-y-1">
          {NAV.map((n) => (
            <Link key={n.href} href={n.href}
              transitionTypes={["slide"]}
              className={`flex items-center gap-3 px-3 py-2 rounded-lg text-sm transition
                ${path === n.href ? "bg-[#111318] text-[#4f8ef7] font-medium" : "text-[#6b7899] hover:text-[#e2e8f8] hover:bg-[#111318]"}`}>
              <span>{n.icon}</span>
              {n.label}
            </Link>
          ))}
        </nav>

        <div className="px-3 pt-4 border-t border-[#1c2132]">
          <UserButton />
        </div>
      </aside>

      {/* Main */}
      <main className="flex-1 p-8">
        <Suspense fallback={<div className="animate-pulse text-[#6b7899]">Loading...</div>}>
          {children}
        </Suspense>
      </main>
    </div>
  );
}
