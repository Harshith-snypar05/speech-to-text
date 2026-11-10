"use client";
import { useEffect, useRef } from "react";

/**
 * Renders the REAL microphone level history (RMS values pushed by the live client). When `levels` is empty the bars
 * sit flat: it never animates on its own, so a moving waveform always means audio is actually being captured.
 */
export function Waveform({ levels, active, bars = 48, height = 72 }: { levels: number[]; active: boolean; bars?: number; height?: number }) {
  const ref = useRef<HTMLCanvasElement>(null);
  useEffect(() => {
    const c = ref.current;
    if (!c) return;
    const dpr = window.devicePixelRatio || 1;
    const w = c.clientWidth;
    c.width = w * dpr;
    c.height = height * dpr;
    const g = c.getContext("2d");
    if (!g) return;
    g.scale(dpr, dpr);
    g.clearRect(0, 0, w, height);
    const slot = w / bars;
    const grad = g.createLinearGradient(0, 0, w, 0);
    grad.addColorStop(0, "#9a29e0");
    grad.addColorStop(1, "#d946ef");
    g.fillStyle = active ? grad : getComputedStyle(document.documentElement).getPropertyValue("--border") || "#ccc";
    const tail = levels.slice(-bars);
    for (let i = 0; i < bars; i++) {
      const v = tail[i - (bars - tail.length)] ?? 0;
      const h = Math.max(3, Math.min(1, Math.sqrt(v) * 2.2) * height);
      g.beginPath();
      g.roundRect(i * slot + slot * 0.2, (height - h) / 2, slot * 0.6, h, slot * 0.3);
      g.fill();
    }
  }, [levels, active, bars, height]);
  return <canvas ref={ref} role="img" aria-label={active ? "Live microphone level" : "Microphone idle"} className="w-full" style={{ height }} />;
}
