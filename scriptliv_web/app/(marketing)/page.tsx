"use client";
import { motion } from "framer-motion";
import {
  AudioLines, Check, Download, FileText, GraduationCap, Headphones, Infinity as Inf, Languages, Laptop, Layers, Lock, Mic, Search, ShieldCheck, Square, Target, Users, Video, Zap,
} from "lucide-react";
import Link from "next/link";
import type { ReactNode } from "react";

const strip = [
  { i: Zap, t: "Real-Time Transcription" },
  { i: Target, t: "High Accuracy" },
  { i: Layers, t: "Lightweight & Fast" },
  { i: ShieldCheck, t: "Privacy First" },
  { i: Laptop, t: "Web & Mobile Access" },
];
const keyFeatures = [
  { i: Mic, t: "Live Transcription", d: "See text as you speak, with low latency." },
  { i: Languages, t: "Multilingual Engine", d: "Transcribe in your language, with more languages on the way." },
  { i: Inf, t: "Continuous Sessions", d: "Record as long as you need. Reconnects keep the same session." },
  { i: Laptop, t: "Web & Mobile", d: "Use it in your browser or on the Android and iOS app." },
  { i: Download, t: "Export Anywhere", d: "Download the transcript as text or CSV, and your own audio." },
];
const useCases = [
  { i: Users, t: "Meetings", d: "Capture and share meeting notes instantly." },
  { i: Video, t: "Interviews", d: "Transcribe interviews with high accuracy." },
  { i: GraduationCap, t: "Education", d: "Turn lectures and discussions into text." },
  { i: Headphones, t: "Client Calls", d: "Keep a clear record of important calls." },
];
const list = ["Live and continuous transcription", "Clear partial vs final text", "Organised transcript history", "Copy, download and export easily"];

const Section = ({ id, children, className = "" }: { id?: string; children: ReactNode; className?: string }) => (
  <section id={id} className={className}><div className="mx-auto max-w-6xl px-4 sm:px-6">{children}</div></section>
);

function Bars({ light }: { light?: boolean }) {
  const h = [8, 16, 10, 22, 14, 26, 12, 18, 9];
  return <span className="flex h-7 items-center gap-[3px]">{h.map((x, i) => <i key={i} style={{ height: x }} className={`w-[3px] rounded-full ${light ? "bg-[#a855f7]" : "bg-primary"}`} />)}</span>;
}

function Devices() {
  return (
    <div className="relative mx-auto w-full max-w-lg pb-6">
      <div className="rounded-t-2xl border border-line bg-surface p-3 shadow-[var(--shadow)]">
        <div className="grid grid-cols-[110px_1fr] gap-3 rounded-xl bg-bg p-3 text-left">
          <div className="space-y-2 text-[10px]">
            <div className="brand-gradient rounded-lg px-2 py-1.5 text-center font-medium text-white">New Transcription</div>
            <div className="px-1 text-ink-2">Home</div><div className="px-1 text-ink-2">Transcripts</div><div className="px-1 text-ink-2">Settings</div>
          </div>
          <div>
            <div className="mb-2 flex items-center gap-1.5 text-xs font-medium"><span className="size-1.5 rounded-full bg-success" /> Live Transcription</div>
            <p className="rounded-lg bg-surface p-3 text-[11px] leading-relaxed">Welcome to the project discussion. Today we will review the current progress, talk about the next steps, and finalise the action items.</p>
            <div className="mt-4 flex items-center justify-center gap-3">
              <Bars /><span className="brand-gradient grid size-9 place-items-center rounded-full text-white"><Square className="size-3.5" fill="currentColor" /></span><Bars />
            </div>
          </div>
        </div>
      </div>
      <div className="mx-auto h-2 w-[108%] -translate-x-[4%] rounded-b-xl bg-line" />
      <div className="absolute -bottom-2 -right-2 w-28 rounded-[1.4rem] border-4 border-[#0F172A] bg-[#150b3a] p-2.5 text-white shadow-xl sm:w-32">
        <div className="mb-2 flex items-center gap-1 text-[8px]"><span className="size-1 rounded-full bg-success" /> Live Transcription</div>
        <div className="flex justify-center py-3"><Bars light /></div>
        <div className="mx-auto grid size-9 place-items-center rounded-full border-2 border-white/80"><Square className="size-3" fill="currentColor" /></div>
        <div className="mt-1 text-center text-[8px] text-white/70">Listening…</div>
      </div>
    </div>
  );
}

export default function Landing() {
  return (
    <main>
      <section className="soft-gradient">
        <div className="mx-auto grid max-w-6xl items-center gap-10 px-4 py-14 sm:px-6 md:grid-cols-2 md:py-20">
          <div>
            <motion.h1 initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.5 }} className="text-4xl font-bold leading-[1.08] tracking-tight sm:text-5xl lg:text-6xl">
              Turn Speech into Text, <span className="text-primary">Instantly.</span>
            </motion.h1>
            <p className="mt-5 max-w-md text-lg text-ink-2">Live, accurate and low-latency transcription for meetings, discussions, interviews and more.</p>
            <div className="mt-7 flex flex-wrap gap-3">
              <Link href="/register" className="brand-gradient rounded-xl px-6 py-3 font-medium text-white shadow-[0_8px_20px_-8px_rgba(106,0,255,0.7)]">Get Started</Link>
              <Link href="/#how" className="rounded-xl border border-primary/40 px-6 py-3 font-medium text-primary hover:bg-surface-alt">How it works</Link>
            </div>
            <ul className="mt-6 flex flex-wrap gap-x-6 gap-y-2 text-sm text-ink-2">
              {["Real-time", "300 free minutes a month", "Share live transcripts"].map((t) => <li key={t} className="flex items-center gap-1.5"><Check className="size-4 text-primary" />{t}</li>)}
            </ul>
          </div>
          <Devices />
        </div>
      </section>

      <Section className="py-10">
        <div className="grid grid-cols-2 gap-4 rounded-2xl border border-line bg-surface p-6 text-center sm:grid-cols-3 lg:grid-cols-5">
          {strip.map((s) => (<div key={s.t} className="flex flex-col items-center gap-2 text-sm font-semibold"><s.i className="size-7 text-primary" aria-hidden />{s.t}</div>))}
        </div>
      </Section>

      <Section id="product" className="py-12">
        <div className="grid items-center gap-10 md:grid-cols-2">
          <div className="rounded-2xl border border-line bg-surface p-4 shadow-[var(--shadow)]">
            <div className="mb-3 font-semibold">Transcripts</div>
            <div className="mb-3 flex items-center gap-2 rounded-xl bg-bg px-3 py-2 text-xs text-ink-3"><Search className="size-3.5" /> Search transcripts…</div>
            {[["Project Meeting", "Today, 10:24 AM · 12 min"], ["Client Call", "Today, 9:15 AM · 8 min"], ["Research Notes", "Yesterday, 4:30 PM · 18 min"]].map(([a, b]) => (
              <div key={a} className="mb-2 flex items-center gap-3 rounded-xl bg-bg p-3"><FileText className="size-5 text-primary" /><div><div className="text-sm font-medium">{a}</div><div className="text-xs text-ink-2">{b}</div></div></div>
            ))}
            <p className="mt-1 text-[11px] text-ink-3">Illustration. Your own sessions appear in History.</p>
          </div>
          <div>
            <h2 className="text-3xl font-bold tracking-tight">Everything You Need for Transcription</h2>
            <p className="mt-3 text-ink-2">A simple and powerful platform to capture conversations, get accurate transcripts and access them anytime.</p>
            <ul className="mt-5 space-y-3">{list.map((t) => <li key={t} className="flex items-center gap-3"><span className="brand-gradient grid size-5 place-items-center rounded-full text-white"><Check className="size-3" /></span>{t}</li>)}</ul>
          </div>
        </div>
      </Section>

      <Section id="features" className="py-12">
        <h2 className="text-3xl font-bold tracking-tight">Key <span className="gradient-text">Features</span></h2>
        <p className="mt-1 text-ink-2">A focused set of features for fast, accurate and reliable transcription.</p>
        <div className="mt-6 grid gap-4 sm:grid-cols-2 lg:grid-cols-5">
          {keyFeatures.map((f) => (
            <div key={f.t} className="rounded-2xl border border-line bg-surface p-5 text-center shadow-[var(--shadow)]">
              <f.i className="mx-auto size-7 text-primary" aria-hidden /><div className="mt-3 font-semibold">{f.t}</div><p className="mt-1 text-xs text-ink-2">{f.d}</p>
            </div>
          ))}
        </div>
      </Section>

      <Section id="how" className="py-12">
        <h2 className="text-center text-3xl font-bold tracking-tight">How <span className="gradient-text">ScriptLiv</span> Works</h2>
        <p className="mt-1 text-center text-ink-2">Go from speech to text in three simple steps.</p>
        <ol className="mt-8 grid gap-6 text-center sm:grid-cols-3">
          {[[Mic, "Speak", "Start a live transcription with one tap."], [AudioLines, "Transcribe", "Get accurate text in real time."], [FileText, "Use", "Read, copy, export or access it later."]].map(([I, t, d], i) => {
            const Icon = I as typeof Mic;
            return (<li key={String(t)}><div className="mx-auto grid size-16 place-items-center rounded-2xl bg-lavender"><Icon className="size-7 text-primary" /></div>
              <div className="mt-3 flex items-center justify-center gap-2 font-semibold"><span className="grid size-5 place-items-center rounded-full bg-primary text-xs text-white">{i + 1}</span>{String(t)}</div><p className="text-sm text-ink-2">{String(d)}</p></li>);
          })}
        </ol>
      </Section>

      <Section id="use-cases" className="py-8">
        <div className="rounded-3xl bg-surface p-8">
          <h2 className="text-center text-3xl font-bold tracking-tight">Built for Real Conversations</h2>
          <div className="mt-6 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            {useCases.map((u) => (<div key={u.t} className="rounded-2xl border border-line bg-bg p-5 text-center"><u.i className="mx-auto size-7 text-primary" /><div className="mt-2 font-semibold">{u.t}</div><p className="mt-1 text-xs text-ink-2">{u.d}</p></div>))}
          </div>
        </div>
      </Section>

      <Section className="py-12">
        <div className="flex flex-col items-center gap-6 rounded-3xl bg-[#1a0b4d] p-8 text-white md:flex-row">
          <div className="grid size-24 shrink-0 place-items-center rounded-3xl bg-gradient-to-br from-[#6a00ff] to-[#a855f7]"><Lock className="size-11" /></div>
          <div>
            <h2 className="text-2xl font-bold">Your Data Stays Private</h2>
            <p className="mt-2 max-w-xl text-white/80">Nothing is recorded until you accept the testing consent. Audio is encrypted at rest, tied to your account, and every access by an administrator is logged.</p>
            <ul className="mt-4 flex flex-wrap gap-x-6 gap-y-1 text-sm">{["Encrypted at rest", "Access is audited", "Consent first"].map((t) => <li key={t} className="flex items-center gap-1.5"><Check className="size-4 text-[#a855f7]" />{t}</li>)}</ul>
          </div>
        </div>
      </Section>
    </main>
  );
}
