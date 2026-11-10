"use client";
import type { ReactNode } from "react";
import { Logo, ThemeToggle } from "@/components/brand";
import { Card, Copyright } from "@/components/ui";

export function AuthShell({ title, subtitle, children, footer }: { title: string; subtitle?: string; children: ReactNode; footer?: ReactNode }) {
  return (
    <main className="soft-gradient relative grid min-h-dvh place-items-center px-4 py-10">
      <div className="absolute right-4 top-4"><ThemeToggle /></div>
      <div className="w-full max-w-sm">
        <div className="mb-6 flex justify-center"><Logo className="h-12 w-auto" /></div>
        <Card className="p-6">
          <h1 className="text-xl font-semibold">{title}</h1>
          {subtitle && <p className="mt-1 text-sm text-ink-2">{subtitle}</p>}
          <div className="mt-5">{children}</div>
        </Card>
        {footer && <div className="mt-4 text-center text-sm text-ink-2">{footer}</div>}
        <Copyright className="mt-6 text-center" />
      </div>
    </main>
  );
}
