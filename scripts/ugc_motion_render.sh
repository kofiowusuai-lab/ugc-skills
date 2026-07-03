#!/usr/bin/env bash
# ugc_motion_render.sh
# -----------------------------------------------------------------------------
# Add the full MOTION-GRAPHICS layer to a finished avatar video: kinetic captions
# (whisper word-timed), brand lower-third, keyword pops — rendered with Remotion.
# This is the YouTube-creator polish stage that runs AFTER the avatar clips are
# stitched (e.g. the output of ugc_video_from_image.sh / ugc_claude_deliver.sh).
#
# USAGE
#   ugc_motion_render.sh --video AVATAR.mp4 --out FINAL.mp4 \
#       [--keywords "comma,separated"] [--brand-title "NAME"] [--handle "@x"] \
#       [--accent "#7CF5C4"] [--no-captions] [--model base.en]
#
# Prints {"ok":true,"out":...} or {"ok":false,"error":...}.
# -----------------------------------------------------------------------------
set -uo pipefail
MG="$HOME/.openclaw/motion-graphics"
SCRIPTS="$HOME/.openclaw/scripts"
VIDEO="" OUT="" KEYWORDS="" BTITLE="" HANDLE="" ACCENT="#7CF5C4" CAPS=1 MODEL="base.en" BROLL=0 STUDIO=0 HEADLINES="" MATTE_MAXSIDE=720
# python interpreter for the matte step (onnxruntime lives on python3.14 here)
MATTE_PY="/opt/homebrew/bin/python3.14"; [[ -x "$MATTE_PY" ]] || MATTE_PY="python3"
while [[ $# -gt 0 ]]; do case "$1" in
  --video) VIDEO="$2"; shift 2;; --out) OUT="$2"; shift 2;;
  --keywords) KEYWORDS="$2"; shift 2;; --brand-title) BTITLE="$2"; shift 2;;
  --handle) HANDLE="$2"; shift 2;; --accent) ACCENT="$2"; shift 2;;
  --no-captions) CAPS=0; shift;; --model) MODEL="$2"; shift 2;;
  --broll) BROLL=1; shift;;
  --studio) STUDIO=1; shift;;
  --headlines) HEADLINES="$2"; shift 2;;
  --matte-maxside) MATTE_MAXSIDE="$2"; shift 2;;
  -h|--help) sed -n '2,18p' "$0"; exit 0;; *) echo "unknown arg: $1" >&2; exit 2;; esac; done
# b-roll cutaways need word timings to plan against — force captions/transcription on.
[[ "$BROLL" -eq 1 ]] && CAPS=1
# studio mode needs word timings for in-time captions too.
[[ "$STUDIO" -eq 1 ]] && CAPS=1

[[ -z "$VIDEO" || -z "$OUT" ]] && { echo "ERROR: --video and --out required" >&2; exit 2; }
[[ ! -f "$VIDEO" ]] && { echo "ERROR: video not found: $VIDEO" >&2; exit 2; }
[[ ! -x "$MG/node_modules/.bin/remotion" ]] && { echo "ERROR: Remotion not installed at $MG" >&2; exit 2; }
VIDEO="$(cd "$(dirname "$VIDEO")" && pwd)/$(basename "$VIDEO")"
OUT="$(cd "$(dirname "$OUT")" 2>/dev/null && pwd || echo .)/$(basename "$OUT")"

# orientation + duration
W=$(ffprobe -v error -select_streams v:0 -show_entries stream=width -of csv=p=0 "$VIDEO" 2>/dev/null)
H=$(ffprobe -v error -select_streams v:0 -show_entries stream=height -of csv=p=0 "$VIDEO" 2>/dev/null)
DUR=$(ffprobe -v error -show_entries format=duration -of default=noprint_wrappers=1:nokey=1 "$VIDEO" 2>/dev/null)
if [[ -n "$H" && -n "$W" && "$H" -ge "$W" ]]; then OW=1080; OH=1920; else OW=1920; OH=1080; fi

mkdir -p "$MG/public" "$MG/out"
STAMP="mg_$(date +%s)_$$"
PUBVID="$MG/public/${STAMP}.mp4"
cp "$VIDEO" "$PUBVID"

# captions (whisper word timings) unless disabled
WORDS_JSON="$MG/public/${STAMP}_words.json"
if [[ "$CAPS" -eq 1 ]]; then
  echo "[motion-render] transcribing for captions..." >&2
  python3 "$SCRIPTS/ugc_captions.py" --video "$VIDEO" --out "$WORDS_JSON" --model "$MODEL" >/tmp/${STAMP}_cap.json 2>&1 \
    || echo "[motion-render] caption step failed; rendering without captions" >&2
fi

# b-roll cutaway timeline (Claude plans which spans become full-screen graphics)
SEGS_JSON="$MG/public/${STAMP}_segments.json"
SFX_JSON="$MG/public/${STAMP}_sfx.json"
COMP="MotionVideo"
if [[ "$BROLL" -eq 1 ]]; then
  if [[ -f "$WORDS_JSON" ]]; then
    echo "[motion-render] planning b-roll cutaways..." >&2
    "$SCRIPTS/ugc_broll_plan.sh" --words "$WORDS_JSON" --out "$SEGS_JSON" >/tmp/${STAMP}_plan.json 2>&1 || echo "[]" > "$SEGS_JSON"
    COMP="BrollVideo"
    # ensure the SFX pack exists (idempotent), then generate b-roll images + build SFX events
    python3 "$SCRIPTS/ugc_sfx_pack.py" >/dev/null 2>&1 || true
    echo "[motion-render] generating b-roll images + placing SFX..." >&2
    MG="$MG" STAMP="$STAMP" SEGS_JSON="$SEGS_JSON" SFX_JSON="$SFX_JSON" OW="$OW" OH="$OH" \
    GROK_IMAGINE="$SCRIPTS/grok_imagine.py" python3 - <<'PY'
import os, json, subprocess
MG=os.environ["MG"]; STAMP=os.environ["STAMP"]
segs_path=os.environ["SEGS_JSON"]
try: segs=json.load(open(segs_path))
except Exception: segs=[]
aspect="9:16" if int(os.environ["OH"])>=int(os.environ["OW"]) else "16:9"
sfxdir_rel="sfx"  # public/sfx
def has(n): return os.path.exists(os.path.join(MG,"public","sfx",n+".mp3"))
# 1) generate images for image-kind segments via grok_imagine.py gen
for i,s in enumerate(segs):
    if s.get("kind")=="image":
        pl=s.get("payload",{})
        prompt=pl.get("image_prompt") or pl.get("text") or "cinematic b-roll, photoreal"
        outname=f"{STAMP}_img{i}.png"; outpath=os.path.join(MG,"public",outname)
        try:
            r=subprocess.run(["python3",os.environ["GROK_IMAGINE"],"gen","--prompt",prompt,
                              "--out",outpath,"--aspect",aspect],capture_output=True,text=True,timeout=300)
            if os.path.exists(outpath) and os.path.getsize(outpath)>5000:
                pl["imageSrc"]=outname
            else:
                s["kind"]="kinetic"; pl.setdefault("text", pl.get("text") or "")  # fallback to typography
        except Exception:
            s["kind"]="kinetic"
        s["payload"]=pl
json.dump(segs,open(segs_path,"w"))
# 2) build SFX events (default mapping by kind)
sfx=[]
def ev(name,at,vol):
    if has(name) and at is not None and at>=0:
        sfx.append({"src":f"{sfxdir_rel}/{name}.mp3","at":round(at,2),"volume":vol})
for s in segs:
    st=float(s.get("start",0)); en=float(s.get("end",st)); k=s.get("kind")
    if k=="stat":
        ev("riser", st-0.9, 0.5); ev("impact", st, 0.85)
    elif k=="quote":
        ev("riser", st-0.9, 0.5); ev("drop", st, 0.7)
    else:  # kinetic / image
        ev("whoosh", st, 0.6)
    ev("swoosh", en-0.12, 0.4)
json.dump(sfx,open(os.environ["SFX_JSON"],"w"))
print("segments:",len(segs),"sfx_events:",len(sfx))
PY
  else
    echo "[motion-render] --broll needs captions/transcription, but none was produced; falling back to overlay mode" >&2
  fi
fi

# studio mode: build a PERSON-ONLY alpha matte so the avatar occludes the text.
MATTE_NAME=""
if [[ "$STUDIO" -eq 1 ]]; then
  COMP="StudioVideo"
  MATTE_NAME="${STAMP}_matte.mov"
  MATTE_OUT="$MG/public/${MATTE_NAME}"
  echo "[motion-render] generating person matte (this is the slow step on M2)..." >&2
  "$MATTE_PY" "$SCRIPTS/ugc_matte.py" --video "$VIDEO" --out "$MATTE_OUT" \
      --max-side "$MATTE_MAXSIDE" >/tmp/${STAMP}_matte.json 2>/tmp/${STAMP}_matte.log
  if [[ ! -f "$MATTE_OUT" ]]; then
    echo "[motion-render] matte failed; studio render will run without behind-avatar occlusion" >&2
    tail -3 /tmp/${STAMP}_matte.log >&2 2>/dev/null
    MATTE_NAME=""
  fi
fi

# build props.json
PROPS="$MG/public/${STAMP}_props.json"
WORDS_JSON="$WORDS_JSON" SEGS_JSON="$SEGS_JSON" SFX_JSON="$SFX_JSON" PROPS="$PROPS" STAMP="$STAMP" DUR="${DUR:-0}" OW="$OW" OH="$OH" \
KEYWORDS="$KEYWORDS" BTITLE="$BTITLE" HANDLE="$HANDLE" ACCENT="$ACCENT" CAPS="$CAPS" COMP="$COMP" \
MATTE_NAME="$MATTE_NAME" HEADLINES="$HEADLINES" python3 - <<'PY'
import os, json
words=[]
wj=os.environ["WORDS_JSON"]
if os.environ["CAPS"]=="1" and os.path.exists(wj):
    try: words=json.load(open(wj))
    except Exception: words=[]
segs=[]; sfx=[]
comp=os.environ["COMP"]
sj=os.environ["SEGS_JSON"]; xj=os.environ["SFX_JSON"]
if comp in ("BrollVideo","StudioVideo") and os.path.exists(sj):
    try: segs=json.load(open(sj))
    except Exception: segs=[]
    if os.path.exists(xj):
        try: sfx=json.load(open(xj))
        except Exception: sfx=[]
kw=[k.strip() for k in os.environ["KEYWORDS"].split(",") if k.strip()]
props={
  "videoSrc": os.environ["STAMP"]+".mp4",
  "words": words,
  "keywords": kw,
  "brand": {"title": os.environ["BTITLE"] or None, "handle": os.environ["HANDLE"] or None,
            "accent": os.environ["ACCENT"]},
  "showCaptions": os.environ["CAPS"]=="1" and bool(words),
  "width": int(os.environ["OW"]), "height": int(os.environ["OH"]),
  "durationInSeconds": float(os.environ["DUR"]) or None,
}
if comp=="BrollVideo":
    props["segments"]=segs
    props["sfx"]=sfx
if comp=="StudioVideo":
    mn=os.environ.get("MATTE_NAME","")
    if mn: props["matteSrc"]=mn
    hl=[h.strip() for h in os.environ.get("HEADLINES","").split(",") if h.strip()]
    if not hl: hl=[k.upper() for k in kw]
    props["headlines"]=hl
    props["segments"]=segs
    props["sfx"]=sfx
json.dump(props, open(os.environ["PROPS"],"w"))
print("words:",len(words),"segments:",len(segs),"sfx:",len(sfx),"dur:",props["durationInSeconds"])
PY

echo "[motion-render] rendering Remotion $COMP (${OW}x${OH}, ${DUR}s)..." >&2
( cd "$MG" && ./node_modules/.bin/remotion render src/index.ts "$COMP" "$OUT" \
    --props="$PROPS" --log=error ) >/tmp/${STAMP}_render.log 2>&1
RC=$?

# cleanup public copies (keep the cached sfx pack)
rm -f "$PUBVID" "$WORDS_JSON" "$PROPS" "$SEGS_JSON" "$SFX_JSON" "$MG"/public/${STAMP}_img*.png "$MG"/public/${STAMP}_matte.mov 2>/dev/null

if [[ -f "$OUT" && $(stat -f%z "$OUT" 2>/dev/null || echo 0) -gt 20000 ]]; then
  echo "{\"ok\": true, \"out\": \"$OUT\"}"
  exit 0
else
  echo "{\"ok\": false, \"error\": \"remotion render failed (see /tmp/${STAMP}_render.log)\"}"
  tail -5 /tmp/${STAMP}_render.log >&2 2>/dev/null
  exit 1
fi
