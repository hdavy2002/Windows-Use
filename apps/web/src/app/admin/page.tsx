import { auth } from "@clerk/nextjs/server";
import { redirect } from "next/navigation";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { api } from "@/lib/api-client";

export default async function AdminPage() {
  const { getToken } = await auth();
  const token = await getToken();

  if (!token) redirect("/sign-in");

  let stats = { totalUsers: 0, totalCalls: 0, totalCostUsd: "0", activeSessions: 0 };

  const data = await api.admin.stats("today", token).catch(() => null);
  if (data) stats = data;

  return (
    <div>
      <h1 className="text-2xl font-bold mb-2">Admin Dashboard</h1>
      <p className="text-[#6b7899] mb-6">Today's platform overview.</p>

      <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
        <Card className="bg-[#111318] border-[#1c2132]">
          <CardHeader className="pb-2">
            <CardTitle className="text-sm text-[#6b7899]">Total Users</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-3xl font-bold text-[#e2e8f8]">
              {stats.totalUsers.toLocaleString()}
            </div>
          </CardContent>
        </Card>

        <Card className="bg-[#111318] border-[#1c2132]">
          <CardHeader className="pb-2">
            <CardTitle className="text-sm text-[#6b7899]">API Calls Today</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-3xl font-bold text-[#e2e8f8]">
              {stats.totalCalls.toLocaleString()}
            </div>
          </CardContent>
        </Card>

        <Card className="bg-[#111318] border-[#1c2132]">
          <CardHeader className="pb-2">
            <CardTitle className="text-sm text-[#6b7899]">Cost Today</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-3xl font-bold text-[#22d3a5]">
              ${Number(stats.totalCostUsd).toFixed(4)}
            </div>
          </CardContent>
        </Card>

        <Card className="bg-[#111318] border-[#1c2132]">
          <CardHeader className="pb-2">
            <CardTitle className="text-sm text-[#6b7899]">Active Sessions</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-3xl font-bold text-[#4f8ef7]">
              {stats.activeSessions.toLocaleString()}
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
