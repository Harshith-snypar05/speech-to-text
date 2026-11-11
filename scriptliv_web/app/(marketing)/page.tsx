"use client";
import { motion } from "framer-motion";
import {
  ArrowRight, AudioLines, Check, Download, FileText, Gift, GraduationCap, Infinity as Inf, Languages, Laptop, Layers, Link2, Mic, Phone, PlayCircle, Search, ShieldCheck, Target, Users, Zap,
} from "lucide-react";
import Image from "next/image";
import Link from "next/link";
import type { ReactNode } from "react";
import { AuthTrigger } from "@/components/auth-modal";
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
  { i: Gift, t: "300 free minutes every month (30 min per session)" },
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

/* Product mock: real laptop + phone device frames (transparent PNG-style cutouts) over app screenshots.
   The screenshots sit behind the frames; each frame has a transparent screen hole. Geometry = hole bounds as fractions of the frame image. */
function Devices() {
  return (
    <div className="relative mx-auto w-full max-w-[720px] pb-6" role="img" aria-label="ScriptLiv on a laptop and a phone">
      <div className="relative w-[84%] drop-shadow-[0_40px_60px_rgba(120,30,200,0.35)]">
        <div className="relative aspect-[1734/1004] w-full">
          <Image src="/brand/shot-laptop.webp" alt="" aria-hidden width={1400} height={875} sizes="(min-width:1024px) 600px, 90vw"
            className="absolute object-cover object-top" style={{ left: "11.765%", top: "6.773%", width: "76.471%", height: "82.171%" }} />
          <Image src="/brand/device-laptop.webp" alt="" aria-hidden priority width={1500} height={869} sizes="(min-width:1024px) 600px, 90vw" className="absolute inset-0 size-full" />
        </div>
      </div>
      <div className="absolute bottom-0 right-0 w-[25%] min-w-24 drop-shadow-[0_30px_40px_rgba(0,0,0,0.55)]">
        <div className="relative aspect-[855/1721] w-full">
          <Image src="/brand/shot-phone.webp" alt="" aria-hidden width={780} height={1688} sizes="180px"
            className="absolute object-cover object-top" style={{ left: "5.848%", top: "2.44%", width: "88.304%", height: "95.119%" }} />
          <Image src="/brand/device-phone.webp" alt="" aria-hidden priority width={640} height={1288} sizes="180px" className="absolute inset-0 size-full" />
        </div>
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
              <AuthTrigger mode="register" className={buttonCls({ size: "lg" })}>Get Started <ArrowRight className="size-5" aria-hidden /></AuthTrigger>
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
