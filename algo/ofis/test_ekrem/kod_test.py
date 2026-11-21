"""Kod Elliott testi (on kayit: kod_plan.md). LLM yok, ag yok (yalniz algo/cache), gercek emir yok.

  python algo/ofis/test_ekrem/kod_test.py backtest   -> kod_sonuc.json + kod_islemler.csv
  python algo/ofis/test_ekrem/kod_test.py backtest2  -> kod_sonuc2.json + kod_islemler2.csv (v2: w3 T1 1.618, T2 2.618)
  python algo/ofis/test_ekrem/kod_test.py noktalar   -> noktalar.json (Ekrem'in sonraki LLM testi icin ~200 kesit)
"""
import json
import pathlib
import sys

import numpy as np
import pandas as pd

HERE = pathlib.Path(__file__).resolve().parent
OFIS = HERE.parent
sys.path.insert(0, str(OFIS))
import elliott_say as E  # noqa: E402

CACHE = OFIS.parent / "cache"
MAIN = ["BTCUSDT", "ETHUSDT"]
ALTS = ["XRPUSDT", "BNBUSDT", "SOLUSDT", "DOGEUSDT", "ADAUSDT", "TRXUSDT", "LINKUSDT", "AVAXUSDT", "LTCUSDT", "BCHUSDT"]
KS = (1.5, 2.5, 4.0)
START, SPLIT = pd.Timestamp("2020-01-01", tz="UTC"), pd.Timestamp("2024-01-01", tz="UTC")
TSTOP = 60
COST = 0.001          # taraf basi: %0.05 komisyon + %0.05 kayma
MIN_SCORE = 50
REPS = 200
V2 = False          # 2026-11-21 v2 (kod_plan.md): w3 T1 = 1.618 x w1, T2 = 2.618 x w1; "gec kaldi" esigi 1.0 x w1
SUF = ""


def load(sym, iv="4h"):
    def rd(s):
        return pd.read_csv(CACHE / f"{s}_{iv}.csv", index_col=0, parse_dates=True)
    if sym == "BCHUSDT":
        a, b = rd("BCHABCUSDT"), rd("BCHUSDT")
        df = pd.concat([a[a.index < b.index[0]], b])
    else:
        df = rd(sym)
    df.index = pd.to_datetime(df.index, utc=True)
    return df[~df.index.duplicated()].sort_index()


# ---------------- sinyaller (yuruyen, sizintisiz) ----------------
def signals(df, sym):
    n, idx = len(df), df.index
    i_start = int(idx.searchsorted(START))
    S = {d: E.space(df, d) for d in (1, -1)}
    out = []
    for k in KS:
        piv, _ = E.zigzag(S[1]["H"], S[1]["L"], S[1]["A"], k)
        for d in (1, -1):
            Sd = S[d]
            Zf = E.to_space(piv, d)
            for m in range(len(Zf)):
                ci = Zf[m][3]
                nxt = Zf[m + 1][3] if m + 1 < len(Zf) else n
                if nxt <= i_start:
                    continue
                Z = Zf[max(0, m + 1 - E.KEEP_PIV):m + 1]     # yalniz ci aninda onayli pivotlar
                cs = E.candidates(Z, Sd)
                for kind in ("w3", "w5"):
                    ok = [c for c in cs if c["kind"] == kind and c["score"] >= MIN_SCORE]
                    if not ok:
                        continue
                    c = max(ok, key=lambda x: x["score"])
                    dead = c["P"][2] if kind == "w3" else c["P"][4]
                    T1, T2 = c["T"][0], c["T"][1]
                    late = T1
                    if V2 and kind == "w3":
                        T1, T2 = c["T"][1], c["T"][2]
                    lo = np.inf
                    for t in range(c["I"][-1] + 1, nxt):
                        lo = min(lo, Sd["L"][t])
                        if lo < dead or Sd["H"][t] >= late:
                            break
                        if t < ci:
                            continue
                        if Sd["C"][t] > c["trig"]:
                            if t >= i_start and t + 1 < n:
                                out.append({"sym": sym, "kind": kind, "d": d, "k": k, "score": c["score"], "t": t,
                                            "stop": c["inval"], "T1": T1, "T2": T2})
                            break
    return out


def sim(Sd, i0, Eu, Su, T1, T2):
    """Yon uzayinda long simulasyonu. Donus: (R, cikis_mumu)."""
    O, H, L, C = Sd["O"], Sd["H"], Sd["L"], Sd["C"]
    n = len(C)
    risk = Eu - Su
    half, R = False, 0.0
    last = min(i0 + TSTOP, n) - 1
    for b in range(i0, last + 1):
        if not half:
            if L[b] <= Su:
                px = O[b] if (b > i0 and O[b] < Su) else Su
                return R + (px - Eu) / risk, b
            if H[b] >= T1:
                half = True
                R += 0.5 * (T1 - Eu) / risk
                if H[b] >= T2:
                    return R + 0.5 * (T2 - Eu) / risk, b
        else:
            if L[b] <= Eu:
                px = O[b] if O[b] < Eu else Eu
                return R + 0.5 * (px - Eu) / risk, b
            if H[b] >= T2:
                return R + 0.5 * (T2 - Eu) / risk, b
    return R + (0.5 if half else 1.0) * (C[last] - Eu) / risk, last


def trades(sigs, S):
    res, busy = [], {}
    for s in sorted(sigs, key=lambda x: (x["t"], -x["score"])):
        key = (s["sym"], s["kind"])
        i0 = s["t"] + 1
        if busy.get(key, -1) >= i0:
            continue
        Sd = S[s["sym"]][s["d"]]
        Eu = Sd["O"][i0]
        if not (s["stop"] < Eu < s["T1"]):
            continue
        r, ex = sim(Sd, i0, Eu, s["stop"], s["T1"], s["T2"])
        risk = Eu - s["stop"]
        r -= 2 * COST * abs(Eu) / risk
        busy[key] = ex
        res.append({**s, "i0": i0, "entry": abs(Eu), "risk_pct": risk / abs(Eu), "t1_pct": (s["T1"] - Eu) / abs(Eu),
                    "t2_pct": (s["T2"] - Eu) / abs(Eu), "R": r, "exit_i": ex})
    return res


def stats(rs):
    r = np.array(rs, float)
    if len(r) == 0:
        return {"n": 0}
    eq = np.cumsum(r)
    dd = float((eq - np.maximum.accumulate(np.maximum(eq, 0))).min())
    sd = r.std(ddof=1) if len(r) > 1 else np.nan
    return {"n": int(len(r)), "win_pct": round(100 * float((r > 0).mean()), 1), "avg_R": round(float(r.mean()), 3),
            "total_R": round(float(r.sum()), 1), "maxDD_R": round(dd, 1),
            "t": round(float(r.mean() / (sd / np.sqrt(len(r)))), 2) if sd and sd > 0 else None}


def random_baseline(tr, S, frames, rng):
    """Her islem icin ayni varlik, ayni donem yarisi, ayni yon ve geometride rastgele giris."""
    rngs = {}
    for sym, df in frames.items():
        idx = df.index
        a, b, c = idx.searchsorted(START), idx.searchsorted(SPLIT), len(idx) - TSTOP - 2
        rngs[sym] = {"is": (a, b), "oos": (b, c)}
    means = {"all": [], "is": [], "oos": []}
    for _ in range(REPS):
        rr, half = [], []
        for x in tr:
            per = "is" if frames[x["sym"]].index[x["i0"]] < SPLIT else "oos"
            lo, hi = rngs[x["sym"]][per]
            i0 = int(rng.integers(lo, hi))
            Sd = S[x["sym"]][x["d"]]
            Eu = Sd["O"][i0]
            ab = abs(Eu)
            st, t1, t2 = Eu - x["risk_pct"] * ab, Eu + x["t1_pct"] * ab, Eu + x["t2_pct"] * ab
            r, _ = sim(Sd, i0, Eu, st, t1, t2)
            rr.append(r - 2 * COST / x["risk_pct"])
            half.append(per)
        rr, half = np.array(rr), np.array(half)
        means["all"].append(rr.mean())
        for p in ("is", "oos"):
            if (half == p).any():
                means[p].append(rr[half == p].mean())
    return {k: np.array(v) for k, v in means.items()}


def backtest():
    syms = MAIN + ALTS
    frames, S, sigs = {}, {}, []
    for s in syms:
        try:
            df = load(s)
        except FileNotFoundError:
            continue
        frames[s] = df
        S[s] = {d: E.space(df, d) for d in (1, -1)}
        sigs += signals(df, s)
        print(s, len(df), "signals so far", len(sigs), flush=True)
    tr = trades(sigs, S)
    for x in tr:
        x["time"] = str(frames[x["sym"]].index[x["i0"]])
        x["per"] = "2020-23" if frames[x["sym"]].index[x["i0"]] < SPLIT else "2024-26"
    rng = np.random.default_rng(7)
    report = {"plan": "kod_plan.md" + (" (v2 section)" if V2 else ""), "cost_per_side": COST, "assets": list(frames), "groups": {}}

    def grp(name, sel):
        g = [x for x in tr if sel(x)]
        st = {"all": stats([x["R"] for x in g]),
              "2020-23": stats([x["R"] for x in g if x["per"] == "2020-23"]),
              "2024-26": stats([x["R"] for x in g if x["per"] == "2024-26"])}
        if g and name in ("H1_w3_all", "H2_w5_all", "w3_btc_eth", "w5_btc_eth"):
            rb = random_baseline(g, S, frames, rng)
            act = st["all"]["avg_R"]
            st["random"] = {"avg_R_mean": round(float(rb["all"].mean()), 3),
                            "avg_R_p95": round(float(np.percentile(rb["all"], 95)), 3),
                            "p_random_ge_actual": round(float((rb["all"] >= act).mean()), 3)}
            for p, key in (("is", "2020-23"), ("oos", "2024-26")):
                if len(rb[p]) and st[key]["n"]:
                    st["random"][f"{key}_avg_R_mean"] = round(float(rb[p].mean()), 3)
                    st["random"][f"{key}_p"] = round(float((rb[p] >= st[key]["avg_R"]).mean()), 3)
        report["groups"][name] = st

    grp("H1_w3_all", lambda x: x["kind"] == "w3")
    grp("H2_w5_all", lambda x: x["kind"] == "w5")
    grp("w3_btc_eth", lambda x: x["kind"] == "w3" and x["sym"] in MAIN)
    grp("w5_btc_eth", lambda x: x["kind"] == "w5" and x["sym"] in MAIN)
    for kind in ("w3", "w5"):          # kesif dilimleri (gecemez)
        grp(f"x_{kind}_long", lambda x, k=kind: x["kind"] == k and x["d"] == 1)
        grp(f"x_{kind}_short", lambda x, k=kind: x["kind"] == k and x["d"] == -1)
        grp(f"x_{kind}_score70+", lambda x, k=kind: x["kind"] == k and x["score"] >= 70)
        for kk in KS:
            grp(f"x_{kind}_k{kk}", lambda x, k=kind, q=kk: x["kind"] == k and x["k"] == q)
    btc = frames["BTCUSDT"]
    b0 = btc.close.iloc[btc.index.searchsorted(START)]
    report["btc_buy_hold_pct"] = round(float((btc.close.iloc[-1] / b0 - 1) * 100), 1)
    report["data_end"] = str(btc.index[-1])
    (HERE / f"kod_sonuc{SUF}.json").write_text(json.dumps(report, indent=1, ensure_ascii=False), encoding="utf-8")
    pd.DataFrame(tr).drop(columns=["stop", "T1", "T2"]).to_csv(HERE / f"kod_islemler{SUF}.csv", index=False)
    print(json.dumps(report, indent=1))


# ---------------- Ekrem icin kesit noktalari ----------------
def noktalar(step=12, n_target=200, seed=11):
    rng = np.random.default_rng(seed)
    pool = []
    for sym in MAIN:
        d4, d1 = load(sym, "4h"), load(sym, "1d")
        S = {d: E.space(d4, d) for d in (1, -1)}
        i_start = int(d4.index.searchsorted(START))
        for i in range(i_start, len(d4) - TSTOP - 1, step):
            t = d4.index[i]
            close_t = t + pd.Timedelta(hours=4)
            fr = {"4h": d4.iloc[max(0, i - 499):i + 1], "1d": d1[d1.index + pd.Timedelta(days=1) <= close_t].tail(400)}
            a = E.analyze(fr)
            st = a["state"]
            fut = d4.iloc[i + 1:i + 1 + TSTOP]
            c0 = d4.close.iloc[i]
            out = {"max_up_pct": round(float((fut.high.max() / c0 - 1) * 100), 2),
                   "max_down_pct": round(float((fut.low.min() / c0 - 1) * 100), 2),
                   "close_chg_pct": round(float((fut.close.iloc[-1] / c0 - 1) * 100), 2)}
            if st in ("w3_setup", "w5_setup") and a.get("targets"):
                d = 1 if a["dir"] == "up" else -1
                Sd = S[d]
                T1, inv = d * a["targets"][0], d * a["invalidation"]
                hit = None
                for b in range(i + 1, i + 1 + TSTOP):
                    if Sd["L"][b] <= inv:
                        hit = "invalidation"
                        break
                    if Sd["H"][b] >= T1:
                        hit = "T1"
                        break
                out["first_hit_60bars"] = hit
            key = {x: a.get(x) for x in ("state", "dir", "tf", "zz_k", "score", "confirmed", "fresh", "phase",
                                         "trigger", "invalidation", "targets", "waves")}
            pool.append({"symbol": sym, "tf": "4h", "cut_utc": t.strftime("%Y-%m-%d %H:%M"),
                         "cut_note": "last closed 4h bar open time; give only bars <= cut",
                         "year": t.year, "setup": st in ("w3_setup", "w5_setup"),
                         "_key_code": key, "_key_outcome": out})
        print(sym, "pool", len(pool), flush=True)
    pick = []
    years = sorted({p["year"] for p in pool})
    for want_setup in (True, False):
        per_year = int(np.ceil(n_target / 2 / len(years)))
        for y in years:
            g = [p for p in pool if p["setup"] == want_setup and p["year"] == y]
            if not g:
                continue
            sel = rng.choice(len(g), size=min(per_year, len(g)), replace=False)
            pick += [g[j] for j in sorted(sel)]
    pick.sort(key=lambda p: (p["cut_utc"], p["symbol"]))
    for j, p in enumerate(pick):
        p["id"] = f"N{j + 1:03d}"
        p.pop("year")
        p["_key_setup"] = p.pop("setup")
    cnt = pd.Series([p["_key_code"]["state"] for p in pick]).value_counts().to_dict()
    pool_cnt = pd.Series([p["_key_code"]["state"] for p in pool]).value_counts().to_dict()
    doc = {"_format": "Cut points for Ekrem's next blind LLM test. Show the model only symbol/tf and closed bars up to "
                      "cut_utc (plus the same snapshot fields as live). Fields starting with _key_ are the answer key "
                      "(code's count, 60-bar outcome) and must NOT be shown. Generated by kod_test.py noktalar (no LLM).",
           "states_in_pick": cnt, "states_in_pool": pool_cnt, "n": len(pick), "points": pick}
    (HERE / "noktalar.json").write_text(json.dumps(doc, ensure_ascii=False, indent=0), encoding="utf-8")
    print("noktalar", len(pick), cnt)


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "backtest"
    if mode == "backtest2":
        V2, SUF = True, "2"
        backtest()
    elif mode == "backtest":
        backtest()
    else:
        noktalar()
