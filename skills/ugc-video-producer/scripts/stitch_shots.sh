#!/usr/bin/env bash
# stitch_shots.sh — concat multiple 6-10s UGC shots into one vertical ad.
# Re-encodes to a uniform 720x1280 / 24fps / aac so mismatched clips join cleanly.
# Usage: stitch_shots.sh out.mp4 shot1.mp4 shot2.mp4 [shot3.mp4 ...]
set -euo pipefail
OUT="$1"; shift
[ "$#" -ge 1 ] || { echo "need at least one shot"; exit 1; }
WORK="$(mktemp -d)"; i=0; LIST="$WORK/list.txt"
for f in "$@"; do
  norm="$WORK/n$i.mp4"
  ffmpeg -y -v error -i "$f" \
    -vf "scale=720:1280:force_original_aspect_ratio=increase,crop=720:1280,fps=24" \
    -c:v libx264 -pix_fmt yuv420p -crf 18 \
    -c:a aac -ar 44100 -ac 2 "$norm"
  echo "file '$norm'" >> "$LIST"; i=$((i+1))
done
ffmpeg -y -v error -f concat -safe 0 -i "$LIST" -c copy "$OUT"
echo "stitched $i shots -> $OUT ($(ffprobe -v error -show_entries format=duration -of csv=p=0 "$OUT")s)"
rm -rf "$WORK"
