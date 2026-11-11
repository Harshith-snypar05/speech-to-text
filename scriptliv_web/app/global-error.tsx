"use client";
import "@fontsource-variable/plus-jakarta-sans";
import "./globals.css";
import { useEffect } from "react";
import { ErrorView } from "@/components/error-view";
import { buttonCls } from "@/components/ui/button-styles";

const themeScript = `try{var t=localStorage.getItem('sl-theme');var d=t==='system'?matchMedia('(prefers-color-scheme: dark)').matches:t!=='light';if(d)document.documentElement.classList.add('dark')}catch(e){document.documentElement.classList.add('dark')}`;

/** Last resort: the root layout itself failed, so this supplies its own <html>. Plain anchors only, no app providers. */
export default function GlobalError({ error, reset }: { error: Error & { digest?: string }; reset: () => void }) {
  useEffect(() => { console.error(error); }, [error]);
  return (
    <html lang="en" suppressHydrationWarning>
      <head><title>Something went wrong · ScriptLiv</title><script dangerouslySetInnerHTML={{ __html: themeScript }} /></head>
      <body className="min-h-dvh antialiased">
        <ErrorView
          code="Oops"
          title="ScriptLiv hit a problem"
          reference={error.digest}
          actions={
            <>
              <button onClick={reset} className={buttonCls({ size: "lg" })}>Try again</button>
              {/* eslint-disable-next-line @next/next/no-html-link-for-pages */}
              <a href="/" className={buttonCls({ variant: "outline", size: "lg" })}>Back to home</a>
            </>
          }
        >
          The site couldn&apos;t start properly. It&apos;s on our side, and your data is safe. Please try again in a moment.
        </ErrorView>
      </body>
    </html>
  );
}
