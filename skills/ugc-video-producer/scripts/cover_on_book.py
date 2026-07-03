#!/usr/bin/env python3
"""
cover_on_book.py — pin a REAL, STATIC book cover onto a held book in a video.

Why this exists: when you animate a book whose cover depicts a SCENE (e.g. a money
printer printing cash), Grok's image_to_video animates the printed artwork — the cover
appears to move, which is wrong (a printed cover is static ink on paper). The fix mirrors
the device-screen trick: animate the book held with a BLANK cover + locked camera, then
warp the real flat cover image onto the book's front-face quad for every frame.

Unlike pdf_screen.py (which builds a tall scrollable strip and shows a window — it cuts
off the bottom of a one-page cover), this warps the ENTIRE cover image onto the quad so
the whole cover shows, perfectly static. Fingers/edges OUTSIDE the quad are preserved
(set the quad to the bare front face, between the gripping fingers).

Usage:
  cover_on_book.py --clip blank_book.mp4 --cover cover.png \
      --quad '[[112,150],[648,132],[635,1050],[122,1015]]' --out out.mp4 [--audio voiced.mp4]
  # --quad is TL,TR,BR,BL in the clip's native pixel space; or a path to a JSON file.
"""
import argparse, json, os, subprocess, sys, tempfile, glob
import numpy as np
import cv2


def probe_fps(clip):
    out = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0",
                          "-show_entries", "stream=r_frame_rate", "-of", "csv=p=0", clip],
                         capture_output=True, text=True).stdout.strip()
    num, den = (out.split("/") + ["1"])[:2]
    return float(num) / float(den or 1)


def has_audio(clip):
    out = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "a",
                          "-show_entries", "stream=index", "-of", "csv=p=0", clip],
                         capture_output=True, text=True).stdout.strip()
    return bool(out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--clip", required=True, help="video of the book held with a BLANK cover, locked camera")
    ap.add_argument("--cover", required=True, help="real flat cover image (png/jpg)")
    ap.add_argument("--quad", required=True, help="TL,TR,BR,BL in clip pixels — inline JSON or a .json path")
    ap.add_argument("--out", required=True)
    ap.add_argument("--audio", help="clip to take the audio track from (default: the input clip's own audio)")
    ap.add_argument("--feather", type=int, default=3, help="mask edge feather in px")
    args = ap.parse_args()

    quad = np.float32(json.load(open(args.quad)) if os.path.exists(args.quad) else json.loads(args.quad))
    cover = cv2.imread(args.cover, cv2.IMREAD_COLOR)
    if cover is None:
        sys.exit(f"could not read cover {args.cover}")
    ch, cw = cover.shape[:2]
    src = np.float32([[0, 0], [cw, 0], [cw, ch], [0, ch]])
    M = cv2.getPerspectiveTransform(src, quad)

    fps = probe_fps(args.clip)
    work = tempfile.mkdtemp()
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", args.clip,
                    os.path.join(work, "f%05d.png")], check=True)
    frames = sorted(glob.glob(os.path.join(work, "f*.png")))
    if not frames:
        sys.exit("no frames extracted")
    H, W = cv2.imread(frames[0]).shape[:2]

    # static warp + feathered mask, reused for every frame
    warped = cv2.warpPerspective(cover, M, (W, H))
    mask = np.zeros((H, W), np.uint8)
    cv2.fillConvexPoly(mask, quad.astype(np.int32), 255)
    if args.feather > 0:
        k = args.feather * 2 + 1
        mask = cv2.GaussianBlur(mask, (k, k), 0)
    alpha = (mask.astype(np.float32) / 255.0)[..., None]

    outdir = os.path.join(work, "out")
    os.makedirs(outdir)
    for i, fp in enumerate(frames):
        frame = cv2.imread(fp).astype(np.float32)
        comp = frame * (1 - alpha) + warped.astype(np.float32) * alpha
        cv2.imwrite(os.path.join(outdir, f"o{i:05d}.png"), comp.astype(np.uint8))

    audio_src = args.audio or args.clip
    tmp_video = os.path.join(work, "video.mp4")
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-framerate", str(fps),
                    "-i", os.path.join(outdir, "o%05d.png"),
                    "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "18", tmp_video], check=True)
    if has_audio(audio_src):
        # -map 0:V:0 dodges Grok's embedded mjpeg cover stream (see QA Bank D3)
        subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", tmp_video, "-i", audio_src,
                        "-map", "0:v:0", "-map", "1:a:0", "-c:v", "copy", "-c:a", "aac",
                        "-shortest", args.out], check=True)
    else:
        subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", tmp_video, "-c", "copy", args.out], check=True)
    print(f"done -> {args.out} ({len(frames)} frames, quad pinned, full cover static)")


if __name__ == "__main__":
    main()
