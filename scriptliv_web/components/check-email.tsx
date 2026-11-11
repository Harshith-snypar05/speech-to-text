"use client";
import Link from "next/link";
import { useState } from "react";
import { Button, Notice } from "@/components/ui";
import { api, ApiError } from "@/lib/api";

/**
 * Shown after sign-up, and when sign-in is refused because the email is not verified yet. The account cannot sign in until
 * the emailed link is opened. In test environments (no mail provider) the API hands back the link itself so it can be opened here.
 */
export function CheckEmail({ email, devToken, onDevToken, onSignIn }: { email: string; devToken?: string; onDevToken?: (t: string) => void; onSignIn?: () => void }) {
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState<{ ok: boolean; text: string } | null>(null);

  async function resend() {
    setBusy(true);
    setNote(null);
    try {
      const r = await api.resendVerificationPublic(email);
      if (r.dev_token) onDevToken?.(r.dev_token);
      setNote({ ok: true, text: "If this account still needs verification, a new link is on its way." });
    } catch (e) {
      setNote({ ok: false, text: e instanceof ApiError ? e.message : "Could not resend. Try again." });
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-4">
      <Notice tone="info" title="Check your email">
        We sent a verification link to <strong>{email}</strong>. Open it to confirm your address, then sign in. You cannot sign in until it is verified.
      </Notice>
      {devToken && (
        <Notice tone="warning" title="Test environment: email is not sent">
          <Link className="font-medium text-primary underline" href={`/verify-email?token=${encodeURIComponent(devToken)}`}>Open the verification link</Link>
        </Notice>
      )}
      {note && <Notice tone={note.ok ? "success" : "error"} title={note.text} />}
      <Button type="button" variant="secondary" className="w-full" disabled={busy} onClick={resend}>{busy ? "Sending…" : "Resend verification email"}</Button>
      <p className="text-center text-sm text-ink-2">Already verified? {onSignIn ? <button type="button" onClick={onSignIn} className="font-medium text-primary">Sign in</button> : <Link href="/login" className="font-medium text-primary">Sign in</Link>}</p>
    </div>
  );
}
