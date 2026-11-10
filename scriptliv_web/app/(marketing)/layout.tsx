import Link from "next/link";
import { Logo, ThemeToggle } from "@/components/brand";

export default function MarketingLayout({ children }: { children: React.ReactNode }) {
  const link = "hidden rounded-lg px-3 py-2 text-ink-2 hover:text-ink lg:block";
  return (
    <div className="min-h-dvh">
      <header className="sticky top-0 z-30 border-b border-line/60 bg-bg/85 backdrop-blur">
        <div className="mx-auto flex h-16 max-w-6xl items-center justify-between px-4 sm:px-6">
          <Logo className="h-9 w-auto" />
          <nav className="flex items-center gap-1 text-sm font-medium">
            <Link href="/#product" className={link}>Product</Link>
            <Link href="/#features" className={link}>Features</Link>
            <Link href="/#use-cases" className={link}>Use Cases</Link>
            <Link href="/#how" className={link}>How it works</Link>
            <ThemeToggle />
            <Link href="/login" className="ml-1 rounded-xl border border-line px-4 py-2 hover:bg-surface-alt">Log In</Link>
            <Link href="/register" className="brand-gradient rounded-xl px-4 py-2 text-white">Get Started</Link>
          </nav>
        </div>
      </header>
      {children}
      <footer className="bg-[#0f0a2e] py-10 text-sm text-white/70">
        <div className="mx-auto grid max-w-6xl gap-8 px-4 sm:px-6 md:grid-cols-[1.2fr_1fr_1fr]">
          <div>
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img src="/brand/scriptliv-logo-dark.png" width={557} height={160} alt="ScriptLiv" className="h-9 w-auto" />
            <p className="mt-3 max-w-xs">Real-time speech to text for modern conversations.</p>
          </div>
          <div><div className="mb-2 font-semibold text-white">Product</div><ul className="space-y-1"><li><Link href="/#features">Features</Link></li><li><Link href="/#use-cases">Use Cases</Link></li><li><Link href="/#how">How it works</Link></li></ul></div>
          <div><div className="mb-2 font-semibold text-white">Account</div><ul className="space-y-1"><li><Link href="/login">Log in</Link></li><li><Link href="/register">Create an account</Link></li></ul></div>
        </div>
        <p className="mx-auto mt-8 max-w-6xl px-4 text-xs text-white/50 sm:px-6">© {new Date().getFullYear()} Snypar Tech. All rights reserved.</p>
      </footer>
    </div>
  );
}
