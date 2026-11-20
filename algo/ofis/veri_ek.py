"""Trader ofisi ek veri (TASARIM.md 14 "Ek veri ve kayitcilar", 2026-11-21): opsiyon, zincir ustu, capraz varlik stresi, emir defteri, kayitlardan
ozetler. Yalniz herkese acik, anahtarsiz uc noktalar; LLM yok. veri_topla.py cagirir; her bolum safe() ile sarili,
hata snapshot'i dusurmez, "errors" listesine yazilir.

Kaynaklar
- Deribit public API (opsiyon defteri ozeti + DVOL). Delta, Deribit mark_iv ve vadeye ait dayanak (forward) fiyatindan
  Black-76 ile hesaplanir (r=0); Deribit'in kendi greeks'i tek tek ticker cagrisi ister, yapilmadi.
- Coin Metrics community API (anahtarsiz): CapMVRVCur, AdrActCnt, FlowInExUSD, FlowOutExUSD, SplyExNtv. Son gunler
  "flash" (on deger) olabilir.
- DefiLlama stablecoins: toplam dolasim (USD karsiligi, tum sabit paralar).
- Yahoo + FRED: veri_topla.yahoo serileri (1 yil) ve FRED BAMLH0A0HYM2.
- Binance REST derinlik (kayit_ortak.book_summary) ve kayit/ klasoru (kayit_derinlik.py, kayit_tasfiye.py).
"""
import datetime as dt
import json
import math

import numpy as np
import pandas as pd

import kayit_ortak as K
import veri_topla as V

DERIBIT = "https://www.deribit.com/api/v2/public"
CM = "https://community-api.coinmetrics.io/v4/timeseries/asset-metrics"
LLAMA = "https://stablecoins.llama.fi/stablecoincharts/all"
MON = {m: i + 1 for i, m in enumerate("JAN FEB MAR APR MAY JUN JUL AUG SEP OCT NOV DEC".split())}
DEF = {"everything_down_pct": 3.0, "everything_down_obs": 5, "corr_break_abs_delta": 0.4, "corr_sign_min_abs": 0.1,
       "liq_min_hours_24h": 18, "liq_min_hours_7d": 120, "heatmap_min_hours": 6, "cluster_bucket_pct": 0.5}


def cfg():
    try:
        c = json.loads((V.ROOT / "ofis-ayar.json").read_text(encoding="utf-8")).get("veri") or {}
    except Exception:  # noqa: BLE001
        c = {}
    return {**DEF, **{k: v for k, v in c.items() if not k.startswith("_")}}


def safe(name, fn, *a, **k):
    try:
        return fn(*a, **k)
    except Exception as e:  # noqa: BLE001
        V.ERR.append(f"{name}: {type(e).__name__} {str(e)[:140]}")
        return None


# ---------------- opsiyon (Deribit) ----------------
def _ncdf(x):
    return 0.5 * (1 + math.erf(x / math.sqrt(2)))


def _parse(name):
    """BTC-25JUN27-105000-P -> (vade 08:00 UTC, kullanim, 'C'/'P')."""
    _, d, k, cp = name.split("-")
    day, mon, yr = int(d[:-5]), MON[d[-5:-2]], 2000 + int(d[-2:])
    return dt.datetime(yr, mon, day, 8, tzinfo=dt.timezone.utc), float(k), cp


def _interp(x, xs, ys):
    """Dogrusal ara deger; x aralik disindaysa None."""
    if len(xs) < 2 or not (min(xs) <= x <= max(xs)):
        return None
    o = np.argsort(xs)
    return float(np.interp(x, np.asarray(xs)[o], np.asarray(ys)[o]))


def _expiry_stats(rows, T):
    """rows: [(K, cp, iv, oi, F)] tek vade. -> atm_iv, rr25 (vol puani, call25 - put25), call/put OI."""
    F = float(np.median([r[4] for r in rows]))
    by_k = {}
    for K_, cp, iv, oi, _ in rows:
        by_k.setdefault(K_, []).append(iv)
    ks = sorted(by_k)
    atm = _interp(F, ks, [np.mean(by_k[k]) for k in ks])
    sq = math.sqrt(T)
    cd, ci, pd_, pi = [], [], [], []
    for K_, cp, iv, oi, _ in rows:
        s = iv / 100
        if s <= 0:
            continue
        d1 = (math.log(F / K_) + 0.5 * s * s * T) / (s * sq)
        if cp == "C" and K_ >= F:
            cd.append(_ncdf(d1))
            ci.append(iv)
        elif cp == "P" and K_ <= F:
            pd_.append(1 - _ncdf(d1))      # |put delta|
            pi.append(iv)
    c25, p25 = _interp(0.25, cd, ci), _interp(0.25, pd_, pi)
    coi = sum(r[3] for r in rows if r[1] == "C")
    poi = sum(r[3] for r in rows if r[1] == "P")
    return {"F": F, "atm": atm, "rr25": None if c25 is None or p25 is None else c25 - p25, "coi": coi, "poi": poi}


def _cm(stats, days, key):
    """Sabit vade: vade gunleri arasinda ara deger (ATM IV toplam varyansla)."""
    pts = [(s["days"], s[key]) for s in stats if s[key] is not None]
    if not pts:
        return None
    if days <= pts[0][0]:
        return pts[0][1]
    for (d0, v0), (d1, v1) in zip(pts, pts[1:]):
        if d0 <= days <= d1:
            w = (days - d0) / (d1 - d0) if d1 > d0 else 0
            if key == "atm":
                return math.sqrt(((1 - w) * v0 * v0 * d0 + w * v1 * v1 * d1) / days)
            return v0 + w * (v1 - v0)
    return None


def _last_friday(d):
    nxt = (d.replace(day=28) + dt.timedelta(days=4)).replace(day=1)
    last = nxt - dt.timedelta(days=1)
    return last - dt.timedelta(days=(last.weekday() - 4) % 7)


def options(cur, now):
    d = V.get(f"{DERIBIT}/get_book_summary_by_currency", {"currency": cur, "kind": "option"})
    if not d or not d.get("result"):
        return None
    exps, idx = {}, []
    for x in d["result"]:
        if x.get("estimated_delivery_price"):
            idx.append(float(x["estimated_delivery_price"]))
        try:
            e, k, cp = _parse(x["instrument_name"])
        except (ValueError, KeyError):
            continue
        iv, F = x.get("mark_iv"), x.get("underlying_price")
        if not iv or float(iv) <= 0 or not F or e <= now:
            continue
        exps.setdefault(e, []).append((k, cp, float(iv), float(x.get("open_interest") or 0), float(F)))
    stats = []
    for e in sorted(exps):
        T = (e - now).total_seconds() / (365 * 86400)
        if T * 365 < 1:                     # 1 gunden kisa vade: IV gurultulu
            continue
        s = _expiry_stats(exps[e], T)
        s.update(exp=e, days=T * 365)
        stats.append(s)
    if not stats:
        return None
    term, used = [], set()
    for tgt in (7, 14, 30, 60, 90, 180):
        s = min(stats, key=lambda z: abs(z["days"] - tgt))
        if s["exp"] in used:
            continue
        used.add(s["exp"])
        term.append([s["exp"].strftime("%Y-%m-%d"), V.r5(round(s["days"], 1)), V.r5(s["atm"]), V.r5(s["rr25"]),
                     V.r5(s["poi"] / s["coi"]) if s["coi"] else None])
    coi, poi = sum(s["coi"] for s in stats), sum(s["poi"] for s in stats)
    out = {"source": "deribit", "index": V.r5(np.median(idx)) if idx else None,
           "atm_iv_cm": {f"{n}d": V.r5(_cm(stats, n, "atm")) for n in (7, 30, 90)},
           "rr25_cm": {f"{n}d": V.r5(_cm(stats, n, "rr25")) for n in (7, 30)},
           "pc_oi_ratio_all": V.r5(poi / coi) if coi else None,
           "term": {"cols": ["expiry", "days", "atm_iv", "rr25", "pc_oi"], "rows": term}}
    monthly = [s for s in stats if s["exp"].date() == _last_friday(s["exp"].date())]
    if monthly:
        m = monthly[0]
        rows = exps[m["exp"]]
        strikes = sorted({r[0] for r in rows})
        pain = [sum(r[3] * max(0.0, S - r[0]) if r[1] == "C" else r[3] * max(0.0, r[0] - S) for r in rows)
                for S in strikes]
        top = lambda cp: [[V.r5(k), V.r5(o)] for k, o in sorted(  # noqa: E731
            ((r[0], r[3]) for r in rows if r[1] == cp), key=lambda z: -z[1])[:3]]
        out["monthly"] = {"expiry": m["exp"].strftime("%Y-%m-%d"), "days": V.r5(round(m["days"], 1)),
                          "max_pain": V.r5(strikes[int(np.argmin(pain))]),
                          "pc_oi": V.r5(m["poi"] / m["coi"]) if m["coi"] else None,
                          "top_call_oi": top("C"), "top_put_oi": top("P"),
                          "oi_total_coins": V.r5(m["coi"] + m["poi"])}
    t1 = int(now.timestamp() * 1000)
    dv = V.get(f"{DERIBIT}/get_volatility_index_data",
               {"currency": cur, "start_timestamp": t1 - 31 * 86400000, "end_timestamp": t1, "resolution": "1D"})
    try:
        c = [float(r[4]) for r in dv["result"]["data"]]
        out["dvol"] = {"last": V.r5(c[-1]), "chg_7d": V.r5(c[-1] - c[-8]) if len(c) > 7 else None,
                       "min_30d": V.r5(min(c)), "max_30d": V.r5(max(c))}
    except (TypeError, KeyError, IndexError, ValueError):
        out["dvol"] = None
    return out


# ---------------- zincir ustu ----------------
def onchain(asset, asof):
    mets = "CapMVRVCur,AdrActCnt,FlowInExUSD,FlowOutExUSD,SplyExNtv"
    d = V.get(CM, {"assets": asset, "metrics": mets, "frequency": "1d", "page_size": 100,
                   "start_time": (asof - pd.Timedelta(days=45)).strftime("%Y-%m-%d")})
    if not d or not d.get("data"):
        return None
    df = pd.DataFrame(d["data"])
    df.index = pd.to_datetime(df.pop("time"), utc=True)
    df = df[df.index <= asof]
    num = lambda c: pd.to_numeric(df[c], errors="coerce") if c in df else pd.Series(dtype=float)  # noqa: E731
    mv, aa, fi, fo, sx = (num(c).dropna() for c in mets.split(","))
    nf = (num("FlowInExUSD") - num("FlowOutExUSD")).dropna()
    chg = lambda s, n: V.pct(s.iloc[-1], s.iloc[-1 - n]) if len(s) > n else None  # noqa: E731
    st = df.get("FlowInExUSD-status")
    return {"date": V.ts(mv.index[-1], True) if len(mv) else None,
            "mvrv": V.r5(mv.iloc[-1]) if len(mv) else None,
            "mvrv_chg_30d": V.r5(mv.iloc[-1] - mv.iloc[-31]) if len(mv) > 30 else None,
            "active_addr": V.r5(aa.iloc[-1]) if len(aa) else None,
            "active_addr_7d_vs_30d_pct": V.pct(aa.tail(7).mean(), aa.tail(30).mean()) if len(aa) >= 30 else None,
            "ex_netflow_musd_7d": V.r5(nf.tail(7).sum() / 1e6) if len(nf) >= 7 else None,
            "ex_netflow_musd_30d": V.r5(nf.tail(30).sum() / 1e6) if len(nf) >= 30 else None,
            "ex_supply_chg_7d_pct": chg(sx, 7), "ex_supply_chg_30d_pct": chg(sx, 30),
            "flows_date": V.ts(nf.index[-1], True) if len(nf) else None,
            "flows_status": None if st is None or not len(st.dropna()) else str(st.dropna().iloc[-1])}


def stablecoins(asof):
    d = V.get(LLAMA)
    if not d:
        return None
    s = pd.Series({pd.Timestamp(int(x["date"]), unit="s", tz="UTC"): sum((x.get("totalCirculatingUSD") or {}).values())
                   for x in d}).sort_index()
    s = s[(s.index <= asof) & (s > 0)]
    return {"date": V.ts(s.index[-1], True), "total_usd_bn": V.r5(s.iloc[-1] / 1e9),
            "chg_7d_pct": V.pct(s.iloc[-1], s.iloc[-8]), "chg_30d_pct": V.pct(s.iloc[-1], s.iloc[-31])}


# ---------------- capraz varlik ----------------
def cross_asset(btc_d1, C):
    """BTC gunluk getirisi ile NDX, SPX, altin, DXY, US10Y (getiri; 10Y icin seviye farki) 30/90 gozlem korelasyonu,
    "her sey dusuyor" ve korelasyon kirilmasi bayraklari. Hizalama: BTC'nin D tarihinde acilan gunluk mumu (D+1 00:00
    UTC kapanis) ile ABD'nin D gunu kapanisi; ortak gunler (hafta sonu BTC hareketi pazartesiye katlanir)."""
    names = {"ndx": "^NDX", "spx": "^GSPC", "gold": "GC=F", "dxy": "DX-Y.NYB", "us10y": "^TNX"}
    cols = {"btc": pd.Series(btc_d1.close.to_numpy(), index=btc_d1.index.normalize())}
    for k, sym in names.items():
        s = V.SERIES.get(sym)
        if s is not None and len(s):
            s = s.copy()
            s.index = s.index.normalize()
            cols[k] = s[~s.index.duplicated(keep="last")]
    df = pd.DataFrame(cols).dropna()
    if len(df) < 40:
        return None
    ret = df.pct_change()
    if "us10y" in df:
        ret["us10y"] = df["us10y"].diff()
    ret = ret.dropna()
    rows, breaks = [], []
    for k in names:
        if k not in ret:
            continue
        c30, c90 = ret.btc.tail(30).corr(ret[k].tail(30)), ret.btc.tail(90).corr(ret[k].tail(90))
        brk = bool(abs(c30 - c90) > C["corr_break_abs_delta"] or
                   (np.sign(c30) != np.sign(c90) and min(abs(c30), abs(c90)) >= C["corr_sign_min_abs"]))
        if brk:
            breaks.append(k)
        rows.append([k, V.r5(round(c30, 2)), V.r5(round(c90, 2)), brk])
    n, x = int(C["everything_down_obs"]), float(C["everything_down_pct"])
    ch = {k: V.pct(df[k].iloc[-1], df[k].iloc[-1 - n]) for k in ("btc", "ndx", "gold", "dxy") if k in df}
    down = (all(k in ch and ch[k] is not None for k in ("btc", "ndx", "gold", "dxy")) and
            ch["btc"] < -x and ch["ndx"] < -x and ch["gold"] < -x and ch["dxy"] > 0)
    return {"btc_corr": {"cols": ["vs", "c30", "c90", "break"], "rows": rows, "last_common_date": V.ts(df.index[-1], True),
                         "obs": len(ret)},
            "stress": {"everything_down": bool(down), "rule": f"btc,ndx,gold all < -{x}% and dxy up over last {n} common days",
                       f"chg_{n}obs_pct": ch, "corr_break": breaks}}


# ---------------- emir defteri (simdi) ----------------
def orderbook(sym):
    out = {"taken_utc": K.now_utc().strftime("%Y-%m-%d %H:%M")}
    for mkt in ("fut", "spot"):
        book, err = K.fetch_book(mkt, sym)
        if err:
            V.ERR.append(err)
            out[mkt] = None
        else:
            out[mkt] = K.book_summary(*book)
    return out if (out.get("fut") or out.get("spot")) else None


# ---------------- kayitlardan ozet ----------------
def _slots(now, hours):
    f = K.KAYIT / "tasfiye" / "kalp.csv"
    lo = (now - dt.timedelta(hours=hours)).strftime("%Y-%m-%d %H:%M")
    hi = now.strftime("%Y-%m-%d %H:%M")
    s = set()
    for r in K.read_csv_any(f):
        t = r.get("ts_utc") or ""
        if lo <= t <= hi:
            s.add(t[:15] + str(int(t[15]) // 5 * 5))   # 5 dk dilimi
    return len(s) * 5 / 60


def liq_clusters(sym, price, now, C):
    rows = []
    for f in K.day_files(K.KAYIT / "tasfiye", 8, ".csv", now):
        rows += [r for r in K.read_csv_any(f) if r.get("sym") == sym]
    step = K.nice(price * C["cluster_bucket_pct"] / 100)
    out = {"bucket": V.r5(step)}   # aciklama legend.recorded'da (token: varlik basina tekrar etmesin)
    for name, hours, need in (("24h", 24, C["liq_min_hours_24h"]), ("7d", 168, C["liq_min_hours_7d"])):
        cov = _slots(now, hours)
        if cov < need:
            out[name] = {"status": "insufficient history", "covered_h": V.r5(round(cov, 1)), "need_h": need}
            continue
        lo = (now - dt.timedelta(hours=hours)).strftime("%Y-%m-%d %H:%M:%S")
        w = [r for r in rows if r["time_utc"] >= lo]
        res = {"covered_h": V.r5(round(cov, 1))}
        for side, lab in (("SELL", "longs_liq"), ("BUY", "shorts_liq")):
            b = {}
            tot = 0.0
            for r in (x for x in w if x["side"] == side):
                u = float(r["usd"])
                tot += u
                k = round(float(r["price"]) / step) * step
                c = b.setdefault(k, [0.0, 0])
                c[0] += u
                c[1] += 1
            res[lab] = {"usd_m": V.r5(tot / 1e6), "n": sum(c[1] for c in b.values()),
                        "top": [[V.r5(k), V.r5(v[0] / 1e6), v[1]] for k, v in sorted(b.items(), key=lambda kv: -kv[1][0])[:3]]}
        out[name] = res
    return out


def depth_heatmap(sym, price, now, C):
    lo = (now - dt.timedelta(hours=24)).strftime("%Y-%m-%d %H:%M")
    rows = []
    for f in K.day_files(K.KAYIT / "derinlik", 1, ".csv.gz", now):
        rows += [r for r in K.read_csv_any(f) if r.get("sym") == sym and r.get("ts_utc", "") >= lo]
    stamps = sorted({r["ts_utc"] for r in rows})
    cov = len(stamps) * 5 / 60
    if cov < C["heatmap_min_hours"]:
        return {"status": "insufficient history", "covered_h": V.r5(round(cov, 1)), "need_h": C["heatmap_min_hours"]}
    step = K.nice(price * C["cluster_bucket_pct"] / 100)
    per = {t: {} for t in stamps}
    for r in rows:
        d = per[r["ts_utc"]]
        for kv in (r.get("heat") or "").split(";"):
            if ":" not in kv:
                continue
            p, u = kv.split(":")
            k = round(float(p) / step) * step
            d[k] = d.get(k, 0.0) + float(u) * 1e3
    tot, hot = {}, {}
    for d in per.values():
        if not d:
            continue
        med = float(np.median(list(d.values())))
        for k, u in d.items():
            tot[k] = tot.get(k, 0.0) + u
            if u >= 2 * med:
                hot[k] = hot.get(k, 0) + 1
    n = len(stamps)
    side = lambda f: [[V.r5(k), V.r5(tot[k] / n / 1e6), round(100 * hot.get(k, 0) / n)]  # noqa: E731
                      for k in sorted((k for k in tot if f(k)), key=lambda k: -tot[k])[:3]]
    return {"window_h": 24, "covered_h": V.r5(round(cov, 1)), "bucket": V.r5(step),
            "bids_below": side(lambda k: k < price - step), "asks_above": side(lambda k: k > price + step),
            "cols": ["bucket_price", "avg_usd_m", "persist_pct"]}


def recorded(sym, price, now, C):
    return {"liq_clusters": safe(f"liq_clusters {sym}", liq_clusters, sym, price, now, C),
            "depth_heatmap": safe(f"depth_heatmap {sym}", depth_heatmap, sym, price, now, C)}
