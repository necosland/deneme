"""Strateji turnuvasi, 4. tur: KOMBINASYONLAR. Kullanim:
    python lab4.py              # tam turnuva -> sonuc/turnuva4.csv
    python lab4.py --leakcheck  # gelecek bilgisi sizintisi testi (kesme testi) -> stdout
    python lab4.py --smoke      # yalniz pozisyon/ maruziyet kontrolu (performans YAZMAZ)

PROTOKOL (on-kayit: sonuc/RAPOR4.md "Plan" bolumu; sonuclari gormeden yazildi ve commit edildi):
- Motor, maliyet (%0.15/taraf), walk-forward (2y egitim / 6 ay test, parametre portfoy Sharpe'iyla, tum
  varliklarda ortak), SECIM (< 2025-01-01), SINAV (2025+), gorulmemis coinler, 18 coin hayatta-kalma-yanliligi
  olmayan evren: tur 2 (lab2.py) ile birebir ayni kod (lab.run_strategy).
- Elemeler A-F: tur 2 ile ayni. E'de deneme sayisi = 115 (onceki) + bu turda calisan TUM yeni seriler
  (kombinasyonlar + yeni bilesenler). Tur 1 sistemlerinin birebir tekrari sayilmaz.
- G (yeni): kombinasyonun secim Sharpe'i en iyi bileseninin (ayni walk-forward, secim Sharpe'ina gore en iyi)
  Sharpe'indan BUYUK ve secim maxDD'si o bilesenden KOTU DEGIL (>=).
- Aday = A..G. Kazanan = aday + tur 2 sinav kurali.
- Walk-forward topluluklari (WF_COMBOS): her uye kendi tur 1 izgarasiyla walk-forward edilir; OOS pozisyonlari
  (held) ortalanir (istenirse rejimle carpilir); maliyet ortalama pozisyonun degisimine kesilir (ayar
  degisimindeki kaymalar dahil -> bilesenlerden biraz daha pahali, temkinli).
"""
import sys
import time

import numpy as np
import pandas as pd

import lab
import lab2
from lab import COST, CORE, SEL_END, buy_hold, daily, deflated_sharpe, run_strategy, sharpe, shift_test, stats
from lab2 import yr_ret
from lab_strategies4 import ALL_FNS, COMBOS, COMPONENTS, NEEDS, R1_COMPONENTS, WF_COMBOS

REG = (ALL_FNS, {})
PRIOR_TRIALS = 115
OUT = lab.OUT
PPY4 = 365 * 6
DATASETS = [(("core", "4h"), [COST, 2 * COST]), (("core", "1d"), [COST]), (("unseen", "4h"), [COST]),
            (("u19", "4h"), [COST, 2 * COST])]


def load_all():
    data, btc, extra = lab2.load_all()
    extra["eth"] = {6: data[("core", "4h")]["ETHUSDT"], 1: data[("core", "1d")]["ETHUSDT"]}
    return data, btc, extra


# ---------------- walk-forward toplulugu ----------------
def wf_combo(spec, dfs, iv, costs, btc, extra):
    members, regime = spec[0], spec[1]
    runs = [run_strategy(f"R1_{m}", dfs, iv, costs, btc, REG, extra)[0] for m in members]
    reg = run_strategy(regime, dfs, iv, costs, btc, REG, extra)[0] if regime else None
    out = {}
    for c in costs:
        H = sum(r[c]["held"] for r in runs) / len(runs)
        if reg is not None:
            H = H * reg[c]["held"]
        nets = {}
        for s, df in dfs.items():
            h = H[s].dropna()
            ret = df["close"].pct_change().fillna(0.0).reindex(h.index).fillna(0.0)
            turn = h.diff().abs()
            if len(turn):
                turn.iloc[0] = abs(h.iloc[0])
            nets[s] = (h * ret - turn * c).reindex(H.index)
        A = pd.DataFrame(nets)
        out[c] = {"port": A.mean(axis=1), "assets": A, "held": H, "segs": [(None, "wf")]}
    return out


def evaluate(name, data, btc, extra):
    res = {}
    for key, costs in DATASETS:
        iv = key[1]
        if name in WF_COMBOS:
            res[key] = wf_combo(WF_COMBOS[name], data[key], iv, costs, btc[iv], extra)
        else:
            res[key] = run_strategy(name, data[key], iv, costs, btc[iv], REG, extra)[0]
    return res


def metrics(name, R, bh, bh_port, bh_btc):
    base = R[("core", "4h")][COST]
    port = base["port"]
    sel, hold = port[port.index < SEL_END], port[port.index >= SEL_END]
    held_mean = base["held"].mean(axis=1)
    row = {"strateji": name}
    row.update({f"sec_{k}": v for k, v in stats(sel, PPY4, held_mean).items()})
    row["sec_bh_sharpe"] = round(sharpe(bh_port[("core", "4h")].loc[sel.index], PPY4), 2)
    row["sec_btc_sharpe"] = round(sharpe(bh_btc[("core", "4h")].loc[sel.index], PPY4), 2)
    a = base["assets"]
    a_sel = a[a.index < SEL_END]
    b_sel = bh[("core", "4h")].loc[a_sel.index]
    row["varlik_gecti_6da"] = int(sum(sharpe(a_sel[s], PPY4) > sharpe(b_sel[s], PPY4) for s in CORE))
    p2 = R[("core", "4h")][2 * COST]["port"]
    row["sec_sharpe_2xmaliyet"] = round(sharpe(p2[p2.index < SEL_END], PPY4), 2)
    p1 = R[("core", "1d")][COST]["port"]
    p1s = p1[p1.index < SEL_END]
    row["sec_sharpe_1d"] = round(sharpe(p1s, 365), 2)
    row["sec_bh_sharpe_1d"] = round(sharpe(bh_port[("core", "1d")].loc[p1s.index], 365), 2)

    row.update({f"sinav_{k}": v for k, v in stats(hold, PPY4, held_mean).items()})
    s_bh = stats(bh_port[("core", "4h")].loc[hold.index], PPY4)
    s_btc = stats(bh_btc[("core", "4h")].loc[hold.index], PPY4)
    row["sinav_bh_sharpe"], row["sinav_bh_getiri_%"], row["sinav_bh_maxDD_%"] = s_bh["sharpe"], s_bh["getiri_%"], s_bh["maxDD_%"]
    row["sinav_btc_sharpe"] = s_btc["sharpe"]
    row["getiri_2025_%"], row["getiri_2026_%"] = yr_ret(hold, 2025), yr_ret(hold, 2026)

    pu = R[("unseen", "4h")][COST]["port"]
    row["gorulmemis_sharpe"] = round(sharpe(pu, PPY4), 2)
    row["gorulmemis_bh_sharpe"] = round(sharpe(bh_port[("unseen", "4h")].loc[pu.index], PPY4), 2)

    u = ("u19", "4h")
    ps, ps2 = R[u][COST]["port"], R[u][2 * COST]["port"]
    ssel, shold = ps[ps.index < SEL_END], ps[ps.index >= SEL_END]
    row["u19_sec_sharpe"] = round(sharpe(ssel, PPY4), 2)
    row["u19_sec_sharpe_2x"] = round(sharpe(ps2[ps2.index < SEL_END], PPY4), 2)
    row["u19_sec_maxDD_%"] = stats(ssel, PPY4)["maxDD_%"]
    row["u19_sec_bh_sharpe"] = round(sharpe(bh_port[u].loc[ssel.index], PPY4), 2)
    row["u19_sec_btc_sharpe"] = round(sharpe(bh_btc[u].loc[ssel.index], PPY4), 2)
    sh = stats(shold, PPY4)
    row["u19_sinav_sharpe"], row["u19_sinav_getiri_%"], row["u19_sinav_maxDD_%"] = sh["sharpe"], sh["getiri_%"], sh["maxDD_%"]
    row["u19_sinav_bh_sharpe"] = round(sharpe(bh_port[u].loc[shold.index], PPY4), 2)
    row["u19_sinav_btc_sharpe"] = round(sharpe(bh_btc[u].loc[shold.index], PPY4), 2)
    last = base["segs"][-1][1]
    row["son_param"] = "wf" if last == "wf" else str(dict(last))
    return row, (base, sel)


# ---------------- sizinti testi ----------------
def cut_ctx(btc4, extra, t_end):
    return {"ppy": PPY4, "ppd": 6, "btc": btc4.loc[:t_end],
            "fng": extra["fng"].loc[:t_end] if extra["fng"] is not None else None,
            "eth": {6: extra["eth"][6].loc[:t_end], 1: extra["eth"][1]}}


def leakcheck(data, btc, extra):
    rng = np.random.default_rng(4)
    u19 = data[("u19", "4h")]
    assets = {"BTC": data[("core", "4h")]["BTCUSDT"], "ETH": data[("core", "4h")]["ETHUSDT"],
              "DOGE(gec liste)": u19["DOGEUSDT"], "XMR(delist)": u19["XMRUSDT"]}
    bad = 0
    for name, (fn, space) in ALL_FNS.items():
        for p in lab.combos(space):
            for aname, X in assets.items():
                ctx = {"ppy": PPY4, "ppd": 6, "btc": btc["4h"], **extra}
                full = np.nan_to_num(np.asarray(fn(X, ctx, **p), dtype=float))
                n_all = len(X)
                for n in rng.integers(n_all // 5, n_all, 4):
                    part = np.nan_to_num(np.asarray(fn(X.iloc[:n], cut_ctx(btc["4h"], extra, X.index[n - 1]), **p),
                                                    dtype=float))
                    diff = int((np.abs(full[:n] - part) > 1e-9).sum())
                    if diff:
                        bad += 1
                        print(f"SIZINTI? {name} {p} {aname} kesme={n}: {diff} farkli deger")
        print(f"ok  {name:24s} {len(lab.combos(space))} param", flush=True)
    print("SIZINTI BULGUSU:", bad)
    return bad


def smoke(data, btc, extra):
    """Performans gostermeden: her fonksiyonun BTC ve SOL'de ortalama maruziyeti ve islem sayisi."""
    ctx = {"ppy": PPY4, "ppd": 6, "btc": btc["4h"], **extra}
    for name, (fn, space) in ALL_FNS.items():
        p = lab.combos(space)[0]
        for s in ("BTCUSDT", "SOLUSDT"):
            x = fn(data[("core", "4h")][s], ctx, **p)
            print(f"{name:24s} {s:8s} {p} maruziyet={x.mean():.2f} degisim={int((x.diff().abs() > 0).sum())}")


# ---------------- ana akis ----------------
def main():
    t0 = time.time()
    data, btc, extra = load_all()
    print("dis veri: FNG", "VAR" if extra["fng"] is not None else "YOK", flush=True)
    bh = {k: buy_hold(v, k[1]) for k, v in data.items()}
    bh_port = {k: v.mean(axis=1) for k, v in bh.items()}
    bh_btc = {k: v["BTCUSDT"] for k, v in bh.items() if "BTCUSDT" in v}

    names_comp = list(COMPONENTS) + list(R1_COMPONENTS)
    names_combo = list(COMBOS) + list(WF_COMBOS)
    names = [n for n in names_comp + names_combo if not (n in NEEDS and extra[NEEDS[n]] is None)]
    rows, keep = [], {}
    for name in names:
        t1 = time.time()
        R = evaluate(name, data, btc, extra)
        row, kp = metrics(name, R, bh, bh_port, bh_btc)
        row["tur"] = "kombinasyon" if name in names_combo else ("tur1_tekrar" if name in R1_COMPONENTS else "bilesen")
        rows.append(row)
        keep[name] = kp
        print(f"... {name:24s} {time.time() - t1:6.1f}s", flush=True)

    df = pd.DataFrame(rows).set_index("strateji")
    new = [n for n in names if n not in R1_COMPONENTS]
    n_total = PRIOR_TRIALS + len(new)
    d_sel = {n: daily(keep[n][1]) for n in names}
    srs = np.array([d_sel[n].mean() / d_sel[n].std() for n in new])
    var_this = float(np.var(srs, ddof=1))
    r1 = pd.read_csv(OUT / "turnuva.csv")
    var_r1 = float(np.var(r1["sec_sharpe"].to_numpy() / np.sqrt(365), ddof=1))
    var = max(var_this, var_r1)
    df["DSR"] = [round(deflated_sharpe(d_sel[n], var, n_total), 3) for n in df.index]

    df["A"] = (df["sec_sharpe"] > df[["sec_bh_sharpe", "sec_btc_sharpe"]].max(axis=1)) & (df["sec_sharpe"] > 0.5)
    df["B"] = df["varlik_gecti_6da"] >= 4
    df["C"] = df["sec_sharpe_2xmaliyet"] > df["sec_bh_sharpe"]
    df["D"] = df["sec_sharpe_1d"] > df["sec_bh_sharpe_1d"]
    df["E"] = df["DSR"] > 0.90
    df["F"] = ((df["u19_sec_sharpe"] > df[["u19_sec_bh_sharpe", "u19_sec_btc_sharpe"]].max(axis=1))
               & (df["u19_sec_sharpe_2x"] > df["u19_sec_bh_sharpe"]))

    # G: en iyi bilesen (secim Sharpe'ina gore) ile karsilastirma
    comp_of = {**{k: v[2] for k, v in COMBOS.items()}, **{k: v[2] for k, v in WF_COMBOS.items()}}
    gcols = {c: {} for c in ["bilesen_en_iyi", "bil_sec_sharpe", "bil_sec_maxDD_%", "bil_sinav_sharpe",
                             "bil_sinav_maxDD_%", "bil_sinav_getiri_%", "bil_u19_sec_sharpe", "bil_u19_sinav_sharpe",
                             "G", "sinavda_bileseni_yendi", "u19_sinavda_bileseni_yendi", "bilesen_kor"]}
    for n in df.index:
        if n not in comp_of:
            continue
        comps = [c for c in comp_of[n] if c in df.index]
        best = max(comps, key=lambda c: df.at[c, "sec_sharpe"])
        b = df.loc[best]
        gcols["bilesen_en_iyi"][n] = best
        for src, dst in [("sec_sharpe", "bil_sec_sharpe"), ("sec_maxDD_%", "bil_sec_maxDD_%"),
                         ("sinav_sharpe", "bil_sinav_sharpe"), ("sinav_maxDD_%", "bil_sinav_maxDD_%"),
                         ("sinav_getiri_%", "bil_sinav_getiri_%"), ("u19_sec_sharpe", "bil_u19_sec_sharpe"),
                         ("u19_sinav_sharpe", "bil_u19_sinav_sharpe")]:
            gcols[dst][n] = b[src]
        gcols["G"][n] = bool(df.at[n, "sec_sharpe"] > b["sec_sharpe"] and df.at[n, "sec_maxDD_%"] >= b["sec_maxDD_%"])
        gcols["sinavda_bileseni_yendi"][n] = bool(df.at[n, "sinav_sharpe"] > b["sinav_sharpe"])
        gcols["u19_sinavda_bileseni_yendi"][n] = bool(df.at[n, "u19_sinav_sharpe"] > b["u19_sinav_sharpe"])
        gcols["bilesen_kor"][n] = round(d_sel[n].corr(d_sel[best]), 2)
    for c, v in gcols.items():
        df[c] = pd.Series(v)

    is_combo = df["tur"] == "kombinasyon"
    # bilesenler yarismaz; yalniz karsilastirma icin
    df["aday"] = is_combo & df[["A", "B", "C", "D", "E", "F"]].all(axis=1) & df["G"].fillna(False).astype(bool)
    df["sinav_gecti"] = ((df["sinav_sharpe"] > df["sinav_bh_sharpe"]) & (df["sinav_maxDD_%"] > df["sinav_bh_maxDD_%"])
                         & (df["u19_sinav_sharpe"] > df[["u19_sinav_bh_sharpe", "u19_sinav_btc_sharpe"]].max(axis=1)))
    df["kazanan"] = df["aday"] & df["sinav_gecti"]
    df["elemeler_gecti"] = df[["A", "B", "C", "D", "E", "F"]].sum(axis=1) + df["G"].fillna(False).astype(int)

    # zamanlama testi: kombinasyonlarda secim Sharpe'ina gore ilk 12 + adaylar
    ranked = df[is_combo].sort_values("sec_sharpe", ascending=False)
    test_set = set(ranked.index[:12]) | set(df.index[df["aday"]])
    pvals = {}
    for n in test_set:
        base, sel = keep[n]
        held = base["held"].loc[sel.index]
        pvals[n] = shift_test(held, bh[("core", "4h")].loc[sel.index], COST, PPY4, sharpe(sel, PPY4))
    df["zamanlama_p"] = pd.Series(pvals).round(3)

    refs = lab2.reference_series(data, btc)
    for rn, rs_ in refs.items():
        rr = rs_[rs_.index < SEL_END]
        df[f"kor_{rn}"] = [round(d_sel[n].corr(rr.reindex(d_sel[n].index)), 2) for n in df.index]
        rh = rs_[rs_.index >= SEL_END]
        kh = {}
        for n in df.index:
            dh = daily(keep[n][0]["port"])
            dh = dh[dh.index >= SEL_END]
            kh[n] = round(dh.corr(rh.reindex(dh.index)), 2)
        df[f"kor_sinav_{rn}"] = pd.Series(kh)

    df["tur_sira"] = df["tur"].map({"kombinasyon": 0, "bilesen": 1, "tur1_tekrar": 2})
    df = df.sort_values(["tur_sira", "kazanan", "aday", "elemeler_gecti", "sec_sharpe"],
                        ascending=[True, False, False, False, False]).drop(columns="tur_sira")
    df.to_csv(OUT / "turnuva4.csv")

    pd.set_option("display.width", 320, "display.max_columns", 120, "display.max_colwidth", 40)
    print(f"\nDENEME SAYISI (DSR): {n_total} = {PRIOR_TRIALS} + {len(new)} | Sharpe varyansi bu tur {var_this:.2e}, "
          f"tur1 {var_r1:.2e}, kullanilan {var:.2e}")
    show = ["tur", "sec_sharpe", "sec_maxDD_%", "bil_sec_sharpe", "bil_sec_maxDD_%", "bilesen_en_iyi", "G",
            "A", "B", "C", "D", "E", "F", "DSR", "u19_sec_sharpe", "sinav_sharpe", "sinav_getiri_%", "sinav_maxDD_%",
            "bil_sinav_sharpe", "u19_sinav_sharpe", "bil_u19_sinav_sharpe", "aday", "kazanan", "zamanlama_p",
            "kor_donchian", "kor_btc_filter_ema", "kor_ema_btcf"]
    print(df[show].to_string())
    print(df.T.to_string())
    print(f"sure {time.time() - t0:.0f}s")


if __name__ == "__main__":
    if "--leakcheck" in sys.argv:
        leakcheck(*load_all())
    elif "--smoke" in sys.argv:
        smoke(*load_all())
    else:
        main()
