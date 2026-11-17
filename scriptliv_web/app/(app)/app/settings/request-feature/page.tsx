"use client";
import Link from "next/link";
import { ChevronLeft } from "lucide-react";
import { useState, type FormEvent } from "react";
import { Button, Card, Field, Notice, inputCls } from "@/components/ui";
import { api, ApiError } from "@/lib/api";
import { useAuth } from "@/lib/auth";

type Kind = "feature" | "bug" | "other";
const KINDS: [Kind, string][] = [["feature", "Feature idea"], ["bug", "Problem"], ["other", "Other"]];

export default function RequestFeaturePage() {
  const { token } = useAuth();
  const [kind, setKind] = useState<Kind>("feature");
  const [title, setTitle] = useState("");
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);
  const [sent, setSent] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const mailto = `mailto:info@scriptliv.com?subject=${encodeURIComponent(`[${kind}] ${title}`)}&body=${encodeURIComponent(message)}`;

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    if (!token) return;
    setBusy(true);
    setErr(null);
    try {
      await api.sendFeedback(token, kind, title.trim(), message.trim());
      setSent(true);
    } catch (x) {
      setErr(x instanceof ApiError ? x.message : "Could not send right now.");
    }
    setBusy(false);
  };

  return (
    <div className="space-y-5">
      <div>
        <Link href="/app/settings" className="inline-flex items-center gap-1 text-sm text-ink-2 hover:text-primary">
          <ChevronLeft className="size-4" aria-hidden /> Settings
        </Link>
        <h1 className="mt-2 text-2xl font-semibold">Request a feature</h1>
        <p className="text-sm text-ink-2">Tell us what would make ScriptLiv better. Your message goes to info@scriptliv.com.</p>
      </div>
      {sent ? (
        <Notice tone="success" title="Thank you! Your message reached the team.">We read every one.</Notice>
      ) : (
        <Card>
          <form onSubmit={submit} className="space-y-4">
            <div role="radiogroup" aria-label="Type" className="flex flex-wrap gap-2">
              {KINDS.map(([k, label]) => (
                <button
                  key={k}
                  type="button"
                  role="radio"
                  aria-checked={kind === k}
                  onClick={() => setKind(k)}
                  className={"rounded-full border px-3 py-1 text-sm " + (kind === k ? "border-primary bg-lavender text-primary" : "border-line text-ink-2")}
                >
                  {label}
                </button>
              ))}
            </div>
            <Field label="Title">
              <input required maxLength={120} value={title} onChange={(e) => setTitle(e.target.value)} className={inputCls} />
            </Field>
            <Field label="Details (optional)">
              <textarea rows={6} maxLength={4000} value={message} onChange={(e) => setMessage(e.target.value)} className={inputCls + " h-auto rounded-2xl py-3"} />
            </Field>
            {err && (
              <Notice tone="error" title={err}>
                You can also <a className="font-medium underline" href={mailto}>email it to info@scriptliv.com</a>.
              </Notice>
            )}
            <Button type="submit" disabled={busy || !title.trim()}>{busy ? "Sending..." : "Send"}</Button>
          </form>
        </Card>
      )}
    </div>
  );
}
