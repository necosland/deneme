"""Trader ofisi gundem ozetleyici: topla.py'nin ham kalemlerini trader-gundem (Defne) ile ozetler.

 1. MODE=item: penceredeki (digest_window_days) henuz cikarilmamis her kalem icin ayri `claude -p --agent trader-gundem`
    (metin stdin'de; en cok 3 paralel). Sonuc ozet/kalem/<id>.json; cagrilar cagrilar.csv'ye eklenir.
 2. MODE=digest: penceredeki tum kalem ciktilari -> ozet/YYYY-MM-DD.json + .md (Turkce) + ozet/son_kisa.json
    (tur.py'nin Kerem ve Riza'ya verdigi <= ~1.5k token ozet).
Ajan yalniz Read kullanir; dosyalari bu kod yazar.

Kullanim: python algo/ofis/gundem/ozetle.py [--no-digest] [--force-digest]
"""
import argparse
import concurrent.futures as cf
import csv
import datetime as dt
import json
import os
import pathlib
import subprocess
import sys
import time

G = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(G.parent))
import ortak as O  # noqa: E402

HAM, OZET = G / "ham", G / "ozet"
KALEM_DIR = OZET / "kalem"
CAGRI = G / "cagrilar.csv"
CAGRI_COLS = ["source", "date", "asset", "call", "level", "horizon", "direction", "condition", "confidence",
              "px_at_call", "item_id", "url", "logged_utc"]
NOWIN = getattr(subprocess, "CREATE_NO_WINDOW", 0)
T_ITEM, T_DIGEST, PAR = 420, 360, 3
SHORT_MAX = 6000                 # son_kisa.json ~1.5k token
LOGF = "gundem.log"
AGENT = "trader-gundem"


def say(m):
    O.log(LOGF, "ozetle: " + m)


def safe(s):
    import re
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", s)[:120]


def run_claude(prompt, timeout, tag):
    exe = O.find_claude()
    if not exe:
        return {"error": "claude CLI not found"}
    cmd = [exe, "-p", "--agent", AGENT, "--output-format", "json", "--permission-mode", "dontAsk",
           "--tools", "Read", "--allowedTools", "Read", "--add-dir", str(O.AGENT_BILGI), "--add-dir", str(O.ROOT),
           "--no-session-persistence"]
    env = {k: v for k, v in os.environ.items() if k not in ("CLAUDECODE", "CLAUDE_CODE_ENTRYPOINT")}
    t0 = time.time()
    p = subprocess.Popen(cmd, cwd=str(O.ROOT), stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                         env=env, creationflags=NOWIN)
    try:
        out, err = p.communicate(prompt.encode("utf-8"), timeout=timeout)
    except subprocess.TimeoutExpired:
        subprocess.run(["taskkill", "/T", "/F", "/PID", str(p.pid)], capture_output=True, creationflags=NOWIN)
        return {"error": f"timeout {timeout}s", "secs": round(time.time() - t0)}
    out = out.decode("utf-8", "replace")
    res = {"secs": round(time.time() - t0)}
    try:
        j = json.loads(out)
    except json.JSONDecodeError:
        res["error"] = f"non-json rc={p.returncode}: {(out or err.decode('utf-8', 'replace'))[:200]}"
        return res
    u = j.get("usage") or {}
    res.update(text=j.get("result") or "", cost_usd=j.get("total_cost_usd"), turns=j.get("num_turns"),
               tok_in=u.get("input_tokens", 0) + u.get("cache_creation_input_tokens", 0) + u.get("cache_read_input_tokens", 0),
               tok_out=u.get("output_tokens", 0))
    if j.get("is_error"):
        res["error"] = f"cli error: {str(j.get('result'))[:200]}"
    return res


# ---------------- kalemler ----------------
def window_items(days):
    cut = O.now_utc() - dt.timedelta(days=days)
    seen, out = set(), []
    for r in O.read_jsonl(HAM / "kalemler.jsonl"):
        t = dt.datetime.strptime(r["published_utc"], "%Y-%m-%dT%H:%MZ").replace(tzinfo=dt.timezone.utc)
        if t >= cut and r["id"] not in seen and pathlib.Path(r["path"]).exists():
            seen.add(r["id"])
            out.append(r)
    return sorted(out, key=lambda r: r["published_utc"])


def kalem_path(item_id):
    return KALEM_DIR / f"{safe(item_id)}.json"


_PX = {}


def px_at(rec):
    """Kalem yayimlandiginda BTC/ETH fiyati (Binance spot 1h kapanisi). Cagri puanlamasi ve seviyenin ust/alt
    yonu icin. Gonderi demetinde en yeni gonderinin saati (published_utc)."""
    when = dt.datetime.strptime(rec["published_utc"], "%Y-%m-%dT%H:%MZ").replace(tzinfo=dt.timezone.utc)
    out = {}
    for sym in ("BTC", "ETH"):
        key = (sym, when.strftime("%Y%m%d%H"))
        if key not in _PX:
            try:
                import urllib.request
                u = f"{O.SPOT_KLINES}?symbol={sym}USDT&interval=1h&limit=1&startTime={O.ms(when.replace(minute=0))}"
                rows = json.loads(urllib.request.urlopen(urllib.request.Request(u, headers=O.UA), timeout=20).read())
                _PX[key] = float(rows[0][4]) if rows else None
            except Exception:  # noqa: BLE001
                _PX[key] = None
        out[sym] = _PX[key]
    return out


def item_prompt(rec, who, px):
    body = pathlib.Path(rec["path"]).read_text(encoding="utf-8").split("\n---\n", 1)[-1]
    imgs = rec.get("images") or []
    return "\n".join([
        "MODE=item", f"ITEM_ID={rec['id']}", f"SOURCE={rec['source_name']} ({rec['source']})", f"WHO={who}",
        f"PUBLISHED_UTC={rec['published_utc']}",
        f"PRICE_AT_PUBLISH=BTC {px.get('BTC')} ETH {px.get('ETH')} (Binance 1h close at PUBLISHED_UTC; for tweets: newest post)",
        f"TITLE={rec['title']}", f"URL={rec['url']}", f"KIND={rec['kind']}",
        f"IMAGES={', '.join(imgs) if imgs else 'none'}",
        "Follow your agent instructions (MODE=item). Final message: only one ```json object.",
        "--- TEXT START ---", body.strip(), "--- TEXT END ---"])


ITEM_KEYS = ("relevant", "btc", "eth", "vol", "risks", "catalysts", "confidence", "hedging", "non_obvious", "calls",
             "summary_tr")


def check_item(x):
    if not isinstance(x, dict):
        return ["not an object"]
    errs = [f"missing {k}" for k in ITEM_KEYS if k not in x]
    for a in ("btc", "eth"):
        if a in x and not isinstance(x[a], dict):
            errs.append(f"{a} not object")
    if "calls" in x and not isinstance(x["calls"], list):
        errs.append("calls not list")
    return errs


def num(v):
    try:
        return float(str(v).replace(",", "")) if v not in (None, "") else None
    except ValueError:
        return None


def log_calls(rec, x):
    new = not CAGRI.exists()
    have = set()
    if not new:
        with open(CAGRI, encoding="utf-8", newline="") as f:
            have = {(r["item_id"], r["asset"], r["call"]) for r in csv.DictReader(f)}
    rows = []
    for c in (x.get("calls") or [])[:6]:
        if not isinstance(c, dict) or not c.get("call"):
            continue
        key = (rec["id"], str(c.get("asset", "")).upper(), c["call"])
        if key in have:
            continue
        lv = num(c.get("level"))
        rows.append({"source": rec["source"], "date": rec["published_utc"], "asset": key[1], "call": c["call"],
                     "px_at_call": (x.get("px_at_publish") or {}).get(key[1], ""),
                     "level": "" if lv is None else (int(lv) if lv == int(lv) else lv), "horizon": c.get("horizon") or "",
                     "direction": c.get("direction") or "", "condition": c.get("condition") or "",
                     "confidence": x.get("confidence") or "", "item_id": rec["id"], "url": rec["url"],
                     "logged_utc": O.fmt(O.now_utc())})
    if rows:
        with open(CAGRI, "a", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=CAGRI_COLS)
            if new:
                w.writeheader()
            w.writerows(rows)
    return len(rows)


def extract_items(recs, who_of):
    todo = [r for r in recs if not kalem_path(r["id"]).exists()]
    stats = {"n": len(todo), "ok": 0, "failed": [], "cost_usd": 0.0, "calls_logged": 0}
    if not todo:
        return stats
    with cf.ThreadPoolExecutor(max_workers=PAR) as pool:
        pxs = {r["id"]: px_at(r) for r in todo}
        futs = {pool.submit(run_claude, item_prompt(r, who_of.get(r["source"], ""), pxs[r["id"]]), T_ITEM, r["id"]): r
                for r in todo}
        for f in cf.as_completed(futs):
            rec, res = futs[f], f.result()
            stats["cost_usd"] += res.get("cost_usd") or 0
            x = O.extract_json(res.get("text")) if not res.get("error") else None
            errs = [res["error"]] if res.get("error") else check_item(x)
            say(f"item {rec['id']}: secs={res.get('secs')} cost={res.get('cost_usd')} tok_in={res.get('tok_in')} "
                f"tok_out={res.get('tok_out')} {'OK' if not errs else 'INVALID ' + '; '.join(errs)[:200]}")
            if errs:
                stats["failed"].append(rec["id"])
                continue
            x.update(item_id=rec["id"], source=rec["source"], date_utc=rec["published_utc"], title=rec["title"],
                     url=rec["url"], kind=rec["kind"], px_at_publish=pxs[rec["id"]], _cost_usd=res.get("cost_usd"))
            O.write_json(kalem_path(rec["id"]), x)
            stats["ok"] += 1
            stats["calls_logged"] += log_calls(rec, x)
    return stats


# ---------------- sentez ----------------
def price_ref():
    f = O.VERI / "son.json"
    if not f.exists():
        return "none"
    try:
        s = json.loads(f.read_text(encoding="utf-8"))
        px = {k.replace("USDT", ""): ((v or {}).get("ctx") or {}).get("last_close") for k, v in s["assets"].items()}
        return json.dumps({"asof_utc": s.get("asof_utc"), **px})
    except Exception:  # noqa: BLE001
        return "none"


DIGEST_KEYS = ("per_source", "consensus", "disagreements", "crowd_expectation", "contrarian_read", "key_levels",
               "vol_view", "risks_catalysts", "surprises", "headline_tr", "ozet_tr")


def compact_item(x):
    return {k: x.get(k) for k in ("source", "date_utc", "title", "relevant", "btc", "eth", "vol", "vol_note", "risks",
                                  "catalysts", "confidence", "hedging", "non_obvious", "calls")}


def make_short(d):
    """tur.py icin <= SHORT_MAX karakter ozet."""
    s = {"date": d["date"], "items": d.get("items"), "headline_tr": d.get("headline_tr"), "consensus": d.get("consensus"),
         "per_source": [{k: p.get(k) for k in ("source", "date", "btc", "eth", "horizon", "line")} for p in d.get("per_source") or []],
         "disagreements": d.get("disagreements"), "crowd_expectation": d.get("crowd_expectation"),
         "contrarian_read": d.get("contrarian_read"), "key_levels": d.get("key_levels"), "vol_view": d.get("vol_view"),
         "risks_catalysts": d.get("risks_catalysts"), "surprises": d.get("surprises")}
    for drop in ("surprises", "risks_catalysts", "contrarian_read", "disagreements"):
        if len(json.dumps(s, ensure_ascii=False)) <= SHORT_MAX:
            break
        s.pop(drop, None)
    while len(json.dumps(s, ensure_ascii=False)) > SHORT_MAX and s["per_source"]:
        s["per_source"].pop(0)
    return s


def write_md(d, path):
    lines = [f"# Gündem özeti {d['date']}", "", f"**{d.get('headline_tr', '')}**", "", d.get("ozet_tr", ""), "",
             f"Kalem: {d.get('items')} · pencere {d.get('window_days')} gün · uzlaşı BTC {d['consensus'].get('btc')} / "
             f"ETH {d['consensus'].get('eth')} ({d['consensus'].get('strength')})", "", "## Kaynaklar", ""]
    for p in d.get("per_source") or []:
        lines.append(f"- {p.get('source')} ({p.get('date')}): BTC {p.get('btc')}, ETH {p.get('eth')}, {p.get('horizon')} — {p.get('line')}")
    lines += ["", "## Ayrışmalar", ""] + [f"- {x}" for x in d.get("disagreements") or []]
    lines += ["", "## Seviyeler", ""]
    for a, lv in (d.get("key_levels") or {}).items():
        lines.append(f"- {a}: " + ", ".join(f"{x.get('level')} {x.get('kind')} (n={x.get('n')})" for x in lv or []))
    lines += ["", f"Maliyet: {d.get('_run', {}).get('cost_usd_total')} USD", ""]
    path.write_text("\n".join(lines), encoding="utf-8")


def digest(window, today):
    xs = []
    for r in window:
        p = kalem_path(r["id"])
        if p.exists():
            xs.append(compact_item(json.loads(p.read_text(encoding="utf-8"))))
    if not xs:
        return None, {"error": "no extracted items in window"}
    days = json.loads((G / "kaynaklar.json").read_text(encoding="utf-8")).get("digest_window_days", 7)
    prompt = "\n".join(["MODE=digest", f"DATE={today}", f"WINDOW_DAYS={days}", f"PRICE_REF={price_ref()}",
                        "Follow your agent instructions (MODE=digest). Final message: only one ```json object.",
                        "ITEMS=", json.dumps(xs, ensure_ascii=False, separators=(",", ":"))])
    res = run_claude(prompt, T_DIGEST, "digest")
    d = O.extract_json(res.get("text")) if not res.get("error") else None
    errs = [res["error"]] if res.get("error") else (
        ["not an object"] if not isinstance(d, dict) else [f"missing {k}" for k in DIGEST_KEYS if k not in d])
    say(f"digest: secs={res.get('secs')} cost={res.get('cost_usd')} tok_in={res.get('tok_in')} tok_out={res.get('tok_out')} "
        f"{'OK' if not errs else 'INVALID ' + '; '.join(errs)[:200]}")
    if errs:
        return None, {"error": "; ".join(errs), "cost_usd": res.get("cost_usd")}
    d.update(date=today, window_days=days, items=len(xs))
    return d, {"cost_usd": res.get("cost_usd")}


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-digest", action="store_true")
    ap.add_argument("--force-digest", action="store_true", help="yeni kalem yoksa da sentez yaz")
    a = ap.parse_args(argv)
    cfg = json.loads((G / "kaynaklar.json").read_text(encoding="utf-8"))
    who_of = {s["id"]: s.get("who", "") for s in cfg["sources"]}
    window = window_items(cfg.get("digest_window_days", 7))
    st = extract_items(window, who_of)
    say(f"items: {st}")
    today = dt.datetime.now().strftime("%Y-%m-%d")   # TR yerel tarih
    out = OZET / f"{today}.json"
    if a.no_digest or (st["ok"] == 0 and out.exists() and not a.force_digest):
        say("digest skipped")
        return 0
    d, info = digest(window, today)
    if not d:
        say(f"digest FAILED {info}")
        return 2
    d["_run"] = {"items_new": st["n"], "items_ok": st["ok"], "items_failed": st["failed"],
                 "calls_logged": st["calls_logged"], "cost_usd_items": round(st["cost_usd"], 4),
                 "cost_usd_digest": info.get("cost_usd"),
                 "cost_usd_total": round(st["cost_usd"] + (info.get("cost_usd") or 0), 4),
                 "generated_utc": O.fmt(O.now_utc())}
    O.write_json(out, d)
    write_md(d, OZET / f"{today}.md")
    O.write_json(OZET / "son_kisa.json", make_short(d))
    say(f"digest written {out.name} headline={d.get('headline_tr')!r} run={d['_run']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
