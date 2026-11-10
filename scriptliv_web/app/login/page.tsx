"use client";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { AuthShell } from "@/components/auth-shell";
import { CheckEmail } from "@/components/check-email";
import { Button, Field, Notice, inputCls } from "@/components/ui";
import { ApiError } from "@/lib/api";
import { useAuth } from "@/lib/auth";

export default function LoginPage() {
  const { signIn } = useAuth();
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [unverified, setUnverified] = useState<string | null>(null);
  const [devToken, setDevToken] = useState<string | undefined>();

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setErr(null);
    setUnverified(null);
    try {
      await signIn(email.trim(), password);
      router.replace("/app");
    } catch (x) {
      if (x instanceof ApiError && x.code === "email_not_verified") { setUnverified(email.trim()); return; }
      setErr(x instanceof ApiError ? x.message : "Sign-in failed. Try again.");
    } finally {
      setBusy(false);
    }
  }

  if (unverified) {
    return (
      <AuthShell title="Verify your email first" subtitle="This account is not verified yet."
        footer={<button type="button" className="font-medium text-primary" onClick={() => setUnverified(null)}>Back to sign in</button>}>
        <CheckEmail email={unverified} devToken={devToken} onDevToken={setDevToken} />
      </AuthShell>
    );
  }

  return (
    <AuthShell title="Welcome back" subtitle="Sign in to your ScriptLiv account."
      footer={<>New to ScriptLiv? <Link href="/register" className="font-medium text-primary">Create an account</Link></>}>
      <form onSubmit={submit} className="space-y-4">
        <Field label="Email">
          <input type="email" required autoComplete="username" value={email} onChange={(e) => setEmail(e.target.value)} className={inputCls} />
        </Field>
        <Field label="Password">
          <input type="password" required autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)} className={inputCls} />
        </Field>
        <div className="text-right text-sm"><Link href="/forgot-password" className="font-medium text-primary">Forgot password?</Link></div>
        {err && <Notice tone="error" title={err} />}
        <Button type="submit" size="lg" className="w-full" disabled={busy}>{busy ? "Signing in…" : "Sign in"}</Button>
      </form>
    </AuthShell>
  );
}
