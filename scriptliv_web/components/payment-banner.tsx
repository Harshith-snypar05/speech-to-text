"use client";
import { useState } from "react";
import { Button, Notice } from "@/components/ui";
import { api, ApiError } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import type { PaymentIssue, Subscription } from "@/lib/types";

/** Failed-payment state. Retry asks the provider to charge again; access only returns when the provider confirms it. */
export function PaymentBanner({ payment, onChanged }: { payment?: PaymentIssue | null; onChanged: (s?: Subscription) => void }) {
  const { token } = useAuth();
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  if (!payment) return null;

  async function retry() {
    if (!token) return;
    setBusy(true); setMsg(null);
    try { const r = await api.retryPayment(token); onChanged(r.subscription); }
    catch (e) { setMsg(e instanceof ApiError ? e.message : "Could not retry the payment. Try again shortly."); onChanged(); }
    setBusy(false);
  }
  async function portal() {
    if (!token) return;
    try { window.location.assign((await api.portal(token)).url); }
    catch (e) { setMsg(e instanceof ApiError ? e.message : "Could not open billing."); }
  }

  return (
    <Notice tone={payment.access_restricted ? "error" : "warning"} title={payment.access_restricted ? "Payment required" : "Your payment failed"}>
      <p>{payment.message}</p>
      <p className="mt-1 text-xs">
        Attempt {Math.min(payment.failed_attempts, payment.max_retries)} of {payment.max_retries}
        {payment.next_attempt_at ? ` · next automatic retry ${new Date(payment.next_attempt_at * 1000).toLocaleDateString()}` : ""}.
        Your account and transcripts are kept.
      </p>
      <div className="mt-2 flex flex-wrap gap-2">
        <Button size="sm" onClick={retry} disabled={busy || !payment.can_retry}>
          {busy ? "Retrying…" : payment.can_retry ? "Retry payment" : `Retry in ${payment.retry_in_seconds}s`}
        </Button>
        <Button size="sm" variant="outline" onClick={portal}>Update payment method</Button>
      </div>
      {msg && <p className="mt-2 text-sm" role="alert">{msg}</p>}
    </Notice>
  );
}
