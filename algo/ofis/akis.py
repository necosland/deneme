"""Trader ofisi emir akisi (orderflow) blogu, 2026-11-21: footprint/delta, buyuk emir balonlari, 24 saat hacim profili ve
kalici emir defteri duvarlari. Yalniz Bora'nin (trader-senaryo) gorunumune gider (tur.py make_view). LLM yok, anahtar yok.

Kaynaklar (hepsi asof_utc'ye kadar; asof sonrasi satir okunmaz, yalniz kapanmis mumlar):
- Binance USD-M vadeli kline (fapi /fapi/v1/klines; yoksa spot data-api): mum hacmi (quote), taker alis -> delta
  = 2 x taker_alis - hacim, islem sayisi; 1m mumlarin kumulatif deltasi -> mum ici en dusuk/en yuksek delta.
- kayit/akis (kayit_akis.py, fapi aggTrades, 5 dk): fiyat hucresi basina taker alis/satis ve buyuk emirler. Bir dakikanin
  kayitli hacmi kline hacmini %3 icinde tutuyorsa hucreler islemlerden gelir; tutmuyorsa (kayit yok/eksik) o dakikanin
  alis/satisi 1m mumun dusuk-yuksek araligina esit yayilir (yaklasik). t_pct = mum hacminin islemlerden gelen yuzdesi.
- kayit/derinlik (kayit_derinlik.py, 5 dk): her ornekte ~%0.1 kovalarda en buyuk duvarlar (spot+vadeli toplam) ->
  kalici duvar = pencere icinde en az walls_min_min dakika gorulen kova.
Esikler ofis-ayar.json veri.orderflow (denenmemis varsayim). Hata snapshot'i dusurmez: alt bolum None + errors.
"""
import datetime as dt
import json
import time

import numpy as np
import pandas as pd

import requests

import kayit_ortak as K
import veri_topla as V

FK = "https://fapi.binance.com/fapi/v1/klines"
DEF = {"n_1h": 6, "n_15m": 8, "cells_1h": 4, "cells_15m": 3, "cell_levels": 10, "tick_pct": 0.05, "vp_h": 24, "va_pct": 70,
       "thin_frac": 0.3, "thin_min_ticks": 3, "thin_max": 3, "bubble_pct": 90, "bubbles_h": 6, "bubbles_top": 5,
       "walls_h": 12, "walls_min_min": 60, "walls_top": 3, "wall_pct": 0.1, "rec_tol": 0.03,
       "budget_s": 60, "req_timeout_s": 8}
# alan aciklamasi: veri_topla.LEGEND_EK['orderflow'] (yalniz Bora'nin gorunumune gider)
_CACHE = {}


def cfg():
    try:
        c = json.loads((V.ROOT / "ofis-ayar.json").read_text(encoding="utf-8")).get("veri", {}).get("orderflow") or {}
    except Exception:  # noqa: BLE001
        c = {}
    return {**DEF, **{k: v for k, v in c.items() if not k.startswith("_")}}


def safe(name, fn, *a):
    try:
        return fn(*a)
    except Exception as e:  # noqa: BLE001
        V.ERR.append(f"orderflow {name}: {type(e).__name__} {str(e)[:120]}")
        return None


def m3(x):
    return K.rn(x / 1e6, 3)


# ---------------- mumlar ----------------
def _get(url, p, deadline, tmo):
    """Tek deneme, sure sinirli (V.get'in 3 deneme + bekleme yolu turu uzatir; 2026-11-21 tur zaman asimi)."""
    left = deadline - time.time()
    if left < 2:
        raise TimeoutError("orderflow time budget used up")
    r = requests.get(url, params=p, headers=V.UA, timeout=min(tmo, left))
    r.raise_for_status()
    return r.json()


def kl(sym, iv, asof, limit, deadline=None, tmo=8):
    """Kapanmis mumlar, asof'a kadar. -> (df[o,h,l,c,qv,n,tbq], 'fut'|'spot') ya da (None, None).
    Vadeli yoksa spot; her istek tek deneme, deadline'a kadar."""
    deadline = deadline or time.time() + 60
    p = dict(symbol=sym, interval=iv, limit=limit, endTime=int(asof.timestamp() * 1000) - 1)
    for mkt, url in (("fut", FK), ("spot", V.SPOT)):
        try:
            d = _get(url, p, deadline, tmo)
        except TimeoutError:
            raise
        except Exception as e:  # noqa: BLE001
            V.ERR.append(f"orderflow {sym} {iv} {mkt}: {type(e).__name__} {str(e)[:80]}")
            continue
        if d:
            df = pd.DataFrame([[r[0], r[1], r[2], r[3], r[4], r[7], r[8], r[10]] for r in d],
                              columns=["t", "o", "h", "l", "c", "qv", "n", "tbq"])
            df.index = pd.to_datetime(df.pop("t"), unit="ms", utc=True)
            df = df.astype(float)
            mins = {"1m": 1, "15m": 15, "1h": 60}[iv]
            return df[df.index + pd.Timedelta(minutes=mins) <= asof], mkt
    return None, None


# ---------------- kayit/akis ----------------
def _rows(f):
    key = (str(f), f.stat().st_mtime)
    if key not in _CACHE:
        if len(_CACHE) > 4:
            _CACHE.clear()
        _CACHE[key] = K.read_csv_any(f)
    return _CACHE[key]


def rec_minutes(sym, lo, hi):
    """kayit/akis dakikalari [lo, hi): {'YYYY-MM-DD HH:MM': {b, s, n, c {fiyat: [alis, satis]}, big [(epoch, B/S, fiyat, usd)]}}."""
    lo_s, hi_s = V.ts(lo), V.ts(hi)
    out, seen = {}, set()
    for f in K.day_files(K.KAYIT / "akis", (hi - lo).days + 1, ".csv.gz", hi.to_pydatetime()):
        for r in _rows(f):
            m = r.get("min_utc") or ""
            if r.get("sym") != sym or not (lo_s <= m < hi_s) or (m, r["id0"]) in seen:
                continue
            seen.add((m, r["id0"]))
            d = out.setdefault(m, {"b": 0.0, "s": 0.0, "n": 0, "c": {}, "big": []})
            d["b"] += float(r["buy_k"]) * 1e3
            d["s"] += float(r["sell_k"]) * 1e3
            d["n"] += int(r["n"])
            for x in (r.get("cells") or "").split(";"):
                if x:
                    p, b, s = x.split(":")
                    c = d["c"].setdefault(float(p), [0.0, 0.0])
                    c[0] += float(b) * 1e3
                    c[1] += float(s) * 1e3
            for x in (r.get("big") or "").split("|"):
                if x:
                    e, sd, p, u = x.split(":")
                    d["big"].append((int(e), sd, float(p), float(u) * 1e3))
    return out


def minute_cells(m1, rec, tick, tol):
    """Her 1m mum icin {kova_no: [alis, satis]} ve islemden mi geldigi. Kayitli hacim kline hacmini tol icinde
    tutuyorsa gercek hucreler, yoksa alis/satis mumun dusuk-yuksek araligina esit yayilir."""
    out = {}
    for t, (h, l, qv, tbq) in zip(m1.index, m1[["h", "l", "qv", "tbq"]].to_numpy()):
        m = V.ts(t)
        r = rec.get(m)
        cells = {}
        if r and qv > 0 and abs(r["b"] + r["s"] - qv) <= tol * qv:
            for p, (b, s) in r["c"].items():
                c = cells.setdefault(round(p / tick), [0.0, 0.0])
                c[0] += b
                c[1] += s
            out[m] = (cells, True)
            continue
        lo, hi = round(l / tick), round(h / tick)
        n = hi - lo + 1
        for k in range(lo, hi + 1):
            cells[k] = [tbq / n, (qv - tbq) / n]
        out[m] = (cells, False)
    return out


def candle_rows(df, iv_min, m1, mc, tick, k_cells, n, levels):
    """Mum basina footprint ozeti. Hucreler mumun araligini ~levels satira bolen adimla (ctick, en az tick) birlestirilir;
    wick_lo/wick_hi = govde altindaki/ustundeki fitil bolgesinin [satis, alis] toplami (emilim okumasi icin)."""
    rows = []
    for t, (o, h, l, c, qv, nt, tbq) in zip(df.index[-n:], df[["o", "h", "l", "c", "qv", "n", "tbq"]].to_numpy()[-n:]):
        sub = m1[(m1.index >= t) & (m1.index < t + pd.Timedelta(minutes=iv_min))]
        run = (2 * sub.tbq - sub.qv).cumsum()
        ct = max(tick, K.nice((h - l) / levels)) if h > l else tick
        cells, tv, wl, wh = {}, 0.0, [0.0, 0.0], [0.0, 0.0]
        for tm in sub.index:
            cm, real = mc.get(V.ts(tm), ({}, False))
            for k, (b, s) in cm.items():
                p = k * tick
                x = cells.setdefault(round(p / ct), [0.0, 0.0])
                x[0] += b
                x[1] += s
                tv += (b + s) if real else 0.0
                w = wl if p < min(o, c) else wh if p > max(o, c) else None
                if w is not None:
                    w[0] += s
                    w[1] += b
        top = sorted(cells.items(), key=lambda kv: -(kv[1][0] + kv[1][1]))[:k_cells]
        delta = 2 * tbq - qv
        rows.append([V.ts(t), V.r5(o), V.r5(h), V.r5(l), V.r5(c), m3(qv), m3(delta),
                     round(100 * delta / qv, 1) if qv else None,
                     m3(run.min()) if len(run) else None, m3(run.max()) if len(run) else None,
                     int(nt), round(qv / nt) if nt else None, round(100 * tv / qv) if qv else 0,
                     [m3(wl[0]), m3(wl[1])], [m3(wh[0]), m3(wh[1])], V.r5(ct),
                     [[V.r5(k * ct), m3(s), m3(b)] for k, (b, s) in sorted(top, key=lambda kv: -kv[0])]])
    return {"cols": ["open_time_utc", "o", "h", "l", "c", "vol", "delta", "delta_pct", "dmin", "dmax", "trades",
                     "avg_trade_usd", "t_pct", "wick_lo", "wick_hi", "ctick", "cells"], "rows": rows}


def vprofile(mc, last, tick, C):
    vol, tv, tot = {}, 0.0, 0.0
    for cm, real in mc.values():
        for k, (b, s) in cm.items():
            vol[k] = vol.get(k, 0.0) + b + s
            tot += b + s
            tv += (b + s) if real else 0.0
    if not vol:
        return None
    ks = list(range(min(vol), max(vol) + 1))
    v = np.array([vol.get(k, 0.0) for k in ks])
    i = int(np.argmax(v))
    lo = hi = i
    acc, need = v[i], C["va_pct"] / 100 * v.sum()
    while acc < need and (lo > 0 or hi < len(v) - 1):
        up = v[hi + 1] if hi < len(v) - 1 else -1
        dn = v[lo - 1] if lo > 0 else -1
        if up >= dn:
            hi += 1
            acc += up
        else:
            lo -= 1
            acc += dn
    med = float(np.median(v[v > 0]))
    thin, run = [], None
    for j, x in enumerate(list(v) + [np.inf]):
        if x < C["thin_frac"] * med:
            run = j if run is None else run
        elif run is not None:
            if j - run >= C["thin_min_ticks"]:
                thin.append((ks[run] * tick, ks[j - 1] * tick))
            run = None
    thin.sort(key=lambda z: 0 if z[0] <= last <= z[1] else min(abs(z[0] - last), abs(z[1] - last)))
    return {"poc": V.r5(ks[i] * tick), "vah": V.r5(ks[hi] * tick), "val": V.r5(ks[lo] * tick),
            "lo": V.r5(ks[0] * tick), "hi": V.r5(ks[-1] * tick), "t_pct": round(100 * tv / tot) if tot else 0,
            "thin": [[V.r5(a), V.r5(b)] for a, b in thin[:C["thin_max"]]]}


def bubbles(rec, asof, C):
    need = C["bubbles_h"] * 60          # esik (yuzdelik) en az pencere kadar kayitli dakikadan
    if len(rec) < need or not any(d["big"] for d in rec.values()):
        return {"status": "insufficient history", "covered_h": round(len(rec) / 60, 1), "need_h": round(need / 60, 1)}
    per_min = [max(u for *_, u in d["big"]) for d in rec.values() if d["big"]]
    thr = float(np.percentile(per_min, C["bubble_pct"]))
    lo = V.ts(asof - pd.Timedelta(hours=C["bubbles_h"]))
    big = [b for m, d in rec.items() if m >= lo for b in d["big"] if b[3] >= thr]
    side = {sd: [b[3] for b in big if b[1] == sd] for sd in ("B", "S")}
    top = sorted(sorted(big, key=lambda b: -b[3])[:C["bubbles_top"]])
    return {"covered_h": round(len(rec) / 60, 1), "thr_usd_m": m3(thr),
            "n_buy": len(side["B"]), "n_sell": len(side["S"]), "buy_usd_m": m3(sum(side["B"])),
            "sell_usd_m": m3(sum(side["S"])),
            "top": [[dt.datetime.fromtimestamp(e, dt.timezone.utc).strftime("%H:%M"), sd, V.r5(p), m3(u)]
                    for e, sd, p, u in top]}


# ---------------- kayit/derinlik ----------------
def walls(sym, last, asof, C):
    lo_s, hi_s = V.ts(asof - pd.Timedelta(hours=C["walls_h"])), V.ts(asof)
    rows = []
    for f in K.day_files(K.KAYIT / "derinlik", 1, ".csv.gz", asof.to_pydatetime()):
        rows += [r for r in _rows(f) if r.get("sym") == sym and lo_s <= r.get("ts_utc", "") <= hi_s]
    stamps = sorted({r["ts_utc"] for r in rows})
    cov = len(stamps) * 5 / 60
    if cov < C["walls_h"] / 2:
        return {"status": "insufficient history", "covered_h": round(cov, 1), "need_h": C["walls_h"] / 2}
    step = K.nice(last * C["wall_pct"] / 100)
    per = {}
    for r in rows:
        d = per.setdefault(r["ts_utc"], {})
        for side, col in (("bid", "walls_bid"), ("ask", "walls_ask")):
            for x in (r.get(col) or "").split("|"):
                if "@" in x:
                    p, u = x.split("@")
                    k = (side, round(float(p) / step))
                    d[k] = d.get(k, 0.0) + float(u)
    seen = {}
    t_end = pd.Timestamp(stamps[-1], tz="UTC")
    for t in stamps:
        for k, u in per.get(t, {}).items():
            s = seen.setdefault(k, [0, 0.0, t])
            s[0] += 1
            s[1] += u
            s[2] = t
    out = {"window_h": C["walls_h"], "covered_h": round(cov, 1), "bucket": V.r5(step)}
    for side in ("bid", "ask"):
        w = [(k[1], s) for k, s in seen.items() if k[0] == side and s[0] * 5 >= C["walls_min_min"]]
        w.sort(key=lambda z: -(z[1][0] * z[1][1]))
        out[side + "s"] = [[V.r5(k * step), round(100 * (k * step - last) / last, 2), K.rn(s[1] / s[0], 3), s[0] * 5,
                            int((t_end - pd.Timestamp(s[2], tz="UTC")).total_seconds() // 60)]
                           for k, s in w[:C["walls_top"]]]
    return out


# ---------------- blok ----------------
def orderflow(sym, asof, deadline=None):
    """deadline: veri_topla'nin tum varliklar icin verdigi ortak son an (budget_s). Asilirsa varlik None + errors;
    kayit (kayit/akis) yoksa API'den geri doldurma yapilmaz, hucreler 1m mumdan yaklasik (t_pct=0)."""
    C = cfg()
    deadline = deadline or time.time() + C["budget_s"]
    try:
        m1, mkt = kl(sym, "1m", asof, min(1500, int(C["vp_h"] * 60)), deadline, C["req_timeout_s"])
        h1, _ = kl(sym, "1h", asof, C["n_1h"] + 1, deadline, C["req_timeout_s"])
        q15, _ = kl(sym, "15m", asof, C["n_15m"] + 1, deadline, C["req_timeout_s"])
    except (TimeoutError, requests.Timeout):
        V.ERR.append(f"orderflow {sym}: skipped, time budget {C['budget_s']}s used up")
        return None
    if m1 is None or h1 is None or q15 is None or not len(m1):
        return None
    last = float(m1.c.iloc[-1])
    tick = K.nice(last * C["tick_pct"] / 100)
    rec = rec_minutes(sym, asof - pd.Timedelta(hours=C["vp_h"]), asof)
    mc = minute_cells(m1, rec, tick, C["rec_tol"])
    return {"mkt": mkt, "tick": V.r5(tick), "last": V.r5(last),
            "1h": safe(f"1h {sym}", candle_rows, h1, 60, m1, mc, tick, C["cells_1h"], C["n_1h"], C["cell_levels"]),
            "15m": safe(f"15m {sym}", candle_rows, q15, 15, m1, mc, tick, C["cells_15m"], C["n_15m"], C["cell_levels"]),
            "vp_24h": safe(f"vp {sym}", vprofile, mc, last, tick, C),
            "bubbles": safe(f"bubbles {sym}", bubbles, rec, asof, C),
            "walls": safe(f"walls {sym}", walls, sym, last, asof, C)}
