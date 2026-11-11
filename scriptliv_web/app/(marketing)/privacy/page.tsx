import type { Metadata } from "next";
import Link from "next/link";
import { CONTACT_EMAIL, LegalPage } from "@/components/legal-page";

export const metadata: Metadata = { title: "Privacy Policy | ScriptLiv", description: "What ScriptLiv collects, why, and the choices you have." };

const mail = <a href={`mailto:${CONTACT_EMAIL}`}>{CONTACT_EMAIL}</a>;

export default function PrivacyPage() {
  return (
    <LegalPage
      eyebrow="Legal"
      title="Privacy Policy"
      updated="11 November 2026"
      intro={<>ScriptLiv turns speech into text in real time. This policy explains what we collect to do that, what we do with it, and the choices you have. We keep it short and plain on purpose. Snypar Tech (&ldquo;we&rdquo;, &ldquo;us&rdquo;) operates ScriptLiv.</>}
      sections={[
        { id: "collect", title: "What we collect", body: (
          <>
            <p><strong>Account details.</strong> Your name, email address and a securely hashed password. We never store your password in readable form.</p>
            <p><strong>Your speech and transcripts.</strong> When you record, your microphone audio is streamed to our transcription service and turned into text. We do not keep your audio recordings. We keep the resulting transcript so you can read, rename, share and delete it.</p>
            <p><strong>Usage records.</strong> How many seconds each session used, when it started and ended, and your plan. We need this to count your minutes and apply limits.</p>
            <p><strong>Settings.</strong> Preferences such as theme, text size and your personal minute limit.</p>
            <p><strong>Billing information.</strong> If you buy a paid plan, payment is handled by our payment provider. We store your plan, invoices and billing details you enter. We do not store your full card number.</p>
          </>
        ) },
        { id: "use", title: "How we use it", body: (
          <ul>
            <li>To provide transcription, save your sessions and let you share them.</li>
            <li>To count your minutes and enforce plan limits, including the 30-minute limit on each free session.</li>
            <li>To send account emails: verification, password reset and billing notices.</li>
            <li>To keep the service secure, prevent abuse and fix problems.</li>
          </ul>
        ) },
        { id: "sharing", title: "Sharing your transcripts", body: (
          <>
            <p>Your transcripts are private to your account. If you turn on a live share link, anyone who has that link can read that session&rsquo;s transcript until you turn sharing off. Treat the link like a password.</p>
            <p>Viewers who open a link are not billed and do not need an account.</p>
          </>
        ) },
        { id: "processors", title: "Who helps us run ScriptLiv", body: (
          <>
            <p>We use a small number of service providers, only for what they are needed for:</p>
            <ul>
              <li><strong>Email delivery</strong> (Resend and Gmail) to send you account emails. They receive your email address and the message.</li>
              <li><strong>Payments</strong> (our payment provider) to take payment for paid plans.</li>
              <li><strong>Database and hosting</strong> to store your account and transcripts.</li>
            </ul>
            <p>We do not sell your personal information, and we do not use your transcripts to advertise to you.</p>
          </>
        ) },
        { id: "keep", title: "How long we keep things", body: (
          <>
            <p>We keep your account and transcripts until you delete them. Deleting a transcript removes its text from our systems. Usage and billing records are kept as billing history, without transcript content, as long as the law and our accounting require.</p>
            <p>To close your account and remove your data, email us at {mail}.</p>
          </>
        ) },
        { id: "security", title: "Security", body: (
          <p>We protect data in transit with encryption, hash passwords, and limit who can reach our systems. No system is perfectly secure, so please use a strong, unique password and keep share links to people you trust.</p>
        ) },
        { id: "rights", title: "Your choices", body: (
          <>
            <p>You can see and edit your name and email in Settings, delete any transcript from your history, turn share links on or off, and ask us for a copy of your data or to delete your account. Depending on where you live, you may have further rights under local law. Email {mail} and we will help.</p>
          </>
        ) },
        { id: "children", title: "Children", body: (
          <p>ScriptLiv is not meant for children under 13, and we do not knowingly collect their information. If you think a child has given us data, tell us and we will remove it.</p>
        ) },
        { id: "changes", title: "Changes to this policy", body: (
          <p>If we change this policy in a meaningful way, we will update the date above and, for significant changes, tell you by email or in the app.</p>
        ) },
        { id: "contact", title: "Contact us", body: (
          <p>Questions about privacy? Email {mail}. You may also like to read our <Link href="/terms">Terms &amp; Conditions</Link>.</p>
        ) },
      ]}
    />
  );
}
