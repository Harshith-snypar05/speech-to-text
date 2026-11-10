// AudioWorklet: mono float32 @ context rate -> 16 kHz PCM16, posted in ~100 ms chunks together with the chunk RMS
// (the RMS drives the real waveform; nothing in the UI is simulated).
class PcmProcessor extends AudioWorkletProcessor {
  constructor() {
    super();
    this.ratio = sampleRate / 16000; // input samples per output sample
    this.pos = 0; // fractional read position in `buf`
    this.buf = [];
    this.out = new Int16Array(1600);
    this.n = 0;
    this.sumSq = 0;
  }

  process(inputs) {
    const ch = inputs[0] && inputs[0][0];
    if (!ch) return true;
    for (let i = 0; i < ch.length; i++) this.buf.push(ch[i]);
    while (this.pos + 1 < this.buf.length) {
      const i = Math.floor(this.pos);
      const f = this.pos - i;
      const s = this.buf[i] * (1 - f) + this.buf[i + 1] * f;
      const c = Math.max(-1, Math.min(1, s));
      this.sumSq += c * c;
      this.out[this.n++] = c < 0 ? c * 0x8000 : c * 0x7fff;
      this.pos += this.ratio;
      if (this.n === this.out.length) {
        this.port.postMessage({ pcm: this.out.buffer, rms: Math.sqrt(this.sumSq / this.n) }, [this.out.buffer]);
        this.out = new Int16Array(1600);
        this.n = 0;
        this.sumSq = 0;
      }
    }
    const drop = Math.floor(this.pos);
    if (drop > 0) {
      this.buf.splice(0, drop);
      this.pos -= drop;
    }
    return true;
  }
}
registerProcessor("pcm-processor", PcmProcessor);
