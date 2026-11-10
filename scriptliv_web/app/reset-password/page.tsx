"use client";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Suspense, useState } from "react";
import { AuthShell } from "@/components/auth-shell";
import { Button, Field, Notice, inputCls } from "@/components/ui";
import { api, ApiError } from "@/lib/api";

function Reset() {
  const token = useSearchParams().get("token");
  const [pw, setPw] = useState("");
  const [pw2, setPw2] = useState("");
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!token) return;
    if (pw !== pw2) { setErr("The two passwords do not match."); return; }
    setBusy(true); setErr(null);
    try { await api.resetPassword(token, pw); setDone(true); }
    catch (x) { setErr(x instanceof ApiError ? x.message : "Could not reset the password. Try again."); }
    setBusy(false);
  }

  return (
    <AuthShell title="Choose a new password" footer={<Link href="/login" className="font-medium text-primary">Sign in</Link>}>
      {!token ? <Notice tone="error" title="This link is missing its token">Request a new reset email from the <Link href="/forgot-password" className="underline">forgot password</Link> page.</Notice>
        : done ? <Notice tone="success" title="Password updated">You were signed out everywhere. <Link href="/login" className="font-medium underline">Sign in with your new password</Link>.</Notice>
        : (
          <form onSubmit={submit} className="space-y-4">
            <Field label="New password"><input type="password" required minLength={8} autoComplete="new-password" value={pw} onChange={(e) => setPw(e.target.value)} className={inputCls} /></Field>
            <Field label="Repeat new password"><input type="password" required minLength={8} autoComplete="new-password" value={pw2} onChange={(e) => setPw2(e.target.value)} className={inputCls} /></Field>
            {err && <Notice tone="error" title={err}>{/expired|invalid/i.test(err) && <Link href="/forgot-password" className="underline">Request a new link</Link>}</Notice>}
            <Button type="submit" size="lg" className="w-full" disabled={busy}>{busy ? "Saving…" : "Update password"}</Button>
          </form>
        )}
    </AuthShell>
  );
}

export default function ResetPasswordPage() { return <Suspense><Reset /></Suspense>; }
