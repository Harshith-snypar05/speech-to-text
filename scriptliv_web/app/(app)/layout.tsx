"use client";
import { CreditCard, History, LayoutDashboard, LogOut, Mic, Settings } from "lucide-react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect } from "react";
import { Logo, ThemeToggle } from "@/components/brand";
import { Copyright, Spinner } from "@/components/ui";
import { useAuth } from "@/lib/auth";
import { cn } from "@/lib/utils";

export default function AppLayout({ children }: { children: React.ReactNode }) {
  const { token, user, ready, signOut } = useAuth();
  const router = useRouter();
  const path = usePathname();

  useEffect(() => {
    if (ready && !token) router.replace("/login");
  }, [ready, token, router]);

  if (!ready || !token || !user) {
    return <div className="grid min-h-dvh place-items-center"><Spinner /></div>;
  }

  const nav = [
    { href: "/app", label: "Home", icon: LayoutDashboard },
    { href: "/app/record", label: "Transcribe", icon: Mic },
    { href: "/app/history", label: "Transcripts", icon: History },
    { href: "/app/plans", label: "Plans", icon: CreditCard },
  ];
  const active = (h: string) => (h === "/app" ? path === "/app" : path.startsWith(h));
  const settingsActive = path.startsWith("/app/settings");
  const out = () => { signOut(); router.replace("/login"); };

  return (
    <div className="flex min-h-dvh flex-col">
      <header className="sticky top-0 z-30 flex h-14 items-center gap-2 border-b border-line bg-bg/90 px-4 backdrop-blur sm:gap-3">
        <Logo href="/app" className="h-8 w-auto" />
        <span aria-hidden className="mx-1 hidden h-5 w-px bg-line sm:block" />
        <Link href="/app/settings" aria-label="Settings" aria-current={settingsActive ? "page" : undefined}
          className={cn("flex h-9 items-center gap-2 rounded-xl px-2.5 text-sm font-medium sm:px-3", settingsActive ? "bg-lavender text-primary" : "text-ink-2 hover:bg-surface-alt hover:text-ink")}>
          <Settings className="size-4" /> <span className="hidden sm:inline">Settings</span>
        </Link>
        <div className="ml-auto flex items-center gap-2">
          <span className="hidden max-w-48 truncate text-xs text-ink-2 lg:block" title={user.email}>{user.email}</span>
          <ThemeToggle />
          <button aria-label="Sign out" title="Sign out" onClick={out} className="grid size-9 place-items-center rounded-xl border border-line text-ink-2 hover:bg-surface-alt hover:text-ink"><LogOut className="size-4" /></button>
        </div>
      </header>

      <div className="flex flex-1 md:grid md:grid-cols-[216px_1fr]">
        <aside className="hidden border-r border-line bg-surface md:block">
          <nav className="sticky top-14 space-y-1 p-4" aria-label="Primary">
            {nav.map((n) => (
              <Link key={n.href} href={n.href} aria-current={active(n.href) ? "page" : undefined}
                className={cn("flex items-center gap-3 rounded-xl px-3 py-2.5 text-sm font-medium", active(n.href) ? "bg-lavender text-primary" : "text-ink-2 hover:bg-surface-alt hover:text-ink")}>
                <n.icon className="size-4" /> {n.label}
              </Link>
            ))}
            <Copyright className="px-3 pt-6 text-[11px]" />
          </nav>
        </aside>
        <main className="mx-auto w-full max-w-5xl flex-1 px-4 py-6 pb-24 sm:px-6 md:pb-6">{children}</main>
      </div>

      <nav className="fixed inset-x-0 bottom-0 z-30 flex border-t border-line bg-bg/95 backdrop-blur md:hidden" aria-label="Primary mobile">
        {nav.map((n) => (
          <Link key={n.href} href={n.href} aria-current={active(n.href) ? "page" : undefined}
            className={cn("flex flex-1 flex-col items-center gap-0.5 py-2 text-[11px]", active(n.href) ? "text-primary" : "text-ink-2")}>
            <n.icon className="size-5" /> {n.label}
          </Link>
        ))}
      </nav>
    </div>
  );
}
