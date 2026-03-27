import Link from "next/link";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Badge } from "@/components/ui/badge";

// TODO: Replace with real Neon query
const mockUsers = [
  { id: "user_1", name: "Humphrey Davy", email: "hdavy2002@gmail.com", plan: "pro", totalCalls: 142, totalTokens: 48320, role: "Admin" },
];

export default function UsersPage() {
  return (
    <div>
      <h1 className="text-2xl font-bold mb-6">Users</h1>
      <div className="rounded-lg border border-[#1c2132] overflow-hidden">
        <Table>
          <TableHeader>
            <TableRow className="border-[#1c2132] bg-[#111318]">
              <TableHead className="text-[#6b7899]">Name</TableHead>
              <TableHead className="text-[#6b7899]">Email</TableHead>
              <TableHead className="text-[#6b7899]">Plan</TableHead>
              <TableHead className="text-[#6b7899]">Calls</TableHead>
              <TableHead className="text-[#6b7899]">Tokens</TableHead>
              <TableHead className="text-[#6b7899]">Role</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {mockUsers.map((u) => (
              <TableRow key={u.id} className="border-[#1c2132] hover:bg-[#111318] cursor-pointer">
                <TableCell>
                  <Link href={`/admin/users/${u.id}`} className="text-[#4f8ef7] hover:underline">{u.name}</Link>
                </TableCell>
                <TableCell className="text-[#6b7899]">{u.email}</TableCell>
                <TableCell><Badge variant="outline" className="border-[#4f8ef7] text-[#4f8ef7]">{u.plan}</Badge></TableCell>
                <TableCell className="text-[#e2e8f8]">{u.totalCalls}</TableCell>
                <TableCell className="text-[#e2e8f8]">{u.totalTokens.toLocaleString()}</TableCell>
                <TableCell className="text-[#6b7899]">{u.role}</TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>
    </div>
  );
}
