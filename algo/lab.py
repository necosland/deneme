"""Strateji turnuvasi. Kullanim: python lab.py
Protokol (sonuclari gormeden yazildi, sonradan degistirilmez):
- Ana evren: BTC ETH BNB SOL XRP ADA, 4 saatlik. Her strateji esit agirlikli portfoy olarak olculur.
- Parametre: walk-forward (2 yil egitim, 6 ay test, kayan). Parametreyi portfoyun egitim Sharpe'i secer,
  tum varliklarda ortak. Raporlanan her sayi out-of-sample.
- SECIM donemi: OOS'un 2024 sonuna kadar olan kismi. Aday kriterleri yalniz buna bakar.
- SINAV donemi: 2025-01-01 -> bugun. Adaylar burada ikinci kez sinanir; secimde hic kullanilmadi.
- Gorulmemis varliklar (LINK AVAX DOGE LTC) bilgi amacli: hic secimde kullanilmadi.

Aday kriterleri (hepsi secim doneminde):
 A) portfoy Sharpe > esit agirlikli al-tut Sharpe ve > 0.5
 B) 6 varligin en az 4'unde OOS Sharpe > o varligin al-tut Sharpe'i
 C) komisyon+slippage 2 katinda (parametre yine walk-forward secilir) Sharpe > al-tut Sharpe
 D) gunluk mumda ayni strateji Sharpe > gunluk al-tut Sharpe
 E) Deflated Sharpe (31 deneme icin sans duzeltmesi) > 0.90
Kazanan: aday + sinav doneminde Sharpe > al-tut Sharpe ve maxDD al-tuttan daha sig.
"""
import itertools
import math
import pathlib
from statistics import NormalDist

import numpy as np
import pandas as pd

from data import fetch_ohlcv
from lab_strategies import PORTFOLIO, SINGLE

CORE = ["BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT", "XRPUSDT", "ADAUSDT"]
UNSEEN = ["LINKUSDT", "AVAXUSDT", "DOGEUSDT", "LTCUSDT"]
SEL_END = pd.Timestamp("2025-01-01", tz="UTC")
COST = 0.001 + 0.0005  # taraf basi komisyon + slippage
PPD = {"4h": 6, "1d": 1}
TRAIN_DAYS, TEST_DAYS = 730, 180
N_TRIALS = len(SINGLE) + len(PORTFOLIO)
OUT = pathlib.Path(__file__).parent / "sonuc"
ND = NormalDist()


# ---------------- olcum ----------------
def sharpe(r, ppy):
    r = r.dropna()
    sd = r.std()
    return float(r.mean() / sd * math.sqrt(ppy)) if len(r) > 2 and sd > 0 else -9.0


def stats(r, ppy, held=None):
    r = r.dropna()
    if len(r) < 3:
        return {}
    eq = (1 + r).cumprod()
    yrs = len(r) / ppy
    out = {
        "sharpe": round(sharpe(r, ppy), 2),
        "getiri_%": round((eq.iloc[-1] - 1) * 100, 1),
        "yillik_%": round((eq.iloc[-1] ** (1 / yrs) - 1) * 100, 1),
        "maxDD_%": round((eq / eq.cummax() - 1).min() * 100, 1),
    }
    if held is not None:
        h = held.loc[r.index]
        out["piyasada_%"] = round(float(np.nanmean(h.to_numpy())) * 100, 1)
    return out


def daily(r):
    return ((1 + r.dropna()).resample("1D").prod() - 1)


def deflated_sharpe(r_daily, sr_var, n):
    """Bailey & Lopez de Prado. sr_var: denemeler arasi (gunluk, yilliklastirilmamis) Sharpe varyansi."""
    r = r_daily.dropna()
    t = len(r)
    sr = r.mean() / r.std()
    g = 0.5772156649
    sr0 = math.sqrt(sr_var) * ((1 - g) * ND.inv_cdf(1 - 1 / n) + g * ND.inv_cdf(1 - 1 / (n * math.e)))
    sk, ku = r.skew(), r.kurt() + 3
    den = math.sqrt(max(1 - sk * sr + (ku - 1) / 4 * sr ** 2, 1e-9))
    return ND.cdf((sr - sr0) * math.sqrt(t - 1) / den)


# ---------------- motor ----------------
def load(syms, iv):
    return {s: fetch_ohlcv(s, iv) for s in syms}


def combos(space):
    keys = list(space)
    out = []
    for vals in itertools.product(*space.values()):
        p = dict(zip(keys, vals))
        if "fast" in p and "slow" in p and p["fast"] >= p["slow"]:
            continue
        out.append(p)
    return out


def single_eval(dfs, fn, p, ctx, U, costs):
    """Her varlik icin pozisyon -> (cost -> net getiri DataFrame), held DataFrame (U uzerinde)."""
    held_cols, net_cols = {}, {c: {} for c in costs}
    for s, df in dfs.items():
        pos = fn(df, ctx, **p).clip(0, 1).fillna(0.0)
        held = pos.shift(1).fillna(0.0)          # t kapanisi sinyali t+1 getirisini kazanir
        ret = df["close"].pct_change().fillna(0.0)
        turn = held.diff().abs().fillna(held.abs())
        for c in costs:
            net_cols[c][s] = (held * ret - turn * c).reindex(U)
        held_cols[s] = held.reindex(U)
    return {c: pd.DataFrame(v) for c, v in net_cols.items()}, pd.DataFrame(held_cols)


def portfolio_eval(dfs, fn, p, ctx, U, costs):
    closes = pd.DataFrame({s: d["close"] for s, d in dfs.items()}).reindex(U)
    rets = closes.pct_change(fill_method=None)
    w = fn(closes.ffill(limit=3), ctx, **p).fillna(0.0)
    held = w.shift(1).fillna(0.0)
    turn = held.diff().abs().fillna(held.abs()).sum(axis=1)
    gross = (held * rets.fillna(0.0)).sum(axis=1)
    nets = {c: (gross - turn * c).to_frame("port") for c in costs}
    return nets, held.sum(axis=1).to_frame("port")


def walk_forward(port_by_key, ppd, U, ppy):
    tr, te = TRAIN_DAYS * ppd, TEST_DAYS * ppd
    segs, i = [], tr
    keys = list(port_by_key)
    while i < len(U):
        tr_idx, te_idx = U[i - tr:i], U[i:i + te]
        best = max(keys, key=lambda k: sharpe(port_by_key[k].loc[tr_idx], ppy))
        segs.append((te_idx, best))
        i += te
    return segs


def stitch(frames_by_key, segs):
    return pd.concat([frames_by_key[k].loc[idx] for idx, k in segs])


def run_strategy(name, dfs, iv, costs, btc, reg=None, extra=None):
    """Walk-forward OOS sonuclari: cost -> dict(port, assets, held, segs).
    reg=(SINGLE, PORTFOLIO) baska strateji kutuphanesi icin (tur 2); extra: ctx'e ek veri."""
    single, portfolio = reg or (SINGLE, PORTFOLIO)
    ppd = PPD[iv]
    ppy = 365 * ppd
    ctx = {"ppy": ppy, "ppd": ppd, "btc": btc, **(extra or {})}
    U = pd.DatetimeIndex(sorted(set().union(*[d.index for d in dfs.values()])))
    is_port = name in portfolio
    fn, space = (portfolio if is_port else single)[name]
    nets, helds = {c: {} for c in costs}, {}
    for p in combos(space):
        key = tuple(sorted(p.items()))
        n, h = (portfolio_eval if is_port else single_eval)(dfs, fn, p, ctx, U, costs)
        for c in costs:
            nets[c][key] = n[c]
        helds[key] = h
    out = {}
    for c in costs:
        port = {k: (v["port"] if is_port else v.mean(axis=1)) for k, v in nets[c].items()}
        segs = walk_forward(port, ppd, U, ppy)
        out[c] = {
            "port": stitch(port, segs),
            "assets": None if is_port else stitch(nets[c], segs),
            "held": stitch(helds, segs),
            "segs": segs,
        }
    return out, ppy


def buy_hold(dfs, iv):
    U = pd.DatetimeIndex(sorted(set().union(*[d.index for d in dfs.values()])))
    rets = pd.DataFrame({s: d["close"].pct_change() for s, d in dfs.items()}).reindex(U)
    return rets


def shift_test(held, assets_ret, cost, ppy, actual, sims=300, seed=7):
    """Pozisyon tablosunu tum varliklarda AYNI miktarda dairesel kaydir: ayni maruziyet,
    tutma suresi ve varliklar arasi eszamanlilik; zamanlama rastgele.
    p = rastgele Sharpe >= gercek Sharpe orani."""
    rng = np.random.default_rng(seed)
    H, R = np.nan_to_num(held.to_numpy()), assets_ret.to_numpy()
    avail = ~np.isnan(R)
    n = len(H)
    res = []
    for _ in range(sims):
        h = np.roll(H, rng.integers(n // 10, n - n // 10), axis=0)
        turn = np.abs(np.diff(h, axis=0, prepend=h[:1]))
        net = np.where(avail, h * np.nan_to_num(R) - turn * cost, np.nan)
        port = np.nanmean(net, axis=1)
        port = port[~np.isnan(port)]
        res.append(port.mean() / port.std() * math.sqrt(ppy))
    res = np.array(res)
    return float((res >= actual).mean())


# ---------------- ana akis ----------------
def main():
    OUT.mkdir(exist_ok=True)
    data = {
        ("core", "4h"): load(CORE, "4h"),
        ("core", "1d"): load(CORE, "1d"),
        ("unseen", "4h"): load(UNSEEN, "4h"),
    }
    btc = {"4h": data[("core", "4h")]["BTCUSDT"], "1d": data[("core", "1d")]["BTCUSDT"]}

    bh = {k: buy_hold(v, k[1]) for k, v in data.items()}
    bh_port = {k: v.mean(axis=1) for k, v in bh.items()}

    names = list(SINGLE) + list(PORTFOLIO)
    rows, keep = [], {}
    for name in names:
        print("...", name, flush=True)
        r4, ppy4 = run_strategy(name, data[("core", "4h")], "4h", [COST, 2 * COST], btc["4h"])
        r1, ppy1 = run_strategy(name, data[("core", "1d")], "1d", [COST], btc["1d"])
        ru, _ = run_strategy(name, data[("unseen", "4h")], "4h", [COST], btc["4h"])
        base = r4[COST]
        port = base["port"]
        sel, hold = port[port.index < SEL_END], port[port.index >= SEL_END]
        bsel = bh_port[("core", "4h")].loc[sel.index]
        bhold = bh_port[("core", "4h")].loc[hold.index]
        held_mean = base["held"].mean(axis=1)

        row = {"strateji": name}
        s_sel = stats(sel, ppy4, held_mean)
        row.update({f"sec_{k}": v for k, v in s_sel.items()})
        row["sec_bh_sharpe"] = round(sharpe(bsel, ppy4), 2)

        # B: varlik bazinda
        if base["assets"] is not None:
            a = base["assets"]
            a_sel = a[a.index < SEL_END]
            b_sel = bh[("core", "4h")].loc[a_sel.index]
            won = sum(sharpe(a_sel[s], ppy4) > sharpe(b_sel[s], ppy4) for s in CORE)
            row["varlik_gecti_6da"] = int(won)
        else:
            row["varlik_gecti_6da"] = np.nan

        p2 = r4[2 * COST]["port"]
        row["sec_sharpe_2xmaliyet"] = round(sharpe(p2[p2.index < SEL_END], ppy4), 2)
        p1 = r1[COST]["port"]
        p1s = p1[p1.index < SEL_END]
        row["sec_sharpe_1d"] = round(sharpe(p1s, ppy1), 2)
        row["sec_bh_sharpe_1d"] = round(sharpe(bh_port[("core", "1d")].loc[p1s.index], ppy1), 2)

        s_h = stats(hold, ppy4, held_mean)
        row.update({f"sinav_{k}": v for k, v in s_h.items()})
        s_bh = stats(bhold, ppy4)
        row["sinav_bh_sharpe"], row["sinav_bh_getiri_%"], row["sinav_bh_maxDD_%"] = (
            s_bh["sharpe"], s_bh["getiri_%"], s_bh["maxDD_%"])

        pu = ru[COST]["port"]
        row["gorulmemis_sharpe"] = round(sharpe(pu, ppy4), 2)
        row["gorulmemis_bh_sharpe"] = round(sharpe(bh_port[("unseen", "4h")].loc[pu.index], ppy4), 2)
        row["son_param"] = str(dict(base["segs"][-1][1]))
        rows.append(row)
        keep[name] = (base, sel, ppy4)

    df = pd.DataFrame(rows).set_index("strateji")

    # E: deflated Sharpe (gunluk getiri, secim donemi)
    d_sel = {n: daily(keep[n][1]) for n in names}
    srs = np.array([d.mean() / d.std() for d in d_sel.values()])
    var = float(np.var(srs, ddof=1))
    df["DSR"] = [round(deflated_sharpe(d_sel[n], var, N_TRIALS), 3) for n in names]

    df["A"] = (df["sec_sharpe"] > df["sec_bh_sharpe"]) & (df["sec_sharpe"] > 0.5)
    df["B"] = df["varlik_gecti_6da"].fillna(4) >= 4  # rotasyonda varlik bazi olcum yok
    df["C"] = df["sec_sharpe_2xmaliyet"] > df["sec_bh_sharpe"]
    df["D"] = df["sec_sharpe_1d"] > df["sec_bh_sharpe_1d"]
    df["E"] = df["DSR"] > 0.90
    df["aday"] = df[["A", "B", "C", "D", "E"]].all(axis=1)
    df["sinav_gecti"] = (df["sinav_sharpe"] > df["sinav_bh_sharpe"]) & (df["sinav_maxDD_%"] > df["sinav_bh_maxDD_%"])
    df["kazanan"] = df["aday"] & df["sinav_gecti"]

    # zamanlama testi: secim donemi, ilk 12 (secim Sharpe'ina gore) + tum adaylar
    ranked = df.sort_values("sec_sharpe", ascending=False)
    test_set = set(ranked.index[:12]) | set(df.index[df["aday"]])
    pvals = {}
    for n in test_set:
        base, sel, ppy = keep[n]
        if base["assets"] is None:
            continue
        held = base["held"].loc[sel.index]
        ar = bh[("core", "4h")].loc[sel.index]
        pvals[n] = shift_test(held, ar, COST, ppy, sharpe(sel, ppy))
    df["zamanlama_p"] = pd.Series(pvals).round(3)

    df = df.sort_values(["kazanan", "aday", "sec_sharpe"], ascending=False)
    df.to_csv(OUT / "turnuva.csv")

    bench = {
        "al_tut_secim": stats(bh_port[("core", "4h")].loc[keep[names[0]][1].index], 365 * 6),
        "al_tut_sinav": stats(bh_port[("core", "4h")].loc[bh_port[("core", "4h")].index >= SEL_END], 365 * 6),
    }
    pd.DataFrame(bench).T.to_csv(OUT / "al_tut.csv")
    pd.set_option("display.width", 250, "display.max_columns", 60)
    print(df.to_string())
    print(pd.DataFrame(bench).T.to_string())


if __name__ == "__main__":
    main()
