import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { currentUser } from "@clerk/nextjs/server";

export default async function SettingsPage() {
  const user = await currentUser();
  return (
    <div>
      <h1 className="text-2xl font-bold mb-2">Settings</h1>
      <p className="text-[#6b7899] mb-6">Manage your preferences</p>

      <div className="space-y-4 max-w-xl">
        <Card className="bg-[#111318] border-[#1c2132]">
          <CardHeader><CardTitle className="text-sm">Profile</CardTitle></CardHeader>
          <CardContent className="space-y-2 text-sm">
            <div className="flex justify-between">
              <span className="text-[#6b7899]">Name</span>
              <span>{user?.firstName} {user?.lastName}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-[#6b7899]">Email</span>
              <span>{user?.emailAddresses?.[0]?.emailAddress}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-[#6b7899]">Plan</span>
              <span className="text-[#4f8ef7]">Free</span>
            </div>
          </CardContent>
        </Card>

        <Card className="bg-[#111318] border-[#1c2132]">
          <CardHeader><CardTitle className="text-sm">AI Voice</CardTitle></CardHeader>
          <CardContent className="text-sm text-[#6b7899]">
            <p>Current voice: <span className="text-[#e2e8f8]">Aoede</span> (calm, professional)</p>
            <p className="mt-2 text-xs">Voice selection will be available in a future update.</p>
          </CardContent>
        </Card>

        <Card className="bg-[#111318] border-[#1c2132]">
          <CardHeader><CardTitle className="text-sm">Theme</CardTitle></CardHeader>
          <CardContent className="text-sm text-[#6b7899]">
            <p>Current: <span className="text-[#e2e8f8]">Dark</span></p>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
