"use client";
import { cva, type VariantProps } from "class-variance-authority";
import type { ButtonHTMLAttributes, HTMLAttributes, ReactNode } from "react";
import { cn } from "@/lib/utils";

const button = cva(
  "inline-flex items-center justify-center gap-2 rounded-xl font-medium transition-all focus-visible:outline-none disabled:opacity-50 disabled:pointer-events-none active:scale-[0.98]",
  {
    variants: {
      variant: {
        primary: "brand-gradient text-white shadow-[0_8px_20px_-8px_rgba(106,0,255,0.7)] hover:brightness-110",
        secondary: "bg-surface-alt text-ink hover:brightness-95 border border-line",
        ghost: "text-ink-2 hover:bg-surface-alt hover:text-ink",
        danger: "bg-error text-white hover:brightness-110",
        outline: "border border-line text-ink hover:bg-surface-alt",
      },
      size: { sm: "h-8 px-3 text-sm", md: "h-10 px-4 text-sm", lg: "h-12 px-6 text-base" },
    },
    defaultVariants: { variant: "primary", size: "md" },
  },
);

export function Button({ className, variant, size, ...p }: ButtonHTMLAttributes<HTMLButtonElement> & VariantProps<typeof button>) {
  return <button className={cn(button({ variant, size }), className)} {...p} />;
}

export function Card({ className, ...p }: HTMLAttributes<HTMLDivElement>) {
  return <div className={cn("rounded-[var(--radius-card)] border border-line bg-surface p-5 shadow-[var(--shadow)]", className)} {...p} />;
}

type Tone = "neutral" | "success" | "error" | "warning" | "info" | "primary";
const tones: Record<Tone, string> = {
  neutral: "bg-surface-alt text-ink-2 border-line",
  success: "bg-success/10 text-success border-success/30",
  error: "bg-error/10 text-error border-error/30",
  warning: "bg-warning/10 text-warning border-warning/30",
  info: "bg-info/10 text-info border-info/30",
  primary: "bg-primary/10 text-primary border-primary/30",
};
export function Badge({ tone = "neutral", children, className }: { tone?: Tone; children: ReactNode; className?: string }) {
  return <span className={cn("inline-flex items-center gap-1 rounded-full border px-2.5 py-0.5 text-xs font-medium", tones[tone], className)}>{children}</span>;
}

export function Stat({ label, value, hint, tone }: { label: string; value: ReactNode; hint?: ReactNode; tone?: Tone }) {
  return (
    <Card className="p-4">
      <div className="text-xs font-medium uppercase tracking-wide text-ink-3">{label}</div>
      <div className={cn("mt-1 text-2xl font-semibold tabular-nums", value === "unavailable" && "text-ink-3 text-lg")}>{value}</div>
      {hint && <div className="mt-1 text-xs text-ink-2">{hint}</div>}
      {tone && <span className="sr-only">{tone}</span>}
    </Card>
  );
}

export function Empty({ title, children }: { title: string; children?: ReactNode }) {
  return (
    <div className="rounded-[var(--radius-card)] border border-dashed border-line p-10 text-center">
      <div className="font-medium">{title}</div>
      {children && <div className="mx-auto mt-1 max-w-md text-sm text-ink-2">{children}</div>}
    </div>
  );
}

export function Notice({ tone = "info", title, children }: { tone?: Tone; title: string; children?: ReactNode }) {
  return (
    <div role="status" className={cn("rounded-xl border p-4 text-sm", tones[tone])}>
      <div className="font-semibold">{title}</div>
      {children && <div className="mt-1 text-ink-2">{children}</div>}
    </div>
  );
}

export function Spinner() {
  return <span aria-label="Loading" className="inline-block size-4 animate-spin rounded-full border-2 border-primary border-t-transparent" />;
}

export const inputCls = "mt-1 h-11 w-full rounded-xl border border-line bg-bg px-3 text-sm outline-none focus:ring-2 focus:ring-[var(--ring)] disabled:opacity-60";

export function Field({ label, hint, children }: { label: string; hint?: ReactNode; children: ReactNode }) {
  return (
    <label className="block text-sm font-medium">
      {label}
      {children}
      {hint && <span className="mt-1 block text-xs font-normal text-ink-2">{hint}</span>}
    </label>
  );
}

export function Progress({ value, tone = "primary", label }: { value: number; tone?: "primary" | "warning" | "error"; label: string }) {
  const bar = tone === "error" ? "bg-error" : tone === "warning" ? "bg-warning" : "brand-gradient";
  return (
    <div role="progressbar" aria-label={label} aria-valuemin={0} aria-valuemax={100} aria-valuenow={Math.round(value)} className="h-2.5 w-full overflow-hidden rounded-full bg-surface-alt">
      <div className={cn("h-full rounded-full transition-[width]", bar)} style={{ width: `${Math.min(100, Math.max(0, value))}%` }} />
    </div>
  );
}

export function Copyright({ className }: { className?: string }) {
  return <p className={cn("text-xs text-ink-3", className)}>© {new Date().getFullYear()} Snypar Tech. All rights reserved.</p>;
}
