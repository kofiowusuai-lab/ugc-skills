#!/usr/bin/env python3
"""
ad_library_scout.py — proven-winner ad mining.

Scrapes the PUBLIC Meta Ad Library (and points at TikTok Creative Center Top Ads) for
competitor brands + product/niche keywords, captures each ad's "Started running on" date,
and ranks by LONGEVITY (advertisers kill losers fast, so an ad live >= N days is a strong
proxy for profitability) plus variant count (more variants = more spend = more confidence).

Heuristic, not a guarantee: we LOG the dates, we don't assume. Output is a ranked
"what's working in-market right now" table the strategist uses to choose its angle and
decide what to differentiate from.

Fetch path (in order, first that works wins):
  1. Meta Ad Library public async search endpoint (best-effort; often bot-gated).
  2. Codex-driven Playwright (persistent browser session per CLAUDE.md) if `codex` is on PATH.
  3. Graceful degrade: emit valid JSON with degraded=true + the exact URLs and a next_step,
     so the calling workflow agent covers the gap with WebSearch/WebFetch. NEVER fabricates ads.

Usage:
  ad_library_scout.py --query "AI course" --country US --min-days 30 --out winners.json
  ad_library_scout.py --query "manifestation journal" --advertisers "BrandA,BrandB" --json
"""
import argparse, json, sys, os, re, subprocess, shutil, datetime, urllib.request, urllib.parse, urllib.error

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")

META_PAGE = ("https://www.facebook.com/ads/library/?active_status=active&ad_type=all"
             "&country={country}&q={q}&media_type=all")
META_ASYNC = "https://www.facebook.com/ads/library/async/search_ads/?{qs}"
TIKTOK_TOPADS = "https://ads.tiktok.com/business/creativecenter/inspiration/topads/pc/en?region={country}"


def today():
    # Date.now() is fine here — this runs as a normal script, not in a Workflow sandbox.
    return datetime.date.today()


def days_since(date_str):
    """Parse a 'Started running on Jan 5, 2026' style string -> int days live, or None."""
    if not date_str:
        return None
    m = re.search(r"([A-Z][a-z]{2,9})\s+(\d{1,2}),?\s+(\d{4})", date_str)
    if not m:
        # try ISO
        try:
            d = datetime.date.fromisoformat(date_str[:10])
            return (today() - d).days
        except Exception:
            return None
    months = {mo: i for i, mo in enumerate(
        ["January", "February", "March", "April", "May", "June", "July",
         "August", "September", "October", "November", "December"], 1)}
    mon = next((v for k, v in months.items() if k.startswith(m.group(1)[:3])), None)
    if not mon:
        return None
    try:
        d = datetime.date(int(m.group(3)), mon, int(m.group(2)))
        return (today() - d).days
    except Exception:
        return None


def try_meta_async(query, country, timeout=25):
    """Best-effort hit on Meta's public async search endpoint. Returns list[ad] or None."""
    params = {
        "active_status": "active", "ad_type": "all", "country": country,
        "q": query, "media_type": "all", "search_type": "keyword_unordered",
        "count": "30", "forward_cursor": "", "backward_cursor": "",
        "collation_token": "", "session_id": "", "__a": "1",
    }
    url = META_ASYNC.format(qs=urllib.parse.urlencode(params))
    req = urllib.request.Request(url, headers={
        "User-Agent": UA, "Accept": "*/*",
        "Accept-Language": "en-US,en;q=0.9", "Referer": META_PAGE.format(country=country, q=urllib.parse.quote(query)),
        "X-Requested-With": "XMLHttpRequest",
    })
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read().decode("utf-8", "replace")
    except Exception as e:
        return None, f"meta_async_error: {e}"
    # Meta prefixes JSON with "for (;;);" to defeat hijacking
    raw = raw.lstrip()
    if raw.startswith("for (;;);"):
        raw = raw[len("for (;;);"):]
    try:
        data = json.loads(raw)
    except Exception as e:
        return None, f"meta_async_unparseable: {e}"
    ads = _walk_meta_payload(data, country)
    if not ads:
        return None, "meta_async_empty (likely bot-gated or zero results)"
    return ads, None


def _walk_meta_payload(data, country):
    """Meta's async payload nests results deeply and changes shape; walk it defensively."""
    out, seen = [], set()

    def visit(node):
        if isinstance(node, dict):
            # an ad node usually carries snapshot + page_name + start date fields
            text = None
            for k in ("body", "ad_creative_body", "link_description", "title"):
                v = node.get(k)
                if isinstance(v, dict):
                    v = v.get("text") or v.get("markup")
                if isinstance(v, str) and len(v) > 8:
                    text = v
                    break
            start = (node.get("start_date") or node.get("ad_delivery_start_time")
                     or node.get("startDate"))
            if isinstance(start, (int, float)):
                start = datetime.date.fromtimestamp(start).isoformat()
            adv = node.get("page_name") or node.get("pageName") or node.get("byline")
            if text and (adv or start):
                key = (adv, text[:60])
                if key not in seen:
                    seen.add(key)
                    out.append({
                        "advertiser": adv, "hook": text.split("\n")[0][:160],
                        "full_text": text[:500], "format": node.get("display_format") or "unknown",
                        "started": start, "days_live": days_since(start) if start else None,
                        "cta": node.get("cta_text") or node.get("cta_type"),
                        "offer": None, "variants": node.get("collation_count") or 1,
                        "source": "meta_ad_library", "country": country,
                    })
            for v in node.values():
                visit(v)
        elif isinstance(node, list):
            for v in node:
                visit(v)

    visit(data)
    return out


def try_codex_playwright(query, country, min_days, timeout=240):
    """Drive Codex's persistent Playwright session to scrape the Ad Library. Returns list or None."""
    if not shutil.which("codex"):
        return None, "codex_not_on_path"
    meta_url = META_PAGE.format(country=country, q=urllib.parse.quote(query))
    instruction = (
        f"Open this Meta Ad Library URL in Playwright (persistent session) and scroll to load "
        f"~30 ad cards: {meta_url}\n"
        "For each ad card extract EXACTLY these fields and output ONLY a JSON array (no prose) of objects "
        "with keys: advertiser, hook (the first line of primary text), full_text, format (image/video/carousel), "
        "started (the 'Started running on' date string verbatim), cta, offer (price if visible), variants "
        "(the 'uses this creative and text' / 'N ads use this' count if shown, else 1). "
        "If the page shows a login wall or zero results, output an empty JSON array []. Output JSON only."
    )
    try:
        proc = subprocess.run(
            ["codex", "exec", "--skip-git-repo-check", "-s", "workspace-write", "-"],
            input=instruction, capture_output=True, text=True, timeout=timeout)
    except Exception as e:
        return None, f"codex_error: {e}"
    blob = proc.stdout or ""
    m = re.search(r"\[\s*{.*}\s*\]", blob, re.S) or re.search(r"\[\s*\]", blob)
    if not m:
        return None, f"codex_no_json (stderr: {(proc.stderr or '')[:200]})"
    try:
        ads = json.loads(m.group(0))
    except Exception as e:
        return None, f"codex_json_parse: {e}"
    for a in ads:
        a.setdefault("source", "meta_ad_library_playwright")
        a.setdefault("country", country)
        a["days_live"] = days_since(a.get("started"))
        a.setdefault("variants", 1)
    return ads, None


def rank(ads, min_days):
    """Rank by longevity (primary) then variant count. Flag likely winners (>= min_days)."""
    for a in ads:
        dl = a.get("days_live")
        var = a.get("variants") or 1
        a["likely_winner"] = bool(dl is not None and dl >= min_days)
        # score: longevity dominates, variants break ties; unknown dates sink to the bottom
        a["score"] = (dl if dl is not None else -1) * 10 + min(var, 20)
    return sorted(ads, key=lambda a: a["score"], reverse=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--query", required=True, help="product/niche keyword")
    ap.add_argument("--country", default="US")
    ap.add_argument("--advertisers", default="", help="comma-separated competitor page names (optional)")
    ap.add_argument("--min-days", type=int, default=30, help="longevity threshold for 'likely winner'")
    ap.add_argument("--out", default="", help="write winners JSON here")
    ap.add_argument("--json", action="store_true", help="print full JSON to stdout")
    ap.add_argument("--no-codex", action="store_true", help="skip the Playwright/Codex path")
    args = ap.parse_args()

    diagnostics = []
    ads, err = try_meta_async(args.query, args.country)
    if err:
        diagnostics.append(err)
    if not ads and not args.no_codex:
        ads, err2 = try_codex_playwright(args.query, args.country, args.min_days)
        if err2:
            diagnostics.append(err2)

    meta_url = META_PAGE.format(country=args.country, q=urllib.parse.quote(args.query))
    tiktok_url = TIKTOK_TOPADS.format(country=args.country)

    if ads:
        ranked = rank(ads, args.min_days)
        winners = [a for a in ranked if a["likely_winner"]]
        result = {
            "query": args.query, "country": args.country, "min_days": args.min_days,
            "degraded": False, "ad_count": len(ranked), "winner_count": len(winners),
            "winners": winners, "all_ads": ranked, "diagnostics": diagnostics,
            "sources": {"meta": meta_url, "tiktok": tiktok_url},
        }
    else:
        result = {
            "query": args.query, "country": args.country, "min_days": args.min_days,
            "degraded": True, "ad_count": 0, "winner_count": 0,
            "winners": [], "all_ads": [], "diagnostics": diagnostics,
            "sources": {"meta": meta_url, "tiktok": tiktok_url},
            "next_step": ("Direct + Playwright scrape unavailable. The calling agent should WebSearch/WebFetch "
                          f"these URLs for active competitor ads and start dates, or open them in a browser:\n"
                          f"  Meta Ad Library: {meta_url}\n  TikTok Top Ads: {tiktok_url}"),
        }

    out_json = json.dumps(result, indent=2)
    if args.out:
        with open(args.out, "w") as f:
            f.write(out_json)
    if args.json or not args.out:
        print(out_json)
    # exit 0 even when degraded — degradation is an expected, handled state, not a failure
    return 0


if __name__ == "__main__":
    sys.exit(main())
