#!/usr/bin/env python3
"""Conservative Grok clip trimming that preserves full words with natural handles.

No default leading trim. No auto-padding beyond source duration, because generated
mouth motion after speech reads fake. The goal is removing obvious dead air while
keeping full syllables and a natural post-word handle.
"""
import argparse, glob as _glob, math, os, struct, subprocess, tempfile, wave


def probe_dur(p):
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", p],
        capture_output=True, text=True, check=True,
    ).stdout.strip()
    return float(out or 0)


def pcm_rms(raw, sampwidth):
    if not raw:
        return 0
    if sampwidth == 2:
        n = len(raw) // 2
        vals = struct.unpack('<' + 'h' * n, raw[:n * 2])
        return int(math.sqrt(sum(v * v for v in vals) / max(1, n)))
    if sampwidth == 4:
        n = len(raw) // 4
        vals = struct.unpack('<' + 'i' * n, raw[:n * 4])
        return int(math.sqrt(sum(v * v for v in vals) / max(1, n)))
    vals = [b - 128 for b in raw]
    return int(math.sqrt(sum(v * v for v in vals) / max(1, len(vals))))


def _rms(src, win=0.05):
    wav = tempfile.mktemp(suffix=".wav")
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", src, "-map", "0:a:0", "-ac", "1", "-ar", "16000", "-sample_fmt", "s16", wav], check=True)
    try:
        w = wave.open(wav, "rb")
        sr, sw = w.getframerate(), w.getsampwidth()
        d = w.readframes(w.getnframes())
        w.close()
    finally:
        try: os.remove(wav)
        except FileNotFoundError: pass
    wl = max(1, int(sr * win))
    wb = wl * sw
    return [pcm_rms(d[i:i + wb], sw) for i in range(0, max(wb, len(d) - wb), wb)], win


def speech_bounds(src, frac=0.045, win=0.05, min_run=2):
    rms, win = _rms(src, win)
    if not rms:
        return None, None
    pk = max(rms) or 1
    th = pk * frac
    hits = [i for i, v in enumerate(rms) if v > th]
    if not hits:
        return None, None

    def first_run():
        run = []
        for i in hits:
            if not run or i == run[-1] + 1:
                run.append(i)
            else:
                if len(run) >= min_run: return run[0]
                run = [i]
        return run[0] if len(run) >= min_run else hits[0]

    def last_run():
        run = []
        for i in reversed(hits):
            if not run or i == run[-1] - 1:
                run.append(i)
            else:
                if len(run) >= min_run: return run[0]
                run = [i]
        return run[0] if len(run) >= min_run else hits[-1]

    return first_run() * win, (last_run() + 1) * win


def reencode(src, out, start=0.0, t=None):
    cmd = ["ffmpeg", "-y", "-v", "error"]
    if start and start > 0.01:
        cmd += ["-ss", f"{start:.3f}"]
    cmd += ["-i", src, "-map", "0:v:0", "-map", "0:a:0"]
    if t is not None:
        cmd += ["-t", f"{t:.3f}"]
    cmd += ["-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "18", "-c:a", "aac", "-ar", "44100", "-ac", "2", out]
    subprocess.run(cmd, check=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--glob", required=True)
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--tail", type=float, default=0.85, help="seconds to preserve after final detected speech")
    ap.add_argument("--head", type=float, default=0.0, help="max leading silence budget; 0 disables leading trim")
    ap.add_argument("--pre-roll", type=float, default=0.22, help="extra audio kept before first detected speech when --head is enabled")
    ap.add_argument("--min-cut", type=float, default=0.35, help="skip cuts smaller than this to avoid rough edit feel")
    ap.add_argument("--frac", type=float, default=0.045)
    a = ap.parse_args()
    os.makedirs(a.out_dir, exist_ok=True)
    files = sorted(_glob.glob(a.glob))
    trimmed = kept = 0
    saved = 0.0
    for src in files:
        out = os.path.join(a.out_dir, os.path.basename(src))
        D = probe_dur(src)
        ss, se = speech_bounds(src, frac=a.frac)
        start = 0.0
        if a.head > 0 and ss is not None and ss > a.head:
            start = max(0.0, ss - a.pre_roll)
        tail_point = min(D, (se + a.tail) if se is not None else D)
        keep_dur = max(0.05, tail_point - start)
        cut = D - keep_dur
        if cut > a.min_cut:
            reencode(src, out, start=start, t=keep_dur)
            trimmed += 1
            saved += cut
            print(f"  {os.path.basename(src)} {D:.2f}->{keep_dur:.2f} (speech {ss or 0:.2f}-{se or D:.2f}, head {start:.2f}, cut {cut:.2f})", flush=True)
        else:
            reencode(src, out)
            kept += 1
            print(f"  {os.path.basename(src)} {D:.2f} keep (speech {ss or 0:.2f}-{se or D:.2f})", flush=True)
    print(f"trimmed {trimmed}, kept {kept}; removed {saved:.1f}s dead air -> {a.out_dir}")


if __name__ == "__main__":
    main()
