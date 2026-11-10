"""Offline VAD experiment: baseline fixed / production adaptive / experimental adaptive
on synthetic scenes. No relay, no model. Writes results/vad_experiment.json and
results/vad_experiment_tables.md.   python run_experiment.py [--quick]
"""
import argparse
import itertools
import json
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))
from audio_utils import simulate_flushes, to_pcm16  # noqa: E402
from synth import CHUNK, Scene, build_scene  # noqa: E402
from vad_experimental import AdaptiveVadBuffer, UtteranceBuffer, VadParams  # noqa: E402

HANG, MIN_U, MAX_U = 0.6, 0.3, 8.0


def make_vad(name: str):
    if name == "fixed":
        return UtteranceBuffer(16000, 2, 0.01, HANG, MIN_U, MAX_U)
    if name == "prod_adaptive":
        return UtteranceBuffer(16000, 2, 0.01, HANG, MIN_U, MAX_U, adaptive_noise_floor=True, noise_floor_multiplier=2.5)
    if name == "exp":
        return AdaptiveVadBuffer(16000, 2, 0.01, HANG, MIN_U, MAX_U, VadParams())
    if name == "exp_v1":
        return AdaptiveVadBuffer(16000, 2, 0.01, HANG, MIN_U, MAX_U, VadParams(gate_speech=False))
    if name == "exp_lowlo_v1":
        return AdaptiveVadBuffer(16000, 2, 0.01, HANG, MIN_U, MAX_U, VadParams(lo=0.004, gate_speech=False))
    if name == "exp_lowlo":
        return AdaptiveVadBuffer(16000, 2, 0.01, HANG, MIN_U, MAX_U, VadParams(lo=0.004))
    if name.startswith("exp_"):  # sensitivity variants: exp_m2, exp_h0.6 ...
        kw = {}
        for part in name[4:].split(","):
            k, v = part.split("=")
            kw[k] = float(v)
        return AdaptiveVadBuffer(16000, 2, 0.01, HANG, MIN_U, MAX_U, VadParams(**kw))
    raise ValueError(name)


def run_vad(name: str, scene: Scene):
    b = make_vad(name)
    pcm = to_pcm16(scene.audio)
    det, flushes = [], []
    for i in range(scene.n_chunks):
        c = pcm[i * CHUNK * 2:(i + 1) * CHUNK * 2]
        if name in ("fixed", "prod_adaptive"):
            rms = float(np.sqrt(np.mean((np.frombuffer(c, np.int16) / 32768.0) ** 2)))
            det.append(rms >= b._effective_threshold())
        full = len(b.buffer) / 32000 + 0.1 >= MAX_U
        if b.add_chunk(c):
            flushes.append(((i + 1) * 0.1, bool(full)))
            b.take()
        if name not in ("fixed", "prod_adaptive"):
            det.append(b.last_is_speech)
    return np.array(det, bool), flushes


def score(scene: Scene, det, flushes):
    truth = scene.truth_speech
    near = np.convolve(truth.astype(int), np.ones(7, int), mode="same") > 0  # within 0.3 s of speech
    nonspeech = ~near
    rec = float((det & truth).sum() / max(truth.sum(), 1))
    fa = float((det & nonspeech).sum() / max(nonspeech.sum(), 1))
    spans = scene.groups
    end_t = scene.n_chunks * 0.1
    false_fl = missed = forced_only = 0
    lat = []
    claimed = set()
    for k, (S, E) in enumerate(spans):
        nxt = spans[k + 1][0] if k + 1 < len(spans) else end_t + 1
        win = [(t, f) for t, f in flushes if E < t <= nxt]
        good = [(t, f) for t, f in win if not f]
        for t, f in flushes:
            if S + 0.05 < t <= E + 1e-9:
                false_fl += 1
        if good:
            lat.append(good[0][0] - E - HANG)
        elif win:
            forced_only += 1
            missed += 1
        else:
            missed += 1
        false_fl += max(len(win) - 1, 0)  # extra flushes after the proper one
    lead_fl = sum(1 for t, f in flushes if t <= spans[0][0] + 0.05)
    false_fl += lead_fl
    n_forced = sum(1 for _, f in flushes if f)
    return dict(recall=rec, false_act=fa, false_flush=false_fl, missed=missed, expected=len(spans),
                forced_flushes=n_forced, lat=lat, truth_chunks=int(truth.sum()), nonspeech_chunks=int(nonspeech.sum()))


def snr_db(scene: Scene) -> float:
    m = scene.meta
    sp = 0.1 * m["gain"]  # placeholder, replaced below
    return sp


def build_grid(quick: bool):
    gaps = ["SS", "SL", "LS", "LL"]
    gains = [1.0, 0.5, 0.25, 0.12]
    levels = [("none", 0.0), ("fan", 0.003), ("fan", 0.01), ("fan", 0.03), ("fan", 0.08)]
    kinds = ["fan", "cafe", "street", "keyboard"]
    leads = [0.3, 2.0]
    if quick:
        gaps, gains, leads = ["SL", "LL"], [1.0, 0.25], [0.3]
    scenes, i = [], 0
    for g, ga, ld in itertools.product(gaps, gains, leads):
        for kind, lvl in levels:
            for k in ([kind] if lvl == 0.0 else kinds):
                i += 1
                scenes.append(build_scene(g, ga, k, lvl, ld, seed=1000 + i))
    return scenes


def speech_active_rms(scene: Scene):
    m = scene.meta
    # recompute from truth chunks of the gain-1 clean: audio contains noise, so use ratio via known jfk rms
    return m["gain"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--quick", action="store_true")
    ap.add_argument("--sweep", action="store_true", help="also run sensitivity variants")
    a = ap.parse_args()
    scenes = build_grid(a.quick)
    names = ["fixed", "prod_adaptive", "exp_v1", "exp", "exp_lowlo_v1", "exp_lowlo"]
    if a.sweep:
        names += ["exp_mult=2", "exp_mult=4", "exp_hi_frac=0.3", "exp_hi_frac=0.6", "exp_percentile=10", "exp_exit_ratio=1.0"]
    # speech-active rms at gain 1 (clean JFK truth chunks) for SNR bookkeeping
    base = build_scene("SS", 1.0, "white", 0.0, 0.3, 0)
    # room-tone-only noise ~0.002 present in all scenes
    # rows
    rows = []
    # sanity: fixed real buffer vs simulate_flushes (fixed rule) on a handful of scenes
    chk = 0
    for sc in scenes[:: max(len(scenes) // 12, 1)]:
        det, fl = run_vad("fixed", sc)
        sim = simulate_flushes(sc.audio, 0.1, 0.0, 0.01, HANG, MIN_U, MAX_U)
        assert len(sim) == len(fl) or abs(len(sim) - len(fl)) <= 1, (sc.name, sim, fl)
        chk += 1
    print(f"sanity: fixed buffer vs simulate_flushes flush counts agree on {chk} scenes")
    sp_rms = float(np.sqrt(np.mean(np.concatenate([
        base.audio.reshape(-1, CHUNK)[i] ** 2 for i in np.nonzero(base.truth_speech)[0]]))))
    for sc in scenes:
        m = sc.meta
        noise_total = float(np.sqrt(m["noise_rms"] ** 2 + 0.002 ** 2))
        snr = 20 * np.log10(max(sp_rms * m["gain"], 1e-9) / noise_total)
        for n in names:
            det, fl = run_vad(n, sc)
            r = score(sc, det, fl)
            rows.append(dict(vad=n, scene=sc.name, snr_db=float(snr), **m, **r))
    out = HERE.parent / "results"
    out.mkdir(exist_ok=True)
    (out / "vad_experiment.json").write_text(json.dumps(rows), encoding="utf-8")
    tables = make_tables(rows, names, sp_rms)
    (out / "vad_experiment_tables.md").write_text(tables, encoding="utf-8")
    print(tables)


def agg(rs):
    if not rs:
        return None
    tr = sum(r["truth_chunks"] for r in rs)
    ns = sum(r["nonspeech_chunks"] for r in rs)
    rec = sum(r["recall"] * r["truth_chunks"] for r in rs) / max(tr, 1)
    fa = sum(r["false_act"] * r["nonspeech_chunks"] for r in rs) / max(ns, 1)
    lat = [v for r in rs for v in r["lat"]]
    exp = sum(r["expected"] for r in rs)
    return dict(n=len(rs), recall=rec, false_act=fa,
                false_flush=sum(r["false_flush"] for r in rs) / len(rs),
                missed=sum(r["missed"] for r in rs) / max(exp, 1),
                forced=sum(r["forced_flushes"] for r in rs) / len(rs),
                lat_med=float(np.median(lat)) if lat else float("nan"),
                lat_p90=float(np.percentile(lat, 90)) if lat else float("nan"), n_lat=len(lat))


def fmt_row(label, d):
    if d is None:
        return f"| {label} | - | - | - | - | - | - | - |"
    return (f"| {label} | {d['recall']*100:.1f}% | {d['false_act']*100:.1f}% | {d['false_flush']:.2f} | "
            f"{d['missed']*100:.1f}% | {d['forced']:.2f} | {d['lat_med']:.2f} / {d['lat_p90']:.2f} (n={d['n_lat']}) | {d['n']} |")


HEAD = ("| {k} | speech recall | false activation | false flushes / scene | missed flushes | cap flushes / scene "
        "| extra latency over 0.6 s hang, med / p90 s | scenes |\n|---|---:|---:|---:|---:|---:|---:|---:|")


def make_tables(rows, names, sp_rms):
    by = defaultdict(list)
    for r in rows:
        by[r["vad"]].append(r)
    out = [f"Active-speech RMS at gain 1: {sp_rms:.3f}. Scenes: {len(by[names[0]])} per VAD.\n"]

    def table(title, keyfn, subset=lambda r: True, order=None):
        out.append(f"\n#### {title}\n")
        groups = sorted({keyfn(r) for r in rows if subset(r)}, key=order or str)
        for g in groups:
            out.append(f"\n**{g}**\n")
            out.append(HEAD.format(k="VAD"))
            for n in names:
                out.append(fmt_row(n, agg([r for r in by[n] if subset(r) and keyfn(r) == g])))

    out.append("\n#### Overall\n")
    out.append(HEAD.format(k="VAD"))
    for n in names:
        out.append(fmt_row(n, agg(by[n])))
    snr_b = lambda r: ("SNR >= 20 dB" if r["snr_db"] >= 20 else "10-20 dB" if r["snr_db"] >= 10 else "0-10 dB" if r["snr_db"] >= 0 else "< 0 dB")  # noqa: E731
    table("By speech/noise ratio (SNR)", snr_b, order=lambda s: ["SNR >= 20 dB", "10-20 dB", "0-10 dB", "< 0 dB"].index(s))
    table("By speech gain (all noise)", lambda r: f"gain {r['gain']}", order=lambda s: -float(s.split()[1]))
    table("QUIET-SPEECH GUARD: gain <= 0.25 and SNR >= 10 dB (separable cases)", lambda r: f"gain {r['gain']}",
          subset=lambda r: r["gain"] <= 0.25 and r["snr_db"] >= 10, order=lambda s: -float(s.split()[1]))
    table("By absolute noise level (rms)", lambda r: f"noise {r['noise_rms']}", order=lambda s: float(s.split()[1]))
    table("By noise type (noise rms > 0)", lambda r: r["noise"], subset=lambda r: r["noise_rms"] > 0)
    table("By pause pattern", lambda r: r["gap_pattern"])
    table("By lead-in before first speech (s)", lambda r: f"lead {r['lead_s']}")
    # per-scene quiet-speech regressions vs fixed
    fx = {r["scene"]: r for r in by["fixed"]}
    out.append("\n#### Per-scene quiet-speech guard check (recall drop vs fixed baseline > 5 points)\n")
    out.append("| VAD | scenes worse than fixed | of which SNR >= 10 dB | scenes better than fixed (>5 pts) |\n|---|---:|---:|---:|")
    for n in names:
        if n == "fixed":
            continue
        w = [r for r in by[n] if fx[r["scene"]]["recall"] - r["recall"] > 0.05]
        b = [r for r in by[n] if r["recall"] - fx[r["scene"]]["recall"] > 0.05]
        out.append(f"| {n} | {len(w)} | {sum(1 for r in w if r['snr_db'] >= 10)} | {len(b)} |")
    return "\n".join(out)


if __name__ == "__main__":
    main()
