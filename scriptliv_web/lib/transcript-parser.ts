/**
 * Parses the relay wire protocol: `{"text": "...", "partial": true|false}` and `{"type": "ended"}`.
 * Partials arrive as incremental words and accumulate until the matching final, which replaces them.
 * Same semantics as the Flutter LiveTranscriptParser, so both clients show identical text.
 */
export interface ParserHandlers {
  onFinal: (text: string) => void;
  onPartial: (text: string) => void;
  onEnded: () => void;
  /** a better version of a line already delivered as a final; matched by its `original` text */
  onRefine?: (original: string, refined: string) => void;
}

export class LiveTranscriptParser {
  private partialWords: string[] = [];

  reset() {
    this.partialWords = [];
  }

  parse(raw: string, h: ParserHandlers) {
    let data: unknown;
    try {
      data = JSON.parse(raw);
    } catch {
      return;
    }
    if (typeof data !== "object" || data === null) return;
    const d = data as { type?: string; text?: unknown; partial?: unknown; original?: unknown; refined?: unknown };
    if (d.type === "ended") {
      h.onEnded();
      return;
    }
    if (d.type === "refine") {
      // never a new line and never touches the live partial
      if (h.onRefine && typeof d.original === "string" && typeof d.refined === "string" && d.refined.trim()) h.onRefine(d.original, d.refined.trim());
      return;
    }
    const text = typeof d.text === "string" ? d.text.trim() : "";
    if (!text) return;
    if (d.partial === true) {
      this.partialWords.push(text);
      h.onPartial(this.partialWords.join(" "));
    } else {
      this.partialWords = [];
      h.onPartial(""); // clear first so the partial is never shown next to its own final
      h.onFinal(text);
    }
  }
}
