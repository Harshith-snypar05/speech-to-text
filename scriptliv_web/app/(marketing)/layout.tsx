import { ArrowRight } from "lucide-react";
import Link from "next/link";
import { AuthTrigger } from "@/components/auth-modal";
import { Logo, ThemeToggle } from "@/components/brand";
import { ScrollHeader } from "@/components/scroll-header";
import { buttonCls } from "@/components/ui/button-styles";

export default function MarketingLayout({ children }: { children: React.ReactNode }) {
  const link = "hidden rounded-full px-4 py-2 text-ink hover:text-violet lg:block";
  const col = "mb-3 font-semibold text-ink";
  const item = "text-ink-2 hover:text-ink";
  return (
    <div className="sl-marketing relative isolate min-h-dvh overflow-x-clip">
      <div aria-hidden className="sl-wave sl-wave-hero" />
      <ScrollHeader>
        <div className="mx-auto grid h-[72px] max-w-[1400px] grid-cols-[auto_1fr_auto] items-center gap-4 px-4 sm:px-8">
          <Logo className="h-9 w-auto" />
          <nav aria-label="Sections" className="flex items-center justify-center gap-2 text-sm font-medium">
            <Link href="/#product" className={link}>Product</Link>
            <Link href="/#features" className={link}>Features</Link>
            <Link href="/#use-cases" className={link}>Use Cases</Link>
            <Link href="/#how" className={link}>How it works</Link>
          </nav>
          <div className="flex items-center gap-2 text-sm">
            <ThemeToggle />
            <AuthTrigger mode="login" className={buttonCls({ variant: "outline", size: "md" })}>Log In</AuthTrigger>
            <AuthTrigger mode="register" className={buttonCls({ size: "md" })}>Get Started <ArrowRight className="size-4" aria-hidden /></AuthTrigger>
          </div>
        </div>
      </ScrollHeader>
      {children}
      <footer className="relative isolate border-t border-line/60 pb-8 pt-14 text-sm">
        <div aria-hidden className="sl-wave sl-wave-footer" />
        <div className="mx-auto grid max-w-[1400px] gap-10 px-4 sm:px-8 md:grid-cols-[1.6fr_1fr_1fr_1fr]">
          <div>
            <Logo className="h-9 w-auto" />
            <p className="mt-4 max-w-xs text-ink-2">Real-time speech to text transcription for meetings, interviews, education and more.</p>
          </div>
          <div>
            <div className={col}>Product</div>
            <ul className="space-y-2.5">
              <li><Link className={item} href="/#features">Features</Link></li>
              <li><Link className={item} href="/#use-cases">Use Cases</Link></li>
              <li><Link className={item} href="/#how">How it Works</Link></li>
            </ul>
          </div>
          <div>
            <div className={col}>Account</div>
            <ul className="space-y-2.5">
              <li><AuthTrigger mode="login" className={item}>Log in</AuthTrigger></li>
              <li><AuthTrigger mode="register" className={item}>Create an account</AuthTrigger></li>
              <li><Link className={item} href="/forgot-password">Reset password</Link></li>
            </ul>
          </div>
          <div>
            <div className={col}>Legal</div>
            <ul className="space-y-2.5">
              <li><Link className={item} href="/privacy">Privacy Policy</Link></li>
              <li><Link className={item} href="/terms">Terms &amp; Conditions</Link></li>
            </ul>
          </div>
        </div>
        <div className="mx-auto mt-12 flex max-w-[1400px] flex-wrap items-center justify-between gap-3 border-t border-line/60 px-4 pt-6 text-xs text-ink-3 sm:px-8">
          <span>© {new Date().getFullYear()} Snypar Tech. All rights reserved.</span>
          <span className="flex gap-4"><Link className="hover:text-ink" href="/privacy">Privacy</Link><Link className="hover:text-ink" href="/terms">Terms</Link></span>
        </div>
      </footer>
    </div>
  );
}
