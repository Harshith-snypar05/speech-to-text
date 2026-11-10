"use client";
import { CreditCard, History, LayoutDashboard, LogOut, Mic, Settings } from "lucide-react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect } from "react";
import { Logo, ThemeToggle } from "@/components/brand";
import { Spinner } from "@/components/ui";
import { buttonCls } from "@/components/ui/button-styles";
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
      <header className="sticky top-0 z-30">
        <div className="mx-auto grid h-[72px] max-w-[1400px] grid-cols-[auto_1fr_auto] items-center gap-4 px-4 sm:px-8">
          <Logo href="/app" className="h-9 w-auto" />
          <nav className="flex items-center justify-center gap-2 text-sm font-medium" aria-label="Primary">
            {nav.map((n) => (
              <Link key={n.href} href={n.href} aria-current={active(n.href) ? "page" : undefined}
                className={cn("hidden rounded-full px-4 py-2 lg:block", active(n.href) ? "text-primary" : "text-ink hover:text-violet")}>
                {n.label}
              </Link>
            ))}
          </nav>
          <div className="flex items-center gap-2 text-sm">
            <span className="hidden max-w-44 truncate text-xs text-ink-2 xl:block" title={user.email}>{user.email}</span>
            <ThemeToggle />
            <Link href="/app/settings" aria-label="Settings" aria-current={settingsActive ? "page" : undefined}
              className={buttonCls({ variant: "outline", size: "md" })}>
              <Settings className="size-4" aria-hidden /> <span className="hidden sm:inline">Settings</span>
            </Link>
            <button aria-label="Sign out" title="Sign out" onClick={out} className={buttonCls({ size: "md" })}>
              <LogOut className="size-4" aria-hidden /> <span className="hidden sm:inline">Sign out</span>
            </button>
          </div>
        </div>
      </header>

      <main className="mx-auto w-full max-w-[1400px] flex-1 px-4 py-6 pb-24 sm:px-8 lg:pb-10">{children}</main>

      <nav className="fixed inset-x-0 bottom-0 z-30 flex border-t border-line/60 bg-bg/85 backdrop-blur-md lg:hidden" aria-label="Primary mobile">
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
