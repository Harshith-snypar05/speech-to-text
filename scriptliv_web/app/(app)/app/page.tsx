"use client";
import { ArrowRight, Mic } from "lucide-react";
import Link from "next/link";
import { useEffect, useState } from "react";
import { Badge, Button, Card, Empty, Notice, Progress, Spinner, Stat } from "@/components/ui";
import { api, ApiError } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { fmtDate, fmtMinutes, fmtSecs, fmtTime } from "@/lib/format";
import type { UsageSession, UsageSummary } from "@/lib/types";

export default function HomePage() {
  const { token, user } = useAuth();
  const [usage, setUsage] = useState<UsageSummary | null>(null);
  const [sessions, setSessions] = useState<UsageSession[] | null>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    if (!token) return;
    Promise.all([api.usage(token), api.usageSessions(token)])
      .then(([u, s]) => { setUsage(u); setSessions(s); })
      .catch((e) => setErr(e instanceof ApiError ? e.message : "Could not load usage."));
  }, [token]);

  if (err) return <Notice tone="error" title="Could not load your usage">{err}</Notice>;
  if (!usage || !sessions) return <div className="py-16 text-center"><Spinner /></div>;

  const pct = usage.percent_used;
  const tone = usage.total_remaining_seconds <= 0 ? "error" : pct >= 80 ? "warning" : "primary";
  const out = usage.total_remaining_seconds <= 0;

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold">Hi {user?.name?.split(" ")[0] ?? "there"}</h1>
          <p className="text-sm text-ink-2">Here is your usage for this period.</p>
        </div>
        <Link href="/app/record"><Button size="lg" disabled={out}><Mic className="size-4" /> Start transcribing</Button></Link>
      </div>

      {user && !user.email_verified && (
        <Notice tone="warning" title="Confirm your email">
          We sent a link to {user.email}. <Link href="/app/settings" className="font-medium text-primary underline">Resend it from Settings</Link>.
        </Notice>
      )}
      {usage.warnings.map((w) => <Notice key={w.level} tone={out ? "error" : "warning"} title={w.message}>
        <Link href="/app/plans" className="font-medium text-primary underline">See plans and add-ons</Link>
      </Notice>)}

      <Card>
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div className="flex items-center gap-2"><h2 className="font-semibold">{usage.plan_name} plan</h2>{usage.cancel_at_period_end && <Badge tone="warning">Ends {fmtDate(usage.reset_at)}</Badge>}</div>
          <span className="text-sm text-ink-2">{usage.cancel_at_period_end ? "Access ends" : "Resets"} {fmtDate(usage.reset_at)}</span>
        </div>
        <div className="mt-4"><Progress value={pct} tone={tone} label="Included minutes used" /></div>
        <p className="mt-2 text-sm text-ink-2">
          {fmtSecs(usage.included_used_seconds)} of {usage.included_minutes.toLocaleString()} min used · {fmtSecs(usage.included_remaining_seconds)} left
        </p>
      </Card>

      <div className="grid gap-3 sm:grid-cols-3">
        <Stat label="Included left" value={fmtMinutes(usage.included_remaining_seconds)} hint={`of ${usage.included_minutes.toLocaleString()} min`} />
        <Stat label="Add-on balance" value={fmtMinutes(usage.addon_remaining_seconds)} hint={usage.addons.length ? `Expires ${fmtDate(Math.min(...usage.addons.map((a) => a.expires_at)))}` : "None active"} />
        <Stat label="Total available" value={fmtMinutes(usage.total_remaining_seconds)} hint={`Resets ${fmtDate(usage.reset_at)}`} />
      </div>
      <p className="text-xs text-ink-2">Only the person speaking uses minutes. People watching a shared transcript never do.</p>

      <section>
        <div className="mb-3 flex items-center justify-between">
          <h2 className="font-semibold">Recent sessions</h2>
          <Link href="/app/history" className="inline-flex items-center gap-1 text-sm font-medium text-primary">All transcripts <ArrowRight className="size-3.5" /></Link>
        </div>
        {sessions.length === 0 ? (
          <Empty title="No sessions yet">Start transcribing and your usage appears here, session by session.</Empty>
        ) : (
          <Card className="divide-y divide-line p-0">
            {sessions.slice(0, 6).map((s) => (
              <div key={s.session_id} className="flex flex-wrap items-center justify-between gap-2 px-4 py-3 text-sm">
                <span>{fmtTime(s.started_at)}{s.ended_at == null && <Badge tone="info" className="ml-2">Live</Badge>}</span>
                <span className="tabular-nums text-ink-2">{fmtSecs(s.metered_seconds)}</span>
              </div>
            ))}
          </Card>
        )}
      </section>
    </div>
  );
}
