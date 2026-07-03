---
name: ugc-vision-referee
category: marketing-and-ads
description: DEPRECATED — folded into the `ugc-minimax-mode` skill. The Claude-vision QA + delivery step (rejecting Grok drift, picking the matching take, stitching) is now Step 4 of `ugc-minimax-mode`. If you are on MiniMax and need UGC/video QA or delivery, use `ugc-minimax-mode`. (The underlying tool is unchanged: `~/.openclaw/scripts/ugc_claude_deliver.sh`.)
version: 3.0.0
pinned: false
---

# ugc-vision-referee — moved

This skill has been consolidated. Use **`ugc-minimax-mode`** — its Step 4 is the
Claude-vision QA + delivery stage that used to live here.

The launcher is unchanged and still callable directly:
```
~/.openclaw/scripts/ugc_claude_deliver.sh --job <DIR> --anchor <IMG> \
  --pattern 'clips/clip*_candidate_*.mp4' --out <DIR>/final_delivery.mp4 [--qa-only]
```
