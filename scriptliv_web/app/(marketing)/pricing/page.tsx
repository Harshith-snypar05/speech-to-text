"use client";
import { Check } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { AuthTrigger } from "@/components/auth-modal";
import { PaymentBanner } from "@/components/payment-banner";
import { Badge, Notice, Spinner } from "@/components/ui";
import { buttonCls } from "@/components/ui/button-styles";
import { startCashfreeCheckout } from "@/lib/cashfree";
import { api, ApiError } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { fmtDate, fmtMinutes } from "@/lib/format";
import type { PaymentIssue, Plans, UsageSummary } from "@/lib/types";

function fmtSessionLimit(minutes?: number | null) {
  if (!minutes) return "No time limit per session";
  if (minutes % 60 === 0) {
    const hours = minutes / 60;
    return `Up to ${hours} ${hours === 1 ? "hour" : "hours"} per session`;
  }
  return `Up to ${minutes} minutes per session`;
}

export default function PricingPage() {
  const { token } = useAuth();
  const [plans, setPlans] = useState<Plans | null>(null);
  const [usage, setUsage] = useState<UsageSummary | null>(null);
  const [pay, setPay] = useState<PaymentIssue | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);

  const loadPay = useCallback(() => { if (token) api.subscription(token).then((r) => setPay(r.subscription.payment ?? null)).catch(() => {}); }, [token]);
  useEffect(() => {
    api.plans().then(setPlans).catch((e) => setErr(e instanceof ApiError ? e.message : "Could not load pricing."));
  }, []);
  useEffect(() => {
    if (!token) { setUsage(null); return; }
    loadPay();
    api.usage(token).then(setUsage).catch(() => {});
  }, [token, loadPay]);

  async function buy(kind: "pro" | "addon") {
    if (!token) return;
    setBusy(kind); setErr(null);
    try {
      const r = await api.checkout(token, kind);
      await startCashfreeCheckout(r);
      setBusy(null);
    } catch (e) { setErr(e instanceof ApiError ? e.message : e instanceof Error ? e.message : "Could not start checkout."); setBusy(null); }
  }

  const can = plans?.purchasing_available ?? false;

  return (
    <main>
      <section className="relative isolate py-16">
        <div className="mx-auto max-w-[1400px] px-4 sm:px-8">
          <div className="text-center">
            <h1 className="text-3xl font-extrabold tracking-tight sm:text-5xl">Simple, <span className="gradient-text">Transparent Pricing</span></h1>
            <p className="mx-auto mt-3 max-w-xl text-ink-2 sm:text-lg">Start free. Upgrade when you need more minutes. Only the speaker uses minutes &mdash; viewers are always free.</p>
          </div>

          {!plans && !err && <div className="py-16 text-center"><Spinner /></div>}
          {err && <div className="mx-auto mt-8 max-w-3xl"><Notice tone="error" title={err} /></div>}

          {plans && (
            <>
              {token && pay && <div className="mx-auto mt-8 max-w-3xl"><PaymentBanner payment={pay} onChanged={loadPay} /></div>}
              {!can && <div className="mx-auto mt-8 max-w-3xl"><Notice tone="info" title="Purchases are not switched on yet">Plans and add-ons can be bought once billing is enabled. Free minutes work as normal.</Notice></div>}

              <div className="mx-auto mt-12 grid max-w-3xl gap-5 sm:grid-cols-2">
                {plans.plans.map((p) => {
                  const current = usage?.plan === p.id;
                  return (
                    <div key={p.id} className={"sl-panel rounded-[var(--radius-card)] p-7" + (current ? " border-primary" : "")}>
                      <div className="flex items-center justify-between">
                        <h2 className="text-lg font-bold">{p.name}</h2>
                        {current && <Badge tone="primary">Your plan</Badge>}
                      </div>
                      <div className="mt-2 text-3xl font-extrabold">
                        {p.price_display ?? "Free"}
                        {(p.price_inr_month ?? 0) > 0 && <span className="text-sm font-normal text-ink-2"> / month</span>}
                      </div>
                      <p className="mt-2 text-sm text-ink-2">{p.blurb}</p>
                      <ul className="mt-5 space-y-2 text-sm">
                        <li className="flex gap-2"><Check className="mt-0.5 size-4 text-primary" aria-hidden /> {p.included_minutes.toLocaleString()} minutes every month</li>
                        <li className="flex gap-2"><Check className="mt-0.5 size-4 text-primary" aria-hidden /> {fmtSessionLimit(p.max_session_minutes)}</li>
                        {p.id === "pro" && <li className="flex gap-2"><Check className="mt-0.5 size-4 text-primary" aria-hidden /> Add-ons supported</li>}
                        <li className="flex gap-2"><Check className="mt-0.5 size-4 text-primary" aria-hidden /> Unlimited viewers on shared links</li>
                        <li className="flex gap-2"><Check className="mt-0.5 size-4 text-primary" aria-hidden /> Use it on any device</li>
                      </ul>
                      {!token && (
                        <AuthTrigger mode="register" className={buttonCls({ variant: p.id === "pro" ? "primary" : "outline", size: "md" }) + " mt-6 w-full justify-center"}>
                          Get Started
                        </AuthTrigger>
                      )}
                      {token && p.id === "pro" && !current && (
                        <button className={buttonCls({ size: "md" }) + " mt-6 w-full justify-center"} disabled={!can || busy !== null} onClick={() => buy("pro")}>
                          {busy === "pro" ? "Opening checkout…" : "Upgrade to Pro"}
                        </button>
                      )}
                      {token && current && usage && <p className="mt-6 text-sm text-ink-2">Resets {fmtDate(usage.reset_at)}</p>}
                    </div>
                  );
                })}
              </div>

              <div className="mx-auto mt-6 max-w-3xl">
                <div className="sl-panel flex flex-wrap items-center justify-between gap-4 rounded-[var(--radius-card)] p-7">
                  <div>
                    <h2 className="text-lg font-bold">Add-on: {plans.addon.minutes.toLocaleString()} minutes for {plans.addon.price_display}</h2>
                    <p className="mt-1 text-sm text-ink-2">{plans.addon.note}</p>
                    {token && usage?.plan === "pro" && <p className="mt-2 text-sm">Add-on balance now: <b>{fmtMinutes(usage.addon_remaining_seconds)}</b></p>}
                    {token && usage && usage.plan !== "pro" && <p className="mt-2 text-sm text-ink-2">Upgrade to Pro to buy add-ons.</p>}
                  </div>
                  {!token && (
                    <AuthTrigger mode="register" className={buttonCls({ variant: "outline", size: "md" })}>Get Started</AuthTrigger>
                  )}
                  {token && usage?.plan === "pro" && (
                    <button className={buttonCls({ variant: "outline", size: "md" })} disabled={!can || busy !== null} onClick={() => buy("addon")}>
                      {busy === "addon" ? "Opening checkout…" : "Buy add-on"}
                    </button>
                  )}
                </div>
              </div>
            </>
          )}
        </div>
      </section>
    </main>
  );
}
