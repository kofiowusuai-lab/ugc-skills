#!/usr/bin/env python3
"""
pdf_screen.py — pin a REAL ebook PDF (or a video) onto a device screen in a Grok
character clip, with sharp text. Works for ANY ebook.

Rule it enforces: a screen never self-scrolls. Motion is only produced when the
avatar drives it (hand-driven scroll) or a real video plays in the interface.

Usage:
  # Hand-driven PDF scroll (default) — scroll advances only when her hand moves
  python3 pdf_screen.py \
      --clip v2/character_clip2.mp4 \
      --pdf "/path/AI Mastery Guide VOL I - Illustrated.pdf" \
      --pages 8-13 \
      --out v2/final.mp4

  # A video playing inside the interface instead of a scroll
  python3 pdf_screen.py --clip clip.mp4 --screen-video promo.mp4 --mode video --out out.mp4

Options:
  --mode  handdriven | continuous | stepped | static | video   (default handdriven)
  --quad  path to screen_quad.json (TL,TR,BR,BL). If omitted, auto-detect.
  --roi   "x0,y0,x1,y1" hand/trackpad region for handdriven mode. Default auto (lower-right of screen).
  --dpi   PDF render dpi (default 200)
  --settle  seconds at start with no scroll (hand settling). Default 0.5
"""
import argparse, glob, json, os, subprocess, sys, tempfile
import numpy as np
import cv2
from PIL import Image, ImageDraw
from scipy import ndimage


def run(cmd):
    subprocess.run(cmd, check=True)


def probe(clip):
    out = subprocess.check_output([
        "ffprobe", "-v", "error", "-select_streams", "v:0",
        "-show_entries", "stream=width,height,r_frame_rate,nb_frames",
        "-of", "json", clip]).decode()
    s = json.loads(out)["streams"][0]
    num, den = s["r_frame_rate"].split("/")
    fps = float(num) / float(den)
    return int(s["width"]), int(s["height"]), fps


def has_audio(clip):
    out = subprocess.check_output([
        "ffprobe", "-v", "error", "-select_streams", "a",
        "-show_entries", "stream=index", "-of", "csv=p=0", clip]).decode().strip()
    return bool(out)


def render_pdf_strip(pdf, pages, dpi, W):
    import fitz
    doc = fitz.open(pdf)
    idx = parse_pages(pages, doc.page_count)
    imgs = []
    for p in idx:
        pix = doc[p].get_pixmap(dpi=dpi)
        im = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
        imgs.append(im)
    imgs = [i.resize((W, int(i.height * W / i.width))) for i in imgs]
    H = sum(i.height for i in imgs)
    strip = Image.new("RGB", (W, H), (255, 255, 255))
    y = 0
    for i in imgs:
        strip.paste(i, (0, y)); y += i.height
    return np.asarray(strip)[:, :, ::-1].copy()  # to BGR


def render_viewer_strip(pdf, pages, dpi, CW, CH):
    """Render pages as a macOS-Preview-style document: each page floats on a dark gray
    matte with side margins and gaps (NOT edge-to-edge). Returns (strip_bgr, spans, total)
    where spans = [(y_top, y_bottom, doc_page_index)] for the page-counter pill."""
    import fitz
    doc = fitz.open(pdf)
    total = doc.page_count
    idx = parse_pages(pages, total)
    BG = (32, 32, 32)  # charcoal matte, like Preview
    margin_top = int(CH * 0.045)
    gap = int(CH * 0.07)
    page_h = CH - 2 * margin_top
    max_w = CW - 2 * int(CW * 0.07)  # always leave side gutters
    placed = []
    y = margin_top
    spans = []
    for p in idx:
        pix = doc[p].get_pixmap(dpi=dpi)
        im = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
        pw = int(page_h * im.width / im.height)
        ph = page_h
        if pw > max_w:
            pw = max_w; ph = int(pw * im.height / im.width)
        im = im.resize((pw, ph))
        x = (CW - pw) // 2
        placed.append((im, x, y))
        spans.append((y - gap // 2, y + ph + gap // 2, p))
        y += ph + gap
    total_h = max(y - gap + margin_top, CH)
    strip = Image.new("RGB", (CW, total_h), BG)
    draw = ImageDraw.Draw(strip)
    for im, x, y0 in placed:
        draw.rectangle([x - 2, y0 - 2, x + im.width + 1, y0 + im.height + 1], fill=(70, 70, 70))  # page edge
        strip.paste(im, (x, y0))
    return np.asarray(strip)[:, :, ::-1].copy(), spans, total


def draw_chrome(win, page_no, total):
    """Overlay a fixed PDF-viewer toolbar + 'Page N of M' pill on the visible window."""
    h, w = win.shape[:2]
    tb = int(h * 0.055) + 14
    cv2.rectangle(win, (0, 0), (w, tb), (52, 52, 52), -1)
    cv2.line(win, (0, tb), (w, tb), (74, 74, 74), 1)
    for j, c in enumerate([(70, 70, 200), (70, 185, 215), (80, 185, 80)]):  # window dots (BGR)
        cv2.circle(win, (20 + j * 20, tb // 2), 6, c, -1)
    txt = f"Page {page_no} of {total}"
    scale, thick = 0.62, 2
    (tw, th), _ = cv2.getTextSize(txt, cv2.FONT_HERSHEY_SIMPLEX, scale, thick)
    cx = w // 2
    px0, px1 = cx - tw // 2 - 14, cx + tw // 2 + 14
    py0, py1 = tb + 7, tb + 7 + th + 14
    roi = win[py0:py1, px0:px1]
    if roi.size:
        win[py0:py1, px0:px1] = cv2.addWeighted(np.full_like(roi, 28), 0.62, roi, 0.38, 0)
    cv2.putText(win, txt, (cx - tw // 2, py1 - 9), cv2.FONT_HERSHEY_SIMPLEX, scale,
                (238, 238, 238), thick, cv2.LINE_AA)
    return win


def parse_pages(spec, total):
    out = []
    for part in str(spec).split(","):
        part = part.strip()
        if "-" in part:
            a, b = part.split("-"); out += list(range(int(a) - 1, int(b)))
        else:
            out.append(int(part) - 1)
    return [p for p in out if 0 <= p < total]


def auto_quad(frame_bgr):
    a = frame_bgr[:, :, ::-1].astype(int)
    h, w, _ = a.shape
    mx = a.max(2); mn = a.min(2)
    mask = (mx > 145) & ((mx - mn) < 45)
    lbl, n = ndimage.label(mask)
    best = None; best_sz = 0
    for cid in range(1, n + 1):
        ys, xs = np.where(lbl == cid)
        sz = len(xs)
        if sz < 8000:
            continue
        cx, cy = xs.mean(), ys.mean()
        # screens sit in the central band, not hugging top edge or far right
        if cy < h * 0.20 or cy > h * 0.90:
            continue
        if cx > w * 0.75:
            continue
        # screen-ish aspect: wider-ish bbox
        bw, bh = xs.max() - xs.min(), ys.max() - ys.min()
        if bh == 0 or bw / bh < 0.6:
            continue
        if sz > best_sz:
            best_sz = sz; best = cid
    if best is None:
        raise SystemExit("Could not auto-detect a screen. Pass --quad screen_quad.json")
    ys, xs = np.where(lbl == best)
    pts = np.stack([xs, ys], 1).astype(float)
    s = pts[:, 0] + pts[:, 1]; d = pts[:, 0] - pts[:, 1]
    TL = pts[s.argmin()]; BR = pts[s.argmax()]; TR = pts[d.argmax()]; BL = pts[d.argmin()]
    return np.float32([TL, TR, BR, BL])


def _detect_screen_in_window(frame_bgr, prev_quad, pad):
    """Find the blank screen as the largest bright/low-saturation blob in a window around the
    previous quad, and return its corner quad (TL,TR,BR,BL). None if not found."""
    a = frame_bgr[:, :, ::-1].astype(int)
    H, W, _ = a.shape
    mx = a.max(2); mn = a.min(2)
    bright = (mx > 135) & ((mx - mn) < 50)
    win = np.zeros((H, W), bool)
    x0 = max(0, int(prev_quad[:, 0].min()) - pad); x1 = min(W, int(prev_quad[:, 0].max()) + pad)
    y0 = max(0, int(prev_quad[:, 1].min()) - pad); y1 = min(H, int(prev_quad[:, 1].max()) + pad)
    win[y0:y1, x0:x1] = True
    mask = bright & win
    if mask.sum() < 4000:
        return None
    lbl, n = ndimage.label(mask)
    if n == 0:
        return None
    sizes = ndimage.sum(np.ones_like(lbl), lbl, index=range(1, n + 1))
    best = 1 + int(np.argmax(sizes))
    ys, xs = np.where(lbl == best)
    pts = np.stack([xs, ys], 1).astype(float)
    s = pts[:, 0] + pts[:, 1]; d = pts[:, 0] - pts[:, 1]
    return np.float32([pts[s.argmin()], pts[d.argmax()], pts[s.argmax()], pts[d.argmin()]])


def track_screen_quads(frames, seed_quad, pad=55, smooth=7, inset=0.018):
    """Planar-track the laptop screen across all frames so content stays locked to the display
    even as the laptop drifts. Detects the screen per frame (constrained near the previous quad),
    temporally smooths the corners (no swimming), and insets slightly so content never spills past
    the bezel. Returns a list of per-frame quads."""
    seed = np.float32(seed_quad)
    raw = []
    prev = seed.copy()
    for fp in frames:
        q = _detect_screen_in_window(cv2.imread(fp), prev, pad)
        if q is None:
            q = prev
        # reject implausible jumps (corner moved > 80px) -> keep previous to stay locked
        if np.abs(q - prev).max() > 80:
            q = prev
        raw.append(q)
        prev = 0.4 * prev + 0.6 * q
    quads = np.array(raw, dtype=np.float32)  # (N,4,2)
    if smooth > 1 and len(quads) > smooth:
        k = np.ones(smooth) / smooth
        pad_n = smooth // 2
        for c in range(4):
            for d in range(2):
                col = quads[:, c, d]
                ext = np.concatenate([np.full(pad_n, col[0]), col, np.full(pad_n, col[-1])])
                quads[:, c, d] = np.convolve(ext, k, mode="same")[pad_n:-pad_n]
    for i in range(len(quads)):
        cen = quads[i].mean(0)
        quads[i] = cen + (quads[i] - cen) * (1 - inset)
    return [np.float32(q) for q in quads]


def hand_progress(frames, roi, settle_frames):
    prev = None; motion = np.zeros(len(frames))
    x0, y0, x1, y1 = roi
    for i, fp in enumerate(frames):
        g = cv2.cvtColor(cv2.imread(fp), cv2.COLOR_BGR2GRAY).astype(np.float32)
        r = g[y0:y1, x0:x1]
        if prev is not None:
            motion[i] = np.abs(r - prev).mean()
        prev = r
    m = np.convolve(motion, np.ones(5) / 5, mode="same")
    vel = np.clip(m - np.percentile(m, 55), 0, None)
    vel[:settle_frames] = 0
    if vel.sum() == 0:
        vel = np.ones(len(frames)); vel[:settle_frames] = 0
    cum = np.cumsum(vel); cum /= cum[-1]
    return cum


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--clip", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--pdf")
    ap.add_argument("--pages", default="1-3")
    ap.add_argument("--screen-video", dest="screen_video")
    ap.add_argument("--mode", default="handdriven",
                    choices=["handdriven", "continuous", "stepped", "static", "video"])
    ap.add_argument("--quad")
    ap.add_argument("--roi")
    ap.add_argument("--dpi", type=int, default=200)
    ap.add_argument("--settle", type=float, default=0.5)
    ap.add_argument("--chrome", default="preview", choices=["preview", "none"],
                    help="preview = render pages in a macOS-Preview-style viewer (gray matte, "
                         "toolbar, 'Page N of M' pill); none = legacy edge-to-edge page fill")
    ap.add_argument("--track", dest="track", action="store_true", default=True,
                    help="planar-track the screen per frame so content stays locked to a moving display (default)")
    ap.add_argument("--no-track", dest="track", action="store_false",
                    help="disable per-frame tracking; pin to a single fixed quad")
    args = ap.parse_args()

    W, H, fps = probe(args.clip)
    tmp = tempfile.mkdtemp(prefix="pdfscreen_")
    fdir = os.path.join(tmp, "f"); odir = os.path.join(tmp, "o")
    os.makedirs(fdir); os.makedirs(odir)
    run(["ffmpeg", "-y", "-v", "error", "-i", args.clip, os.path.join(fdir, "f%04d.png")])
    frames = sorted(glob.glob(os.path.join(fdir, "f*.png")))
    N = len(frames)

    quad = (np.float32(json.load(open(args.quad))) if args.quad
            else auto_quad(cv2.imread(frames[0])))
    print("screen quad (TL,TR,BR,BL):", quad.astype(int).tolist())

    # Planar-track the screen across frames so content stays locked to the display even as the
    # laptop drifts. Falls back to a fixed quad with --no-track. The seed quad calibrates frame 0.
    if args.track:
        quads = track_screen_quads(frames, quad)
        drift = max(float(np.abs(quads[k] - quads[0]).max()) for k in range(len(quads)))
        print(f"per-frame planar tracking ON — max corner drift tracked: {drift:.0f}px")
    else:
        quads = [quad] * N

    CW, CH = 1000, 820

    if args.mode == "video":
        if not args.screen_video:
            sys.exit("--mode video needs --screen-video")
        vdir = os.path.join(tmp, "v"); os.makedirs(vdir)
        run(["ffmpeg", "-y", "-v", "error", "-i", args.screen_video,
             "-vf", f"scale={CW}:{CH}:force_original_aspect_ratio=increase,crop={CW}:{CH},fps={fps}",
             os.path.join(vdir, "v%04d.png")])
        vframes = sorted(glob.glob(os.path.join(vdir, "v*.png")))
        content_at = lambda i: cv2.imread(vframes[i % len(vframes)])
        max_off = 0; cum = np.zeros(N)
        spans = None; total_pages = 0
    else:
        if args.chrome == "preview":
            strip, spans, total_pages = render_viewer_strip(args.pdf, args.pages, args.dpi, CW, CH)
        else:
            strip = render_pdf_strip(args.pdf, args.pages, args.dpi, CW); spans = None; total_pages = 0
        SH = strip.shape[0]; max_off = max(SH - CH, 0)
        if args.mode == "static":
            cum = np.zeros(N)
        elif args.mode == "continuous":
            t = np.linspace(0, 1, N); cum = 0.5 - 0.5 * np.cos(np.clip((t - 0.08) / 0.84, 0, 1) * np.pi)
        elif args.mode == "stepped":
            cum = np.clip(np.floor(np.linspace(0, 3, N)) / 3, 0, 1)
        else:  # handdriven
            roi = (tuple(int(v) for v in args.roi.split(",")) if args.roi
                   else (int(quad[2][0] * 0.55), int(quad[2][1]) + 5,
                         int(min(W, quad[2][0] + 120)), int(min(H, quad[2][1] + 230))))
            cum = hand_progress(frames, roi, int(args.settle * fps))
        content_at = lambda i: strip[int(cum[i] * max_off):int(cum[i] * max_off) + CH].copy()

    yy, xx = np.mgrid[0:CH, 0:CW]
    vig = np.clip(1 - 0.12 * (((xx - CW / 2) / (CW / 2)) ** 2 + ((yy - CH / 2) / (CH / 2)) ** 2), 0, 1)[..., None]
    src_rect = np.float32([[0, 0], [CW, 0], [CW, CH], [0, CH]])

    for i, fp in enumerate(frames):
        base = cv2.imread(fp).astype(np.float32)
        content = content_at(i).astype(np.float32) * vig
        content[..., 0] *= 1.03
        content = np.clip(content, 0, 255).astype(np.uint8)
        if spans is not None:
            off = int(cum[i] * max_off); center = off + CH // 2
            page_no = next((dp + 1 for (y0, y1, dp) in spans if y0 <= center < y1),
                           spans[min(range(len(spans)), key=lambda k: abs((spans[k][0] + spans[k][1]) / 2 - center))][2] + 1)
            content = draw_chrome(content, page_no, total_pages)
        # per-frame quad keeps the page locked to the (possibly moving) display plane
        Mwarp = cv2.getPerspectiveTransform(src_rect, quads[i])
        mask = cv2.GaussianBlur(cv2.warpPerspective(np.full((CH, CW), 255, np.uint8), Mwarp, (W, H)), (3, 3), 0)
        alpha = (mask.astype(np.float32) / 255)[..., None]
        warp = cv2.warpPerspective(content, Mwarp, (W, H)).astype(np.float32)
        out = (warp * alpha + base * (1 - alpha)).astype(np.uint8)
        cv2.imwrite(os.path.join(odir, f"f{i:04d}.png"), out)

    cmd = ["ffmpeg", "-y", "-v", "error", "-framerate", f"{fps}",
           "-i", os.path.join(odir, "f%04d.png")]
    if has_audio(args.clip):
        cmd += ["-i", args.clip, "-map", "0:v", "-map", "1:a"]
    cmd += ["-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "18", "-c:a", "aac", "-shortest", args.out]
    run(cmd)
    print(f"done -> {args.out}  ({N} frames, {fps:.0f}fps, mode={args.mode}, scroll_max={max_off}px)")


if __name__ == "__main__":
    main()
