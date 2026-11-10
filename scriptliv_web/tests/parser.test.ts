import { describe, expect, it } from "vitest";
import { fmtBytes, fmtTime, num, toCsv } from "../lib/format";
import { LiveTranscriptParser } from "../lib/transcript-parser";

function run(msgs: string[]) {
  const p = new LiveTranscriptParser();
  const partials: string[] = [];
  const finals: string[] = [];
  let ended = 0;
  for (const m of msgs) p.parse(m, { onPartial: (t) => partials.push(t), onFinal: (t) => finals.push(t), onEnded: () => ended++ });
  return { partials, finals, ended };
}
const part = (t: string) => JSON.stringify({ text: t, partial: true });
const fin = (t: string) => JSON.stringify({ text: t, partial: false });

describe("LiveTranscriptParser", () => {
  it("accumulates incremental partials", () => {
    expect(run([part("hello"), part("world")]).partials).toEqual(["hello", "hello world"]);
  });
  it("final clears the partial first so it is never shown beside its own final", () => {
    const r = run([part("hello"), part("world"), fin("Hello world.")]);
    expect(r.partials.at(-1)).toBe("");
    expect(r.finals).toEqual(["Hello world."]);
  });
  it("next utterance starts a fresh partial after a final", () => {
    expect(run([part("a"), fin("A."), part("b")]).partials.at(-1)).toBe("b");
  });
  it("ignores malformed, empty and non-object messages", () => {
    const r = run(["not json", "null", "5", JSON.stringify({ text: "  " }), JSON.stringify({})]);
    expect(r).toEqual({ partials: [], finals: [], ended: 0 });
  });
  it("reports ended", () => {
    expect(run([JSON.stringify({ type: "ended" })]).ended).toBe(1);
  });
  it("reset drops a half-built partial", () => {
    const p = new LiveTranscriptParser();
    const seen: string[] = [];
    const h = { onPartial: (t: string) => seen.push(t), onFinal: () => {}, onEnded: () => {} };
    p.parse(part("x"), h);
    p.reset();
    p.parse(part("y"), h);
    expect(seen).toEqual(["x", "y"]);
  });
});

describe("format", () => {
  it("shows unavailable, never zero, for missing values", () => {
    expect(num(null)).toBe("unavailable");
    expect(num(undefined)).toBe("unavailable");
    expect(num(0)).toBe("0");
    expect(fmtBytes(null)).toBe("unavailable");
    expect(fmtTime(null)).toBe("unavailable");
  });
  it("formats bytes", () => {
    expect(fmtBytes(512)).toBe("512 B");
    expect(fmtBytes(2048)).toBe("2.0 KB");
  });
  it("escapes csv", () => {
    expect(toCsv([{ a: 'x,"y"', b: 1 }])).toBe('a,b\n"x,""y""",1');
    expect(toCsv([])).toBe("");
  });
  it("refine reports original/refined, is never a final, and leaves the live partial alone", () => {
    const p = new LiveTranscriptParser();
    const refines: string[] = [];
    const finals: string[] = [];
    const partials: string[] = [];
    const h = { onPartial: (t: string) => partials.push(t), onFinal: (t: string) => finals.push(t), onEnded: () => {}, onRefine: (o: string, r: string) => refines.push(o + "=>" + r) };
    p.parse(part("hello"), h);
    p.parse(JSON.stringify({ type: "refine", seq: 0, original: "hello there", refined: " Hello, there. " }), h);
    p.parse(JSON.stringify({ type: "refine", original: "x" }), h);
    p.parse(JSON.stringify({ type: "refine", original: "x", refined: "  " }), h);
    expect(refines).toEqual(["hello there=>Hello, there."]);
    expect(finals).toEqual([]);
    expect(partials).toEqual(["hello"]);
  });
});
