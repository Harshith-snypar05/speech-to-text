"use client";
import { ArrowLeft, Check, Copy, FileText, Link2, Link2Off, Pencil, Trash2 } from "lucide-react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { Button, Card, Empty, Notice, Spinner, inputCls } from "@/components/ui";
import { api, ApiError } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { download, fmtTime } from "@/lib/format";
import type { SessionItem } from "@/lib/types";

const absolute = (u: string) => (u.startsWith("http") ? u : `${location.origin}${u.startsWith("/") ? "" : "/"}${u}`);

export default function SessionDetail() {
  const { id } = useParams<{ id: string }>();
  const { token } = useAuth();
  const router = useRouter();
  const [s, setS] = useState<SessionItem | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [msg, setMsg] = useState<string | null>(null);
  const [editing, setEditing] = useState(false);
  const [title, setTitle] = useState("");
  const [copied, setCopied] = useState(false);
  const [confirmDel, setConfirmDel] = useState(false);

  useEffect(() => {
    if (!token) return;
    api.session(token, id).then((r) => { setS(r); setTitle(r.title); })
      .catch((e) => setErr(e instanceof ApiError && e.status === 404 ? "Transcript not found." : "Could not load this transcript."));
  }, [token, id]);

  async function run<T>(fn: () => Promise<T>, ok?: (r: T) => void) {
    setMsg(null);
    try { ok?.(await fn()); } catch (e) { setMsg(e instanceof ApiError ? e.message : "That did not work. Try again."); }
  }
  const rename = () => run(() => api.renameSession(token!, id, title.trim()), (r) => { setS(r); setEditing(false); });
  const toggleShare = () => run(() => (s?.sharing ? api.unshare(token!, id) : api.share(token!, id)), (r) => setS(r));
  const remove = () => run(() => api.deleteSession(token!, id), () => router.replace("/app/history"));
  async function copy() {
    if (!s?.share_url) return;
    try { await navigator.clipboard.writeText(absolute(s.share_url)); setCopied(true); setTimeout(() => setCopied(false), 1500); }
    catch { setMsg("Could not copy. Select the link and copy it by hand."); }
  }

  const lines = s?.transcript ?? [];

  return (
    <div className="space-y-5">
      <Link href="/app/history" className="inline-flex items-center gap-1 text-sm text-ink-2 hover:text-ink"><ArrowLeft className="size-4" /> Transcripts</Link>
      {err && <Notice tone="error" title={err} />}
      {!s && !err && <Spinner />}
      {s && (
        <>
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div className="min-w-0 flex-1">
              {editing ? (
                <form onSubmit={(e) => { e.preventDefault(); void rename(); }} className="flex gap-2">
                  <input aria-label="Title" autoFocus maxLength={120} value={title} onChange={(e) => setTitle(e.target.value)} className={inputCls + " mt-0"} />
                  <Button type="submit" size="md">Save</Button>
                  <Button type="button" variant="ghost" onClick={() => { setEditing(false); setTitle(s.title); }}>Cancel</Button>
                </form>
              ) : (
                <div className="flex items-center gap-2">
                  <h1 className="truncate text-2xl font-semibold">{s.title || "Untitled session"}</h1>
                  <button aria-label="Rename" onClick={() => setEditing(true)} className="grid size-8 place-items-center rounded-lg text-ink-2 hover:bg-surface-alt"><Pencil className="size-4" /></button>
                </div>
              )}
              <p className="text-xs text-ink-2">{fmtTime(s.started_at)}</p>
            </div>
            <Button variant="outline" disabled={!lines.length} onClick={() => download(`${s.title || "transcript"}.txt`, lines.join("\n"))}><FileText className="size-4" /> Export text</Button>
          </div>

          {msg && <Notice tone="error" title={msg} />}

          <Card className="space-y-3">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <div>
                <h2 className="font-semibold">Share this transcript</h2>
                <p className="text-sm text-ink-2">{s.sharing ? "Anyone with the link can read it, live or after. They never use your minutes." : "Sharing is off. Only you can see this transcript."}</p>
              </div>
              <Button variant={s.sharing ? "outline" : "primary"} onClick={toggleShare}>
                {s.sharing ? <><Link2Off className="size-4" /> Stop sharing</> : <><Link2 className="size-4" /> Create link</>}
              </Button>
            </div>
            {s.sharing && s.share_url && (
              <div className="flex gap-2">
                <input readOnly aria-label="Share link" value={absolute(s.share_url)} onFocus={(e) => e.currentTarget.select()} className={inputCls + " mt-0"} />
                <Button variant="outline" onClick={copy}>{copied ? <><Check className="size-4" /> Copied</> : <><Copy className="size-4" /> Copy</>}</Button>
              </div>
            )}
          </Card>

          {lines.length === 0 ? <Empty title="No transcript text">Nothing was transcribed in this session.</Empty> : (
            <Card className="space-y-3">
              {lines.map((t, i) => <p key={i} className="leading-relaxed">{t}</p>)}
            </Card>
          )}

          <div className="pt-2">
            {confirmDel ? (
              <div className="flex flex-wrap items-center gap-3 rounded-xl border border-error/30 bg-error/10 p-3 text-sm">
                <span>Delete this transcript and its share link? This cannot be undone.</span>
                <Button variant="danger" size="sm" onClick={remove}>Delete</Button>
                <Button variant="ghost" size="sm" onClick={() => setConfirmDel(false)}>Keep</Button>
              </div>
            ) : (
              <Button variant="ghost" onClick={() => setConfirmDel(true)} className="text-error"><Trash2 className="size-4" /> Delete transcript</Button>
            )}
          </div>
        </>
      )}
    </div>
  );
}
