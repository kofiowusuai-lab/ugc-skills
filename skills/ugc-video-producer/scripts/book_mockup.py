#!/usr/bin/env python3
"""
book_mockup.py — turn a REAL book cover into a photoreal physical hardcover anchor.

Grok cannot invent a faithful book; it will redesign the cover. So for any "hold the physical book"
shot we anchor on the book's REAL cover art and only give it physical form (3D hardback wrapped with
the exact cover). This resolves the right cover by volume, builds a leak-proof mockup prompt, and
prints the ready-to-run codex/grok commands (matching the producer's verified image-gen pattern).
It does NOT redesign the cover — keep all text/layout identical, just wrap it on a real book.

Usage:
  book_mockup.py --book "AI Mastery Vol I"            # resolves the cover, prints the gen commands
  book_mockup.py --cover /abs/cover.png --hold desk   # explicit cover + staging
  book_mockup.py --book vol2 --run-dir ~/ad_run --stage   # also copy the cover into the run dir
"""
import argparse, os, re, shutil, sys, glob

COVERS_DIR = os.path.expanduser("~/code/aimastery-salespage/covers")
# volume aliases -> cover filename
ALIASES = {
    "vol1": "ai-mastery-vol1.png", "voli": "ai-mastery-vol1.png", "vol 1": "ai-mastery-vol1.png", "volume 1": "ai-mastery-vol1.png",
    "vol2": "ai-mastery-vol2.png", "volii": "ai-mastery-vol2.png", "vol 2": "ai-mastery-vol2.png", "volume 2": "ai-mastery-vol2.png",
    "vol3": "ai-mastery-vol3.png", "voliii": "ai-mastery-vol3.png", "vol 3": "ai-mastery-vol3.png", "volume 3": "ai-mastery-vol3.png",
    "bonus": "ai-mastery-bonus.png", "workbook": "ai-mastery-bonus.png",
}


def resolve_cover(book):
    key = re.sub(r"[^a-z0-9 ]", "", book.lower()).strip()
    key_nospace = key.replace(" ", "")
    for k in (key, key_nospace):
        if k in ALIASES:
            p = os.path.join(COVERS_DIR, ALIASES[k])
            if os.path.exists(p):
                return p
    # substring match against alias keys
    for alias, fname in ALIASES.items():
        if alias.replace(" ", "") in key_nospace:
            p = os.path.join(COVERS_DIR, fname)
            if os.path.exists(p):
                return p
    # fall back: any cover whose name shares a token
    for tok in key.split():
        for p in glob.glob(os.path.join(COVERS_DIR, "*.png")):
            if tok and tok in os.path.basename(p).lower():
                return p
    return None


def mockup_prompt(stage):
    staging = {
        "hands": "held in a person's two hands at chest height, slight natural tilt toward camera",
        "desk": "standing upright on a warm wooden desk beside a laptop, soft window light from the left",
        "stack": "the front book standing, two more copies stacked behind it, on a clean surface",
    }.get(stage, "held in a person's hands")
    return (
        "Photorealistic product photo of a physical HARDBACK book. The front cover is EXACTLY the "
        "provided cover image, wrapped onto a real 3D hardcover with realistic thickness, visible spine "
        "and page edges, subtle paper texture and soft studio reflections. "
        f"The book is {staging}. "
        "DO NOT redesign, restyle, recolor, or re-typeset the cover — keep every word, logo, and layout "
        "element identical to the provided image. No added text, no watermark, no border. "
        "Realistic depth of field, natural lighting, shot on a phone camera."
    )


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--book", help="book/volume name or alias (vol1/vol2/vol3/bonus)")
    ap.add_argument("--cover", help="explicit path to the real cover PNG")
    ap.add_argument("--hold", "--stage", dest="stage", default="hands", choices=["hands", "desk", "stack"])
    ap.add_argument("--out", default="hardcover_mockup.png")
    ap.add_argument("--run-dir", default="")
    ap.add_argument("--stage-cover", action="store_true", help="copy the resolved cover into the run dir")
    args = ap.parse_args()

    cover = args.cover or (resolve_cover(args.book) if args.book else None)
    if not cover or not os.path.exists(cover):
        print(f"ERROR: could not resolve a real cover (book={args.book!r}, cover={args.cover!r}).", file=sys.stderr)
        print(f"Available covers in {COVERS_DIR}:", file=sys.stderr)
        for p in sorted(glob.glob(os.path.join(COVERS_DIR, '*.png'))):
            print("  " + p, file=sys.stderr)
        return 2

    out = args.out
    if args.run_dir:
        os.makedirs(os.path.expanduser(args.run_dir), exist_ok=True)
        out = os.path.join(os.path.expanduser(args.run_dir), os.path.basename(out))
        if args.stage_cover:
            staged = os.path.join(os.path.expanduser(args.run_dir), os.path.basename(cover))
            shutil.copy(cover, staged)
            cover = staged

    prompt = mockup_prompt(args.stage)
    print(f"REAL_COVER: {cover}")
    print(f"OUT:        {out}")
    print(f"STAGE:      {args.stage}\n")
    print("# --- Generate the hardcover mockup (verified producer pattern) ---")
    print("# Codex (preferred; -i is variadic so the prompt goes via stdin with a trailing '-'):")
    print(f'echo {shell_quote(prompt)} | codex exec --skip-git-repo-check -s workspace-write -i {shell_quote(cover)} -')
    print("\n# Grok fallback (if Codex is usage-limited):")
    grok_inner = 'Call image_edit image="%s" prompt="%s"' % (cover, prompt)
    print("grok -p %s --always-approve" % shell_quote(grok_inner))
    print("\n# Then use the mockup as the physical anchor: image_edit it into the avatar still, OR")
    print("# reference_to_video with the mockup + the staged character keyframe (keeps cover faithful).")
    return 0


def shell_quote(s):
    return "'" + s.replace("'", "'\\''") + "'"


if __name__ == "__main__":
    sys.exit(main())
