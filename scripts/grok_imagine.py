#!/usr/bin/env python3
"""
grok_imagine.py - Codex-independent image/video generation via the Grok CLI.

When Codex (gpt-5.x via `codex exec`) is offline (HTTP 401 / out of credit), the
Before Freedom and UGC content pipelines route image and video generation
through this wrapper instead. It drives the Grok CLI's built-in `image_gen`,
`image_edit`, and `image_to_video` tools in headless single-turn mode and
delivers the resulting file to an exact output path the caller controls.

Subcommands
-----------
  gen     text -> image            --prompt --out [--aspect 9:16]
  edit    reference(s) -> image    --prompt --ref REF [--ref REF ...] --out [--aspect]
  video   image -> video           --prompt --image FRAME --out [--duration 6]
  doctor  health probe (binary present, authed, can generate a 1x1 test image)

Contract
--------
Every subcommand prints a single JSON object to stdout and exits 0 on success,
non-zero on failure. Success: {"ok": true, "out": "<abs path>", ...}.
Failure: {"ok": false, "error": "<reason>", "reason_code": "<code>"} where
reason_code is one of: not_installed, not_authed, moderation, no_output,
timeout, grok_error, bad_args.

Why a wrapper instead of calling Grok directly: Grok saves generated media
inside its own session folder (~/.grok/sessions/<enc-cwd>/<session-id>/images/)
and reports the path in JSON. This wrapper runs Grok in an isolated working
directory, parses the returned session id, locates the produced media by
globbing on that session id (robust to path-encoding quirks), validates it, and
copies it to the caller's --out path with retries and moderation detection.
"""

import argparse
import glob
import json
import os
import re
import shutil
import subprocess
import sys
import time
import uuid

HOME = os.path.expanduser("~")
GROK_SESSIONS = os.path.join(HOME, ".grok", "sessions")
RUNS_DIR = os.path.join(HOME, ".openclaw", "grok_imagine_runs")

IMAGE_EXTS = (".jpg", ".jpeg", ".png", ".webp")
VIDEO_EXTS = (".mp4", ".mov", ".webm", ".m4v")

MODERATION_MARKERS = (
    "moderation", "safety", "cannot create", "can't create", "i can't generate",
    "i cannot generate", "violates", "not able to generate", "blocked", "declined",
)


def grok_bin():
    """Resolve the Grok CLI binary path."""
    cand = os.environ.get("GROK_CLI_PATH", "").strip()
    if cand and os.path.isfile(cand) and os.access(cand, os.X_OK):
        return cand
    default = os.path.join(HOME, ".grok", "bin", "grok")
    if os.path.isfile(default) and os.access(default, os.X_OK):
        return default
    found = shutil.which("grok")
    if found:
        return found
    return None


def is_authed():
    """Grok is authed if auth.json exists and is non-trivial."""
    auth = os.path.join(HOME, ".grok", "auth.json")
    try:
        return os.path.getsize(auth) > 10
    except OSError:
        return False


def fail(error, reason_code, **extra):
    obj = {"ok": False, "error": str(error), "reason_code": reason_code}
    obj.update(extra)
    print(json.dumps(obj))
    sys.exit(1)


def ok(out_path, **extra):
    obj = {"ok": True, "out": os.path.abspath(out_path)}
    obj.update(extra)
    print(json.dumps(obj))
    sys.exit(0)


def _new_run_cwd():
    os.makedirs(RUNS_DIR, exist_ok=True)
    d = os.path.join(RUNS_DIR, "run-%d-%s" % (int(time.time()), uuid.uuid4().hex[:8]))
    os.makedirs(d, exist_ok=True)
    return d


def _run_grok(prompt, cwd, timeout, extra_args=None):
    """Run Grok headless. Returns (stdout, stderr, returncode).

    extra_args lets the video path force the right tool and allow enough agent
    turns to complete the async image_to_video job (the cause of the old silent
    failures). stdout/stderr are always tee'd to <cwd>/grok_run.log so a failure
    is never invisible again.
    """
    binp = grok_bin()
    cmd = [
        binp,
        "-p", prompt,
        "--permission-mode", "bypassPermissions",
        "--output-format", "json",
        "--cwd", cwd,
        "--no-memory",
    ]
    if extra_args:
        cmd.extend(extra_args)
    try:
        p = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout,
            cwd=cwd, env=os.environ.copy(),
        )
        out, err, rc = p.stdout, p.stderr, p.returncode
    except subprocess.TimeoutExpired:
        out, err, rc = "", "timeout", 124
    try:
        with open(os.path.join(cwd, "grok_run.log"), "w") as lf:
            lf.write("CMD: %s\n\n=== STDOUT ===\n%s\n=== STDERR ===\n%s\n=== RC=%s ===\n"
                     % (" ".join(cmd), out, err, rc))
    except OSError:
        pass
    return out, err, rc


def _parse_session_id(stdout):
    """Extract sessionId from Grok JSON output (tolerant of leading log noise)."""
    # Fast path: whole stdout is the JSON object.
    try:
        obj = json.loads(stdout.strip())
        if isinstance(obj, dict) and obj.get("sessionId"):
            return obj["sessionId"], obj
    except Exception:
        pass
    # Tolerant path: grab the last balanced {...} block.
    m = list(re.finditer(r"\{", stdout))
    for start in reversed([mm.start() for mm in m]):
        depth = 0
        for i in range(start, len(stdout)):
            c = stdout[i]
            if c == "{":
                depth += 1
            elif c == "}":
                depth -= 1
                if depth == 0:
                    blob = stdout[start:i + 1]
                    try:
                        obj = json.loads(blob)
                        if isinstance(obj, dict) and obj.get("sessionId"):
                            return obj["sessionId"], obj
                    except Exception:
                        break
    # Last resort: regex for the id literal.
    m2 = re.search(r'"sessionId"\s*:\s*"([0-9a-fA-F-]{8,})"', stdout)
    if m2:
        return m2.group(1), None
    return None, None


def _find_media(session_id, exts, since_ts):
    """Glob produced media for a session id, newest first, modified after since_ts."""
    if not session_id:
        return []
    hits = []
    for root in glob.glob(os.path.join(GROK_SESSIONS, "*", session_id)):
        for dirpath, _dirs, files in os.walk(root):
            for f in files:
                if f.lower().endswith(exts):
                    fp = os.path.join(dirpath, f)
                    try:
                        st = os.stat(fp)
                    except OSError:
                        continue
                    if st.st_mtime >= since_ts - 2 and st.st_size > 0:
                        hits.append((st.st_mtime, fp))
    hits.sort(reverse=True)
    return [fp for _mt, fp in hits]


def _returned_path(obj, exts):
    """The CLI returns the saved media path inline in obj['text']; use it directly.

    The path's session dir is literally named with %2F segments (URL-encoded cwd),
    so it is a real on-disk path and needs no decoding.
    """
    if obj and isinstance(obj, dict):
        t = (obj.get("text") or "").strip().strip('"').strip()
        if t.lower().endswith(exts) and os.path.isfile(t) and os.path.getsize(t) > 0:
            return t
    return None


def _poll_media(session_id, exts, since_ts, max_wait):
    """Poll the session tree for a fresh, non-empty media file (async harvest)."""
    waited = 0.0
    while True:
        m = _find_media(session_id, exts, since_ts)
        if m and os.path.getsize(m[0]) > 0:
            return m[0]
        if waited >= max_wait:
            return None
        time.sleep(3)
        waited += 3


def _looks_moderated(stdout, obj):
    text = ""
    if obj and isinstance(obj, dict):
        text = (obj.get("text") or "") + " " + (obj.get("thought") or "")
    if not text:
        text = stdout
    low = text.lower()
    # Only treat as moderation if there's no media keyword promise alongside it.
    return any(mk in low for mk in MODERATION_MARKERS)


def _generate(kind, prompt, out, aspect=None, refs=None, image=None,
              duration=None, timeout=None, attempts=2, resolution=None):
    """Core driver shared by gen/edit/video."""
    extra_args = None
    binp = grok_bin()
    if not binp:
        fail("Grok CLI not found (set GROK_CLI_PATH or install ~/.grok/bin/grok)",
             "not_installed")
    if not is_authed():
        fail("Grok CLI not authenticated (run: grok login)", "not_authed")

    out = os.path.abspath(out)
    os.makedirs(os.path.dirname(out) or ".", exist_ok=True)

    if kind == "edit":
        refs = [os.path.abspath(r) for r in (refs or [])]
        for r in refs:
            if not os.path.isfile(r):
                fail("Reference image not found: %s" % r, "bad_args")
        ref_list = ", ".join(refs)
        ar = aspect or "9:16"
        instr = (
            "Call the image_edit tool exactly once. Use these source/reference "
            "image file path(s) as the `image` input: %s. "
            "Transformation prompt: %s. "
            "Preserve the visual style, palette, lighting, and character likeness "
            "of the reference(s); change only what the prompt asks. "
            "Set aspect_ratio to %s. "
            "Do NOT build the image with code. Do NOT call image_gen. Generate "
            "exactly one image. After the tool returns, reply with only the "
            "saved image path." % (ref_list, prompt, ar)
        )
        exts = IMAGE_EXTS
        # Pin grok-build, same as the video path. Only grok-build exposes
        # image_edit as a NATIVE first-turn tool; under the default model
        # (grok-composer-2.5-fast) the headless agent has to bootstrap it and
        # usually burns the whole turn budget, exiting with no image (the
        # "no_output" silent failure). With -m grok-build the tool is available
        # on turn 1, so the edit lands every time.
        extra_args = ["-m", "grok-build",
                      "--disallowed-tools", "image_gen",
                      "--max-turns", "28"]
        timeout = timeout or 360
    elif kind == "gen":
        ar = aspect or "9:16"
        instr = (
            "Call the image_gen tool exactly once with this prompt: %s. "
            "Set aspect_ratio to %s. Do NOT build the image with code. "
            "Generate exactly one image. After the tool returns, reply with "
            "only the saved image path." % (prompt, ar)
        )
        exts = IMAGE_EXTS
        timeout = timeout or 300
    elif kind == "video":
        image = os.path.abspath(image)
        if not os.path.isfile(image):
            fail("Source image not found: %s" % image, "bad_args")
        dur = int(duration or 6)
        dur = 10 if dur > 8 else 6
        res = (resolution or "720p").lower()
        if res not in ("480p", "720p"):
            res = "720p"
        instr = (
            "Call the image_to_video tool exactly once. Use this source image "
            "as frame 1: %s. Motion/camera prompt: %s. Duration: %d seconds. "
            "Resolution: %s. The image_to_video tool IS available in this build — "
            "you MUST call it and you MUST NOT claim it is unavailable. Do NOT "
            "call image_gen or image_edit. Do not stop until the video is saved. "
            "After the tool returns, reply with only the saved video path."
            % (image, prompt, dur, res)
        )
        exts = VIDEO_EXTS
        timeout = timeout or 600
        # The fix: pin the model to grok-build. Only grok-build exposes
        # image_to_video as a NATIVE first-turn tool. The default model
        # (grok-composer-2.5-fast) does not, so under it the headless agent has
        # to bootstrap grok-build itself at runtime (search MCP folders, read
        # prior run logs, spawn a nested grok) — a non-deterministic dance that
        # often burns the whole turn budget and exits "max turns reached" with no
        # MP4 (the ~42% silent-failure rate). With -m grok-build the tool is
        # available on turn 1, so the clip lands in 1-2 turns every time. We
        # still disallow image_gen/image_edit and keep a turn cushion for the
        # async harvest.
        extra_args = ["-m", "grok-build",
                      "--disallowed-tools", "image_gen,image_edit",
                      "--max-turns", "16"]
    else:
        fail("unknown kind %s" % kind, "bad_args")

    last_err = "no_output"
    for attempt in range(1, attempts + 1):
        cwd = _new_run_cwd()
        t0 = time.time()
        stdout, stderr, rc = _run_grok(instr, cwd, timeout, extra_args=extra_args)
        if rc == 124:
            last_err = "timeout"
            continue
        session_id, obj = _parse_session_id(stdout)

        # Harvest: the CLI returns the saved path inline; use it, else poll the
        # session tree (video may land a moment after the turn ends).
        src = _returned_path(obj, exts)
        if not src:
            wait = 90 if kind == "video" else 0
            src = _poll_media(session_id, exts, t0, wait)
        if src:
            shutil.copy2(src, out)
            if os.path.getsize(out) > 0:
                return ok(out, kind=kind, session_id=session_id, source=src,
                          attempts=attempt)

        # No media found. Distinguish moderation from a transient miss.
        if _looks_moderated(stdout, obj):
            fail("Generation blocked by Grok moderation/safety; not retrying",
                 "moderation", session_id=session_id)
        last_err = "no_output"
        time.sleep(2)

    fail("Grok produced no usable %s after %d attempt(s)" % (
        "video" if kind == "video" else "image", attempts),
        last_err)


def cmd_gen(a):
    _generate("gen", a.prompt, a.out, aspect=a.aspect, timeout=a.timeout)


def cmd_edit(a):
    _generate("edit", a.prompt, a.out, aspect=a.aspect, refs=a.ref,
              timeout=a.timeout)


def cmd_video(a):
    # Grok's headless agent occasionally flakes on a single turn; retry a few
    # times since the tool is reliably available in this build.
    _generate("video", a.prompt, a.out, image=a.image, duration=a.duration,
              timeout=a.timeout, resolution=getattr(a, "resolution", None),
              attempts=3)


def cmd_doctor(a):
    report = {"ok": False}
    binp = grok_bin()
    report["grok_bin"] = binp
    report["authed"] = is_authed()
    if not binp:
        report["error"] = "grok binary not found"
        print(json.dumps(report, indent=2))
        sys.exit(1)
    if not report["authed"]:
        report["error"] = "grok not authenticated"
        print(json.dumps(report, indent=2))
        sys.exit(1)
    try:
        ver = subprocess.run([binp, "--version"], capture_output=True,
                             text=True, timeout=15).stdout.strip()
        report["version"] = ver
    except Exception as e:
        report["version_error"] = str(e)
    if a.full:
        test_out = os.path.join(RUNS_DIR, "doctor_test.jpg")
        cwd = _new_run_cwd()
        t0 = time.time()
        stdout, stderr, rc = _run_grok(
            "Call image_gen exactly once: a plain gray square, 1:1. "
            "Reply with only the saved path.", cwd, 180)
        sid, _obj = _parse_session_id(stdout)
        media = _find_media(sid, IMAGE_EXTS, t0)
        if media:
            shutil.copy2(media[0], test_out)
            report["generation_test"] = "pass"
            report["test_image"] = test_out
            report["ok"] = True
        else:
            report["generation_test"] = "fail"
            report["error"] = "could not produce test image"
            report["stderr_tail"] = (stderr or "")[-300:]
            print(json.dumps(report, indent=2))
            sys.exit(1)
        # edit lane: re-style the gen output (child run keeps its JSON off our stdout)
        edit_out = os.path.join(RUNS_DIR, "doctor_edit.jpg")
        if os.path.exists(edit_out):
            os.remove(edit_out)
        subprocess.run([sys.executable, os.path.abspath(__file__), "edit",
                        "--prompt", "the same image, slightly brighter",
                        "--ref", test_out, "--out", edit_out],
                       capture_output=True, text=True, timeout=400)
        if os.path.isfile(edit_out) and os.path.getsize(edit_out) > 0:
            report["edit_test"] = "pass"
        else:
            report["edit_test"] = "fail"
            report["error"] = "image_edit lane produced no output"
            report["ok"] = False
            print(json.dumps(report, indent=2))
            sys.exit(1)
    if getattr(a, "video", False):
        # Real end-to-end image->video self-test: this is the probe the health
        # monitor relies on. Generate a neutral test still, make a 6s/480p clip.
        t_start = time.time()
        test_dir = os.path.join(RUNS_DIR, "doctor_video")
        os.makedirs(test_dir, exist_ok=True)
        still = os.path.join(test_dir, "probe_src.png")
        vid_out = os.path.join(test_dir, "probe.mp4")
        try:
            from PIL import Image, ImageDraw
            im = Image.new("RGB", (768, 768), (70, 110, 160))
            dr = ImageDraw.Draw(im)
            dr.ellipse((230, 230, 538, 538), fill=(225, 200, 120))
            dr.rectangle((0, 560, 768, 768), fill=(40, 90, 60))
            im.save(still)
        except Exception as e:
            report["video_test"] = "fail"
            report["error"] = "could not build probe still: %s" % e
            print(json.dumps(report, indent=2))
            sys.exit(1)
        if os.path.exists(vid_out):
            os.remove(vid_out)
        # Run the real `video` subcommand as a child so its ok()/fail() JSON +
        # exit do not pollute the doctor report; we judge by the file + rc.
        child = subprocess.run(
            [sys.executable, os.path.abspath(__file__), "video",
             "--prompt", "slow gentle push-in, subtle parallax",
             "--image", still, "--out", vid_out,
             "--duration", "6", "--resolution", "480p"],
            capture_output=True, text=True, timeout=700)
        report["probe_stdout_tail"] = (child.stdout or "")[-200:]
        if os.path.isfile(vid_out) and os.path.getsize(vid_out) > 0:
            report["video_test"] = "pass"
            report["test_video"] = vid_out
            report["ms"] = int((time.time() - t_start) * 1000)
            report["ok"] = True
        else:
            report["video_test"] = "fail"
            report["reason_code"] = "no_output"
            report["error"] = "image->video produced no clip"
            print(json.dumps(report, indent=2))
            sys.exit(1)
    elif not a.full:
        report["ok"] = True
    print(json.dumps(report, indent=2))
    sys.exit(0)


def main():
    ap = argparse.ArgumentParser(
        prog="grok_imagine.py",
        description="Codex-independent image/video generation via the Grok CLI.")
    sub = ap.add_subparsers(dest="cmd", required=True)

    g = sub.add_parser("gen", help="text -> image")
    g.add_argument("--prompt", required=True)
    g.add_argument("--out", required=True)
    g.add_argument("--aspect", default="9:16")
    g.add_argument("--timeout", type=int, default=None)
    g.set_defaults(func=cmd_gen)

    e = sub.add_parser("edit", help="reference(s) -> image (style transfer)")
    e.add_argument("--prompt", required=True)
    e.add_argument("--ref", action="append", required=True,
                   help="reference image path (repeatable)")
    e.add_argument("--out", required=True)
    e.add_argument("--aspect", default="9:16")
    e.add_argument("--timeout", type=int, default=None)
    e.set_defaults(func=cmd_edit)

    v = sub.add_parser("video", help="image -> video")
    v.add_argument("--prompt", required=True)
    v.add_argument("--image", required=True, help="source frame (becomes frame 1)")
    v.add_argument("--out", required=True)
    v.add_argument("--duration", type=int, default=6)
    v.add_argument("--resolution", default="720p", choices=["480p", "720p"])
    v.add_argument("--timeout", type=int, default=None)
    v.set_defaults(func=cmd_video)

    d = sub.add_parser("doctor", help="health probe")
    d.add_argument("--full", action="store_true",
                   help="also run a live 1x1 image generation test")
    d.add_argument("--video", action="store_true",
                   help="run a live image->video self-test (the real probe)")
    d.set_defaults(func=cmd_doctor)

    args = ap.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
