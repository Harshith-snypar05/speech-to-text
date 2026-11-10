"use client";
import { Moon, Sun } from "lucide-react";
import Link from "next/link";
import { useEffect, useState } from "react";
import { cn } from "@/lib/utils";

/* Official lockups (PNG, trimmed). Dark theme gets a variant with the navy "Script" lightened so it stays legible. */
export function Logo({ className, href = "/", icon = false }: { className?: string; href?: string; icon?: boolean }) {
  const img = icon ? (
    // eslint-disable-next-line @next/next/no-img-element
    <img src="/brand/scriptliv-emblem.png" width={262} height={256} alt="ScriptLiv" className={cn("block", className)} />
  ) : (
    <>
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img src="/brand/scriptliv-logo-light.png" width={557} height={160} alt="ScriptLiv" className={cn("block dark:hidden", className)} />
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img src="/brand/scriptliv-logo-dark.png" width={557} height={160} alt="" aria-hidden className={cn("hidden dark:block", className)} />
    </>
  );
  return <Link href={href} aria-label="ScriptLiv home" className="inline-flex shrink-0 items-center">{img}</Link>;
}

/* Round sun/moon switch (reference navbar). Shows the icon of the theme you will switch to. */
export function ThemeToggle() {
  const [dark, setDark] = useState(true);
  useEffect(() => setDark(document.documentElement.classList.contains("dark")), []);
  return (
    <button
      aria-label={dark ? "Switch to light theme" : "Switch to dark theme"}
      onClick={() => {
        const n = !dark;
        document.documentElement.classList.toggle("dark", n);
        try { localStorage.setItem("sl-theme", n ? "dark" : "light"); } catch { /* ignore */ }
        setDark(n);
      }}
      className="grid size-10 place-items-center rounded-full border border-line bg-surface/60 text-ink-2 transition-colors hover:border-violet hover:text-ink"
    >
      {dark ? <Sun className="size-[18px]" /> : <Moon className="size-[18px]" />}
    </button>
  );
}

/* Outlined pill label ("Real-time Speech to Text", "Use Cases"). */
export function Chip({ children, className }: { children: React.ReactNode; className?: string }) {
  return (
    <span className={cn("inline-flex items-center gap-2 rounded-full border border-line bg-surface/50 px-4 py-1.5 text-sm font-medium text-ink-2", className)}>
      {children}
    </span>
  );
}
