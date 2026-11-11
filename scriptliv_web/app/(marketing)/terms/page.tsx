import type { Metadata } from "next";
import Link from "next/link";
import { CONTACT_EMAIL, LegalPage } from "@/components/legal-page";

export const metadata: Metadata = { title: "Terms & Conditions | ScriptLiv", description: "The rules for using ScriptLiv: accounts, plans, limits and acceptable use." };

const mail = <a href={`mailto:${CONTACT_EMAIL}`}>{CONTACT_EMAIL}</a>;

export default function TermsPage() {
  return (
    <LegalPage
      eyebrow="Legal"
      title="Terms & Conditions"
      updated="11 November 2026"
      intro={<>These terms are the agreement between you and Snypar Tech for using ScriptLiv. By creating an account or using the service, you agree to them. If you do not agree, please do not use ScriptLiv.</>}
      sections={[
        { id: "service", title: "The service", body: (
          <p>ScriptLiv provides real-time speech-to-text transcription on the web and in our mobile app. Transcription is produced automatically and can contain mistakes. Please check anything important before you rely on it, especially for legal, medical or safety decisions.</p>
        ) },
        { id: "account", title: "Your account", body: (
          <ul>
            <li>You must give accurate details and verify your email address before you can record.</li>
            <li>You are responsible for what happens under your account, so keep your password private.</li>
            <li>You must be at least 13 years old, or the age of digital consent where you live.</li>
            <li>Tell us right away at {mail} if you think someone else has accessed your account.</li>
          </ul>
        ) },
        { id: "plans", title: "Plans, minutes and limits", body: (
          <>
            <p><strong>Basic (free)</strong> includes 300 minutes every month. Each free session can run for up to <strong>30 minutes</strong>. When a session reaches 30 minutes it stops, your transcript is saved, and you can start a new session while you still have minutes left.</p>
            <p><strong>Pro</strong> includes 2,500 minutes every month, with no per-session time limit. Extra minutes can be bought as add-ons and are valid until the end of the period they were bought in.</p>
            <p>Minutes are counted as the seconds you actually speak into a session. Unused monthly minutes do not roll over. You can set your own personal limit in Settings. We may change plan details with notice; changes do not affect minutes you have already paid for.</p>
          </>
        ) },
        { id: "payments", title: "Payments", body: (
          <>
            <p>Paid plans renew monthly until you cancel. You can cancel in the app and keep Pro until the end of the period you paid for. Payments are processed by our payment provider and prices are shown before you pay.</p>
            <p>If a payment fails, we will tell you and give you a chance to fix it. Until it is fixed, your account falls back to the free Basic allowance. Except where the law says otherwise, payments are not refundable once minutes have been used.</p>
          </>
        ) },
        { id: "content", title: "Your content", body: (
          <>
            <p>You own what you say and the transcripts made from it. You give us permission to process your audio and store your transcripts only so we can run the service for you.</p>
            <p>Only record people who know they are being recorded, and follow the laws on recording where you are. You are responsible for getting any consent needed. If you share a transcript through a link, you are responsible for who you give that link to.</p>
          </>
        ) },
        { id: "use", title: "Acceptable use", body: (
          <>
            <p>Please do not:</p>
            <ul>
              <li>use ScriptLiv for anything unlawful, harassing or harmful;</li>
              <li>record people secretly or without a legal right to do so;</li>
              <li>try to break, overload, probe or bypass the limits of the service;</li>
              <li>share your account, or resell access, without our written permission;</li>
              <li>use automated means to create accounts or drain free minutes.</li>
            </ul>
            <p>We may pause or close accounts that break these rules.</p>
          </>
        ) },
        { id: "availability", title: "Availability", body: (
          <p>We work hard to keep ScriptLiv running, but we cannot promise it will always be available or error-free. We may update or change features, and sometimes need to pause the service for maintenance.</p>
        ) },
        { id: "liability", title: "Liability", body: (
          <p>ScriptLiv is provided &ldquo;as is&rdquo;. To the extent the law allows, Snypar Tech is not liable for indirect or consequential losses, or for losses caused by transcription errors, and our total liability for any claim is limited to the amount you paid us in the 12 months before it. Nothing here limits rights you have by law that cannot be limited.</p>
        ) },
        { id: "ending", title: "Ending your account", body: (
          <p>You can stop using ScriptLiv at any time and ask us to delete your account at {mail}. We may suspend or end your access if you break these terms or the law. How we handle your data is explained in our <Link href="/privacy">Privacy Policy</Link>.</p>
        ) },
        { id: "changes", title: "Changes to these terms", body: (
          <p>We may update these terms. When we do, we will change the date above, and for significant changes we will tell you in the app or by email. Using ScriptLiv after a change means you accept the new terms.</p>
        ) },
        { id: "contact", title: "Contact us", body: (
          <p>Questions about these terms? Email {mail}.</p>
        ) },
      ]}
    />
  );
}
