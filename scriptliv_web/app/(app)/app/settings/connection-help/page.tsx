import Link from "next/link";
import { ChevronLeft } from "lucide-react";
import { Card } from "@/components/ui";

const FIXES: { problem: string; steps: string[] }[] = [
  {
    problem: "\"Could not reach the server\"",
    steps: [
      "Check that your device has internet (open any other website).",
      "Switch between Wi-Fi and mobile data and try again.",
      "If you use a VPN or a work or school network, turn it off or try another network; some block live connections.",
      "Wait a minute and retry. If it keeps failing, the service may be updating; email info@scriptliv.com.",
    ],
  },
  {
    problem: "Live transcript does not start or keeps disconnecting",
    steps: [
      "Allow microphone access for this site in your browser's address-bar settings.",
      "Move somewhere with steadier signal; live transcription needs a continuous connection.",
      "Stop the session and start a new one. Your text so far is saved in Transcripts.",
      "Close other tabs or apps that use the microphone.",
    ],
  },
  {
    problem: "No words appear while I speak",
    steps: [
      "Check you are not muted and the right microphone is chosen in Settings > Microphone.",
      "Close other apps that use the microphone (calls, voice recorders).",
      "Speak close to the microphone and reduce background noise.",
      "Unplug or reconnect Bluetooth headsets, then try again.",
    ],
  },
  {
    problem: "\"Session expired. Sign in again.\"",
    steps: [
      "This happens after you change your password, or if you signed out other devices.",
      "Log out from Settings, then sign in again.",
    ],
  },
  {
    problem: "Shared link will not open for viewers",
    steps: [
      "Make sure sharing is turned on for the session.",
      "Send the full link, not a shortened or edited one.",
      "Viewers need an internet connection; they do not need an account.",
    ],
  },
  {
    problem: "I did not get the verification or reset email",
    steps: [
      "Check the Spam or Promotions folder.",
      "Make sure you typed the right address, then ask for a new link; links expire after 24 hours.",
      "Still nothing after a few minutes? Email info@scriptliv.com from that address.",
    ],
  },
  {
    problem: "Out of minutes or \"Payment required\"",
    steps: [
      "Open Settings to see your minutes left and your payment status.",
      "Fix a failed payment from Change plan, or wait for your minutes to reset on the date shown.",
    ],
  },
];

export default function ConnectionHelpPage() {
  return (
    <div className="space-y-5">
      <div>
        <Link href="/app/settings" className="inline-flex items-center gap-1 text-sm text-ink-2 hover:text-primary">
          <ChevronLeft className="size-4" aria-hidden /> Settings
        </Link>
        <h1 className="mt-2 text-2xl font-semibold">Fix a connection issue</h1>
        <p className="text-sm text-ink-2">Find your problem below and follow the steps.</p>
      </div>
      <div className="space-y-3">
        {FIXES.map((f) => (
          <Card key={f.problem} className="p-0">
            <details>
              <summary className="cursor-pointer px-5 py-4 text-sm font-semibold">{f.problem}</summary>
              <ol className="list-decimal space-y-1.5 px-5 pb-4 pl-9 text-sm text-ink-2">
                {f.steps.map((s) => <li key={s}>{s}</li>)}
              </ol>
            </details>
          </Card>
        ))}
        <p className="text-sm text-ink-2">Still stuck? Email info@scriptliv.com and tell us what you see.</p>
      </div>
    </div>
  );
}
