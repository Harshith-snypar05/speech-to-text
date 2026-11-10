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

export function ThemeToggle() {
  const [dark, setDark] = useState(false);
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
      className="grid size-9 place-items-center rounded-xl border border-line text-ink-2 hover:bg-surface-alt hover:text-ink"
    >
      {dark ? <Sun className="size-4" /> : <Moon className="size-4" />}
    </button>
  );
}
