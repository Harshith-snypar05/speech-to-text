"use client";
import { Smartphone } from "lucide-react";
import { useParams } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { Logo, ThemeToggle } from "@/components/brand";
import { Badge, Card, Copyright, Empty, Notice, Spinner } from "@/components/ui";
import { api, ApiError } from "@/lib/api";
import { fmtTime } from "@/lib/format";
import type { SharedView } from "@/lib/types";

/** Public, read-only transcript. No sign-in; viewers never use minutes. Polls while the session is live. */
export default function SharedPage() {
  const { token } = useParams<{ token: string }>();
  const [v, setV] = useState<SharedView | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const end = useRef<HTMLDivElement>(null);

  useEffect(() => {
    let stop = false;
    let timer: ReturnType<typeof setTimeout>;
    async function tick() {
      try {
        const r = await api.shared(token);
        if (stop) return;
        setV(r); setErr(null);
        timer = setTimeout(tick, r.live ? 1000 : 15000);
      } catch (e) {
        if (stop) return;
        if (e instanceof ApiError && e.status === 404) { setErr("This link is not available. The owner may have stopped sharing it."); return; }
        setErr("Connection problem. Retrying…");
        timer = setTimeout(tick, 4000);
      }
    }
    void tick();
    return () => { stop = true; clearTimeout(timer); };
  }, [token]);

  useEffect(() => { if (v?.live) end.current?.scrollIntoView({ behavior: "smooth", block: "end" }); }, [v?.transcript.length, v?.live]);

  return (
    <div className="mx-auto flex min-h-dvh max-w-2xl flex-col px-4 py-5">
      <header className="mb-5 flex items-center justify-between"><Logo className="h-8 w-auto" /><ThemeToggle /></header>
      {err && <Notice tone={v ? "warning" : "error"} title={err} />}
      {!v && !err && <div className="py-16 text-center"><Spinner /></div>}
      {v && (
        <main className="flex-1 space-y-4">
          <div>
            <div className="flex flex-wrap items-center gap-2">
              <h1 className="text-xl font-semibold">{v.title || "Shared transcript"}</h1>
              {v.live ? <Badge tone="success"><span className="size-1.5 animate-pulse rounded-full bg-current" />Live</Badge> : <Badge>Ended</Badge>}
            </div>
            <p className="text-xs text-ink-2">{fmtTime(v.started_at)}</p>
          </div>
          {v.transcript.length === 0 ? (
            <Empty title={v.live ? "Waiting for speech…" : "No transcript text"}>{v.live ? "Text appears here as the speaker talks." : "Nothing was transcribed in this session."}</Empty>
          ) : (
            <Card className="space-y-3" aria-live="polite">
              {v.transcript.map((t, i) => <p key={i} className="leading-relaxed">{t}</p>)}
              <div ref={end} />
            </Card>
          )}
          <Card className="flex flex-wrap items-center justify-between gap-3 bg-lavender/50">
            <div className="flex items-center gap-3 text-sm"><Smartphone className="size-5 text-primary" /> Read this on your phone with the ScriptLiv app.</div>
            <div className="flex gap-2 text-sm font-medium">
              <a href={v.app_links.deep_link} className="rounded-xl border border-primary px-3 py-1.5 text-primary">Open in app</a>
              {v.app_links.android_store && <a href={v.app_links.android_store} className="rounded-xl border border-line px-3 py-1.5">Google Play</a>}
              {v.app_links.ios_store && <a href={v.app_links.ios_store} className="rounded-xl border border-line px-3 py-1.5">App Store</a>}
            </div>
          </Card>
        </main>
      )}
      <Copyright className="mt-8 text-center" />
    </div>
  );
}
