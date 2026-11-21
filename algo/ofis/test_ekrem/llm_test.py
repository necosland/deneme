"""Ekrem (trader-elliott) LLM filter test on noktalar.json (pre-registration: llm_plan.md). Paper only, no keys.

  python llm_test.py hazirla                 # snap_llm/<code>.json (shown to Ekrem) + llm_meta.json (hidden)
  python llm_test.py calistir --tag pilot --n 6 [--cap 12]
  python llm_test.py calistir --tag full [--cap 12]      # skips points already answered in --reuse tags
  python llm_test.py puanla --tags pilot,full            # -> llm_sonuc.json
"""
import argparse
import concurrent.futures as cf
import hashlib
import json
import os
import pathlib
import subprocess
import sys
import threading
import time

import numpy as np
import pandas as pd

HERE = pathlib.Path(__file__).resolve().parent
OFIS = HERE.parent
sys.path.insert(0, str(OFIS))
sys.path.insert(0, str(HERE))
import elliott_say as E  # noqa: E402
import ortak as O  # noqa: E402
from veri_topla import atr, rsi, ema, pct, r5, structure, dump  # noqa: E402
import kod_test as K  # noqa: E402

SNAP = HERE / "snap_llm"
OUT = HERE / "cikti_llm"
META = HERE / "llm_meta.json"
NOWIN = getattr(subprocess, "CREATE_NO_WINDOW", 0)
FAKE = pd.Timestamp("2001-06-01", tz="UTC")
GAP_DAYS = 460
BATCH = 6
LIM = {"min_rr_t1": 1.5, "min_stop_atr4h": 0.5, "max_confidence": 80, "event_blackout_h": 12}
LEGEND = {
    "structure.pivots": "[time, price, HH/HL/LH/LL, first_close_beyond_time, first_wick_sweep_time(before any close "
                        "beyond), rsi14_at_pivot]; confirmed by k*ATR14 reversal (1d k=3, 4h k=2)",
    "current_leg_extreme": "unconfirmed extreme of the running leg (H?/L?)",
    "candles": "closed candles only, times are open times UTC",
    "elliott": "code impulse count (elliott_say.py, 4h+1d multi-degree zigzag): state w3_setup/w3_in_progress/"
               "w5_setup/impulse_done/corrective_or_unclear, trigger, invalidation, targets, waves [label,time,price], "
               "alts; backtest: no edge, map not signal"}
VIEW_NOTE = ("Trimmed snapshot for role 'elliott' (offline replay test). Omitted ON PURPOSE (not missing data, do not "
             "list in data_gaps): charts, candles 1h/15m, structure 1h, levels, fvg, equal_hl, vp, avwap_1d, derivs, "
             "macro, sentiment, qvol. Prices rescaled, dates shifted, symbol anonymized.")


def code_of(pid):
    return "K" + hashlib.sha1(("ekrem-llm-" + pid).encode()).hexdigest()[:8].upper() + "USDT"  # v2: 8 hex (4-5 hex collided N015/N208)


def cut_frames(d4, d1, cut):
    i = int(d4.index.get_loc(cut))
    close_t = cut + pd.Timedelta(hours=4)
    return i, d4.iloc[max(0, i - 499):i + 1], d1[d1.index + pd.Timedelta(days=1) <= close_t].tail(400)


def rows(df, n, day):
    d = df.tail(n)
    f = "%Y-%m-%d" if day else "%Y-%m-%d %H:%M"
    return {"cols": ["open_time_utc", "o", "h", "l", "c"],
            "rows": [[t.strftime(f), r5(o), r5(h), r5(l), r5(c)]
                     for t, (o, h, l, c) in zip(d.index, d[["open", "high", "low", "close"]].to_numpy())]}


def weekly(d1, n=12):
    w = d1.resample("W-MON", label="left", closed="left").agg(
        {"open": "first", "high": "max", "low": "min", "close": "last"}).dropna().tail(n)
    o = rows(w, n, True)
    o["note"] = "built from closed daily candles; last row = current week, incomplete"
    return o


def ctx(h4, d1):
    c = d1.close
    return {"last_close": r5(h4.close.iloc[-1]), "chg_24h_pct": pct(h4.close.iloc[-1], h4.close.iloc[-7]),
            "chg_7d_pct": pct(c.iloc[-1], c.iloc[-8]), "sma200_1d": r5(c.rolling(200).mean().iloc[-1]),
            "ema20_50_200_1d": [r5(ema(c, n).iloc[-1]) for n in (20, 50, 200)],
            "ema20_50_4h": [r5(ema(h4.close, n).iloc[-1]) for n in (20, 50)],
            "atr14": {"1d": r5(atr(d1).iloc[-1]), "4h": r5(atr(h4).iloc[-1])},
            "rsi14": {"1d": r5(rsi(c).iloc[-1]), "4h": r5(rsi(h4.close).iloc[-1])}}


def hazirla():
    SNAP.mkdir(exist_ok=True)
    pts = json.loads((HERE / "noktalar.json").read_text(encoding="utf-8"))["points"]
    data = {s: (K.load(s, "4h"), K.load(s, "1d")) for s in K.MAIN}
    meta, mism = {}, 0
    for p in pts:
        d4, d1 = data[p["symbol"]]
        cut = pd.Timestamp(p["cut_utc"], tz="UTC")
        i, h4, dd = cut_frames(d4, d1, cut)
        s = 1000.0 / float(h4.close.iloc[-1])
        off = pd.Timedelta(days=7 * ((cut - FAKE).days // 7))
        def sc(df):
            x = df.copy()
            x[["open", "high", "low", "close"]] *= s
            x.index = x.index - off
            return x
        h4s, d1s = sc(h4), sc(dd)
        el = E.analyze({"4h": h4s, "1d": d1s})
        k = p["_key_code"]
        if (el.get("state"), el.get("dir"), el.get("tf")) != (k.get("state"), k.get("dir"), k.get("tf")):
            mism += 1
        code = code_of(p["id"])
        asof = (cut - off + pd.Timedelta(hours=4)).strftime("%Y-%m-%d %H:%M")
        a = {"ctx": ctx(h4s, d1s),
             "structure": {"1d": structure(d1s, "1d", 12), "4h": structure(h4s, "4h", 12)},
             "elliott": el,
             "candles": {"1w": weekly(d1s), "1d": rows(d1s, 30, True), "4h": rows(h4s, 30, False)}}
        snap = {"asof_utc": asof, "generated_utc": asof, "mode": "replay_test", "legend": LEGEND,
                "assets": {code: a}, "macro": {"calendar_usd_high": None}, "errors": [], "_view": VIEW_NOTE}
        (SNAP / f"{code}.json").write_text(dump(snap) + "\n", encoding="utf-8")
        meta[p["id"]] = {"code": code, "sym": p["symbol"], "cut": p["cut_utc"], "i": i, "scale": s, "asof": asof,
                         "setup": p["_key_setup"], "key_state": k["state"], "el": el,
                         "last_close": a["ctx"]["last_close"], "atr4h": a["ctx"]["atr14"]["4h"]}
    META.write_text(json.dumps(meta, ensure_ascii=False, indent=0), encoding="utf-8")
    print("points", len(meta), "state mismatch vs key", mism)


# ---------------- calistir ----------------
HEAD = """TEST MODE - offline replay of your live round (paper research, no orders). Each SNAPSHOT below is an independent, anonymized past moment of a crypto pair: prices rescaled (last 4h close = 1000), dates shifted, symbol replaced by a code. Do not try to identify the market or date; use only the snapshot.
Treat each snapshot exactly like a live round with PREV=none OPEN=none CHARTS=none (no charts in this test; skip chart steps). LIMITS={lim}
Read your INDEX ({index}) and its every-round files once, then every snapshot. Snapshots are unrelated to each other.
Final message: only one ```json array with exactly one block per snapshot (asset = its code, asof_utc = its asof_utc), schema as in cikti-semasi.md.
"""


def run_batch(pids, meta, tag, bno):
    exe = O.find_claude()
    head = HEAD.format(lim=" ".join(f"{k}={v}" for k, v in LIM.items()),
                       index=O.AGENT_BILGI / "trader-elliott" / "INDEX.md")
    lines = [f"SNAPSHOT={SNAP / (meta[p]['code'] + '.json')} ASSETS={meta[p]['code']}" for p in pids]
    prompt = head + "\n".join(lines)
    od = OUT / tag
    od.mkdir(parents=True, exist_ok=True)
    (od / f"b{bno}_prompt.txt").write_text(prompt, encoding="utf-8")
    cmd = [exe, "-p", "--agent", "trader-elliott", "--output-format", "json", "--permission-mode", "dontAsk",
           "--tools", "Read", "--allowedTools", "Read", "--add-dir", str(O.AGENT_BILGI), "--add-dir", str(SNAP),
           "--no-session-persistence"]
    env = {k: v for k, v in os.environ.items() if k not in ("CLAUDECODE", "CLAUDE_CODE_ENTRYPOINT")}
    t0 = time.time()
    try:
        p = subprocess.run(cmd, cwd=str(SNAP), input=prompt.encode("utf-8"), capture_output=True, env=env,
                           creationflags=NOWIN, timeout=1200)
    except subprocess.TimeoutExpired:
        return {"batch": bno, "pids": pids, "cost_usd": 0, "error": "timeout"}
    out = p.stdout.decode("utf-8", "replace")
    (od / f"b{bno}.out.json").write_text(out, encoding="utf-8")
    try:
        j = json.loads(out)
    except json.JSONDecodeError:
        return {"batch": bno, "pids": pids, "cost_usd": 0, "error": (out[:300] + p.stderr.decode("utf-8", "replace")[:300])}
    arr = O.extract_json(j.get("result") or "") or []
    if isinstance(arr, dict):
        arr = [arr]
    (od / f"b{bno}.parsed.json").write_text(json.dumps(arr, ensure_ascii=False, indent=1), encoding="utf-8")
    got = {b.get("asset") for b in arr if isinstance(b, dict)}
    return {"batch": bno, "pids": pids, "cost_usd": j.get("total_cost_usd") or 0, "secs": round(time.time() - t0),
            "turns": j.get("num_turns"), "n_out": len(arr),
            "missing": [p for p in pids if meta[p]["code"] not in got], "error": None if arr else "no json parsed"}


def make_batches(pids, meta, size, seed):
    rng = np.random.default_rng(seed)
    order = list(rng.permutation(pids))
    batches = []
    for p in order:
        t = pd.Timestamp(meta[p]["cut"])
        for b in batches:
            if len(b) < size and all(abs((t - pd.Timestamp(meta[x]["cut"])).days) > GAP_DAYS for x in b):
                b.append(p)
                break
        else:
            batches.append([p])
    return batches


def done_pids(tags, meta):
    code2p = {m["code"]: p for p, m in meta.items()}
    got = set()
    for tg in tags:
        for f in (OUT / tg).glob("b*.parsed.json"):
            for b in json.loads(f.read_text(encoding="utf-8")):
                if isinstance(b, dict) and b.get("asset") in code2p:
                    got.add(code2p[b["asset"]])
    return got


def spent(tags):
    tot = 0.0
    for tg in tags:
        lg = OUT / tg / "calisma.json"
        if lg.exists():
            tot += sum(r.get("cost_usd") or 0 for r in json.loads(lg.read_text(encoding="utf-8")))
    return tot


def calistir(tag, n, cap, reuse, workers=3, seed=5):
    meta = json.loads(META.read_text(encoding="utf-8"))
    alltags = sorted({tag, *reuse} | {d.name for d in OUT.glob("*") if d.is_dir()}) if OUT.exists() else [tag]
    base = spent(alltags)
    skip = done_pids(reuse, meta)
    pids = [p for p in sorted(meta) if p not in skip]
    if n:   # pilot: 3 setup + 3 non-setup, spread
        rng = np.random.default_rng(seed)
        s = [p for p in pids if meta[p]["setup"]]
        o = [p for p in pids if not meta[p]["setup"]]
        pids = list(rng.choice(s, n // 2, replace=False)) + list(rng.choice(o, n - n // 2, replace=False))
    batches = make_batches(pids, meta, BATCH, seed)
    print(f"spent so far ${base:.2f}; {len(pids)} points in {len(batches)} batches", flush=True)
    stamp = time.strftime("%m%d%H%M")
    res, lock, tot = [], threading.Lock(), [base]
    per_batch = [0.4]
    def job(nb, b):
        with lock:
            if tot[0] + per_batch[0] * workers > cap:
                return {"batch": f"{stamp}_{nb}", "pids": b, "cost_usd": 0, "error": "skipped: cost cap"}
        r = run_batch(b, meta, tag, f"{stamp}_{nb}")
        with lock:
            tot[0] += r.get("cost_usd") or 0
            if r.get("cost_usd"):
                per_batch[0] = max(per_batch[0], r["cost_usd"])
        return r
    with cf.ThreadPoolExecutor(max_workers=workers) as pool:
        futs = [pool.submit(job, nb, b) for nb, b in enumerate(batches)]
        for f in cf.as_completed(futs):
            r = f.result()
            print({k: r.get(k) for k in ("batch", "cost_usd", "secs", "n_out", "missing", "error")}, flush=True)
            res.append(r)
    (OUT / tag).mkdir(parents=True, exist_ok=True)
    lg = OUT / tag / "calisma.json"
    old = json.loads(lg.read_text(encoding="utf-8")) if lg.exists() else []
    lg.write_text(json.dumps(old + res, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"cost this run ${sum(r.get('cost_usd') or 0 for r in res):.3f}; total ${tot[0]:.3f}")


# ---------------- puanla ----------------
def fill_and_sim(S, i, d, etype, eprice, stop, t1, t2):
    """Real-price inputs. Entry on bar i+1 (market open / stop / limit, next bar only). Returns dict or None."""
    Sd = S[d]
    b = i + 1
    if b >= len(Sd["O"]):
        return None
    Ou, Hu, Lu = Sd["O"][b], Sd["H"][b], Sd["L"][b]
    if etype == "market":
        Eu = Ou
    elif etype == "stop":
        Pu = d * eprice
        Eu = Ou if Ou >= Pu else (Pu if Hu >= Pu else None)
    else:
        Pu = d * eprice
        Eu = Ou if Ou <= Pu else (Pu if Lu <= Pu else None)
    if Eu is None:
        return None
    Su, T1u, T2u = d * stop, d * t1, d * t2
    if not (Su < Eu < T1u):
        return None
    r, ex = K.sim(Sd, b, Eu, Su, T1u, T2u)
    risk = Eu - Su
    r -= 2 * K.COST * abs(Eu) / risk
    return {"i0": b, "d": d, "R": float(r), "exit_i": int(ex), "risk_pct": risk / abs(Eu), "t1_pct": (T1u - Eu) / abs(Eu),
            "t2_pct": (T2u - Eu) / abs(Eu)}


def code_trade(m):
    """Baseline 2: mechanical trade from the code's primary w3/w5 setup (scaled levels)."""
    el = m["el"]
    st = el.get("state")
    if st not in ("w3_setup", "w5_setup"):
        return None, "not setup"
    side = "long" if el["dir"] == "up" else "short"
    stop = el.get("invalidation") if st == "w3_setup" else el.get("stop_tight")
    if stop is None or not el.get("targets"):
        return None, "no levels"
    entry = {"type": "market", "price": None} if el.get("confirmed") else {"type": "stop", "price": el["trigger"]}
    e = m["last_close"] if el.get("confirmed") else el["trigger"]
    if e is None:
        return None, "no trigger"
    sg = 1 if side == "long" else -1
    tg = el["targets"]
    k = next((j for j, t in enumerate(tg) if sg * (e - stop) > 0 and sg * (t - e) / (sg * (e - stop)) >= LIM["min_rr_t1"]), None)
    if k is None:
        return None, "rr<1.5"
    targets = tg[k:k + 2]
    errs = O.geometry_errors(side, entry, stop, targets, m["last_close"], m["atr4h"], LIM)
    if errs:
        return None, errs[0][:40]
    return {"side": side, "entry": entry, "stop": stop, "targets": targets}, None


def puanla(tags):
    meta = json.loads(META.read_text(encoding="utf-8"))
    code2p = {m["code"]: p for p, m in meta.items()}
    blocks = {}
    for tg in tags:
        for f in sorted((OUT / tg).glob("b*.parsed.json")):
            for b in json.loads(f.read_text(encoding="utf-8")):
                if isinstance(b, dict) and b.get("asset") in code2p:
                    blocks[code2p[b["asset"]]] = b
    frames = {s: K.load(s, "4h") for s in K.MAIN}
    S = {s: {d: E.space(df, d) for d in (1, -1)} for s, df in frames.items()}
    rows_, ek, cd = [], [], []
    for p, m in sorted(meta.items()):
        b = blocks.get(p)
        rec = {"id": p, "sym": m["sym"], "cut": m["cut"], "setup": m["setup"], "code_state": m["el"].get("state"),
               "answered": b is not None}
        bias = (b or {}).get("bias", "flat")
        rec["bias"] = bias
        rec["ekrem_setup"] = (b or {}).get("setup")
        rec["conf"] = (b or {}).get("confidence")
        if b and bias in ("long", "short"):
            errs = O.geometry_errors(bias, b.get("entry"), b.get("stop"), b.get("targets") or [], m["last_close"],
                                     m["atr4h"], LIM)
            rec["geom_err"] = errs[0] if errs else None
            if not errs:
                s, d = m["scale"], 1 if bias == "long" else -1
                tg = b["targets"]
                en = b["entry"]
                tr = fill_and_sim(S[m["sym"]], m["i"], d, en["type"], (en.get("price") or 0) / s, b["stop"] / s,
                                  tg[0] / s, (tg[1] if len(tg) > 1 else tg[0]) / s)
                rec["ekrem_trade"] = tr
                if tr:
                    ek.append({**tr, "sym": m["sym"], "id": p})
        ct, why = code_trade(m) if b is not None else (None, "point not answered")
        rec["code_skip"] = why
        if ct:
            s, d = m["scale"], 1 if ct["side"] == "long" else -1
            tg = ct["targets"]
            tr = fill_and_sim(S[m["sym"]], m["i"], d, ct["entry"]["type"], (ct["entry"].get("price") or 0) / s,
                              ct["stop"] / s, tg[0] / s, (tg[1] if len(tg) > 1 else tg[0]) / s)
            rec["code_trade"] = tr
            if tr:
                cd.append({**tr, "sym": m["sym"], "id": p})
        rows_.append(rec)
    for x in ek + cd:
        x["per"] = "is" if frames[x["sym"]].index[x["i0"]] < K.SPLIT else "oos"
    ek_ids = {x["id"] for x in ek}
    rep = {"plan": "llm_plan.md", "tags": tags, "answered": sum(r["answered"] for r in rows_), "points": len(rows_),
           "cost_usd": round(spent(tags), 3)}
    setup = [r for r in rows_ if r["setup"] and r["answered"]]
    non = [r for r in rows_ if not r["setup"] and r["answered"]]
    rep["ekrem_dir_votes"] = sum(r["bias"] != "flat" for r in rows_)
    rep["ekrem_dir_votes_valid_geom"] = sum(1 for r in rows_ if r["bias"] != "flat" and not r.get("geom_err"))
    rep["flat_rate_nonsetup_pct"] = round(100 * sum(r["bias"] == "flat" for r in non) / max(1, len(non)), 1)
    rep["vote_rate_setup_pct"] = round(100 * sum(r["bias"] != "flat" for r in setup) / max(1, len(setup)), 1)
    rep["E1_ekrem"] = K.stats([x["R"] for x in ek])
    rep["E2_code_setups"] = K.stats([x["R"] for x in cd])
    rep["E2b_code_where_ekrem_traded"] = K.stats([x["R"] for x in cd if x["id"] in ek_ids])
    rep["E2c_code_where_ekrem_flat"] = K.stats([x["R"] for x in cd if x["id"] not in ek_ids])
    if ek:
        rng = np.random.default_rng(7)
        rngs = {}
        for sym, df in frames.items():
            idx = df.index
            a, bb, c = idx.searchsorted(K.START), idx.searchsorted(K.SPLIT), len(idx) - K.TSTOP - 2
            rngs[sym] = {"is": (a, bb), "oos": (bb, c)}
        means = []
        for _ in range(K.REPS):
            rr = []
            for x in ek:
                lo, hi = rngs[x["sym"]][x["per"]]
                i0 = int(rng.integers(lo, hi))
                Sd = S[x["sym"]][x["d"]]
                Eu = Sd["O"][i0]
                ab = abs(Eu)
                r, _ = K.sim(Sd, i0, Eu, Eu - x["risk_pct"] * ab, Eu + x["t1_pct"] * ab, Eu + x["t2_pct"] * ab)
                rr.append(r - 2 * K.COST / x["risk_pct"])
            means.append(np.mean(rr))
        means = np.array(means)
        rep["E3_random"] = {"avg_R_mean": round(float(means.mean()), 3),
                            "avg_R_p95": round(float(np.percentile(means, 95)), 3),
                            "p_random_ge_ekrem": round(float((means >= rep["E1_ekrem"]["avg_R"]).mean()), 3)}
    e1, e2 = rep["E1_ekrem"], rep["E2_code_setups"]
    ok = (e1.get("n", 0) >= 10 and e1["avg_R"] > 0 and e2.get("n") and e1["avg_R"] > e2["avg_R"]
          and rep.get("E3_random", {}).get("p_random_ge_ekrem", 1) < 0.05 and rep["flat_rate_nonsetup_pct"] >= 90)
    rep["verdict"] = ("too few trades to judge" if e1.get("n", 0) < 10 else ("pass (worth live paper tracking)" if ok
                      else "not shown"))
    (HERE / "llm_sonuc.json").write_text(json.dumps({"report": rep, "rows": rows_}, ensure_ascii=False, indent=1),
                                         encoding="utf-8")
    print(json.dumps(rep, indent=1))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("mode")
    ap.add_argument("--tag", default="pilot")
    ap.add_argument("--tags", default="pilot")
    ap.add_argument("--n", type=int, default=0)
    ap.add_argument("--cap", type=float, default=12.0)
    ap.add_argument("--reuse", default="")
    a = ap.parse_args()
    if a.mode == "hazirla":
        hazirla()
    elif a.mode == "calistir":
        calistir(a.tag, a.n, a.cap, [x for x in a.reuse.split(",") if x])
    else:
        puanla([x for x in a.tags.split(",") if x])
