"use client";
import { useEffect, useState } from "react";
import { cn } from "@/lib/utils";

/** Sticky header: clear at the top of the page, translucent blurred bar once scrolled. */
export function ScrollHeader({ children }: { children: React.ReactNode }) {
  const [scrolled, setScrolled] = useState(false);
  useEffect(() => {
    const on = () => setScrolled(window.scrollY > 8);
    on();
    window.addEventListener("scroll", on, { passive: true });
    return () => window.removeEventListener("scroll", on);
  }, []);
  return (
    <header
      className={cn(
        "sticky top-0 z-30 border-b transition-[background-color,border-color,backdrop-filter] duration-200",
        scrolled ? "border-line/60 bg-bg/70 backdrop-blur-xl" : "border-transparent bg-transparent",
      )}
    >
      {children}
    </header>
  );
}
