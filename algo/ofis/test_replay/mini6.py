"""Mini-replay for fix 6 (pre-registration: mini6_plan.md). Paper only; reuses replay.py (sandboxed office modules).
Runs Selin, Bora, Tolga on 8 cached rounds with the exact old prompts; never touches live defter/log/veri.

  python mini6.py run --arm ctrl|new [--workers 6]   # calls (resumable); outputs mini6/raw_<arm>/Rxx/
  python mini6.py score                              # mini6/sonuc.json + mini6/bloklar.csv (all arms)
"""
import argparse
import concurrent.futures as cf
import json
import pathlib
import statistics
import sys

import pandas as pd

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import replay as RP  # noqa: E402  (sandbox + clock patch happen on import)

O, D, T = RP.O, RP.D, RP.T
M6 = HERE / "mini6"
ROUNDS6 = ["R06", "R17", "R19", "R33", "R04", "R12", "R35", "R40"]
EXP3 = ["trader-seviye", "trader-senaryo", "trader-likidite"]
ARMS = ["orig", "ctrl", "new"]


def raw_dir(arm):
    return RP.RAW if arm == "orig" else M6 / f"raw_{arm}"


def run(arm, workers):
    assert arm in ("ctrl", "new")
    RP.RAW = M6 / f"raw_{arm}"
    RP.LOGF = M6 / f"calls_{arm}.json"
    jobs = []
    for code in ROUNDS6:
        for ex in EXP3:
            out = RP.RAW / code / f"{ex}.out.json"
            if out.exists() and '"is_error":false' in out.read_text(encoding="utf-8").replace(" ", ""):
                continue
            prompt = (HERE / "raw" / code / f"prompt_{ex}.txt").read_text(encoding="utf-8")
            jobs.append((code, ex, prompt))
    RP.say(f"arm {arm}: {len(jobs)} calls")
    res = {}
    for i in range(0, len(jobs), workers):
        RP.gate()
        batch = jobs[i:i + workers]
        with cf.ThreadPoolExecutor(max_workers=len(batch)) as pool:
            futs = {pool.submit(RP.run_agent, ex, p, code, RP.T_EXPERT): (code, ex) for code, ex, p in batch}
            for f in cf.as_completed(futs):
                code, ex = futs[f]
                r = f.result()
                RP.log_calls(code, [r])
                res.setdefault(code, {})[ex] = r
                RP.say(arm, code, ex, "err" if r.get("error") else "ok", f"${r.get('cost_usd') or 0:.3f}",
                       r.get("error") or "")
        for code in {c for c, _, _ in batch}:
            old = RP.RAW / code / "experts_res.json"
            prev = json.loads(old.read_text(encoding="utf-8")) if old.exists() else {}
            prev.update(res.get(code, {}))
            O.write_json(old, prev)
    validate(arm)
    RP.say(f"arm {arm} spent ${RP.spent():.2f}")


def validate(arm):
    cfg = dict(RP.FROZEN)
    cfg["assets"] = list(RP.ASSETS)
    vb = O.validator("expert_block")
    for code in ROUNDS6:
        _, ss, _ = RP.load_round(code)
        rd = raw_dir(arm) / code
        resf = rd / "experts_res.json"
        results = json.loads(resf.read_text(encoding="utf-8")) if resf.exists() else {}
        rows = []
        for ex in EXP3:
            r = results.get(ex, {"error": "no result"})
            parsed = O.extract_json(r.get("text")) if not r.get("error") else None
            rr = T.validate_blocks(ex, parsed, ss, cfg, vb) if not r.get("error") else \
                [{"asset": a, "valid": False, "errors": [r["error"]], "block": None} for a in RP.ASSETS]
            for x in rr:
                x["expert"] = ex
                rows.append(x)
        O.write_json(rd / "blocks.json", {"asof_shifted": ss["asof_utc"], "rows": rows, "auto": [], "called": EXP3})


# ---------------- scoring ----------------
def nums(o, lo, hi, out):
    if isinstance(o, dict):
        for k, v in o.items():
            if k in ("atr14", "qvol_avg20_musd", "rsi14", "candles", "charts"):
                continue
            nums(v, lo, hi, out)
    elif isinstance(o, list):
        for v in o:
            nums(v, lo, hi, out)
    elif isinstance(o, (int, float)) and not isinstance(o, bool) and lo <= o <= hi:
        out.append(float(o))
    return out


def struct_flag(b, a, last):
    """True if no snapshot level lies strictly between entry and stop (stop not beyond any structure)."""
    e = O.entry_px(b.get("entry"), last)
    s = b.get("stop")
    if e is None or s is None:
        return None
    src = {k: a.get(k) for k in ("levels", "structure", "fvg", "equal_hl", "vp", "avwap_1d")}
    lv = nums(src, last * 0.8, last * 1.2, [])
    lo, hi = min(e, s), max(e, s)
    return not any(lo < p < hi for p in lv)


def trend_state(a):
    c = a["ctx"]
    e20, e50 = c["ema20_50_4h"]
    piv = [p[2] for p in a["structure"]["4h"]["pivots"]]
    lows = [x for x in piv if x in ("HL", "LL")]
    highs = [x for x in piv if x in ("HH", "LH")]
    if e20 > e50 and c["last_close"] > e50 and lows and lows[-1] == "HL":
        return "up"
    if e20 < e50 and c["last_close"] < e50 and highs and highs[-1] == "LH":
        return "down"
    return "none"


def score_arm(arm, meta):
    cfg = dict(RP.FROZEN)
    cfg["assets"] = list(RP.ASSETS)
    R = RP.FROZEN["risk"]
    band = (cfg.get("measure") or {}).get("flat_band_atr4h", 1.0)
    rows = []
    st = RP.fresh_state()
    ptr = {s: 0 for s in RP.ASSETS}
    for code in sorted(ROUNDS6, key=lambda c: meta["slots"][c]["asof"]):
        snap = json.loads((RP.SNAPS / f"{code}.json").read_text(encoding="utf-8"))
        bj = json.loads((raw_dir(arm) / code / "blocks.json").read_text(encoding="utf-8"))
        asof = pd.Timestamp(meta["slots"][code]["asof"], tz="UTC")
        asof_s = RP.fmt(asof)
        t0 = int(asof.timestamp() * 1000)
        mine = [x for x in bj["rows"] if x.get("expert") in EXP3]
        valid = []
        for x in mine:
            b = RP.shift_obj(x["block"], -1) if isinstance(x["block"], dict) else None
            row = {"arm": arm, "round": code, "regime": meta["slots"][code]["regime"], "expert": x["expert"],
                   "asset": x["asset"], "valid": x["valid"], "errors": "; ".join(x["errors"])[:200]}
            if b is None or b.get("asset") not in RP.ASSETS:
                rows.append({**row, "bias": None})
                continue
            a = snap["assets"][b["asset"]]
            last = a["ctx"]["last_close"]
            row.update(bias=b.get("bias"), setup=b.get("setup"), conf=b.get("confidence"),
                       etype=(b.get("entry") or {}).get("type"), horizon_h=b.get("horizon_h"),
                       trend4h=trend_state(a), rationale=" | ".join(b.get("rationale") or [])[:600])
            if b.get("bias") in ("long", "short"):
                g = O.geometry_errors(b["bias"], b.get("entry"), b.get("stop"), b.get("targets") or [], last,
                                      a["ctx"]["atr14"]["4h"], R)
                row["geom_errors"] = "; ".join(g)
                if b.get("stop") is not None and b.get("targets") and b.get("entry"):
                    rr, cost_r, net = O.rr_cost(b["bias"], b["entry"], b["stop"], b["targets"][0], last, R)
                    row.update(rr_gross=round(rr, 3), rr_net=round(net, 3), cost_r=round(cost_r, 3),
                               stop_atr=round(abs(O.entry_px(b["entry"], last) - b["stop"]) / a["ctx"]["atr14"]["4h"], 3),
                               entry_atr=round(abs(O.entry_px(b["entry"], last) - last) / a["ctx"]["atr14"]["4h"], 3))
                row["stop_no_struct"] = struct_flag(b, a, last)
                row["counter_regime"] = D.counter_regime(b["bias"], a["ctx"])
                try:
                    ok, why = D.vote_check(b, b["asset"], asof_s, cfg, snap)
                except Exception as e:  # noqa: BLE001
                    ok, why = False, type(e).__name__
                row.update(ev_pass=ok, vote_why=why[:160])
                h = int(b.get("horizon_h") or 4)
                c4 = RP.klines_c(b["asset"], "4h", t0 - 15 * 4 * 3600000, t0)
                c1 = RP.klines_c(b["asset"], "1h", t0, t0 + h * 3600000)
                if c1 and c1[0][0] == t0 and len(c1) >= h:
                    trs = [max(c4[i][2], c4[i - 1][4]) - min(c4[i][3], c4[i - 1][4]) for i in range(1, len(c4))]
                    atr = sum(trs[-14:]) / 14
                    sc = D.score_one(b, c1, atr, band)
                    row.update(hit=sc["hit"], path=sc["path"], dir_atr=sc.get("dir_atr"))
                if x["valid"]:
                    valid.append(b)
            rows.append(row)
        created = asof + pd.Timedelta(minutes=20)
        for s in RP.ASSETS:
            RP.advance(st, s, ptr, int(created.timestamp() * 1000))
        RP.SIM_NOW[0] = created.to_pydatetime()
        D.add_shadow(st, valid, EXP3, f"{arm}-{code}", snap, errored=set())
        RP.SIM_NOW[0] = None
    last = max(pd.Timestamp(meta["slots"][c]["asof"], tz="UTC") for c in ROUNDS6)
    end = (last + pd.Timedelta(hours=96)).floor("h")
    for s in RP.ASSETS:
        RP.advance(st, s, ptr, int(end.timestamp() * 1000))
    trades = [{k: t.get(k) for k in ("book", "asset", "side", "status", "entry_type", "entry_price", "fill_px",
                                     "stop0", "targets", "confidence", "created_utc", "fill_utc", "exit_utc",
                                     "exit_reason", "r_mult")} | {"arm": arm} for t in st["trades"]]
    return rows, trades


def summ(rows, trades):
    df = pd.DataFrame(rows)
    d = df[df.bias.isin(["long", "short"])] if len(df) else df
    dv = d[d.valid] if len(d) else d
    closed = [t["r_mult"] for t in trades if t["status"] == "closed" and t["r_mult"] is not None]
    filled = [t for t in trades if t.get("fill_utc")]
    conf = list(dv.conf.dropna()) if len(dv) else []
    hit = dv.hit.dropna() if len(dv) and "hit" in dv else []
    return {"blocks": len(df), "schema_or_geom_ok": int((df.valid | df.errors.str.contains("R:R|stop distance|entry ", na=False)).sum()),
            "dir_all": len(d), "dir_valid": len(dv),
            "market": int((dv.etype == "market").sum()), "limit": int((dv.etype == "limit").sum()),
            "stop_entry": int((dv.etype == "stop").sum()),
            "conf_min_med_max": [min(conf), statistics.median(conf), max(conf)] if conf else None,
            "ev_pass": int(dv.ev_pass.sum()) if len(dv) else 0,
            "hit_n": [int(sum(hit)), len(hit)],
            "t1_first": int((dv.path == "t1").sum()) if len(dv) else 0,
            "stop_first": int((dv.path == "stop").sum()) if len(dv) else 0,
            "counter_regime": int(dv.counter_regime.sum()) if len(dv) else 0,
            "shadow_orders": len(trades), "shadow_filled": len(filled), "shadow_closed": len(closed),
            "shadow_R": [round(x, 2) for x in closed], "shadow_sum_R": round(sum(closed), 2),
            "shadow_mean_R": round(sum(closed) / len(closed), 3) if closed else None,
            "flag_invalid_dir": int((~d.valid).sum()) if len(d) else 0,
            "flag_stop_no_struct_valid": int(dv.stop_no_struct.fillna(False).sum()) if len(dv) else 0}


def score():
    meta = json.loads((HERE / "rounds.json").read_text(encoding="utf-8"))
    allrows, alltr, out = [], [], {}
    for arm in ARMS:
        if not (raw_dir(arm) / ROUNDS6[0] / "blocks.json").exists():
            continue
        rows, trades = score_arm(arm, meta)
        allrows += rows
        alltr += trades
        df = pd.DataFrame(rows)
        o = {"all": summ(rows, trades)}
        for ex in EXP3:
            o[ex] = summ([r for r in rows if r["expert"] == ex], [t for t in trades if t["book"] == ex])
        for rg in ("trend-up", "range"):
            cs = [c for c in ROUNDS6 if meta["slots"][c]["regime"] == rg]
            o[rg] = summ([r for r in rows if r["round"] in cs],
                         [t for t in trades if t["created_utc"] and any(
                             t["created_utc"].startswith(meta["slots"][c]["asof"][:13]) for c in cs)])
        out[arm] = o
        del df
    O.write_json(M6 / "sonuc.json", out)
    pd.DataFrame(allrows).to_csv(M6 / "bloklar.csv", index=False)
    pd.DataFrame(alltr).to_csv(M6 / "islemler.csv", index=False)
    print(json.dumps({a: v["all"] for a, v in out.items()}, indent=1))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("mode", choices=["run", "score", "validate"])
    ap.add_argument("--arm")
    ap.add_argument("--workers", type=int, default=6)
    a = ap.parse_args()
    if a.mode == "run":
        run(a.arm, a.workers)
    elif a.mode == "validate":
        validate(a.arm)
    else:
        score()
