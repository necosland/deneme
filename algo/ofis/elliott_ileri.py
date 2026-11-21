"""Elliott k=4 3. dalga ileri (forward) sahte para testi. On kayit: test_ekrem/ileri_plan.md. LLM yok, gercek emir yok.

Kural = test_ekrem/kod_test.py backtest2 (v2 hedefleri) icinde yalniz zigzag k=4.0 ve w3 kurulumlari. Sinyal kodu
kod_test.signals() ile AYNI fonksiyon (kopya degil); yonetim kod_test.sim() ile ayni mantik, yalniz "hala acik" durumu da
dondurur. Her calismada tum ileri donem bastan yeniden hesaplanir (kapanmis 4h mumlar; zigzag/ATR geriye bakmaz),
deftere yazilmis islemin giris/stop/hedefleri dondurulur; fark cikarsa log'a WARN. Bu yuzden iki kez calismak guvenli.

  python algo/ofis/elliott_ileri.py                 # canli: veri guncelle, defteri yaz
  python algo/ofis/elliott_ileri.py --dir TMP --start "2026-11-07 00:00" --now "2026-11-14 08:00"   # geri doldurma testi
Defter: defter/elliott_ileri.json + .csv (ofis defterinden ayri), log: log/elliott_ileri.log, durum: elliott_ileri.md
"""
import argparse
import json
import math
import pathlib
import sys
import time

import numpy as np
import pandas as pd

ROOT = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "test_ekrem"))
import ortak as O  # noqa: E402
import elliott_say as E  # noqa: E402
import kod_test as KT  # noqa: E402

# ---- on kayitli sabitler (ileri_plan.md; baslangictan sonra degismez) ----
PLAN = "algo/ofis/test_ekrem/ileri_plan.md"
FWD_START = "2026-11-21 08:00"     # sinyal mumunun acilisi >= bu an (UTC)
UNIVERSE = ["BTCUSDT", "ETHUSDT", "BNBUSDT", "XRPUSDT", "SOLUSDT", "TRXUSDT", "HYPEUSDT", "ZECUSDT", "DOGEUSDT",
            "LINKUSDT"]           # veri/evren.json 2026-11-20 21:40, donduruldu
K, KIND = 4.0, "w3"
EVAL_N, EVAL_MAX_DAYS, INTERIM_DAYS = 30, 365, 56   # ilk 30 kapanan, en erken 8 hafta, en gec 12 ay
BAR = pd.Timedelta(hours=4)
SEED_CACHE = ROOT.parent / "cache"   # backtest verisi (2019 ->); yoksa Binance'ten sayfa sayfa
DATA_START = pd.Timestamp("2019-01-01", tz="UTC")


def setup_kt(start):
    KT.KS, KT.V2, KT.START = (K,), True, start
    assert KT.TSTOP == 60 and KT.COST == 0.001 and KT.MIN_SCORE == 50


# ---------------- veri ----------------
def fetch(sym, start_ms, end_ms=None):
    import requests
    rows, cur = [], start_ms
    for _ in range(200):
        p = dict(symbol=sym, interval="4h", startTime=cur, limit=1000)
        if end_ms:
            p["endTime"] = end_ms
        r = requests.get(O.SPOT_KLINES, params=p, timeout=30, headers=O.UA)
        r.raise_for_status()
        x = r.json()
        if not x:
            break
        rows += [[k[0], k[1], k[2], k[3], k[4], k[5]] for k in x]   # base volume (algo/cache ile ayni)
        if len(x) < 1000:
            break
        cur = x[-1][0] + 1
        time.sleep(0.2)
    df = pd.DataFrame(rows, columns=["t", "open", "high", "low", "close", "volume"])
    df.index = pd.to_datetime(df.pop("t"), unit="ms", utc=True)
    df.index.name = "open_time"
    return df.astype(float)


def load(sym, cache_dir, now, offline=False):
    """Kapanmis 4h mumlar (acilis + 4h <= now). cache_dir/<sym>_4h.csv yerel kopya, algo/cache'ten tohumlanir."""
    f = cache_dir / f"{sym}_4h.csv"
    if f.exists():
        df = pd.read_csv(f, index_col=0, parse_dates=True)
    elif (SEED_CACHE / f"{sym}_4h.csv").exists():
        df = pd.read_csv(SEED_CACHE / f"{sym}_4h.csv", index_col=0, parse_dates=True)
    else:
        df = None
    if df is not None:
        df.index = pd.to_datetime(df.index, utc=True)
    if not offline:
        s = DATA_START if df is None else df.index[-1] + BAR
        if s + BAR <= pd.Timestamp(O.now_utc()):
            new = fetch(sym, O.ms(s))
            df = new if df is None else pd.concat([df, new])
    if df is None:
        raise RuntimeError(f"{sym}: no data")
    df = df[~df.index.duplicated(keep="last")].sort_index()
    df = df[df.index + BAR <= O.now_utc()]            # hic kapanmamis mum saklanmaz
    if not offline:
        cache_dir.mkdir(parents=True, exist_ok=True)
        df.to_csv(f)
    return df[df.index + BAR <= now]


# ---------------- islemler (kod_test.trades ile ayni sira ve kurallar) ----------------
def sim_live(Sd, i0, Eu, Su, T1, T2):
    """kod_test.sim ile ayni; ek olarak durum: 'closed' ya da 'open' (60 mum dolmadi, olay yok)."""
    O_, H, L, C = Sd["O"], Sd["H"], Sd["L"], Sd["C"]
    n = len(C)
    risk = Eu - Su
    half, R = False, 0.0
    last = min(i0 + KT.TSTOP, n) - 1
    for b in range(i0, last + 1):
        if not half:
            if L[b] <= Su:
                px = O_[b] if (b > i0 and O_[b] < Su) else Su
                return R + (px - Eu) / risk, b, "stop", half
            if H[b] >= T1:
                half = True
                R += 0.5 * (T1 - Eu) / risk
                if H[b] >= T2:
                    return R + 0.5 * (T2 - Eu) / risk, b, "T2", half
        else:
            if L[b] <= Eu:
                px = O_[b] if O_[b] < Eu else Eu
                return R + 0.5 * (px - Eu) / risk, b, "breakeven_after_T1", half
            if H[b] >= T2:
                return R + 0.5 * (T2 - Eu) / risk, b, "T2", half
    mark = R + (0.5 if half else 1.0) * (C[last] - Eu) / risk
    if i0 + KT.TSTOP <= n:
        return mark, last, "time_stop_60", half
    return mark, last, "open", half


def compute(frames):
    """Ileri donemin tum islemleri (bastan, deterministik)."""
    S, sigs = {}, []
    for s, df in frames.items():
        S[s] = {d: E.space(df, d) for d in (1, -1)}
        sigs += [x for x in KT.signals(df, s) if x["kind"] == KIND and x["k"] == K]
    res, busy = [], {}
    for s in sorted(sigs, key=lambda x: (x["t"], -x["score"])):
        key = (s["sym"], s["kind"])
        i0 = s["t"] + 1
        if busy.get(key, -1) >= i0:
            continue
        Sd = S[s["sym"]][s["d"]]
        Eu = Sd["O"][i0]
        T1c, T2c, capped = KT.cap_targets(Eu, s["T1"], s["T2"], s["d"])
        if capped:
            O.log("elliott_ileri.log", f"target_capped {s['sym']} {O.fmt(frames[s['sym']].index[s['t']])} short: "
                                       f"T1 {E.r5(-s['T1'])}->{E.r5(-T1c)} T2 {E.r5(-s['T2'])}->{E.r5(-T2c)}")
        s = {**s, "T1": T1c, "T2": T2c}
        if not (s["stop"] < Eu < s["T1"]):
            continue
        r, ex, why, half = sim_live(Sd, i0, Eu, s["stop"], s["T1"], s["T2"])
        risk = Eu - s["stop"]
        cost_r = 2 * KT.COST * abs(Eu) / risk
        busy[key] = ex if why != "open" else 10 ** 9
        idx, d = frames[s["sym"]].index, s["d"]
        res.append({"id": f"{s['sym']}|{O.fmt(idx[s['t']])}|{'long' if d == 1 else 'short'}",
                    "sym": s["sym"], "side": "long" if d == 1 else "short", "score": s["score"],
                    "signal_bar_utc": O.fmt(idx[s["t"]]), "entry_bar_utc": O.fmt(idx[i0]),
                    "entry": E.r5(d * Eu), "stop": E.r5(d * s["stop"]), "T1": E.r5(d * s["T1"]),
                    "T2": E.r5(d * s["T2"]), "risk_pct": round(100 * risk / abs(Eu), 3),
                    "status": "open" if why == "open" else "closed", "target_capped": capped, "exit_reason": why, "half_at_T1": half,
                    "exit_bar_utc": O.fmt(idx[ex]), "bars": int(ex - i0 + 1),
                    "R": round(float(r - cost_r), 4), "cost_R": round(float(cost_r), 4)})
    return res


def ci90(r):
    n = len(r)
    if n < 2:
        return None, None
    m, sd = float(np.mean(r)), float(np.std(r, ddof=1))
    try:
        from scipy.stats import t as tdist
        q = float(tdist.ppf(0.95, n - 1))
    except Exception:  # noqa: BLE001
        q = 1.645
    h = q * sd / math.sqrt(n)
    return round(m - h, 3), round(m + h, 3)


def summary(trades, frames, start, now):
    cl = [t["R"] for t in trades if t["status"] == "closed"]
    lo, hi = ci90(cl)
    btc = frames.get("BTCUSDT")
    bh = None
    if btc is not None:
        w = btc[btc.index >= start]
        if len(w):
            bh = round(float(100 * (w.close.iloc[-1] / w.open.iloc[0] - 1)), 2)
    days = max(0.0, (now - start).total_seconds() / 86400)
    # on kayit: birincil hukum = kapanis sirasina gore ilk 30 islem, en erken 56. gunde; ikincil = ilk 100 (ayni cita);
    # 365. gunde 30'a ulasilmadiysa eldekilerle hukum
    by_exit = [t["R"] for t in sorted((t for t in trades if t["status"] == "closed"), key=lambda t: t["exit_bar_utc"])]
    verdicts = {}
    for name, n_req in (("primary_30", EVAL_N), ("secondary_100", 100)):
        if (len(by_exit) >= n_req and days >= INTERIM_DAYS) or (name == "primary_30" and days >= EVAL_MAX_DAYS
                                                                  and by_exit):
            sample = by_exit[:n_req]
            l, h = ci90(sample)
            verdicts[name] = {"n": len(sample), "mean_R": round(float(np.mean(sample)), 3), "ci90": [l, h],
                              "result": "PASS" if (l is not None and l > 0) else "FAIL"}
    p = verdicts.get("primary_30")
    verdict = p["result"] if p else "running"
    return {"closed_n": len(cl), "open_n": sum(t["status"] == "open" for t in trades), "verdicts": verdicts,
            "mean_R": round(float(np.mean(cl)), 3) if cl else None, "total_R": round(float(np.sum(cl)), 2),
            "win_pct": round(100 * float(np.mean(np.array(cl) > 0)), 1) if cl else None,
            "ci90": [lo, hi], "btc_buy_hold_pct": bh, "days": round(days, 1), "verdict": verdict,
            "by_side": {sd: {"n": len(x), "mean_R": round(float(np.mean(x)), 3) if x else None}
                        for sd in ("long", "short")
                        for x in [[t["R"] for t in trades if t["status"] == "closed" and t["side"] == sd]]}}


def write_md(path, led):
    s = led["summary"]
    tr = lambda x, d=2: "-" if x is None else f"{x:+.{d}f}".replace(".", ",")  # noqa: E731
    L = ["# Elliott 3. dalga ileri testi (sahte para, 1R sabit)", "",
         f"Ön kayıt: `{PLAN}`. Başlangıç {led['start_utc']} UTC. Son çalışma {led['last_run_utc']} UTC, "
         f"son kapanmış mum {led['last_bar_utc']} UTC. Kural kanıtlı değil; ofis kararlarını etkilemez.", "",
         "| Kapanan | Açık | Ort. R | Toplam R | %90 aralık | BTC al-tut | Gün | Durum |", "|---|---|---|---|---|---|---|---|",
         f"| {s['closed_n']} | {s['open_n']} | {tr(s['mean_R'], 3)} | {tr(s['total_R'])} | "
         f"{tr(s['ci90'][0], 3)} / {tr(s['ci90'][1], 3)} | %{tr(s['btc_buy_hold_pct'])} | {s['days']} | {s['verdict']} |", ""]
    if led["trades"]:
        L += ["| Varlık | Yön | Sinyal mumu | Giriş | Stop | T1 | T2 | Durum | Çıkış | R |",
              "|---|---|---|---|---|---|---|---|---|---|"]
        for t in led["trades"][-20:]:
            L.append(f"| {t['sym']} | {t['side']} | {t['signal_bar_utc']} | {t['entry']} | {t['stop']} | {t['T1']} | "
                     f"{t['T2']} | {t['exit_reason']} | {t['exit_bar_utc'] if t['status'] == 'closed' else '-'} | "
                     f"{tr(t['R'], 3)} |")
    else:
        L.append("Henüz işlem yok.")
    path.write_text("\n".join(L) + "\n", encoding="utf-8")


FROZEN = ("sym", "side", "signal_bar_utc", "entry_bar_utc", "entry", "stop", "T1", "T2")


def run(out_dir, cache_dir, start, now, offline=False, logf="elliott_ileri.log"):
    def say(m):
        O.log(logf, m)
    setup_kt(start)
    frames = {}
    for s in UNIVERSE:
        try:
            frames[s] = load(s, cache_dir, now, offline)
        except Exception as e:  # noqa: BLE001
            say(f"data FAILED {s}: {type(e).__name__} {e}")
    if not frames:
        say("no data: stop")
        return 2
    new = compute(frames)
    lf = out_dir / "elliott_ileri.json"
    led = json.loads(lf.read_text(encoding="utf-8")) if lf.exists() else {"plan": PLAN, "start_utc": O.fmt(start),
                                                                          "universe": UNIVERSE, "rule": f"k={K} {KIND}",
                                                                          "trades": []}
    old = {t["id"]: t for t in led["trades"]}
    seen, out, nnew = set(), [], 0
    for t in new:
        o = old.get(t["id"])
        if o:
            diff = [f for f in FROZEN if o.get(f) != t.get(f)]
            if diff:
                say(f"WARN recompute differs for {t['id']} on {diff}: keeping frozen values")
                for f in FROZEN:
                    t[f] = o[f]
            if o["status"] == "closed" and (t["status"] != "closed" or o["R"] != t["R"]):
                say(f"WARN closed trade changed on recompute {t['id']}: keeping old close")
                t = o
            t["logged_utc"] = o.get("logged_utc")
        else:
            t["logged_utc"] = O.fmt(O.now_utc())
            nnew += 1
            say(f"NEW {t['id']} entry {t['entry']} stop {t['stop']} T1 {t['T1']} T2 {t['T2']} status {t['status']}")
        if o is None or o["status"] != t["status"]:
            if t["status"] == "closed":
                say(f"CLOSED {t['id']} {t['exit_reason']} R={t['R']}")
        seen.add(t["id"])
        out.append(t)
    for i, o in old.items():
        if i not in seen:
            say(f"WARN ledger trade {i} not found on recompute: kept")
            o["missing_in_recompute"] = True
            out.append(o)
    out.sort(key=lambda t: (t["entry_bar_utc"], t["sym"]))
    last_bar = max(df.index[-1] for df in frames.values())
    led.update(trades=out, last_run_utc=O.fmt(O.now_utc()), last_bar_utc=O.fmt(last_bar),
               bars_per_sym={s: O.fmt(df.index[-1]) for s, df in frames.items()},
               summary=summary(out, frames, start, now))
    O.write_json(lf, led)
    pd.DataFrame(out).to_csv(out_dir / "elliott_ileri.csv", index=False)
    write_md(out_dir / "elliott_ileri.md" if out_dir != O.DEFTER else ROOT / "elliott_ileri.md", led)
    say(f"run ok: last_bar {O.fmt(last_bar)} syms {len(frames)} trades {len(out)} new {nnew} summary {led['summary']}")
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", help="cikti klasoru (varsayilan defter/); test icin gecici klasor")
    ap.add_argument("--cache", help="veri kopyasi klasoru (varsayilan veri/elliott_ileri/)")
    ap.add_argument("--start", default=FWD_START, help="yalniz geri doldurma testi icin")
    ap.add_argument("--now", help="bu ana kadar kapanmis mumlar (UTC 'YYYY-mm-dd HH:MM'); test icin")
    ap.add_argument("--offline", action="store_true", help="veri indirme, yalniz yerel kopya")
    a = ap.parse_args()
    out = pathlib.Path(a.dir) if a.dir else O.DEFTER
    out.mkdir(parents=True, exist_ok=True)
    cache = pathlib.Path(a.cache) if a.cache else O.VERI / "elliott_ileri"
    start = pd.Timestamp(a.start, tz="UTC")
    now = pd.Timestamp(a.now, tz="UTC") if a.now else pd.Timestamp(O.now_utc())
    if (a.now or start != pd.Timestamp(FWD_START, tz="UTC")) and out.resolve() == O.DEFTER.resolve():
        raise SystemExit("--start/--now override is for test dirs only (live ledger is pre-registered)")
    logf = "elliott_ileri.log" if out.resolve() == O.DEFTER.resolve() else str((out / "elliott_ileri.log").resolve())
    return run(out, cache, start, now, a.offline, logf)


if __name__ == "__main__":
    sys.exit(main())
