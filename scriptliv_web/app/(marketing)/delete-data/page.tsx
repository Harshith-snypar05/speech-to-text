import type { Metadata } from "next";
import Link from "next/link";
import { CONTACT_EMAIL, LegalPage } from "@/components/legal-page";

export const metadata: Metadata = {
  title: "Delete your data | ScriptLiv",
  description: "How to delete your ScriptLiv transcripts or your whole account, and what is deleted or kept.",
};

const mail = <a href={`mailto:${CONTACT_EMAIL}`}>{CONTACT_EMAIL}</a>;

export default function DeleteDataPage() {
  return (
    <LegalPage
      eyebrow="Your data"
      title="Delete your ScriptLiv data"
      updated="19 November 2026"
      intro={<>This page is for ScriptLiv, the speech-to-text app by Snypar Tech. You can delete a single transcript, or your whole account and everything in it, yourself in the app or on the website. If you cannot sign in, email {mail} and we will do it for you.</>}
      sections={[
        { id: "transcript", title: "Delete one transcript", body: (
          <>
            <ol className="list-decimal space-y-1.5 pl-5">
              <li>Open ScriptLiv (app or <Link href="/app/history">website</Link>) and sign in.</li>
              <li>Go to History and open the transcript.</li>
              <li>Choose Delete and confirm.</li>
            </ol>
            <p>The transcript text is removed from our systems, and its share link stops working. Your account stays.</p>
          </>
        ) },
        { id: "account", title: "Delete your account and all data", body: (
          <>
            <ol className="list-decimal space-y-1.5 pl-5">
              <li>Open ScriptLiv (app or <Link href="/app/settings">website</Link>) and sign in.</li>
              <li>Go to Settings and choose Delete account.</li>
              <li>Enter your password and confirm. If you have a paid plan, cancel it first.</li>
            </ol>
            <p>Deleting the account is immediate and cannot be undone.</p>
          </>
        ) },
        { id: "no-access", title: "Cannot sign in?", body: (
          <p>Email {mail} from the address you registered with and ask us to delete your data. We reply within 7 days.</p>
        ) },
        { id: "deleted", title: "What is deleted", body: (
          <ul>
            <li>Your name, email address and password hash.</li>
            <li>All your transcripts and their share links.</li>
            <li>Your usage records, add-on balances, settings, saved billing details and any pending email tokens.</li>
          </ul>
        ) },
        { id: "kept", title: "What is kept, and for how long", body: (
          <>
            <p>We do not keep your audio. It is never stored as a recording.</p>
            <p>Payment and invoice records for purchases you made are kept without any transcript content, as long as tax and accounting law require us to keep them. Backups of our database are overwritten on their normal cycle, so deleted data can remain in a backup for a short time before it disappears.</p>
          </>
        ) },
        { id: "more", title: "More", body: (
          <p>Read our <Link href="/privacy">Privacy Policy</Link> for everything we collect and why. Questions: {mail}.</p>
        ) },
      ]}
    />
  );
}
