"""Ekrem (trader-elliott) kor testi: kurs egitmeninin gercek grafikteki dalga sayimina karsi.

Tek komut (bu klasorun .venv python'u ile):
  python test_ekrem.py hazirla                      # vakalar.json -> snap/<kod>.json + .png, anahtar/<id>.json
  python test_ekrem.py calistir --tag once [--set heldout] [--only H01,F01] [--batch 4]
  python test_ekrem.py puanla --tag once [--set heldout]
  python test_ekrem.py hepsi --tag once             # uc adim arka arkaya

Yeni vaka eklemek: vakalar.json'a ayni bicimde bir kayit ekle (alanlar dosyanin "_format" satirinda),
ham/<data>.csv gunluk OHLC olsun (veri_cek.py), sonra hazirla + calistir --only <id> + puanla.

Gizleme: fiyat ilk kapanis = 100 olacak sekilde olceklenir, tarih ve sembol cikarilir, bar suresi soylenmez.
Pivotlar canli ofisin zigzag'i (veri_topla.zigzag, k x ATR14) ile bulunur; k vaka basina egitmenin noktalarini
yakalayan en buyuk deger secilir (sayimi test ediyoruz, pivot bulucuyu degil). Canli ofis dosyalari degismez.
"""
import argparse
import concurrent.futures as cf
import hashlib
import json
import os
import pathlib
import re
import subprocess
import sys
import time

import numpy as np
import pandas as pd

HERE = pathlib.Path(__file__).resolve().parent
OFIS = HERE.parent
sys.path.insert(0, str(OFIS))
from veri_topla import atr, rsi, zigzag, r5, dump  # noqa: E402  (canli ofisin pivot ve RSI fonksiyonlari)
import ortak as O  # noqa: E402  (yalniz find_claude, AGENT_BILGI)

HAM, SNAP, KEY, OUT = HERE / "ham", HERE / "snap", HERE / "anahtar", HERE / "cikti"
K_LIST = [8, 6, 5, 4, 3.5, 3, 2.5, 2, 1.5, 1.2, 1.0]
MAX_PIV = 45
NOWIN = getattr(subprocess, "CREATE_NO_WINDOW", 0)
FAMILY = {"impulse": "impulse", "leading_diagonal": "diagonal", "ending_diagonal": "diagonal", "diagonal": "diagonal",
          "zigzag": "zigzag", "flat": "flat", "regular_flat": "flat", "expanded_flat": "flat", "running_flat": "flat",
          "triangle": "triangle", "contracting_triangle": "triangle", "expanding_triangle": "triangle",
          "barrier_triangle": "triangle", "running_triangle": "triangle", "double_zigzag": "combination",
          "triple_zigzag": "combination", "double_three": "combination", "triple_three": "combination",
          "combination": "combination"}


# ---------------- vakalar ----------------
def load_cases():
    d = json.loads((HERE / "vakalar.json").read_text(encoding="utf-8"))
    cases = {c["id"]: c for c in d["cases"]}
    for c in cases.values():
        if c.get("parent"):
            p = cases[c["parent"]]
            for k in ("src", "instrument", "data", "bar", "from", "family", "direction"):
                c.setdefault(k, p[k])
    return cases


def code_of(cid):
    """Ekrem'e giden notr kod (H/F ayrimini ve sirayi gizler)."""
    return "K" + hashlib.sha1(("ekrem-test-" + cid).encode()).hexdigest()[:4].upper()


def bars(c, full=False):
    df = pd.read_csv(HAM / f"{c['data']}.csv", index_col=0, parse_dates=True)
    df = df[(df.high >= df.low) & (df.close > 0)]
    df = df[df.index >= pd.Timestamp(c["from"])]
    if not full:
        df = df[df.index <= pd.Timestamp(c["cut"])]
    rule = c["bar"]
    if rule == "D":
        return df
    if rule.startswith("W"):
        g = df.resample(rule)
    else:   # "2D", "3D": n ardisik islem gunu
        n = int(rule[:-1])
        g = df.groupby(np.arange(len(df)) // n)
    out = g.agg(open=("open", "first"), high=("high", "max"), low=("low", "min"), close=("close", "last"))
    if not rule.startswith("W"):
        out.index = df.index[::n][:len(out)]
    return out.dropna()


def locate(df, typ, date, win):
    d = pd.Timestamp(date)
    w = max(win, 8 if c_rule_weekly(df) else 0)
    m = (df.index >= d - pd.Timedelta(days=w)) & (df.index <= d + pd.Timedelta(days=w))
    if not m.any():
        return None
    sub = df[m]
    i = sub.high.idxmax() if typ == "H" else sub.low.idxmin()
    return int(df.index.get_loc(i))


def c_rule_weekly(df):
    return len(df) > 2 and (df.index[1] - df.index[0]).days >= 6


MIN_PIV = 15


def _hits(df, k, pts):
    piv, prov = zigzag(df, k)
    allp = list(piv) + ([prov] if prov else [])
    hit = {}
    for lab, typ, bi in pts:
        cand = [(abs(i - bi), j) for j, (i, p, t) in enumerate(allp) if t.rstrip("?") == typ and abs(i - bi) <= 2]
        if cand:
            hit[lab] = min(cand)[1]
    return piv, prov, hit


def pick_k(df, pts, fixed=None):
    """Egitmen noktalarini (ayni tip, +-2 bar) yakalayan en buyuk k; ama en az MIN_PIV pivot olsun ki
    pivot listesi egitmenin iskeletini hazir vermesin (gurultu pivotlari da olsun)."""
    if fixed is not None:
        piv, prov, hit = _hits(df, fixed, pts)
        if len(hit) == len(pts):
            return fixed, piv, prov, hit
    full_ok, best = [], None
    for k in K_LIST:
        piv, prov, hit = _hits(df, k, pts)
        if len(piv) > MAX_PIV:
            continue
        if best is None or len(hit) > len(best[3]):
            best = (k, piv, prov, hit)
        if len(hit) == len(pts):
            full_ok.append((k, piv, prov, hit))
    for cand in full_ok:
        if len(cand[1]) >= MIN_PIV:
            return cand
    return full_ok[-1] if full_ok else best


def next_swing(c, k):
    """Kesimden sonraki ilk onayli pivotun tipi -> sonraki bacagin yonu (veriden; ayni k)."""
    full = bars(c, full=True)
    cut_i = int((full.index <= pd.Timestamp(c["cut"])).sum()) - 1
    for kk in (k, k * 0.75, k * 0.5, 1.5):
        piv, _ = zigzag(full, kk)
        after = [(i, t) for i, p, t in piv if i > cut_i]
        if after:
            return "up" if after[0][1] == "H" else "down"
    return None


# ---------------- hazirla ----------------
def hazirla(ids=None):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    SNAP.mkdir(exist_ok=True)
    KEY.mkdir(exist_ok=True)
    cases = load_cases()
    KFIX = {}
    order = sorted(cases, key=lambda i: bool(cases[i].get("parent")))   # once ana vakalar (k'yi F devralir)
    for cid in order:
        c = cases[cid]
        if ids and cid not in ids and cid not in [cases[i].get("parent") for i in ids]:
            continue
        df = bars(c)
        scale = 100.0 / df.close.iloc[0]
        df = df[["open", "high", "low", "close"]] * scale
        pts = []
        for lab, typ, date, win in c["points"]:
            bi = locate(df, typ, date, win)
            pts.append((lab, typ, bi))
        fixed = KFIX.get(c.get("parent"))
        k, piv, prov, hit = pick_k(df, [p for p in pts if p[2] is not None], fixed)
        KFIX[cid] = k
        r = rsi(df.close).to_numpy()
        a = atr(df).to_numpy()
        plist, last = [], {"H": None, "L": None}
        for j, (i, p, t) in enumerate(piv):
            lab = t if last[t] is None else (("HH" if p > last[t] else "LH") if t == "H" else ("HL" if p > last[t] else "LL"))
            last[t] = p
            plist.append([f"P{j}", int(i), r5(p), t, lab, r5(round(r[i], 1))])
        prov_l = None
        if prov:
            prov_l = [f"P{len(piv)}?", int(prov[0]), r5(prov[1]), prov[2], r5(round(r[prov[0]], 1))]
        code = code_of(cid)
        tail = df.tail(30)
        snap = {
            "case": code,
            "note": ("Anonymized price series for an offline Elliott counting test. Prices rescaled (first close = 100); "
                     "dates, symbol and bar interval removed on purpose. Bars are equal fixed intervals."),
            "bars": len(df), "last_bar_index": len(df) - 1, "last_close": r5(df.close.iloc[-1]),
            "atr14_last": r5(a[-1]),
            "pivot_rule": f"confirmed swing when price reverses {k} x ATR14 from the extreme (office zigzag)",
            "pivots_cols": ["id", "bar_index", "price", "type", "vs_prev_same_type", "rsi14_at_pivot"],
            "pivots": plist,
            "current_leg_extreme_unconfirmed": prov_l,
            "candles_tail_cols": ["bar_index", "o", "h", "l", "c"],
            "candles_tail": [[int(len(df) - len(tail) + n), r5(o), r5(h), r5(l), r5(cl)]
                             for n, (o, h, l, cl) in enumerate(tail.to_numpy())],
            "chart": str(SNAP / f"{code}.png"),
        }
        (SNAP / f"{code}.json").write_text(dump(snap) + "\n", encoding="utf-8")
        # grafik
        fig, ax = plt.subplots(figsize=(12, 6.5), dpi=100)
        x = np.arange(len(df))
        up = (df.close >= df.open).to_numpy()
        col = np.where(up, "#26a69a", "#ef5350")
        ax.vlines(x, df.low, df.high, color=col, linewidth=0.8)
        ax.bar(x, (df.close - df.open).abs().clip(lower=1e-9), bottom=np.minimum(df.open, df.close), color=col,
               width=0.7)
        pv = [(i, p, t, f"P{j}") for j, (i, p, t) in enumerate(piv)]
        ax.plot([q[0] for q in pv], [q[1] for q in pv], color="#9e9e9e", linewidth=0.7, alpha=0.8)
        for i, p, t, name in pv:
            ax.annotate(f"{name}\n{r5(p)}" if t == "H" else f"{r5(p)}\n{name}", (i, p),
                        xytext=(0, 12 if t == "H" else -22), textcoords="offset points", ha="center", fontsize=7,
                        color="#1a237e")
            ax.plot(i, p, "v" if t == "H" else "^", color="#1a237e", markersize=4)
        if prov:
            ax.plot(prov[0], prov[1], "o", mfc="none", color="#ff9800", markersize=8)
        ax.set_xlim(-1, len(df) + 4)
        ax.set_xlabel("bar index")
        ax.grid(alpha=0.2)
        ax.set_title(f"Case {code} | {len(df)} bars, price rescaled (first close=100) | pivots k={k}xATR14, "
                     f"orange ring = unconfirmed leg extreme", fontsize=9)
        fig.tight_layout()
        fig.savefig(SNAP / f"{code}.png")
        plt.close(fig)
        # anahtar (Ekrem'e gitmez)
        nxt = c.get("next") or None
        key = {"id": cid, "code": code, "set": c["set"], "instrument": c["instrument"], "src": c["src"],
               "bar": c["bar"], "from": c["from"], "cut": c["cut"], "k": k, "n_pivots": len(piv),
               "family": c["family"], "direction": c["direction"], "parent": c.get("parent"),
               "points": [{"label": lab, "type": typ, "bar": bi, "pivot": (f"P{hit[lab]}" if lab in hit else None)}
                          for lab, typ, bi in pts],
               "next_given": nxt, "next_data": next_swing(c, k), "instructor_next": c.get("instructor_next"),
               "last_close": r5(df.close.iloc[-1]), "pivot_prices": {f"P{j}": r5(p) for j, (i, p, t) in enumerate(piv)}}
        if prov:
            key["pivot_prices"][f"P{len(piv)}"] = r5(prov[1])
        (KEY / f"{cid}.json").write_text(json.dumps(key, ensure_ascii=False, indent=1), encoding="utf-8")
        miss = [p["label"] for p in key["points"] if p["pivot"] is None]
        print(f"{cid} {code} bars={len(df)} k={k} piv={len(piv)} pts={[(p['label'], p['pivot']) for p in key['points']]}"
              f"{' MISSING ' + str(miss) if miss else ''} next={nxt}/{key['next_data']}")


# ---------------- calistir ----------------
PROMPT_HEAD = """TEST MODE - offline Elliott wave counting test. This is NOT a trading round: ignore SNAPSHOT/PREV/LIMITS, the BTC/ETH blocks and the output schema in ortak\\cikti-semasi.md.
1. Read your INDEX ({index}) and every file it lists to read every round EXCEPT the ..\\ortak\\ files. Do NOT open anything under C:\\Users\\pc\\trader-ofis-egitim (raw course notes) - not allowed in this test.
2. Each case below is an independent, anonymized price series (rescaled so first close = 100; dates, symbol and bar interval removed). Do not try to identify the market or use remembered history; count only from the given pivots, RSI and chart. Cases are unrelated to each other.
3. For each case read its JSON and its chart PNG (paths below), then give your primary and alternate Elliott count of the dominant structure in the window - the pattern that the latest price action completes or is still developing - at the degree the visible data supports. Label pivots by their ids (P0, P1, ...). Check hard rules before answering.
Label keys: impulse/diagonal "0","1".."5"; zigzag/flat "0","A","B","C"; triangle "0","A".."E"; double/triple zigzag or three "0","W","X","Y","X2","Z". "0" = pivot where the pattern starts. Omit labels not yet formed.
pattern one of: impulse, leading_diagonal, ending_diagonal, zigzag, regular_flat, expanded_flat, running_flat, contracting_triangle, expanding_triangle, barrier_triangle, running_triangle, double_zigzag, triple_zigzag, double_three, triple_three.
direction = direction of the pattern's FIRST leg (wave 1 / A / W): "up" or "down".
Final message: only a ```json array, one object per case:
{{"case":"K...","primary":{{"pattern":"...","direction":"up|down","labels":{{"0":"P3","1":"P5"}},"weight":60,"invalidation":{{"price":0.0,"rule":"<=120 chars"}}}},"alternate":{{same keys}},"status":"complete|in_progress","next_leg":{{"direction":"up|down","note":"<=120 chars"}},"why":"<=200 chars"}}
weight = primary probability %, alternate gets the rest. next_leg = direction of the next swing of the same degree after the last bar.
CASES:
"""


def run_batch(codes, tag, bno, skip=None):
    exe = O.find_claude()
    lines = [f"{c}: json={SNAP / (c + '.json')} chart={SNAP / (c + '.png')}" for c in codes]
    head = PROMPT_HEAD.format(index=O.AGENT_BILGI / "trader-elliott" / "INDEX.md")
    if skip:   # karsilastirma olcumu: bu bilgi dosyasi olmadan ayni vakalari kostur
        mark = "EXCEPT the ..\\ortak\\ files."
        assert mark in head
        head = head.replace(mark, f"EXCEPT the ..\\ortak\\ files and EXCEPT {skip} (excluded in this run).")
    prompt = head + "\n".join(lines)
    od = OUT / tag
    od.mkdir(parents=True, exist_ok=True)
    (od / f"b{bno}_prompt.txt").write_text(prompt, encoding="utf-8")
    cmd = [exe, "-p", "--agent", "trader-elliott", "--output-format", "json", "--permission-mode", "dontAsk",
           "--tools", "Read", "--allowedTools", "Read", "--add-dir", str(O.AGENT_BILGI), "--add-dir", str(HERE),
           "--no-session-persistence"]
    env = {k: v for k, v in os.environ.items() if k not in ("CLAUDECODE", "CLAUDE_CODE_ENTRYPOINT")}
    t0 = time.time()
    p = subprocess.run(cmd, cwd=str(HERE), input=prompt.encode("utf-8"), capture_output=True, env=env,
                       creationflags=NOWIN, timeout=900)
    out = p.stdout.decode("utf-8", "replace")
    (od / f"b{bno}.out.json").write_text(out, encoding="utf-8")
    try:
        j = json.loads(out)
    except json.JSONDecodeError:
        return {"batch": bno, "codes": codes, "error": out[:300] + p.stderr.decode("utf-8", "replace")[:300]}
    txt = j.get("result") or ""
    m = re.search(r"```json\s*(.*?)```", txt, re.S)
    try:
        arr = json.loads(m.group(1) if m else txt)
    except (json.JSONDecodeError, AttributeError):
        arr = []
    (od / f"b{bno}.parsed.json").write_text(json.dumps(arr, ensure_ascii=False, indent=1), encoding="utf-8")
    return {"batch": bno, "codes": codes, "cost_usd": j.get("total_cost_usd"), "secs": round(time.time() - t0),
            "turns": j.get("num_turns"), "n_out": len(arr), "error": None if arr else "no json parsed"}


def make_batches(ids, cases, size):
    """Ayni serinin onek (F) ve tam (H) halleri ayni cagriya dusmez (gelecegi gormesin)."""
    fam = lambda i: cases[i].get("parent") or i  # noqa: E731
    order = sorted(ids, key=lambda i: hashlib.sha1(i.encode()).hexdigest())
    batches = []
    for i in order:
        for b in batches:
            if len(b) < size and all(fam(x) != fam(i) for x in b):
                b.append(i)
                break
        else:
            batches.append([i])
    return batches


def calistir(tag, ids, size, workers=3, skip=None):
    cases = load_cases()
    batches = make_batches(ids, cases, size)
    stamp = time.strftime("%m%d%H%M")
    print("batches:", batches)
    res = []
    with cf.ThreadPoolExecutor(max_workers=workers) as pool:
        futs = [pool.submit(run_batch, [code_of(i) for i in b], tag, f"{stamp}_{n}", skip) for n, b in enumerate(batches)]
        for f in cf.as_completed(futs):
            r = f.result()
            print(r)
            res.append(r)
    log = OUT / tag / "calisma.json"
    old = json.loads(log.read_text(encoding="utf-8")) if log.exists() else []
    log.write_text(json.dumps(old + res, ensure_ascii=False, indent=1), encoding="utf-8")
    print("cost this run: $%.3f" % sum(r.get("cost_usd") or 0 for r in res))


# ---------------- puanla ----------------
def norm_lab(s):
    s = re.sub(r"[()\s]", "", str(s)).upper()
    return {"I": "1", "II": "2", "III": "3", "IV": "4", "V": "5"}.get(s, s)


def pidx(p):
    try:
        return int(str(p).strip().lstrip("Pp").rstrip("?"))
    except ValueError:
        return None


def score_count(cnt, key):
    if not isinstance(cnt, dict):
        return {"family": None, "dir_ok": False, "fam_ok": False, "rate": 0.0, "strict": 0.0, "n": 0}
    pat = str(cnt.get("pattern", "")).lower().replace(" ", "_")
    fam = FAMILY.get(pat, pat)
    labs = {norm_lab(k): pidx(v) for k, v in (cnt.get("labels") or {}).items()}
    pts = [p for p in key["points"] if p["pivot"]]
    ok = strict = 0
    for p in pts:
        want, got = pidx(p["pivot"]), labs.get(norm_lab(p["label"]))
        if got is not None and abs(got - want) <= 2:   # ayni tip komsu pivot (+-1 salinim)
            ok += 1
        if got is not None and got == want:
            strict += 1
    n = len(pts)
    return {"pattern": pat, "family": fam, "fam_ok": fam == key["family"],
            "dir_ok": str(cnt.get("direction", "")).lower() == key["direction"],
            "rate": round(ok / n, 2) if n else 0.0, "strict": round(strict / n, 2) if n else 0.0, "n": n}


def inval_ok(out, key):
    """Iptal fiyati tutarli mi: (a) kendi ana sayiminda etiketledigi bir pivotun fiyatina (+-0.5%) denk (kural
    seviyesi bir dalga ucudur); (b) sayim 'in_progress' ise sonraki bacak yonuyle uyumlu tarafta (yukari bacak ->
    iptal son kapanisin altinda; asagi -> ustunde)."""
    try:
        pr = out["primary"]
        price = float(pr["invalidation"]["price"])
        nd = out["next_leg"]["direction"]
    except (KeyError, TypeError, ValueError):
        return None
    own = [key["pivot_prices"].get(f"P{pidx(v)}") for v in (pr.get("labels") or {}).values()]
    near = any(v and abs(price / v - 1) <= 0.005 for v in own)
    if out.get("status") == "in_progress":
        side = price < key["last_close"] if nd == "up" else price > key["last_close"]
        return bool(near and side)
    return bool(near)


def puanla(tag, ids):
    cases = load_cases()
    outs = {}
    for f in sorted((OUT / tag).glob("b*.parsed.json")):
        for o in json.loads(f.read_text(encoding="utf-8")):
            if isinstance(o, dict) and o.get("case"):
                outs[o["case"]] = o
    rows = []
    for cid in ids:
        key = json.loads((KEY / f"{cid}.json").read_text(encoding="utf-8"))
        o = outs.get(key["code"])
        if not o:
            rows.append({"id": cid, "verdict": "no_output"})
            continue
        pr, al = score_count(o.get("primary"), key), score_count(o.get("alternate"), key)
        good = lambda s: s["fam_ok"] and s["dir_ok"] and s["rate"] >= 0.67  # noqa: E731
        if good(pr):
            v = "primary"
        elif good(al):
            v = "alternate"
        elif (pr["fam_ok"] and pr["dir_ok"]) or max(pr["rate"], al["rate"]) >= 0.5:
            v = "partial"
        else:
            v = "miss"
        nl = (o.get("next_leg") or {}).get("direction")
        truth = key["next_given"] or key["next_data"]
        rows.append({"id": cid, "set": key["set"], "instrument": key["instrument"], "verdict": v,
                     "instr": f"{key['direction']} {key['family']}",
                     "ekrem_primary": f"{o.get('primary', {}).get('direction')} {pr.get('pattern')}",
                     "ekrem_alt": f"{(o.get('alternate') or {}).get('direction')} {al.get('pattern')}",
                     "weight": (o.get("primary") or {}).get("weight"), "lab_rate_p": pr["rate"], "lab_rate_a": al["rate"],
                     "strict_p": pr["strict"], "status": o.get("status"), "next_ekrem": nl, "next_true": truth,
                     "next_ok": (nl == truth) if truth else None, "instructor_next": key["instructor_next"],
                     "next_data": key["next_data"], "inval_ok": inval_ok(o, key),
                     "ekrem_labels_p": (o.get("primary") or {}).get("labels"),
                     "instr_labels": {p["label"]: p["pivot"] for p in key["points"]}, "why": o.get("why")})
    sc = [r for r in rows if r["verdict"] != "no_output"]
    struct = [r for r in sc if r["id"].startswith("H")]
    fc = [r for r in sc if r.get("next_ok") is not None]

    def share(rs, f):
        return f"{sum(1 for r in rs if f(r))}/{len(rs)}" if rs else "0/0"
    summ = {"n": len(sc),
            "structure_cases": len(struct),
            "primary_match": share(struct, lambda r: r["verdict"] == "primary"),
            "primary_or_alt": share(struct, lambda r: r["verdict"] in ("primary", "alternate")),
            "partial": share(struct, lambda r: r["verdict"] == "partial"),
            "miss": share(struct, lambda r: r["verdict"] == "miss"),
            "forecast_cases_F": share([r for r in fc if r["id"].startswith("F")], lambda r: r["next_ok"]),
            "next_leg_all": share(fc, lambda r: r["next_ok"]),
            "invalidation_consistent": share([r for r in sc if r["inval_ok"] is not None], lambda r: r["inval_ok"])}
    od = OUT / tag
    (od / "puan.json").write_text(json.dumps({"summary": summ, "rows": rows}, ensure_ascii=False, indent=1),
                                  encoding="utf-8")
    for r in rows:
        print({k: r.get(k) for k in ("id", "set", "verdict", "instr", "ekrem_primary", "ekrem_alt", "lab_rate_p",
                                     "lab_rate_a", "next_ekrem", "next_true", "inval_ok")})
    print(json.dumps(summ, indent=1))
    log = od / "calisma.json"
    if log.exists():
        print("cost $%.3f" % sum(r.get("cost_usd") or 0 for r in json.loads(log.read_text(encoding="utf-8"))))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["hazirla", "calistir", "puanla", "hepsi"])
    ap.add_argument("--tag", default="once")
    ap.add_argument("--set", choices=["lesson", "heldout"])
    ap.add_argument("--only")
    ap.add_argument("--batch", type=int, default=4)
    ap.add_argument("--skip", help="bilgi dosyasi adi; bu kosuda okunmaz (gurultu/karsilastirma olcumu)")
    a = ap.parse_args()
    cases = load_cases()
    ids = [i for i, c in cases.items() if (not a.set or c["set"] == a.set) and (not a.only or i in a.only.split(","))]
    if a.cmd in ("hazirla", "hepsi"):
        hazirla(ids)
    if a.cmd in ("calistir", "hepsi"):
        calistir(a.tag, ids, a.batch, skip=a.skip)
    if a.cmd in ("puanla", "hepsi"):
        puanla(a.tag, ids)


if __name__ == "__main__":
    main()
