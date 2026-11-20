"""Trader ofisi kod tarayicisi (LLM yok). Her turda evrendeki (evren.py) her coin icin kurulum yakinligi puani
hesaplar, en iyi K coini (+ acik/bekleyen ofis pozisyonu olan coinleri) secer; BTC secilmediyse yalniz baglam olur.
Uzmanlar yalniz secilen coinleri gorur: tur maliyeti coin sayisiyla degil K ile buyur.
Varsayilan btc_always_trade: BTC her tur islem adayi, K coin BTC disindan secilir (2026-11-21 karari).

Puan (0-100, agirliklar ofis-ayar.json universe.weights):
  sr    anahtar seviyeye / deger alani kenarina yakinlik (hafta/ay H-L, 4h ve 180g VAH/VAL/POC, son 1d/4h pivotlar),
        mesafe ATR14(4h) cinsinden; 0 ATR = 1, >= sr_atr = 0
  bos   taze yapi kirilimi ya da likidite supurmesi (4h pivot: ilk kapanis otesi / fitil supurmesi son 2 mumda 1, son 6 mumda 0,6;
        1h supurme son 4 mumda 0,5)
  harm  veri_topla.harmonics adayi: at_prz fit, reacted 0,8 x fit, PRZ'ye <= 1 ATR forming 0,5 x fit
  brk   son kapali 4h mum 20 mumluk araligin disinda kapandi + hacim >= 1,5x ort. (hacimsiz 0,4); 1d icin 1,3x
  ew    Elliott'a uygun salinim tamamlanmasi: 4h zigzag'da kurallara uyan 5 dalga itki (3 en kisa degil, 4 ile 1 ortusmez)
        son pivotu <= 8 mum once onaylandi = 1; 1d trendine karsi ABC (C, A'nin otesinde) = 0,6
  div   RSI uyumsuzlugu: son iki ayni tip 4h pivotta fiyat yeni uc, RSI14 degil, son pivot <= 10 mum = 1 (1d: <= 5 mum = 1)
Akil saglik suzgeci: 4h ort. spot hacim >= min_qvol_4h_musd ve ATR14(4h)/fiyat min_atr_pct..max_atr_pct; disi secilmez.
Beta: 30 gun 4h log getirisinin BTC'ye regresyonu (risk: altcoin = beta x BTC riski).

Kullanim: python algo/ofis/tarayici.py   # canli tarama, veri/tarama_son.json yazar, secimi basar
"""
import concurrent.futures as cf
import json
import sys
import time

import numpy as np
import pandas as pd

import ortak as O

DEF = {"enabled": False, "k": 3, "btc_always_trade": True, "min_score": 15, "sr_atr": 0.75, "min_qvol_4h_musd": 2.0, "min_atr_pct": 0.3,
       "max_atr_pct": 8.0, "weights": {"sr": 20, "bos": 20, "harm": 15, "brk": 20, "ew": 10, "div": 15}}


def ucfg(cfg=None):
    u = dict(DEF)
    u.update((cfg or O.ayar()).get("universe") or {})
    u["weights"] = {**DEF["weights"], **(u.get("weights") or {})}
    return u


def _recent(t, idx, n, day=False):
    """t (ts metni) son n kapali mumun icinde mi."""
    if not t:
        return False
    import veri_topla as V
    return t >= V.ts(idx[-n], day)


# ---------------- bilesenler ----------------
def c_sr(V, fr, last, a4, asof, lim):
    d1, h4 = fr["1d"], fr["4h"]
    lv = V.key_levels(d1, asof)
    cand = []
    for k in ("prev_week_hl", "prev_month_hl"):
        cand += [(k, x) for x in (lv.get(k) or [])]
    for name, vp in (("vp4h", V.vprofile(h4)), ("vp180d", V.vprofile(d1.tail(180)))):
        if vp:
            cand += [(f"{name}.{k}", vp[k]) for k in ("vah", "val", "poc")]
    for iv, df, n in (("4h", h4, 3), ("1d", d1, 2)):
        piv, _ = V.zigzag(df, V.ZZ_K[iv])
        cand += [(f"pivot{iv}", p) for _, p, _ in piv[-n:]]
    cand = [(k, x) for k, x in cand if x]
    if not cand or not a4:
        return 0.0, None
    k, x = min(cand, key=lambda c: abs(last - c[1]))
    d = abs(last - x) / a4
    return max(0.0, 1 - d / lim), f"{k} {V.r5(x)} at {d:.2f} ATR"


def c_bos(V, fr):
    best, why = 0.0, None
    for iv, df, keep in (("4h", fr["4h"], 12), ("1h", fr["1h"], 10)):
        st = V.structure(df, iv, keep)
        for t, p, lab, broke, swept, _ in st["pivots"]:
            for ev, tt in (("BOS", broke), ("sweep", swept)):
                if iv == "4h" and _recent(tt, df.index, 2):
                    s = 1.0
                elif iv == "4h" and _recent(tt, df.index, 6):
                    s = 0.6
                elif iv == "1h" and ev == "sweep" and _recent(tt, df.index, 4):
                    s = 0.5
                else:
                    continue
                if s > best:
                    best, why = s, f"{iv} {ev} of {lab} {p} at {tt}"
    return best, why


def c_harm(V, fr):
    try:
        hs = V.harmonics(fr)
    except Exception:  # noqa: BLE001
        return 0.0, None
    best, why = 0.0, None
    for h in hs:
        f = (h.get("fit") or 0) / 100
        s = {"at_prz": f, "reacted": 0.8 * f}.get(h["status"], 0.0)
        if h["status"] == "forming" and (h.get("dist_prz_atr") or 9) <= 1:
            s = 0.5 * f
        if s > best:
            best, why = s, f"{h['dir']} {h['pattern']} {h['tf']} {h['status']} fit {h.get('fit')}"
    return best, why


def c_brk(fr):
    best, why = 0.0, None
    for iv, df, vm in (("4h", fr["4h"], 1.5), ("1d", fr["1d"], 1.3)):
        prev = df.iloc[-21:-1]
        c, v = df.close.iloc[-1], df.qvol.iloc[-1]
        hi, lo, va = prev.high.max(), prev.low.min(), prev.qvol.mean()
        side = "up" if c > hi else "down" if c < lo else None
        if not side:
            continue
        s = 1.0 if va > 0 and v >= vm * va else 0.4
        if s > best:
            best, why = s, f"{iv} close {side} out of 20-bar range, vol x{v / va:.1f}" if va > 0 else f"{iv} breakout {side}"
    return best, why


def c_ew(V, fr):
    h4, d1 = fr["4h"], fr["1d"]
    piv, _ = V.zigzag(h4, V.ZZ_K["4h"])
    n = len(h4)
    if len(piv) >= 6:
        p = [x[1] for x in piv[-6:]]
        t = [x[2] for x in piv[-6:]]
        recent = n - 1 - piv[-1][0] <= 8
        for up in (True, False):
            s = 1 if up else -1
            if t[0] != ("L" if up else "H"):
                continue
            w1, w3, w5 = s * (p[1] - p[0]), s * (p[3] - p[2]), s * (p[5] - p[4])
            rules = (min(w1, w3, w5) > 0 and s * (p[2] - p[0]) > 0 and s * (p[4] - p[1]) > 0
                     and w3 > min(w1, w5) and s * (p[5] - p[3]) > 0)
            if rules and recent:
                return 1.0, f"4h 5-wave {'up' if up else 'down'} impulse completed at {V.r5(p[5])}"
    if len(piv) >= 4:
        trend_up = d1.close.iloc[-1] > V.ema(d1.close, 50).iloc[-1]
        (_, p0, t0), (_, pa, _), (_, pb, _), (ic, pc, tc) = piv[-4:]
        recent = n - 1 - ic <= 8
        if recent and trend_up and tc == "L" and t0 == "H" and pc < pa:
            return 0.6, f"4h ABC pullback in 1d uptrend, C {V.r5(pc)} < A {V.r5(pa)}"
        if recent and not trend_up and tc == "H" and t0 == "L" and pc > pa:
            return 0.6, f"4h ABC bounce in 1d downtrend, C {V.r5(pc)} > A {V.r5(pa)}"
    return 0.0, None


def c_div(V, fr):
    for iv, df, nmax, keep in (("4h", fr["4h"], 10, 12), ("1d", fr["1d"], 5, 12)):
        st = V.structure(df, iv, keep)
        idx = {V.ts(t, iv == "1d"): i for i, t in enumerate(df.index)}
        for typ in ("H", "L"):
            ps = [x for x in st["pivots"] if x[2].endswith(typ)]
            if len(ps) < 2:
                continue
            (t1, p1, _, _, _, r1), (t2, p2, _, _, _, r2) = ps[-2], ps[-1]
            i2 = idx.get(t2)
            if i2 is None or len(df) - 1 - i2 > nmax or r1 is None or r2 is None:
                continue
            if typ == "H" and p2 > p1 and r2 < r1:
                return 1.0, f"{iv} bearish RSI div: high {p2}>{p1}, RSI {r2}<{r1}"
            if typ == "L" and p2 < p1 and r2 > r1:
                return 1.0, f"{iv} bullish RSI div: low {p2}<{p1}, RSI {r2}>{r1}"
    return 0.0, None


def beta(fr, btc):
    a = np.log(fr["4h"].close).diff().tail(180)
    b = np.log(btc["4h"].close).diff().reindex(a.index)
    m = a.notna() & b.notna()
    if m.sum() < 60 or b[m].var() <= 0:
        return None
    return round(float(np.cov(a[m], b[m])[0, 1] / b[m].var()), 2)


def score_coin(V, sym, fr, btc, asof, u):
    h4 = fr["4h"]
    last, a4 = float(h4.close.iloc[-1]), float(V.atr(h4).iloc[-1])
    qv = float(h4.qvol.tail(20).mean()) / 1e6
    atr_pct = 100 * a4 / last
    out = {"last_close": V.r5(last), "atr4h_pct": round(atr_pct, 2), "qvol_4h_musd": round(qv, 1),
           "beta_btc_30d": 1.0 if sym == "BTCUSDT" else beta(fr, btc), "parts": {}, "why": []}
    sane = qv >= u["min_qvol_4h_musd"] and u["min_atr_pct"] <= atr_pct <= u["max_atr_pct"]
    out["sane"] = bool(sane)
    if not sane:
        out["why"].append(f"sanity fail: qvol4h {qv:.1f}M, ATR {atr_pct:.2f}%")
    comps = {"sr": lambda: c_sr(V, fr, last, a4, asof, u["sr_atr"]), "bos": lambda: c_bos(V, fr),
             "harm": lambda: c_harm(V, fr), "brk": lambda: c_brk(fr), "ew": lambda: c_ew(V, fr),
             "div": lambda: c_div(V, fr)}
    tot = 0.0
    for k, f in comps.items():
        try:
            s, why = f()
        except Exception as e:  # noqa: BLE001
            s, why = 0.0, f"{k} error {type(e).__name__}"
        out["parts"][k] = round(s, 2)
        tot += u["weights"][k] * s
        if why and s > 0:
            out["why"].append(f"{k}: {why}")
    out["score"] = round(tot, 1)
    return out


# ---------------- secim ----------------
def live_assets():
    """Acik ya da bekleyen OFIS pozisyonu olan coinler (her zaman analiz edilir)."""
    try:
        import defter as D
        st = D.load_state()
        return sorted({t["asset"] for t in st["trades"] if t["book"] == "ofis" and t["status"] in ("pending", "open")})
    except Exception:  # noqa: BLE001
        return []


def secim(cfg=None, log=print, force_universe=False):
    """Donus: {"assets": analiz edilecekler, "context": ["BTCUSDT"] ya da [], "fetch": veri_topla listesi, "scores": ...}."""
    import veri_topla as V
    import evren as E
    t0 = time.time()
    u = ucfg(cfg)
    uni = E.get_universe(force=force_universe, log=log)
    asof = pd.Timestamp.now(tz="UTC").floor("4h")
    frames, syms = {}, list(dict.fromkeys(["BTCUSDT"] + uni))
    jobs = [(s, iv) for s in syms for iv in ("1h", "4h", "1d")]
    with cf.ThreadPoolExecutor(max_workers=8) as pool:   # 30 istek sirayla ~50 sn, paralel ~8 sn
        got = dict(zip(jobs, pool.map(lambda j: V.klines(j[0], j[1], asof), jobs)))
    for s in syms:
        fr = {iv: got[(s, iv)] for iv in ("1h", "4h", "1d")}
        if any(v is None or len(v) < 30 for v in fr.values()):   # veri_topla ile ayni alt sinir
            log(f"tarama: {s} klines missing")
            continue
        frames[s] = fr
    btc = frames.get("BTCUSDT")
    sc = {}
    for s in uni:
        if s in frames and btc is not None:
            sc[s] = score_coin(V, s, frames[s], btc, asof, u)
    # btc_always_trade (varsayilan, 2026-11-21): BTC her tur tam analiz + islem adayi; K coin BTC disindan secilir.
    # false ise BTC de siralamaya girer, secilmezse yalniz baglam blogu olur.
    base = ["BTCUSDT"] if u["btc_always_trade"] else []
    rank = sorted((s for s in sc if sc[s]["sane"] and s not in base), key=lambda s: -sc[s]["score"])
    pick = [s for s in rank if sc[s]["score"] >= u["min_score"]][:u["k"]] or rank[:1]
    forced = [s for s in live_assets() if s not in pick + base]
    assets = base + pick + forced
    context = [] if "BTCUSDT" in assets else ["BTCUSDT"]
    res = {"asof_utc": V.ts(asof), "generated_utc": O.fmt(O.now_utc()), "universe": uni, "k": u["k"],
           "assets": assets, "picked": pick, "forced_open": forced, "context": context,
           "fetch": context + assets, "ranking": [[s, sc[s]["score"]] for s in sorted(sc, key=lambda s: -sc[s]["score"])],
           "scores": sc, "secs": round(time.time() - t0, 1), "errors": list(V.ERR)}
    O.write_json(O.VERI / "tarama_son.json", res)
    O.write_json(O.VERI / f"tarama_{asof.strftime('%Y%m%d_%H%M')}.json", res)
    log(f"tarama {res['secs']}s: picked={pick} forced={forced} context={context} ranking={res['ranking']}")
    return res


def btc_context(a):
    """BTC secilmediginde uzmanlara giden kucuk baglam blogu (~400 token): blok yazilmaz."""
    if not a:
        return None
    lv = a.get("levels") or {}
    dv = a.get("derivs") or {}
    st = a.get("structure") or {}
    return {"_context_only": True,
            "_note": "BTC market context only (regime/beta reference). Not analysed this round: write NO block for it.",
            "ctx": a.get("ctx"),
            "levels": {k: lv.get(k) for k in ("prev_week_hl", "prev_month_hl", "week_open", "month_open")},
            "structure": {iv: {"pivots": (st.get(iv) or {}).get("pivots", [])[-5:],
                               "current_leg_extreme": (st.get(iv) or {}).get("current_leg_extreme")}
                          for iv in ("1d", "4h")},
            "derivs_lite": {k: dv.get(k) for k in ("funding_last", "funding_7d_avg", "oi_chg_24h_pct")}}


def uygula(snap, sel, log=print):
    """Snapshot'i secime gore kirpar (bellekte; diskteki dosya ve SHA degismez). Donus: (snap, tur varliklari)."""
    sa = snap.get("assets") or {}
    for s in sel.get("context", []):
        sa[s] = btc_context(sa.get(s))
    for s in sel["assets"]:
        x = sa.get(s)
        if x and isinstance(x.get("ctx"), dict):
            x["ctx"]["beta_btc_30d"] = (sel["scores"].get(s) or {}).get("beta_btc_30d", 1.0 if s == "BTCUSDT" else None)
    for s in list(sa):
        if s not in sel["assets"] and s not in sel.get("context", []):
            sa.pop(s)
    round_assets = [s for s in sel["assets"] if sa.get(s)]
    miss = [s for s in sel["assets"] if s not in round_assets]
    if miss:
        log(f"tarama: selected but missing in snapshot: {miss}")
    return snap, round_assets


if __name__ == "__main__":
    sys.path.insert(0, str(O.ROOT))
    r = secim(force_universe="--force-universe" in sys.argv)
    print(json.dumps({k: r[k] for k in ("assets", "context", "ranking", "secs")}, ensure_ascii=False))
    for s, x in sorted(r["scores"].items(), key=lambda kv: -kv[1]["score"]):
        print(f"{s:10s} {x['score']:5.1f} beta={x['beta_btc_30d']} parts={x['parts']} | " + " ; ".join(x["why"]))
