"use client";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { ChevronLeft, Receipt } from "lucide-react";
import { useEffect, useState } from "react";
import { Badge, Card, Notice, Spinner } from "@/components/ui";
import { api, ApiError } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { SHOW_SUBSCRIPTIONS } from "@/lib/features";
import { fmtDate, fmtMoney } from "@/lib/format";
import type { PaymentRow } from "@/lib/types";

/** With subscriptions hidden there is no payment history: send direct visits back to Settings. */
export default function PaymentHistoryPage() {
  const router = useRouter();
  useEffect(() => { if (!SHOW_SUBSCRIPTIONS) router.replace("/app/settings"); }, [router]);
  return SHOW_SUBSCRIPTIONS ? <PaymentHistory /> : null;
}

function PaymentHistory() {
  const { token } = useAuth();
  const [rows, setRows] = useState<PaymentRow[] | null>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    if (!token) return;
    api.payments(token)
      .then((r) => setRows(r.payments))
      .catch((e) => setErr(e instanceof ApiError ? e.message : "Could not load payments."));
  }, [token]);

  return (
    <div className="space-y-5">
      <div>
        <Link href="/app/settings" className="inline-flex items-center gap-1 text-sm text-ink-2 hover:text-primary">
          <ChevronLeft className="size-4" aria-hidden /> Settings
        </Link>
        <h1 className="mt-2 text-2xl font-semibold">Payment history</h1>
      </div>
      {err && <Notice tone="error" title={err} />}
      {!rows && !err && <Card><Spinner /></Card>}
      {rows && rows.length === 0 && <Card><p className="text-sm text-ink-2">No payments yet.</p></Card>}
      {rows && rows.length > 0 && (
        <Card className="divide-y divide-line p-0">
          {rows.map((p) => (
            <div key={p.id} className="flex items-center justify-between gap-3 px-5 py-4">
              <div className="min-w-0">
                <div className="truncate text-sm font-medium">{p.description || "Payment"}</div>
                <div className="text-xs text-ink-2">{fmtDate(p.created_at)}</div>
              </div>
              <div className="flex items-center gap-3">
                <div className="text-right">
                  <div className="text-sm font-semibold">{fmtMoney(p.amount_cents, p.currency)}</div>
                  <Badge tone={p.status === "paid" ? "success" : "neutral"}>{p.status}</Badge>
                </div>
                {p.receipt_url && (
                  <a href={p.receipt_url} target="_blank" rel="noreferrer" aria-label="Receipt" className="text-primary">
                    <Receipt className="size-5" aria-hidden />
                  </a>
                )}
              </div>
            </div>
          ))}
        </Card>
      )}
    </div>
  );
}
