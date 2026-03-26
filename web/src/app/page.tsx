import Link from "next/link";

export default function Home() {
  return (
    <div className="min-h-screen flex flex-col items-center justify-center bg-[#0a0c10] px-4">
      <div className="text-center max-w-lg">
        <div className="text-5xl mb-6">⚡</div>
        <h1 className="text-4xl font-bold tracking-tight mb-4 bg-gradient-to-r from-[#e2e8f8] to-[#4f8ef7] bg-clip-text text-transparent">
          Humphi AI
        </h1>
        <p className="text-[#6b7899] text-lg mb-8">
          AI Desktop Operator — real-time assistant, system operator, visual guide.
        </p>
        <div className="flex gap-4 justify-center">
          <Link href="/sign-in"
            className="px-6 py-3 rounded-lg bg-[#4f8ef7] text-white font-semibold hover:bg-[#3d7ae5] transition">
            Sign In
          </Link>
          <Link href="/sign-up"
            className="px-6 py-3 rounded-lg border border-[#1f2535] text-[#6b7899] font-semibold hover:border-[#4f8ef7] hover:text-[#e2e8f8] transition">
            Create Account
          </Link>
        </div>
      </div>
    </div>
  );
}
