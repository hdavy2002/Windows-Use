import { FolderOpen } from "lucide-react";

export function FilesPage() {
  return (
    <div className="flex flex-col items-center justify-center h-full text-center">
      <FolderOpen className="w-12 h-12 text-[#1c2132] mb-4" />
      <h2 className="text-lg font-semibold text-[#e2e8f8] mb-1">File Browser</h2>
      <p className="text-sm text-[#6b7899] max-w-xs">
        Browse and manage files on your PC. Powered by Desktop Commander MCP.
      </p>
      <p className="text-xs text-[#6b7899] mt-4">Coming in Phase 2B</p>
    </div>
  );
}
