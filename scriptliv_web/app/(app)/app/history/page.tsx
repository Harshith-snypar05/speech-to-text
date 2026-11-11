"use client";
import { Link2 } from "lucide-react";
import Link from "next/link";
import { useEffect, useState } from "react";
import { Badge, Empty, Notice, Spinner } from "@/components/ui";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { fmtTime } from "@/lib/format";
import type { SessionItem } from "@/lib/types";

export default function HistoryPage() {
  const { token } = useAuth();
  const [rows, setRows] = useState<SessionItem[] | null>(null);
  const [err, setErr] = useState(false);
  useEffect(() => { if (token) api.sessions(token).then(setRows).catch(() => setErr(true)); }, [token]);

  return (
    <div className="space-y-5">
      <h1 className="text-2xl font-semibold">Transcripts</h1>
      {err && <Notice tone="error" title="Could not load your transcripts" />}
      {!rows && !err && <Spinner />}
      {rows && rows.length === 0 && <Empty title="No transcripts yet">Sessions you record will be listed here.</Empty>}
      {rows && rows.length > 0 && (
        <ul className="space-y-2">
          {rows.map((r) => (
            <li key={r.session_id}>
              <Link href={`/app/history/${r.session_id}`} className="flex flex-col items-start gap-2 rounded-2xl border border-line bg-surface p-4 hover:border-primary sm:flex-row sm:items-center sm:justify-between sm:gap-3">
                <div className="min-w-0 max-w-full">
                  <div className="truncate font-medium">{r.title || "Untitled session"}</div>
                  <div className="text-xs text-ink-2">{fmtTime(r.started_at)}</div>
                </div>
                <div className="flex shrink-0 flex-wrap gap-2">
                  {r.sharing && <Badge tone="primary"><Link2 className="size-3" /> Shared</Badge>}
                  <Badge tone={r.ended_at ? "neutral" : "info"}>{r.ended_at ? "Completed" : "In progress"}</Badge>
                </div>
              </Link>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
