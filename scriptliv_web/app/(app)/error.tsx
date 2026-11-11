"use client";
import { LayoutDashboard, RotateCcw } from "lucide-react";
import Link from "next/link";
import { useEffect } from "react";
import { ErrorView } from "@/components/error-view";
import { buttonCls } from "@/components/ui/button-styles";

/** Crash inside the signed-in app. Keeps the navbar (this renders in the app layout), so people can move on instead of being stranded. */
export default function AppError({ error, reset }: { error: Error & { digest?: string }; reset: () => void }) {
  useEffect(() => { console.error(error); }, [error]);
  return (
    <ErrorView
      inline
      code="Oops"
      title="This page couldn't load"
      reference={error.digest}
      actions={
        <>
          <button onClick={reset} className={buttonCls({ size: "lg" })}><RotateCcw className="size-4" aria-hidden /> Try again</button>
          <Link href="/app" className={buttonCls({ variant: "outline", size: "lg" })}><LayoutDashboard className="size-4" aria-hidden /> Go to my dashboard</Link>
        </>
      }
    >
      Something went wrong while showing this page. Your transcripts and minutes are safe. Try again, or head back to your dashboard.
    </ErrorView>
  );
}
