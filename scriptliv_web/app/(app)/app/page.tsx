"use client";
import { ArrowRight, Mic } from "lucide-react";
import Link from "next/link";
import { useEffect, useState } from "react";
import { Badge, Button, Card, Empty, Notice, Spinner } from "@/components/ui";
import { api, ApiError } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { fmtTime } from "@/lib/format";
import type { SessionItem, UsageSummary } from "@/lib/types";

export default function HomePage() {
  const { token, user } = useAuth();
  const [usage, setUsage] = useState<UsageSummary | null>(null);
  const [rows, setRows] = useState<SessionItem[] | null>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    if (!token) return;
    Promise.all([api.usage(token), api.sessions(token)])
      .then(([u, s]) => { setUsage(u); setRows(s); })
      .catch((e) => setErr(e instanceof ApiError ? e.message : "Could not load your transcripts."));
  }, [token]);

  if (err) return <Notice tone="error" title="Could not load your transcripts">{err}</Notice>;
  if (!usage || !rows) return <div className="py-16 text-center"><Spinner /></div>;

  const out = usage.total_remaining_seconds <= 0;

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold">Hi {user?.name?.split(" ")[0] ?? "there"}</h1>
          <p className="text-sm text-ink-2">Your recent transcriptions.</p>
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

      <section>
        <div className="mb-3 flex items-center justify-between">
          <h2 className="font-semibold">Recent transcriptions</h2>
          <Link href="/app/history" className="inline-flex items-center gap-1 text-sm font-medium text-primary">All transcripts <ArrowRight className="size-3.5" /></Link>
        </div>
        {rows.length === 0 ? (
          <Empty title="No transcriptions yet">Start transcribing and your sessions are listed here.</Empty>
        ) : (
          <Card className="divide-y divide-line p-0">
            {rows.slice(0, 8).map((r) => (
              <Link key={r.session_id} href={`/app/history/${r.session_id}`} className="flex items-center justify-between gap-3 px-4 py-3 text-sm hover:bg-lavender/40">
                <div className="min-w-0">
                  <div className="truncate font-medium">{r.title || "Untitled session"}</div>
                  <div className="text-xs text-ink-2">{fmtTime(r.started_at)}</div>
                </div>
                <Badge tone={r.ended_at ? "neutral" : "info"}>{r.ended_at ? "Completed" : "In progress"}</Badge>
              </Link>
            ))}
          </Card>
        )}
      </section>
    </div>
  );
}
