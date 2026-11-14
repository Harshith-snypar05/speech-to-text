import type { Metadata, Viewport } from "next";
import "@fontsource-variable/plus-jakarta-sans";
import "./globals.css";
import { AuthModalProvider } from "@/components/auth-modal";
import { AuthProvider } from "@/lib/auth";

export const metadata: Metadata = {
  title: { default: "ScriptLiv — live speech to text", template: "%s · ScriptLiv" },
  description: "Real-time, on-device-class speech transcription. Speak, and watch the transcript appear as you talk.",
  icons: { icon: "/favicon.ico", apple: "/apple-touch-icon.png" },
};

export const viewport: Viewport = {
  themeColor: "#faf7ff", // light theme's --bg, now the default
};

// Light is the default for anyone with no saved choice; 'dark' wins, 'system' follows the OS.
const themeScript = `try{var t=localStorage.getItem('sl-theme');var d=t==='dark'?true:t==='system'?matchMedia('(prefers-color-scheme: dark)').matches:false;if(d)document.documentElement.classList.add('dark')}catch(e){}`;

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" suppressHydrationWarning>
      <head><script dangerouslySetInnerHTML={{ __html: themeScript }} /></head>
      <body suppressHydrationWarning className="min-h-dvh antialiased">
        <AuthProvider><AuthModalProvider>{children}</AuthModalProvider></AuthProvider>
      </body>
    </html>
  );
}
