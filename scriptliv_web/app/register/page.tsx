"use client";
import Link from "next/link";
import { useState } from "react";
import { AuthShell } from "@/components/auth-shell";
import { CheckEmail } from "@/components/check-email";
import { Button, Field, Notice, inputCls } from "@/components/ui";
import { ApiError } from "@/lib/api";
import { useAuth } from "@/lib/auth";

export default function RegisterPage() {
  const { signUp } = useAuth();
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [sent, setSent] = useState<{ email: string; devToken?: string } | null>(null);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (password.length < 8) { setErr("Password must be at least 8 characters."); return; }
    setBusy(true);
    setErr(null);
    try {
      const r = await signUp(name.trim(), email.trim(), password);
      setSent({ email: r.user.email, devToken: r.verification?.dev_token });
    } catch (x) {
      setErr(x instanceof ApiError ? x.message : "Could not create the account. Try again.");
    } finally {
      setBusy(false);
    }
  }

  if (sent) {
    return (
      <AuthShell title="Verify your email" subtitle="One more step before you can sign in.">
        <CheckEmail email={sent.email} devToken={sent.devToken} onDevToken={(t) => setSent({ ...sent, devToken: t })} />
      </AuthShell>
    );
  }

  return (
    <AuthShell title="Create your account" subtitle="Start with 300 free minutes every month. No card needed."
      footer={<>Already have an account? <Link href="/login" className="font-medium text-primary">Sign in</Link></>}>
      <form onSubmit={submit} className="space-y-4">
        <Field label="Name">
          <input required maxLength={80} autoComplete="name" value={name} onChange={(e) => setName(e.target.value)} className={inputCls} />
        </Field>
        <Field label="Email">
          <input type="email" required autoComplete="email" value={email} onChange={(e) => setEmail(e.target.value)} className={inputCls} />
        </Field>
        <Field label="Password" hint="At least 8 characters.">
          <input type="password" required minLength={8} autoComplete="new-password" value={password} onChange={(e) => setPassword(e.target.value)} className={inputCls} />
        </Field>
        {err && <Notice tone="error" title={err} />}
        <Button type="submit" size="lg" className="w-full" disabled={busy}>{busy ? "Creating account…" : "Create account"}</Button>
        <p className="text-xs text-ink-3">By creating an account you agree to the Terms and Privacy Policy of Snypar Tech.</p>
      </form>
    </AuthShell>
  );
}
