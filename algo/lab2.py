"""Strateji turnuvasi, 2. tur (yeni aileler). Kullanim:
    python lab2.py              # tam turnuva -> sonuc/turnuva2.csv
    python lab2.py --leakcheck  # gelecek bilgisi sizintisi testi (kesme testi)
    python lab2.py --only a,b   # yalniz secilen stratejiler (gelistirme icin; CSV yazmaz)

PROTOKOL (sonuclari gormeden yazildi, sonradan degistirilmez):
- Motor, maliyet (%0.15/taraf), walk-forward (2y egitim / 6 ay test, parametre portfoy Sharpe'iyla,
  tum varliklarda ortak), SECIM donemi (< 2025-01-01), SINAV donemi (2025+), gorulmemis coinler:
  tur 1 (lab.py) ile birebir ayni kod.
- Elemeler (secim donemi, 6 coin, 4h):
  A) Sharpe > max(6 coin esit agirlikli al-tut, BTC al-tut) ve > 0.5      [tur 1'de yalniz esit agirlik]
  B) 6 coinin en az 4'unde coin al-tutunu yener (portfoy stratejilerinde olculemez -> gecti)
  C) 2x maliyette Sharpe > esit agirlikli al-tut
  D) gunluk mumda Sharpe > gunluk al-tut (season_hour: gunluk mumda gun ici saat yok -> uygulanamaz, gecti)
  E) Deflated Sharpe > 0.90, deneme sayisi = 31 (tur 1) + 56 (diger turnuva) + bu turun denemeleri.
     Sharpe varyansi = bu turun denemeleri ile tur 1 (turnuva.csv) varyansindan BUYUK olani.
  F) KARAR TESTI - hayatta kalma yanliligi olmayan evren (2019 basi top-20'den 18 coin, cokenler dahil,
     4h, o an islem goren coinler arasinda esit agirlik; EOS->A ad degisimi birlestirildi): secim doneminde Sharpe > max(18 coin al-tut,
     BTC al-tut) VE 2x maliyetle Sharpe > 18 coin al-tut.
- Aday = A..F hepsi. Kazanan = aday + SINAV: 6 coinde Sharpe > al-tut ve maxDD daha sig (tur 1 kurali)
  VE 18 coin evreninde sinav Sharpe > max(18 coin al-tut, BTC al-tut).
- Zamanlama testi (tur 1): secim Sharpe'ina gore ilk 12 + adaylar, ortak kaydirmali dairesel test.
- Mevcut kazananlarla korelasyon (gunluk getiri, secim donemi): donchian, btc_filter_ema (tur 1, 6 coin 4h),
  ema_btcf (diger turnuva, 18 coin 1d). > 0.8 = yeni bilgi tasimiyor.
"""
import sys
import time

import numpy as np
import pandas as pd

import lab
from data import UNIVERSE_2019, fetch_ohlcv, fetch_symbol, load_panel
from ext_data import fear_greed, funding
from lab import (COST, CORE, SEL_END, UNSEEN, buy_hold, daily, deflated_sharpe, run_strategy, sharpe,
                 shift_test, stats)
from lab_strategies2 import NEEDS, PORTFOLIO2, SINGLE2

REG = (SINGLE2, PORTFOLIO2)
PRIOR_TRIALS = 31 + 56
OUT = lab.OUT
PPY4 = 365 * 6


def fetch_u19(s, iv):
    """data.fetch_symbol + EOS -> A (Vaulta) ad degisimi (Mayis 2025, 1:1): EOS'u delist sayma, birlestir."""
    if s == "EOSUSDT":
        a, b = fetch_ohlcv("EOSUSDT", iv), fetch_ohlcv("AUSDT", iv)
        return pd.concat([a, b[b.index > a.index[-1]]])
    return fetch_symbol(s, iv)


def load_all():
    data = {
        ("core", "4h"): lab.load(CORE, "4h"),
        ("core", "1d"): lab.load(CORE, "1d"),
        ("unseen", "4h"): lab.load(UNSEEN, "4h"),
        ("u19", "4h"): {s: fetch_u19(s, "4h") for s in UNIVERSE_2019},
    }
    btc = {"4h": data[("core", "4h")]["BTCUSDT"], "1d": data[("core", "1d")]["BTCUSDT"]}
    extra = {"fng": fear_greed(), "funding": funding("BTCUSDT")}
    return data, btc, extra


def yr_ret(r, y):
    x = r[r.index.year == y]
    return round(((1 + x).prod() - 1) * 100, 1) if len(x) else np.nan


# ---------------- sizinti (lookahead) testi ----------------
def leakcheck(data, btc, extra):
    """Strateji pozisyonunu tum veriyle ve veri T'de KESILMIS olarak hesapla. t < T icin ayni olmali.
    Fark varsa fonksiyon t'den sonraki veriyi kullaniyor demektir."""
    rng = np.random.default_rng(1)
    u19 = data[("u19", "4h")]
    assets = {"BTC": data[("core", "4h")]["BTCUSDT"], "DOGE(gec liste)": u19["DOGEUSDT"],
              "XMR(delist)": u19["XMRUSDT"]}
    closes = {"6coin": pd.DataFrame({s: d["close"] for s, d in data[("core", "4h")].items()}),
              "18coin": pd.DataFrame({s: d["close"] for s, d in u19.items()})}
    bad = 0
    for name, (fn, space) in {**SINGLE2, **PORTFOLIO2}.items():
        is_port = name in PORTFOLIO2
        heavy = name in ("ml_logit", "ml_gbm", "hmm_regime")
        for p in lab.combos(space):
            for aname, obj in (closes if is_port else assets).items():
                X = obj.ffill(limit=3) if is_port else obj
                ctx = {"ppy": PPY4, "ppd": 6, "btc": btc["4h"], **extra}
                full = np.nan_to_num(np.asarray(fn(X, ctx, **p), dtype=float))
                n_all = len(X)
                cuts = list(rng.integers(n_all // 5, n_all, 2 if heavy else 6))
                if heavy:  # yeniden egitim anlarinin hemen cevresi (etiket ufku hatasini yakalar)
                    R = 365 * 6 + 180 * 6
                    cuts += [R + d for d in (0, 1, 2, 6, 7, 8)]
                for n in cuts:
                    t_end = X.index[n - 1]
                    ctx_t = {"ppy": PPY4, "ppd": 6, "btc": btc["4h"].loc[:t_end],
                             "fng": extra["fng"].loc[:t_end] if extra["fng"] is not None else None,
                             "funding": extra["funding"].loc[:t_end] if extra["funding"] is not None else None}
                    part = np.nan_to_num(np.asarray(fn(X.iloc[:n], ctx_t, **p), dtype=float))
                    diff = int((np.abs(full[:n] - part) > 1e-9).sum())
                    if diff:
                        bad += 1
                        print(f"SIZINTI? {name} {p} {aname} kesme={n}: {diff} farkli deger")
        print(f"ok  {name:22s} {len(lab.combos(space))} param", flush=True)
    print("SIZINTI BULGUSU:", bad)
    return bad


# ---------------- mevcut kazananlar (korelasyon icin) ----------------
def reference_series(data, btc):
    refs = {}
    for name in ("donchian", "btc_filter_ema"):
        r, _ = run_strategy(name, data[("core", "4h")], "4h", [COST], btc["4h"])
        refs[name] = daily(r[COST]["port"])
    import tournament as T
    P = load_panel("1d")
    elig = T.eligibility(P, 1)
    res = T.run_system(P, 1, elig, "ema_btcf")
    idx = next(iter(res.values()))["1x"].index
    parts, _ = T.walk_forward(res, "1x", idx)
    refs["ema_btcf"] = T.stitch(res, parts, "1x")
    return refs


# ---------------- ana akis ----------------
def main(only=None):
    t0 = time.time()
    data, btc, extra = load_all()
    print("dis veri: FNG", "VAR" if extra["fng"] is not None else "YOK",
          "| fonlama", "VAR" if extra["funding"] is not None else "YOK", flush=True)
    bh = {k: buy_hold(v, k[1]) for k, v in data.items()}
    bh_port = {k: v.mean(axis=1) for k, v in bh.items()}
    bh_btc = {k: v["BTCUSDT"] for k, v in bh.items() if "BTCUSDT" in v}

    names = [n for n in list(SINGLE2) + list(PORTFOLIO2) if not only or n in only]
    skipped = [n for n in names if n in NEEDS and extra[NEEDS[n]] is None]
    names = [n for n in names if n not in skipped]
    rows, keep = [], {}
    for name in names:
        t1 = time.time()
        r4, ppy4 = run_strategy(name, data[("core", "4h")], "4h", [COST, 2 * COST], btc["4h"], REG, extra)
        r1, ppy1 = run_strategy(name, data[("core", "1d")], "1d", [COST], btc["1d"], REG, extra)
        ru, _ = run_strategy(name, data[("unseen", "4h")], "4h", [COST], btc["4h"], REG, extra)
        rs, _ = run_strategy(name, data[("u19", "4h")], "4h", [COST, 2 * COST], btc["4h"], REG, extra)
        base = r4[COST]
        port = base["port"]
        sel, hold = port[port.index < SEL_END], port[port.index >= SEL_END]
        held_mean = base["held"].mean(axis=1)
        row = {"strateji": name}
        row.update({f"sec_{k}": v for k, v in stats(sel, ppy4, held_mean).items()})
        row["sec_bh_sharpe"] = round(sharpe(bh_port[("core", "4h")].loc[sel.index], ppy4), 2)
        row["sec_btc_sharpe"] = round(sharpe(bh_btc[("core", "4h")].loc[sel.index], ppy4), 2)
        if base["assets"] is not None:
            a = base["assets"]
            a_sel = a[a.index < SEL_END]
            b_sel = bh[("core", "4h")].loc[a_sel.index]
            row["varlik_gecti_6da"] = int(sum(sharpe(a_sel[s], ppy4) > sharpe(b_sel[s], ppy4) for s in CORE))
        else:
            row["varlik_gecti_6da"] = np.nan
        p2 = r4[2 * COST]["port"]
        row["sec_sharpe_2xmaliyet"] = round(sharpe(p2[p2.index < SEL_END], ppy4), 2)
        p1 = r1[COST]["port"]
        p1s = p1[p1.index < SEL_END]
        row["sec_sharpe_1d"] = round(sharpe(p1s, ppy1), 2)
        row["sec_bh_sharpe_1d"] = round(sharpe(bh_port[("core", "1d")].loc[p1s.index], ppy1), 2)

        row.update({f"sinav_{k}": v for k, v in stats(hold, ppy4, held_mean).items()})
        s_bh = stats(bh_port[("core", "4h")].loc[hold.index], ppy4)
        s_btc = stats(bh_btc[("core", "4h")].loc[hold.index], ppy4)
        row["sinav_bh_sharpe"], row["sinav_bh_getiri_%"], row["sinav_bh_maxDD_%"] = s_bh["sharpe"], s_bh["getiri_%"], s_bh["maxDD_%"]
        row["sinav_btc_sharpe"], row["sinav_btc_getiri_%"], row["sinav_btc_maxDD_%"] = s_btc["sharpe"], s_btc["getiri_%"], s_btc["maxDD_%"]
        row["sinav_alfa"] = round(row["sinav_getiri_%"] - row["sinav_piyasada_%"] / 100 * s_bh["getiri_%"], 1)
        row["getiri_2025_%"], row["getiri_2026_%"] = yr_ret(hold, 2025), yr_ret(hold, 2026)

        pu = ru[COST]["port"]
        row["gorulmemis_sharpe"] = round(sharpe(pu, ppy4), 2)
        row["gorulmemis_bh_sharpe"] = round(sharpe(bh_port[("unseen", "4h")].loc[pu.index], ppy4), 2)

        # F: hayatta kalma yanliligi olmayan 18 coin evreni
        ps, ps2 = rs[COST]["port"], rs[2 * COST]["port"]
        ssel, shold = ps[ps.index < SEL_END], ps[ps.index >= SEL_END]
        u = ("u19", "4h")
        row["u19_sec_sharpe"] = round(sharpe(ssel, ppy4), 2)
        row["u19_sec_sharpe_2x"] = round(sharpe(ps2[ps2.index < SEL_END], ppy4), 2)
        row["u19_sec_maxDD_%"] = stats(ssel, ppy4)["maxDD_%"]
        row["u19_sec_getiri_%"] = stats(ssel, ppy4)["getiri_%"]
        row["u19_sec_bh_sharpe"] = round(sharpe(bh_port[u].loc[ssel.index], ppy4), 2)
        row["u19_sec_btc_sharpe"] = round(sharpe(bh_btc[u].loc[ssel.index], ppy4), 2)
        sh = stats(shold, ppy4)
        row["u19_sinav_sharpe"], row["u19_sinav_getiri_%"], row["u19_sinav_maxDD_%"] = sh["sharpe"], sh["getiri_%"], sh["maxDD_%"]
        row["u19_sinav_bh_sharpe"] = round(sharpe(bh_port[u].loc[shold.index], ppy4), 2)
        row["u19_sinav_btc_sharpe"] = round(sharpe(bh_btc[u].loc[shold.index], ppy4), 2)
        row["son_param"] = str(dict(base["segs"][-1][1]))
        rows.append(row)
        keep[name] = (base, sel, ppy4)
        print(f"... {name:22s} {time.time() - t1:6.1f}s  sec={row['sec_sharpe']}  u19={row['u19_sec_sharpe']}"
              f"  sinav={row['sinav_sharpe']}", flush=True)

    df = pd.DataFrame(rows).set_index("strateji")
    if only:
        pd.set_option("display.width", 250, "display.max_columns", 80)
        print(df.T.to_string())
        return

    # E: deflated Sharpe - tum denemeler
    n_total = PRIOR_TRIALS + len(names)
    d_sel = {n: daily(keep[n][1]) for n in names}
    srs = np.array([d.mean() / d.std() for d in d_sel.values()])
    var_this = float(np.var(srs, ddof=1))
    r1 = pd.read_csv(OUT / "turnuva.csv")
    var_r1 = float(np.var(r1["sec_sharpe"].to_numpy() / np.sqrt(365), ddof=1))
    var = max(var_this, var_r1)
    df["DSR"] = [round(deflated_sharpe(d_sel[n], var, n_total), 3) for n in names]
    # yalniz bilgi (karar DSR ile): tur 1 varyansiyla, ayni deneme sayisi
    df["DSR_tur1_varyans"] = [round(deflated_sharpe(d_sel[n], var_r1, n_total), 3) for n in names]

    df["A"] = (df["sec_sharpe"] > df[["sec_bh_sharpe", "sec_btc_sharpe"]].max(axis=1)) & (df["sec_sharpe"] > 0.5)
    df["B"] = df["varlik_gecti_6da"].fillna(4) >= 4
    df["C"] = df["sec_sharpe_2xmaliyet"] > df["sec_bh_sharpe"]
    df["D"] = (df["sec_sharpe_1d"] > df["sec_bh_sharpe_1d"]) | (df.index == "season_hour")
    df["E"] = df["DSR"] > 0.90
    df["F"] = ((df["u19_sec_sharpe"] > df[["u19_sec_bh_sharpe", "u19_sec_btc_sharpe"]].max(axis=1))
               & (df["u19_sec_sharpe_2x"] > df["u19_sec_bh_sharpe"]))
    df["aday"] = df[["A", "B", "C", "D", "E", "F"]].all(axis=1)
    df["sinav_gecti"] = ((df["sinav_sharpe"] > df["sinav_bh_sharpe"]) & (df["sinav_maxDD_%"] > df["sinav_bh_maxDD_%"])
                         & (df["u19_sinav_sharpe"] > df[["u19_sinav_bh_sharpe", "u19_sinav_btc_sharpe"]].max(axis=1)))
    df["kazanan"] = df["aday"] & df["sinav_gecti"]
    df["elemeler_gecti"] = df[["A", "B", "C", "D", "E", "F"]].sum(axis=1)

    # zamanlama testi
    ranked = df.sort_values("sec_sharpe", ascending=False)
    test_set = set(ranked.index[:12]) | set(df.index[df["aday"]])
    pvals = {}
    for n in test_set:
        base, sel, ppy = keep[n]
        if base["assets"] is None:
            continue
        held = base["held"].loc[sel.index]
        pvals[n] = shift_test(held, bh[("core", "4h")].loc[sel.index], COST, ppy, sharpe(sel, ppy))
    df["zamanlama_p"] = pd.Series(pvals).round(3)

    # korelasyon
    refs = reference_series(data, btc)
    for rn, rs_ in refs.items():
        rr = rs_[(rs_.index < SEL_END)]
        df[f"kor_{rn}"] = [round(d_sel[n].corr(rr.reindex(d_sel[n].index)), 2) for n in df.index]

    df = df.sort_values(["kazanan", "aday", "elemeler_gecti", "sec_sharpe"], ascending=False)
    df.to_csv(OUT / "turnuva2.csv")

    sel_idx = keep[names[0]][1].index
    bench = {
        "al_tut_6coin_secim": stats(bh_port[("core", "4h")].loc[sel_idx], PPY4),
        "btc_secim": stats(bh_btc[("core", "4h")].loc[sel_idx], PPY4),
        "al_tut_6coin_sinav": stats(bh_port[("core", "4h")].loc[bh_port[("core", "4h")].index >= SEL_END], PPY4),
        "btc_sinav": stats(bh_btc[("core", "4h")].loc[bh_btc[("core", "4h")].index >= SEL_END], PPY4),
    }
    u = ("u19", "4h")
    usel = bh_port[u].loc[(bh_port[u].index >= sel_idx[0]) & (bh_port[u].index < SEL_END)]
    bench["al_tut_18coin_secim"] = stats(usel, PPY4)
    bench["al_tut_18coin_sinav"] = stats(bh_port[u].loc[bh_port[u].index >= SEL_END], PPY4)
    for y in (2025, 2026):
        bench[f"al_tut_6coin_{y}_getiri"] = {"getiri_%": yr_ret(bh_port[("core", "4h")], y)}
        bench[f"btc_{y}_getiri"] = {"getiri_%": yr_ret(bh_btc[("core", "4h")], y)}
    pd.DataFrame(bench).T.to_csv(OUT / "al_tut2.csv")

    pd.set_option("display.width", 300, "display.max_columns", 80)
    print(f"\nDENEME SAYISI (DSR): {n_total}  | Sharpe varyansi bu tur {var_this:.2e}, tur1 {var_r1:.2e}, kullanilan {var:.2e}")
    print("Atlanan (dis veri yok):", skipped or "-")
    print(df.to_string())
    print(pd.DataFrame(bench).T.to_string())
    print(f"sure {time.time() - t0:.0f}s")


if __name__ == "__main__":
    if "--leakcheck" in sys.argv:
        leakcheck(*load_all())
    else:
        only = None
        if "--only" in sys.argv:
            only = sys.argv[sys.argv.index("--only") + 1].split(",")
        main(only)
