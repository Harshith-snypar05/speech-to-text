"use client";
import { CreditCard, History, LayoutDashboard, Mic } from "lucide-react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { Logo, ThemeToggle } from "@/components/brand";
import { ProfileMenu } from "@/components/profile-menu";
import { Spinner } from "@/components/ui";
import { useAuth } from "@/lib/auth";
import { cn } from "@/lib/utils";

export default function AppLayout({ children }: { children: React.ReactNode }) {
  const { token, user, ready, signOut } = useAuth();
  const router = useRouter();
  const path = usePathname();
  const [scrolled, setScrolled] = useState(false);

  // Navbar is clear at the top of the page and turns translucent (blurred) once the page scrolls under it.
  useEffect(() => {
    const on = () => setScrolled(window.scrollY > 8);
    on();
    window.addEventListener("scroll", on, { passive: true });
    return () => window.removeEventListener("scroll", on);
  }, []);

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
  const out = () => { signOut(); router.replace("/login"); };

  return (
    <div className="flex min-h-dvh flex-col">
      <header className={cn("sticky top-0 z-30 border-b transition-[background-color,border-color,backdrop-filter] duration-200", scrolled ? "border-line/60 bg-bg/70 backdrop-blur-xl" : "border-transparent bg-transparent")}>
        <div className="grid h-[72px] grid-cols-[1fr_auto_1fr] items-center gap-4 px-4 sm:px-6">
          <div className="flex justify-start"><Logo href="/app" className="h-9 w-auto" /></div>
          <nav className="flex items-center justify-center gap-2 text-sm font-medium" aria-label="Primary">
            {nav.map((n) => (
              <Link key={n.href} href={n.href} aria-current={active(n.href) ? "page" : undefined}
                className={cn("hidden rounded-full px-4 py-2 lg:block", active(n.href) ? "text-primary" : "text-ink hover:text-violet")}>
                {n.label}
              </Link>
            ))}
          </nav>
          <div className="flex items-center justify-end gap-3">
            <ThemeToggle />
            <ProfileMenu user={user} onSignOut={out} />
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
