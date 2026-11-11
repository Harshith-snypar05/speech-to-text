"use client";
import { Home, RotateCcw } from "lucide-react";
import Link from "next/link";
import { useEffect } from "react";
import { ErrorView } from "@/components/error-view";
import { buttonCls } from "@/components/ui/button-styles";

/** Catches a crash on any public page. The raw error is never shown to people; only a short reference they can quote to support. */
export default function Error({ error, reset }: { error: Error & { digest?: string }; reset: () => void }) {
  useEffect(() => { console.error(error); }, [error]);
  return (
    <ErrorView
      code="Oops"
      title="Something went wrong"
      reference={error.digest}
      actions={
        <>
          <button onClick={reset} className={buttonCls({ size: "lg" })}><RotateCcw className="size-4" aria-hidden /> Try again</button>
          <Link href="/" className={buttonCls({ variant: "outline", size: "lg" })}><Home className="size-4" aria-hidden /> Back to home</Link>
        </>
      }
    >
      This page hit a problem and couldn&apos;t load. It&apos;s on our side, not yours. Try again, and if it still fails, come back in a few minutes.
    </ErrorView>
  );
}
