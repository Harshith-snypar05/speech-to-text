"use client";
import { Link2 } from "lucide-react";
import Link from "next/link";
import { useEffect, useState } from "react";
import { Badge, Empty, Notice, PaginationControls, Spinner } from "@/components/ui";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { fmtTime } from "@/lib/format";
import type { SessionItem } from "@/lib/types";

export default function HistoryPage() {
  const { token } = useAuth();
  const [rows, setRows] = useState<SessionItem[] | null>(null);
  const [err, setErr] = useState(false);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(10);

  useEffect(() => {
    if (token) api.sessions(token).then(setRows).catch(() => setErr(true));
  }, [token]);

  const total = rows ? rows.length : 0;
  const paginated = rows ? rows.slice((page - 1) * pageSize, page * pageSize) : [];

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-2xl font-semibold">Transcripts</h1>
        {rows && rows.length > 0 && (
          <span className="text-xs text-ink-2">{rows.length} total transcripts</span>
        )}
      </div>

      {err && <Notice tone="error" title="Could not load your transcripts" />}
      {!rows && !err && <Spinner />}
      {rows && rows.length === 0 && <Empty title="No transcripts yet">Sessions you record will be listed here.</Empty>}

      {rows && rows.length > 0 && (
        <div className="space-y-4">
          <ul className="space-y-2">
            {paginated.map((r) => (
              <li key={r.session_id}>
                <Link
                  href={`/app/history/${r.session_id}`}
                  className="flex flex-col items-start gap-2 rounded-2xl border border-line bg-surface p-4 hover:border-primary sm:flex-row sm:items-center sm:justify-between sm:gap-3 transition-colors"
                >
                  <div className="min-w-0 max-w-full">
                    <div className="truncate font-medium">{r.title || "Untitled session"}</div>
                    <div className="text-xs text-ink-2">{fmtTime(r.started_at)}</div>
                  </div>
                  <div className="flex shrink-0 flex-wrap gap-2">
                    {r.sharing && (
                      <Badge tone="primary">
                        <Link2 className="size-3" /> Shared
                      </Badge>
                    )}
                    <Badge tone={r.ended_at ? "neutral" : "info"}>
                      {r.ended_at ? "Completed" : "In progress"}
                    </Badge>
                  </div>
                </Link>
              </li>
            ))}
          </ul>

          <div className="rounded-2xl border border-line bg-surface overflow-hidden">
            <PaginationControls
              page={page}
              pageSize={pageSize}
              total={total}
              pageSizeOptions={[10, 20, 30, 40, 50]}
              onPageChange={setPage}
              onPageSizeChange={setPageSize}
            />
          </div>
        </div>
      )}
    </div>
  );
}
