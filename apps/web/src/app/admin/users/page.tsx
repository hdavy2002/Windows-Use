import { auth } from "@clerk/nextjs/server";
import { redirect } from "next/navigation";
import Link from "next/link";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Badge } from "@/components/ui/badge";
import { api } from "@/lib/api-client";

const PLAN_COLORS: Record<string, string> = {
  free: "border-[#6b7899] text-[#6b7899]",
  pro: "border-[#4f8ef7] text-[#4f8ef7]",
  corporate: "border-[#22d3a5] text-[#22d3a5]",
};

export default async function UsersPage() {
  const { getToken } = await auth();
  const token = await getToken();

  if (!token) redirect("/sign-in");

  const data = await api.admin.users({}, token).catch(() => null);
  const users: any[] = data?.users ?? [];

  return (
    <div>
      <h1 className="text-2xl font-bold mb-6">Users</h1>

      {users.length === 0 ? (
        <div className="rounded-lg border border-[#1c2132] bg-[#111318] p-8 text-center text-[#6b7899]">
          No users found.
        </div>
      ) : (
        <div className="rounded-lg border border-[#1c2132] overflow-hidden">
          <Table>
            <TableHeader>
              <TableRow className="border-[#1c2132] bg-[#111318]">
                <TableHead className="text-[#6b7899]">Name</TableHead>
                <TableHead className="text-[#6b7899]">Email</TableHead>
                <TableHead className="text-[#6b7899]">Plan</TableHead>
                <TableHead className="text-[#6b7899]">Role</TableHead>
                <TableHead className="text-[#6b7899]">Joined</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {users.map((u: any) => (
                <TableRow key={u.id} className="border-[#1c2132] hover:bg-[#111318] cursor-pointer">
                  <TableCell>
                    <Link
                      href={`/admin/users/${u.id}`}
                      className="text-[#4f8ef7] hover:underline"
                    >
                      {u.name ?? u.email}
                    </Link>
                  </TableCell>
                  <TableCell className="text-[#6b7899]">{u.email}</TableCell>
                  <TableCell>
                    <Badge
                      variant="outline"
                      className={PLAN_COLORS[u.plan] ?? PLAN_COLORS.free}
                    >
                      {u.plan}
                    </Badge>
                  </TableCell>
                  <TableCell className="text-[#6b7899] capitalize">{u.role ?? "user"}</TableCell>
                  <TableCell className="text-[#6b7899]">
                    {u.createdAt
                      ? new Date(u.createdAt).toLocaleDateString("en-GB", {
                          day: "2-digit", month: "short", year: "numeric",
                        })
                      : "—"}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      )}
    </div>
  );
}
