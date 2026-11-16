"""Sistem turnuvasi.

Protokol (sonuclari gormeden sabitlendi):
  - Evren: 2019 basi top-20 coin (delist olanlar dahil), 4h ve 1d.
  - Her sistem x aralik icin parametre grid'i; walk-forward: 2 yil egitim, 6 ay test
    (egitimde en yuksek Sharpe'li parametre bir sonraki 6 aya uygulanir). Tum parametreler
    TUM coinlerde ortak (coin basina optimizasyon yok = daha az overfit).
  - Maliyet: 1x = taraf basi %0.15 (komisyon %0.1 + slippage %0.05), 2x = %0.30.
  - DEV donemi: 2021-01-01 -> HOLDOUT_START. Secim SADECE dev, 2x maliyetle yapilir.
  - HOLDOUT: son 12 ay. Secim bittikten sonra finalistlere bakilir.
  - Coklu test: Deflated Sharpe Ratio (Bailey & Lopez de Prado), deneme sayisi = sistem x aralik.
Kullanim: python tournament.py"""
import itertools
import math
import pathlib
import time
from statistics import NormalDist

import numpy as np
import pandas as pd

from data import load_panel
from systems import SYSTEMS, valid

BPD = {"4h": 6, "1d": 1}
COST = 0.0015            # taraf basi, 1x
WF_START = pd.Timestamp("2021-01-01", tz="UTC")
HOLDOUT_START = pd.Timestamp("2025-11-16", tz="UTC")
TRAIN_DAYS, TEST_MONTHS = 730, 6
WARMUP_DAYS = 200        # yeni listelenen coin bu kadar gun sonra evrene girer
OUT = pathlib.Path(__file__).parent / "results"
N = NormalDist()


# ---------------------------------------------------------------- motor
def eligibility(P, bpd):
    avail = P["close"].notna()
    return avail & (avail.cumsum() > WARMUP_DAYS * bpd)


def to_weights(pos, kind, elig):
    pos = pos.where(elig, 0.0).fillna(0.0)
    if kind == "single":
        return pos.div(elig.sum(axis=1).replace(0, np.nan), axis=0).fillna(0.0)
    return pos


def simulate(P, w, pos=None):
    """t kapanisindaki agirlik t+1 getirisini kazanir. Gunluk net getiriler (1x, 2x) + yardimci seriler.
    pos verilirse coin bazli (tam pozisyon, 2x maliyetli) getiri de saklanir: genislik analizi icin."""
    ret = P["close"].pct_change(fill_method=None).fillna(0.0)
    held = w.shift(1).fillna(0.0)
    gross = (held * ret).sum(axis=1)
    turn = w.diff().abs().sum(axis=1).fillna(w.abs().sum(axis=1))
    day = lambda x: (1 + x).resample("1D").prod() - 1
    asset = None
    if pos is not None:
        asset = pos.shift(1).fillna(0.0) * ret - pos.diff().abs().fillna(0.0) * 2 * COST
    return {
        "1x": day(gross - turn * COST),
        "2x": day(gross - turn * 2 * COST),
        "turn": turn.resample("1D").sum(),
        "expo": held.sum(axis=1).resample("1D").mean(),
        "asset": asset,
    }


def sharpe(d):
    sd = d.std()
    return d.mean() / sd * math.sqrt(365) if sd > 0 and len(d) > 30 else -9.0


def stats(d, turn=None, expo=None):
    d = d.dropna()
    eq = (1 + d).cumprod()
    yrs = len(d) / 365
    out = {
        "sharpe": round(sharpe(d), 2),
        "cagr_%": round((eq.iloc[-1] ** (1 / yrs) - 1) * 100, 1),
        "maxDD_%": round((eq / eq.cummax() - 1).min() * 100, 1),
        "vol_%": round(d.std() * math.sqrt(365) * 100, 1),
    }
    out["calmar"] = round(out["cagr_%"] / -out["maxDD_%"], 2) if out["maxDD_%"] < 0 else np.nan
    if turn is not None:
        out["devir_yil"] = round(turn.loc[d.index].sum() / yrs, 1)
    if expo is not None:
        out["piyasada_%"] = round(expo.loc[d.index].mean() * 100, 1)
    return out


def wf_windows(index):
    s = WF_START
    while s < index[-1]:
        e = s + pd.DateOffset(months=TEST_MONTHS)
        yield s - pd.Timedelta(days=TRAIN_DAYS), s, e
        s = e


def walk_forward(res, cost, index):
    parts, picks = [], []
    for tr0, s, e in wf_windows(index):
        best = max(res, key=lambda k: sharpe(res[k][cost].loc[tr0:s - pd.Timedelta(seconds=1)]))
        parts.append((best, s, e))
        picks.append((s.date(), best))
    return parts, picks


def stitch(res, parts, key):
    return pd.concat([res[k][key].loc[s:e - pd.Timedelta(seconds=1)] for k, s, e in parts])


# ---------------------------------------------------------------- deflated sharpe
def dsr(d, n_trials, var_sr):
    """Gunluk getiri serisi icin DSR (0-1). SR'ler periyot basi (yilliklandirilmamis)."""
    d = d.dropna()
    T, sr = len(d), d.mean() / d.std()
    g3, g4 = d.skew(), d.kurt() + 3
    em = 0.5772156649
    sr0 = math.sqrt(var_sr) * ((1 - em) * N.inv_cdf(1 - 1 / n_trials) + em * N.inv_cdf(1 - 1 / (n_trials * math.e)))
    z = (sr - sr0) * math.sqrt(T - 1) / math.sqrt(max(1e-12, 1 - g3 * sr + (g4 - 1) / 4 * sr ** 2))
    return N.cdf(z)


# ---------------------------------------------------------------- ana akis
def run_system(P, bpd, elig, name):
    fn, kind, grid, scaled = SYSTEMS[name]
    res = {}
    for combo in itertools.product(*grid.values()):
        p = dict(zip(grid, combo))
        if not valid(p):
            continue
        q = {k: (max(2, int(round(v * bpd))) if k in scaled and v else v) for k, v in p.items()}
        key = tuple(sorted(p.items()))
        if key in res:
            continue
        pos = fn(P, bpd, **q)
        w = to_weights(pos, kind, elig)
        res[key] = simulate(P, w, pos.where(elig, 0.0).fillna(0.0) if kind == "single" else None)
    return res


def main():
    OUT.mkdir(exist_ok=True)
    rows, series = [], {}
    for itv, bpd in BPD.items():
        P = load_panel(itv)
        elig = eligibility(P, bpd)
        ones = pd.DataFrame(1.0, index=P["close"].index, columns=P["close"].columns)
        bh = simulate(P, to_weights(ones, "single", elig))
        btc = ones * 0.0
        btc["BTC"] = 1.0
        bh_btc = simulate(P, btc)
        series[("BH_esit", itv)] = bh["1x"]
        series[("BH_btc", itv)] = bh_btc["1x"]
        asset_ret = P["close"].pct_change(fill_method=None)

        for name in SYSTEMS:
            t0 = time.time()
            res = run_system(P, bpd, elig, name)
            idx = next(iter(res.values()))["1x"].index
            for cost in ["1x", "2x"]:
                parts, picks = walk_forward(res, cost, idx)
                oos = stitch(res, parts, cost)
                series[(name, itv, cost)] = oos
                if cost == "2x":
                    turn, expo = stitch(res, parts, "turn"), stitch(res, parts, "expo")
                    # genislik: secilen parametrelerle coin bazinda OOS (dev) Sharpe > coin al-tut Sharpe?
                    a = None if SYSTEMS[name][1] != "single" else pd.concat([res[k]["asset"].loc[s:e - pd.Timedelta(seconds=1)] for k, s, e in parts])
                    a = None if a is None else a.loc[:HOLDOUT_START - pd.Timedelta(seconds=1)]
                    win, tot = 0, 0
                    if SYSTEMS[name][1] == "single":
                        held_bh = asset_ret.loc[a.index]
                        for col in a.columns:
                            m = held_bh[col].notna()
                            if m.sum() < 365 * bpd:
                                continue
                            day_s = (1 + a.loc[m, col]).resample("1D").prod() - 1
                            day_b = (1 + held_bh.loc[m, col]).resample("1D").prod() - 1
                            tot += 1
                            win += sharpe(day_s) > sharpe(day_b)
                    rows.append({"sistem": name, "aralik": itv, "genislik": f"{win}/{tot}" if tot else "-",
                                 "genislik_oran": win / tot if tot else np.nan,
                                 "son_param": dict(picks[-1][1]), "_turn": turn, "_expo": expo})
            print(f"{itv} {name:14s} {len(res):3d} kombinasyon {time.time() - t0:5.1f}s", flush=True)

    # ---------------- DEV degerlendirme (holdout'a bakmadan)
    dev = lambda s: s.loc[WF_START:HOLDOUT_START - pd.Timedelta(seconds=1)]
    hold = lambda s: s.loc[HOLDOUT_START:]
    table = []
    for r in rows:
        k = (r["sistem"], r["aralik"])
        s1, s2 = series[k + ("1x",)], series[k + ("2x",)]
        d2 = dev(s2)
        st2 = stats(d2, r["_turn"], r["_expo"])
        st1 = stats(dev(s1))
        halves = [d2.loc[s:e - pd.Timedelta(seconds=1)] for _, s, e in wf_windows(d2.index)]
        pos_win = sum((1 + h).prod() > 1 for h in halves if len(h)) / max(1, sum(len(h) > 0 for h in halves))
        table.append({"sistem": r["sistem"], "aralik": r["aralik"],
                      "sharpe_1x": st1["sharpe"], "sharpe_2x": st2["sharpe"], "cagr_2x": st2["cagr_%"],
                      "maxDD_2x": st2["maxDD_%"], "calmar_2x": st2["calmar"], "piyasada_%": st2["piyasada_%"],
                      "devir_yil": st2["devir_yil"], "pozitif_6ay": round(pos_win, 2),
                      "genislik": r["genislik"], "genislik_oran": r["genislik_oran"], "son_param": r["son_param"]})
    T = pd.DataFrame(table)

    n_trials = len(T)
    var_sr = np.var([dev(series[(a, b, "2x")]).mean() / dev(series[(a, b, "2x")]).std() for a, b in zip(T.sistem, T.aralik)])
    T["DSR"] = [round(dsr(dev(series[(a, b, "2x")]), n_trials, var_sr), 3) for a, b in zip(T.sistem, T.aralik)]

    bench = {}
    for itv in BPD:
        bench[itv] = {"esit": stats(dev(series[("BH_esit", itv)])), "btc": stats(dev(series[("BH_btc", itv)]))}
    T["bh_esit_sharpe"] = T.aralik.map(lambda i: bench[i]["esit"]["sharpe"])
    T["bh_btc_sharpe"] = T.aralik.map(lambda i: bench[i]["btc"]["sharpe"])
    T["bh_btc_dd"] = T.aralik.map(lambda i: bench[i]["btc"]["maxDD_%"])

    # ---------------- ON-TANIMLI SECIM KURALI (dev, 2x maliyet)
    T["gecti"] = ((T.sharpe_2x > T.bh_esit_sharpe) & (T.sharpe_2x > T.bh_btc_sharpe)
                  & (T.maxDD_2x > T.bh_btc_dd) & (T.pozitif_6ay >= 0.5)
                  & (T.genislik_oran.fillna(1) >= 0.5))
    T = T.sort_values("sharpe_2x", ascending=False).reset_index(drop=True)

    # ---------------- HOLDOUT (secim bittikten sonra)
    def hstats(k):
        return stats(hold(series[k]))
    T["holdout_sharpe_2x"] = [hstats((a, b, "2x"))["sharpe"] for a, b in zip(T.sistem, T.aralik)]
    T["holdout_getiri_2x"] = [round(((1 + hold(series[(a, b, "2x")])).prod() - 1) * 100, 1) for a, b in zip(T.sistem, T.aralik)]
    T["holdout_dd_2x"] = [hstats((a, b, "2x"))["maxDD_%"] for a, b in zip(T.sistem, T.aralik)]

    finalists = T[T.gecti].head(5)  # secim: sadece dev kolonlarina gore siralanmis T
    ens = None
    if len(finalists):
        ens = pd.concat([series[(a, b, "2x")] for a, b in zip(finalists.sistem, finalists.aralik)], axis=1).mean(axis=1)
        series[("ENSEMBLE", "mix", "2x")] = ens

    T.drop(columns=["genislik_oran"]).to_csv(OUT / "tournament.csv", index=False)
    eq = pd.DataFrame({"|".join(k): (1 + v.loc[WF_START:]).cumprod() for k, v in series.items()
                       if k[-1] in ("2x",) or k[0].startswith("BH")})
    eq.to_csv(OUT / "equity_curves.csv")

    # ---------------- rapor
    pd.set_option("display.width", 300, "display.max_columns", 40, "display.max_colwidth", 60)
    cols = ["sistem", "aralik", "sharpe_1x", "sharpe_2x", "cagr_2x", "maxDD_2x", "calmar_2x", "piyasada_%",
            "devir_yil", "pozitif_6ay", "genislik", "DSR", "gecti"]
    print(f"\nDENEME SAYISI: {n_trials}  (DSR bunu cezalandiriyor)")
    for itv in BPD:
        print(f"Al-tut {itv} dev: esit-agirlik {bench[itv]['esit']}  |  BTC {bench[itv]['btc']}")
    print("\n=== DEV SIRALAMA (2021-01 -> 2025-11, walk-forward OOS, 2x maliyet) ===")
    print(T[cols].to_string())
    print("\n=== FINALISTLER (kural: Sharpe2x > iki al-tut, DD < BTC DD, >=%50 pozitif 6 ay, genislik >=%50) ===")
    hc = ["sistem", "aralik", "sharpe_2x", "DSR", "holdout_sharpe_2x", "holdout_getiri_2x", "holdout_dd_2x", "son_param"]
    print(finalists[hc].to_string())
    for itv in BPD:
        for b in ["BH_esit", "BH_btc"]:
            h = hold(series[(b, itv)])
            print(f"HOLDOUT {b} {itv}: sharpe {stats(h)['sharpe']} getiri {round(((1 + h).prod() - 1) * 100, 1)}% dd {stats(h)['maxDD_%']}")
    if ens is not None:
        print("ENSEMBLE dev:", stats(dev(ens)), " holdout:", stats(hold(ens)),
              "holdout getiri %", round(((1 + hold(ens)).prod() - 1) * 100, 1))
    print("\nHoldout'ta TUM sistemler (secim kuralinin bilgi tasiyip tasimadigini gormek icin):")
    print(T[["sistem", "aralik", "sharpe_2x", "gecti", "holdout_sharpe_2x", "holdout_getiri_2x", "holdout_dd_2x"]].to_string())


if __name__ == "__main__":
    main()
