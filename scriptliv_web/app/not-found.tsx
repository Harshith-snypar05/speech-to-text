import { ArrowLeft, History } from "lucide-react";
import type { Metadata } from "next";
import Link from "next/link";
import { ErrorView } from "@/components/error-view";
import { buttonCls } from "@/components/ui/button-styles";

export const metadata: Metadata = { title: "Page not found" };

export default function NotFound() {
  return (
    <ErrorView
      code="404"
      title="We can't find that page"
      actions={
        <>
          <Link href="/" className={buttonCls({ size: "lg" })}><ArrowLeft className="size-4" aria-hidden /> Back to home</Link>
          <Link href="/app/history" className={buttonCls({ variant: "outline", size: "lg" })}><History className="size-4" aria-hidden /> My transcripts</Link>
        </>
      }
    >
      The link may be old or mistyped, or the page was moved. Nothing is wrong with your account.
    </ErrorView>
  );
}
