import type { ReactNode } from "react";
import { Logo } from "@/components/brand";
import { cn } from "@/lib/utils";

/**
 * Shared full-page message for 404s and crashes. Plain-language title + one sentence of what to do next,
 * a big gradient code as the visual anchor, and action buttons passed in by the caller.
 * `inline` drops the logo/min-height so it sits inside the signed-in app shell.
 */
export function ErrorView({ code, title, children, actions, reference, inline = false }: {
  code: string; title: string; children: ReactNode; actions: ReactNode; reference?: string; inline?: boolean;
}) {
  return (
    <div className={cn("sl-marketing relative isolate grid overflow-hidden px-4", inline ? "min-h-[60dvh] place-items-center py-10" : "min-h-dvh place-items-center py-16")}>
      {!inline && <div aria-hidden className="sl-wave sl-wave-hero" />}
      <div className="w-full max-w-xl text-center">
        {!inline && <div className="mb-10 flex justify-center"><Logo className="h-10 w-auto" /></div>}
        <div aria-hidden className="gradient-text select-none text-[7rem] font-extrabold leading-none tracking-tighter sm:text-[9rem]">{code}</div>
        <h1 className="mt-4 text-3xl font-bold tracking-tight sm:text-4xl">{title}</h1>
        <p className="mx-auto mt-3 max-w-md text-lg leading-relaxed text-ink-2">{children}</p>
        <div className="mt-8 flex flex-wrap items-center justify-center gap-3">{actions}</div>
        {reference && <p className="mt-8 text-xs text-ink-3">If this keeps happening, tell support this reference: <span className="tabular rounded bg-surface-alt px-1.5 py-0.5 font-mono text-ink-2">{reference}</span></p>}
      </div>
    </div>
  );
}
