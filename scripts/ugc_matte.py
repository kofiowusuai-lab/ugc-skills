#!/usr/bin/env python3
"""
ugc_matte.py
------------------------------------------------------------------------------
Produce a PERSON-ONLY alpha matte version of a talking-head video: transparent
everywhere there is no person, opaque on the person. The result is a ProRes 4444
.mov with a real alpha channel (pix_fmt yuva444p10le) that Remotion can layer ON
TOP of animated text so the avatar OCCLUDES the text (text-behind-avatar effect).

NOTE on container choice: this machine's ffmpeg 7.0 libvpx-vp9 build drops the
alpha plane (yuva420p in -> yuv420p out), so VP9 webm is NOT reliable here.
ProRes 4444 (.mov) preserves alpha correctly and is supported by Remotion's
OffthreadVideo, so it is the chosen output. A PNG sequence is also kept available
internally as the source of truth for the alpha.

Approach (reliable baseline, no rembg CLI dependency):
  - Decode frames with ffmpeg to a temp PNG sequence.
  - Run the U^2-Net salient-object/person segmentation model directly via
    onnxruntime (CoreML EP on Apple Silicon). This is the exact model the rembg
    `u2net` backend uses (~/.u2net/u2net.onnx), but called directly so we do not
    depend on the broken rembg CLI (missing `packaging`) on this machine.
  - Light temporal smoothing of the alpha across frames (EMA) to reduce flicker,
    plus a small feather (gaussian blur on alpha edges) for clean compositing.
  - Composite the original RGB with the predicted alpha -> RGBA PNG sequence.
  - Reassemble to ProRes 4444 .mov (yuva444p10le) so the alpha survives.

Prints JSON: {"ok": true, "out": "..."} or {"ok": false, "error": "..."}.

USAGE
  ugc_matte.py --video IN.mp4 --out OUT.mov [--fps 30] [--max-side 720]
               [--model ~/.u2net/u2net.onnx] [--no-smooth] [--frames N]
------------------------------------------------------------------------------
"""
import argparse, json, os, shutil, subprocess, sys, tempfile, glob

FFMPEG = os.path.expanduser("~/bin/ffmpeg")
if not os.path.exists(FFMPEG):
    FFMPEG = shutil.which("ffmpeg") or "ffmpeg"
FFPROBE = "/opt/homebrew/bin/ffprobe"
if not os.path.exists(FFPROBE):
    FFPROBE = shutil.which("ffprobe") or "ffprobe"
DEFAULT_MODEL = os.path.expanduser("~/.u2net/u2net.onnx")


def die(msg):
    print(json.dumps({"ok": False, "error": msg}))
    sys.exit(1)


def probe_fps(path):
    try:
        out = subprocess.run(
            [FFPROBE, "-v", "error", "-select_streams", "v:0",
             "-show_entries", "stream=r_frame_rate", "-of", "csv=p=0", path],
            capture_output=True, text=True, timeout=30).stdout.strip()
        n, d = out.split("/")
        return float(n) / float(d) if float(d) else 30.0
    except Exception:
        return 30.0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--video", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--fps", type=float, default=0.0, help="output fps (0 = source)")
    ap.add_argument("--max-side", type=int, default=720,
                    help="downscale longest side before matting (speed); output kept at this res")
    ap.add_argument("--model", default=DEFAULT_MODEL)
    ap.add_argument("--no-smooth", action="store_true")
    ap.add_argument("--frames", type=int, default=0, help="cap number of frames (debug)")
    args = ap.parse_args()

    video = os.path.abspath(os.path.expanduser(args.video))
    out = os.path.abspath(os.path.expanduser(args.out))
    model = os.path.abspath(os.path.expanduser(args.model))
    if not os.path.exists(video):
        die(f"video not found: {video}")
    if not os.path.exists(model):
        die(f"model not found: {model} (expected u2net.onnx)")

    try:
        import numpy as np
        from PIL import Image, ImageFilter
        import onnxruntime as ort
    except Exception as e:
        die(f"missing python deps (numpy/Pillow/onnxruntime): {e}")

    fps = args.fps if args.fps > 0 else probe_fps(video)
    os.makedirs(os.path.dirname(out) or ".", exist_ok=True)

    tmp = tempfile.mkdtemp(prefix="ugc_matte_")
    frm_dir = os.path.join(tmp, "frames")
    rgba_dir = os.path.join(tmp, "rgba")
    os.makedirs(frm_dir); os.makedirs(rgba_dir)

    try:
        # 1) extract frames (scaled so longest side <= max_side, even dims for vp9)
        ms = args.max_side
        scale = (f"scale='if(gt(iw,ih),min({ms},iw),-2)':'if(gt(iw,ih),-2,min({ms},ih))'"
                 f":flags=lanczos")
        cmd = [FFMPEG, "-y", "-i", video, "-vf", f"fps={fps},{scale}",
               "-start_number", "0", os.path.join(frm_dir, "f_%05d.png")]
        r = subprocess.run(cmd, capture_output=True, text=True)
        if r.returncode != 0:
            die("ffmpeg frame extract failed: " + r.stderr[-500:])
        frames = sorted(glob.glob(os.path.join(frm_dir, "f_*.png")))
        if args.frames > 0:
            frames = frames[:args.frames]
        if not frames:
            die("no frames extracted")

        # 2) onnxruntime session (CoreML on Apple Silicon, fallback CPU)
        providers = []
        avail = ort.get_available_providers()
        if "CoreMLExecutionProvider" in avail:
            providers.append("CoreMLExecutionProvider")
        providers.append("CPUExecutionProvider")
        so = ort.SessionOptions()
        so.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
        sess = ort.InferenceSession(model, sess_options=so, providers=providers)
        inp = sess.get_inputs()[0]
        in_name = inp.name
        # u2net expects 320x320 normalized input
        IN = 320
        mean = np.array([0.485, 0.456, 0.406], dtype=np.float32)
        std = np.array([0.229, 0.224, 0.225], dtype=np.float32)

        def predict_alpha(pil_rgb):
            w, h = pil_rgb.size
            small = pil_rgb.resize((IN, IN), Image.BILINEAR)
            a = np.asarray(small, dtype=np.float32) / 255.0
            a = (a - mean) / std
            a = a.transpose(2, 0, 1)[None, ...]  # 1,3,320,320
            out_maps = sess.run(None, {in_name: a})
            m = out_maps[0]  # 1,1,320,320 (first/finest map)
            m = np.squeeze(m)
            mn, mx = float(m.min()), float(m.max())
            if mx - mn > 1e-6:
                m = (m - mn) / (mx - mn)
            mask = Image.fromarray((m * 255).astype(np.uint8)).resize((w, h), Image.BILINEAR)
            return mask

        prev = None  # for EMA smoothing
        EMA = 0.0 if args.no_smooth else 0.45  # blend weight of previous frame
        n = len(frames)
        for i, fp in enumerate(frames):
            rgb = Image.open(fp).convert("RGB")
            mask = predict_alpha(rgb)
            ma = np.asarray(mask, dtype=np.float32)
            if prev is not None and EMA > 0:
                ma = EMA * prev + (1.0 - EMA) * ma
            prev = ma
            alpha = Image.fromarray(np.clip(ma, 0, 255).astype(np.uint8))
            # feather the matte edge slightly for clean compositing over text
            alpha = alpha.filter(ImageFilter.GaussianBlur(radius=1.2))
            rgba = rgb.convert("RGBA")
            rgba.putalpha(alpha)
            rgba.save(os.path.join(rgba_dir, "r_%05d.png" % i))
            if i % 30 == 0:
                sys.stderr.write(f"[matte] {i+1}/{n}\n"); sys.stderr.flush()

        # 3) reassemble to ProRes 4444 .mov with alpha (yuva444p10le).
        #    ffmpeg 7.0 libvpx-vp9 here drops the alpha plane, so use ProRes,
        #    which preserves alpha and is readable by Remotion OffthreadVideo.
        cmd = [FFMPEG, "-y", "-framerate", str(fps),
               "-i", os.path.join(rgba_dir, "r_%05d.png"),
               "-c:v", "prores_ks", "-profile:v", "4444",
               "-pix_fmt", "yuva444p10le", "-an", out]
        r = subprocess.run(cmd, capture_output=True, text=True)
        if r.returncode != 0 or not os.path.exists(out):
            die("ffmpeg ProRes assemble failed: " + r.stderr[-500:])

        # 4) verify the output actually has an alpha channel
        pf = subprocess.run(
            [FFPROBE, "-v", "error", "-select_streams", "v:0",
             "-show_entries", "stream=pix_fmt", "-of", "csv=p=0", out],
            capture_output=True, text=True).stdout.strip()
        if "yuva" not in pf and "a" not in pf:
            die(f"output has no alpha channel (pix_fmt={pf})")

        print(json.dumps({"ok": True, "out": out, "pix_fmt": pf,
                          "frames": n, "fps": fps}))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    main()
