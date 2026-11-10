"use client";
import { Check } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { Badge, Button, Card, Notice, Spinner } from "@/components/ui";
import { api, ApiError } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { fmtDate, fmtMinutes } from "@/lib/format";
import { PaymentBanner } from "@/components/payment-banner";
import type { PaymentIssue, Plans, UsageSummary } from "@/lib/types";

export default function PlansPage() {
  const { token } = useAuth();
  const [plans, setPlans] = useState<Plans | null>(null);
  const [usage, setUsage] = useState<UsageSummary | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [pay, setPay] = useState<PaymentIssue | null>(null);

  const loadPay = useCallback(() => { if (token) api.subscription(token).then((r) => setPay(r.subscription.payment ?? null)).catch(() => {}); }, [token]);
  useEffect(() => {
    if (!token) return;
    loadPay();
    Promise.all([api.plans(), api.usage(token)]).then(([p, u]) => { setPlans(p); setUsage(u); })
      .catch((e) => setErr(e instanceof ApiError ? e.message : "Could not load plans."));
  }, [token, loadPay]);

  async function buy(kind: "pro" | "addon") {
    if (!token) return;
    setBusy(kind); setErr(null);
    try { window.location.assign((await api.checkout(token, kind)).url); }
    catch (e) { setErr(e instanceof ApiError ? e.message : "Could not start checkout."); setBusy(null); }
  }

  if (!plans || !usage) return err ? <Notice tone="error" title={err} /> : <div className="py-16 text-center"><Spinner /></div>;
  const can = plans.purchasing_available;

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold">Plans and add-ons</h1>
        <p className="text-sm text-ink-2">Only the speaker uses minutes. Viewers are always free.</p>
      </div>
      <PaymentBanner payment={pay} onChanged={loadPay} />
      {!can && <Notice tone="info" title="Purchases are not switched on yet">Plans and add-ons can be bought once billing is enabled. Your free minutes work as normal.</Notice>}
      {err && <Notice tone="error" title={err} />}

      <div className="grid gap-4 md:grid-cols-2">
        {plans.plans.map((p) => {
          const current = usage.plan === p.id;
          return (
            <Card key={p.id} className={current ? "border-primary" : ""}>
              <div className="flex items-center justify-between">
                <h2 className="text-lg font-semibold">{p.name}</h2>
                {current && <Badge tone="primary">Your plan</Badge>}
              </div>
              <div className="mt-2 text-3xl font-semibold">{p.price_usd_month ? `$${p.price_usd_month}` : "Free"}<span className="text-sm font-normal text-ink-2">{p.price_usd_month ? " / month" : ""}</span></div>
              <p className="mt-1 text-sm text-ink-2">{p.blurb}</p>
              <ul className="mt-4 space-y-1.5 text-sm">
                <li className="flex gap-2"><Check className="mt-0.5 size-4 text-primary" /> {p.included_minutes.toLocaleString()} minutes every month</li>
                <li className="flex gap-2"><Check className="mt-0.5 size-4 text-primary" /> Unlimited viewers on shared links</li>
                <li className="flex gap-2"><Check className="mt-0.5 size-4 text-primary" /> Use it on any device</li>
              </ul>
              {p.id === "pro" && !current && <Button className="mt-5 w-full" disabled={!can || busy !== null} onClick={() => buy("pro")}>{busy === "pro" ? "Opening checkout…" : "Upgrade to Pro"}</Button>}
              {current && <p className="mt-5 text-sm text-ink-2">Resets {fmtDate(usage.reset_at)}</p>}
            </Card>
          );
        })}
      </div>

      <Card className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h2 className="font-semibold">Add-on: {plans.addon.minutes.toLocaleString()} minutes for ${plans.addon.price_usd}</h2>
          <p className="text-sm text-ink-2">{plans.addon.note}</p>
          <p className="mt-1 text-sm">Add-on balance now: <b>{fmtMinutes(usage.addon_remaining_seconds)}</b></p>
        </div>
        <Button variant="outline" disabled={!can || busy !== null} onClick={() => buy("addon")}>{busy === "addon" ? "Opening checkout…" : "Buy add-on"}</Button>
      </Card>
    </div>
  );
}
