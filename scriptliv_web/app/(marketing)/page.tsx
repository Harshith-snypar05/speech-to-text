"use client";
import { motion } from "framer-motion";
import {
  ArrowRight, AudioLines, Check, Download, FileText, Gift, GraduationCap, Home, Infinity as Inf, Languages, Laptop, Layers, Link2, Mic, Phone, PlayCircle, Search, Settings, ShieldCheck, Square, Target, Users, Zap,
} from "lucide-react";
import Link from "next/link";
import type { ReactNode } from "react";
import { Chip } from "@/components/brand";
import { buttonCls } from "@/components/ui/button-styles";

const tiles = [
  { i: AudioLines, t: "Real-Time Transcription" },
  { i: Target, t: "High Accuracy" },
  { i: Layers, t: "Lightweight & Fast" },
  { i: ShieldCheck, t: "Private by Default" },
  { i: Laptop, t: "Web & Mobile Access" },
];
const facts = [
  { i: Zap, t: "Real-time" },
  { i: Gift, t: "300 free minutes every month" },
  { i: Link2, t: "Share live transcripts" },
];
const keyFeatures = [
  { i: Mic, t: "Live Transcription", d: "See text as you speak, with low latency." },
  { i: Languages, t: "Multilingual Engine", d: "Transcribe in your language, with more languages on the way." },
  { i: Inf, t: "Continuous Sessions", d: "Record as long as you need. Reconnects keep the same session." },
  { i: Laptop, t: "Web & Mobile", d: "Use it in your browser or on the Android and iOS app." },
  { i: Download, t: "Export Anywhere", d: "Download the transcript as text or CSV, and your own audio." },
];
const useCases = [
  { i: Users, t: "Meetings", d: "Capture discussions, decisions and action items in real time." },
  { i: Mic, t: "Interviews", d: "Transcribe interviews accurately and stay focused on the conversation." },
  { i: GraduationCap, t: "Education", d: "Turn lectures, classes and study sessions into clear, searchable text." },
  { i: Phone, t: "Client Calls", d: "Get accurate transcripts for sales, support and project calls." },
];
const list = ["Live and continuous transcription", "Clear partial vs final text", "Organised transcript history", "Copy, download and export easily"];

const Section = ({ id, children, className = "" }: { id?: string; children: ReactNode; className?: string }) => (
  <section id={id} className={`relative isolate scroll-mt-24 ${className}`}>{id === "use-cases" && <div aria-hidden className="sl-wave sl-wave-section" />}<div className="mx-auto max-w-[1400px] px-4 sm:px-8">{children}</div></section>
);

const Heading = ({ chip, icon, children, sub }: { chip: string; icon: ReactNode; children: ReactNode; sub?: string }) => (
  <div className="text-center">
    <Chip>{icon}{chip}</Chip>
    <h2 className="mt-5 text-3xl font-extrabold tracking-tight sm:text-5xl">{children}</h2>
    {sub && <p className="mx-auto mt-3 max-w-xl text-ink-2 sm:text-lg">{sub}</p>}
  </div>
);

/* Waveform glyph. Static (it illustrates the product, it does not claim live audio). */
function Wave({ n = 11, h = 34, className = "" }: { n?: number; h?: number; className?: string }) {
  const f = [0.18, 0.34, 0.22, 0.6, 0.4, 0.95, 0.5, 0.75, 0.3, 0.5, 0.2, 0.36, 0.16];
  return (
    <span aria-hidden className={`flex items-center gap-[3px] ${className}`} style={{ height: h }}>
      {Array.from({ length: n }, (_, i) => <i key={i} style={{ height: Math.max(3, f[i % f.length] * h) }} className="w-[3px] rounded-full bg-[#b86cf5]" />)}
    </span>
  );
}

/* Product mock: laptop + phone. Fixed dark colours on purpose, it shows the app UI. */
function Devices() {
  return (
    <div className="relative mx-auto w-full max-w-[640px] pb-10 pr-8 sm:pr-12" role="img" aria-label="ScriptLiv live transcription on a laptop and a phone">
      <div className="rounded-t-[22px] border-[5px] border-[#2a2038] bg-[#0b0614] p-3 shadow-[0_40px_80px_-30px_rgba(160,43,230,0.55)]">
        <div className="grid grid-cols-[132px_1fr] gap-3 text-left text-white">
          <div className="rounded-xl bg-[#120a20] p-3 text-[10px]">
            <div className="mb-3 font-bold text-[12px]">ScriptLiv</div>
            <div className="brand-gradient mb-2 flex items-center gap-1.5 rounded-lg px-2 py-1.5 font-semibold"><Mic className="size-3" aria-hidden />New Transcription</div>
            {[[Home, "Home"], [FileText, "Transcripts"], [Settings, "Settings"]].map(([I, t]) => {
              const Icon = I as typeof Home;
              return <div key={String(t)} className="flex items-center gap-1.5 px-2 py-1.5 text-white/75"><Icon className="size-3" aria-hidden />{String(t)}</div>;
            })}
          </div>
          <div>
            <div className="mb-2 flex items-center justify-between text-xs font-semibold">
              <span className="flex items-center gap-1.5"><span className="size-1.5 rounded-full bg-[#34d399]" />Live Transcription</span>
              <span className="brand-gradient rounded-full px-3 py-0.5 text-[10px]">Live</span>
            </div>
            <p className="rounded-xl bg-[#1b0f30] p-3 pr-[36%] text-[11px] leading-relaxed text-white/90">Welcome to the project discussion. Today we will review the current progress, talk about the next steps, and finalise the action items.</p>
            <div className="mt-4 flex items-center justify-center gap-3">
              <Wave n={11} h={30} />
              <span className="brand-gradient grid size-10 place-items-center rounded-full"><Square className="size-3.5" fill="currentColor" aria-hidden /></span>
              <Wave n={11} h={30} />
            </div>
          </div>
        </div>
      </div>
      <div className="mx-auto h-2.5 w-[106%] -translate-x-[3%] rounded-b-2xl bg-gradient-to-b from-[#6b5a86] to-[#2a2038]" />
      <div className="absolute -bottom-1 right-0 w-[34%] min-w-28 max-w-40 rounded-[26px] border-[4px] border-[#2a2038] bg-[#0b0614] p-3 text-white shadow-[0_30px_60px_-20px_rgba(0,0,0,0.8)]">
        <div className="mb-2 text-[8px] text-white/70">9:41</div>
        <div className="mb-3 flex items-center gap-1 text-[9px] font-semibold"><span className="size-1.5 rounded-full bg-[#34d399]" />Live Transcription</div>
        <div className="flex justify-center py-3"><Wave n={13} h={44} /></div>
        <div className="mx-auto grid size-9 place-items-center rounded-full border-2 border-white/80"><Square className="size-3" fill="currentColor" aria-hidden /></div>
        <div className="mt-1.5 text-center text-[9px] text-white/80">Listening...</div>
      </div>
    </div>
  );
}

export default function Landing() {
  return (
    <main>
      <section>
        <div className="mx-auto grid max-w-[1400px] items-center gap-12 px-4 pb-10 pt-12 sm:px-8 lg:grid-cols-[1fr_1.05fr] lg:pt-16">
          <div>
            <Chip><AudioLines className="size-4 text-violet" aria-hidden />Real-time Speech to Text</Chip>
            <motion.h1 initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.5 }} className="mt-6 text-5xl font-extrabold leading-[1.04] tracking-tight sm:text-6xl lg:text-[4.5rem]">
              Turn Speech into Text, <span className="gradient-text">Instantly.</span>
            </motion.h1>
            <p className="mt-6 max-w-lg text-lg text-ink-2 sm:text-xl">Live, accurate and low-latency transcription for meetings, discussions, interviews and more.</p>
            <div className="mt-8 flex flex-wrap gap-3">
              <Link href="/register" className={buttonCls({ size: "lg" })}>Get Started <ArrowRight className="size-5" aria-hidden /></Link>
              <Link href="/#how" className={buttonCls({ variant: "outline", size: "lg" })}><PlayCircle className="size-5" aria-hidden />See How it Works</Link>
            </div>
            <ul className="mt-8 flex flex-wrap gap-x-8 gap-y-4 text-sm text-ink-2">
              {facts.map((f) => <li key={f.t} className="flex max-w-[11rem] items-center gap-3"><f.i className="size-7 shrink-0 text-violet" aria-hidden />{f.t}</li>)}
            </ul>
          </div>
          <Devices />
        </div>
      </section>

      <Section className="py-8">
        <ul className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-5">
          {tiles.map((s) => (
            <li key={s.t} className="sl-panel flex min-h-40 flex-col items-center justify-center gap-4 rounded-[var(--radius-card)] p-5 text-center font-semibold">
              <s.i className="size-9 text-violet" aria-hidden />{s.t}
            </li>
          ))}
        </ul>
      </Section>

      <Section id="product" className="py-16">
        <div className="grid items-center gap-12 md:grid-cols-2">
          <div className="sl-panel rounded-[var(--radius-card)] p-5">
            <div className="mb-3 font-semibold">Transcripts</div>
            <div className="mb-3 flex items-center gap-2 rounded-full border border-line bg-bg/60 px-4 py-2 text-xs text-ink-3"><Search className="size-3.5" aria-hidden /> Search transcripts…</div>
            {[["Project Meeting", "Today, 10:24 AM · 12 min"], ["Client Call", "Today, 9:15 AM · 8 min"], ["Research Notes", "Yesterday, 4:30 PM · 18 min"]].map(([a, b]) => (
              <div key={a} className="mb-2 flex items-center gap-3 rounded-2xl border border-line/70 bg-bg/50 p-3"><span className="grid size-9 place-items-center rounded-full bg-lavender"><FileText className="size-4 text-primary" aria-hidden /></span><div><div className="text-sm font-semibold">{a}</div><div className="text-xs text-ink-2">{b}</div></div></div>
            ))}
            <p className="mt-2 text-[11px] text-ink-3">Illustration. Your own sessions appear in History.</p>
          </div>
          <div>
            <h2 className="text-3xl font-extrabold tracking-tight sm:text-4xl">Everything You Need for <span className="gradient-text">Transcription</span></h2>
            <p className="mt-4 text-ink-2 sm:text-lg">A simple and powerful platform to capture conversations, get accurate transcripts and access them anytime.</p>
            <ul className="mt-6 space-y-3">{list.map((t) => <li key={t} className="flex items-center gap-3"><span className="brand-gradient grid size-6 place-items-center rounded-full"><Check className="size-3.5" aria-hidden /></span>{t}</li>)}</ul>
          </div>
        </div>
      </Section>

      <Section id="features" className="py-14">
        <h2 className="text-center text-3xl font-extrabold tracking-tight sm:text-5xl">Key <span className="gradient-text">Features</span></h2>
        <p className="mx-auto mt-3 max-w-xl text-center text-ink-2 sm:text-lg">A focused set of features for fast, accurate and reliable transcription.</p>
        <div className="mt-10 grid gap-4 sm:grid-cols-2 lg:grid-cols-5">
          {keyFeatures.map((f) => (
            <div key={f.t} className="sl-panel rounded-[var(--radius-card)] p-6 text-center">
              <span className="mx-auto grid size-14 place-items-center rounded-full bg-lavender"><f.i className="size-6 text-primary" aria-hidden /></span>
              <div className="mt-4 font-bold">{f.t}</div><p className="mt-1.5 text-sm text-ink-2">{f.d}</p>
            </div>
          ))}
        </div>
      </Section>

      <Section id="how" className="py-14">
        <h2 className="text-center text-3xl font-extrabold tracking-tight sm:text-5xl">How <span className="gradient-text">ScriptLiv</span> Works</h2>
        <p className="mx-auto mt-3 max-w-xl text-center text-ink-2 sm:text-lg">Go from speech to text in three simple steps.</p>
        <ol className="mt-10 grid gap-5 text-center sm:grid-cols-3">
          {[[Mic, "Speak", "Start a live transcription with one tap."], [AudioLines, "Transcribe", "Get accurate text in real time."], [FileText, "Use", "Read, copy, export or access it later."]].map(([I, t, d], i) => {
            const Icon = I as typeof Mic;
            return (
              <li key={String(t)} className="sl-panel rounded-[var(--radius-card)] p-7">
                <div className="mx-auto grid size-16 place-items-center rounded-full bg-lavender"><Icon className="size-7 text-primary" aria-hidden /></div>
                <div className="mt-4 flex items-center justify-center gap-2 text-lg font-bold"><span className="brand-gradient grid size-6 place-items-center rounded-full text-xs">{i + 1}</span>{String(t)}</div>
                <p className="mt-1 text-sm text-ink-2">{String(d)}</p>
              </li>
            );
          })}
        </ol>
      </Section>

      <Section id="use-cases" className="py-16">
        <Heading chip="Use Cases" icon={<Users className="size-4 text-violet" aria-hidden />} sub="Accurate, real-time transcription for the conversations that matter most.">
          Built for <span className="gradient-text">Real Conversations</span>
        </Heading>
        <div className="mt-12 grid gap-5 sm:grid-cols-2 lg:grid-cols-4">
          {useCases.map((u) => (
            <div key={u.t} className="sl-panel rounded-[var(--radius-card)] p-6">
              <span className="grid size-14 place-items-center rounded-full bg-lavender"><u.i className="size-6 text-primary" aria-hidden /></span>
              <div className="mt-5 text-xl font-bold">{u.t}</div>
              <p className="mt-2 text-ink-2">{u.d}</p>
            </div>
          ))}
        </div>
      </Section>
    </main>
  );
}
