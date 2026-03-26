import { currentUser } from "@clerk/nextjs/server";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

export default async function DashboardPage() {
  const user = await currentUser();
  return (
    <div>
      <h1 className="text-2xl font-bold mb-6">
        Welcome, {user?.firstName || "User"}
      </h1>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-8">
        <Card className="bg-[#111318] border-[#1c2132]">
          <CardHeader className="pb-2">
            <CardTitle className="text-sm text-[#6b7899]">API Calls Today</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-3xl font-bold text-[#e2e8f8]">0</div>
          </CardContent>
        </Card>

        <Card className="bg-[#111318] border-[#1c2132]">
          <CardHeader className="pb-2">
            <CardTitle className="text-sm text-[#6b7899]">Tokens Used</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-3xl font-bold text-[#e2e8f8]">0</div>
          </CardContent>
        </Card>

        <Card className="bg-[#111318] border-[#1c2132]">
          <CardHeader className="pb-2">
            <CardTitle className="text-sm text-[#6b7899]">Est. Cost</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-3xl font-bold text-[#22d3a5]">$0.00</div>
          </CardContent>
        </Card>
      </div>

      <p className="text-[#6b7899]">
        Download the Humphi desktop app to get started with AI-powered PC assistance.
      </p>
    </div>
  );
}
