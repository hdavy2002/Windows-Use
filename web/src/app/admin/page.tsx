import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

export default function AdminPage() {
  return (
    <div>
      <h1 className="text-2xl font-bold mb-6">Admin Dashboard</h1>
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
        <Card className="bg-[#111318] border-[#1c2132]">
          <CardHeader className="pb-2">
            <CardTitle className="text-sm text-[#6b7899]">Total Users</CardTitle>
          </CardHeader>
          <CardContent><div className="text-3xl font-bold text-[#e2e8f8]">0</div></CardContent>
        </Card>
        <Card className="bg-[#111318] border-[#1c2132]">
          <CardHeader className="pb-2">
            <CardTitle className="text-sm text-[#6b7899]">Total Calls</CardTitle>
          </CardHeader>
          <CardContent><div className="text-3xl font-bold text-[#e2e8f8]">0</div></CardContent>
        </Card>
        <Card className="bg-[#111318] border-[#1c2132]">
          <CardHeader className="pb-2">
            <CardTitle className="text-sm text-[#6b7899]">Total Cost</CardTitle>
          </CardHeader>
          <CardContent><div className="text-3xl font-bold text-[#22d3a5]">$0.00</div></CardContent>
        </Card>
        <Card className="bg-[#111318] border-[#1c2132]">
          <CardHeader className="pb-2">
            <CardTitle className="text-sm text-[#6b7899]">Active Sessions</CardTitle>
          </CardHeader>
          <CardContent><div className="text-3xl font-bold text-[#4f8ef7]">0</div></CardContent>
        </Card>
      </div>
    </div>
  );
}
