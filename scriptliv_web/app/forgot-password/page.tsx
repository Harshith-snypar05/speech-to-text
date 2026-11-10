"use client";
import Link from "next/link";
import { useState } from "react";
import { AuthShell } from "@/components/auth-shell";
import { Button, Field, Notice, inputCls } from "@/components/ui";
import { api, ApiError } from "@/lib/api";

export default function ForgotPasswordPage() {
  const [email, setEmail] = useState("");
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true); setErr(null);
    try { setDone((await api.forgotPassword(email.trim())).message); }
    catch (x) { setErr(x instanceof ApiError ? x.message : "Could not send the email. Try again."); }
    setBusy(false);
  }

  return (
    <AuthShell title="Reset your password" subtitle="Enter your account email and we will send you a reset link."
      footer={<Link href="/login" className="font-medium text-primary">Back to sign in</Link>}>
      {done ? (
        <Notice tone="success" title="Check your inbox">{done} The link works once and expires in 1 hour.</Notice>
      ) : (
        <form onSubmit={submit} className="space-y-4">
          <Field label="Email"><input type="email" required autoComplete="username" value={email} onChange={(e) => setEmail(e.target.value)} className={inputCls} /></Field>
          {err && <Notice tone="error" title={err} />}
          <Button type="submit" size="lg" className="w-full" disabled={busy}>{busy ? "Sending…" : "Send reset link"}</Button>
        </form>
      )}
    </AuthShell>
  );
}
