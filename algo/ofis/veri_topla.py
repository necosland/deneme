"""Trader ofisi: veri anlik goruntusu. LLM yok, API anahtari yok, yalniz herkese acik uc noktalar.

Kullanim:
  python algo/ofis/veri_topla.py                          # canli: son kapanan 4h mumuna gore
  python algo/ofis/veri_topla.py --asof 2026-11-20T08:00Z # yeniden oynatma (YALNIZ tesisat testi)
Cikti: algo/ofis/veri/snap_<YYYYMMDD_HHMM>.json ve algo/ofis/veri/son.json (ayni icerik)

Kurallar
- Yalniz kapanmis mumlar: acilis + aralik <= asof. Uzman asof sonrasini goremez.
- Turev, duygu ve makro verisi cekildigi anin degeridir; --asof verilince bu bolumler bos kalir
  (gecmis bir ana ait degiller, sizinti olur).
- Ulasilamayan kaynak null olur, nedeni "errors" listesine yazilir; uzman tahmin etmez, "veri yok" der.
- est_liq_zones bir TAHMINDIR (4h OI artisi + kaldirac varsayimi), gozlenmis tasfiye verisi degildir.
- Hacim profili Binance SPOT hacmidir (quote, USDT); vadeli hacmi icermez.
"""
import argparse
import io
import json
import math
import pathlib
import sys
import time
from urllib.parse import urlparse

import numpy as np
import pandas as pd
import requests

ROOT = pathlib.Path(__file__).parent
OUT = ROOT / "veri"
SPOT = "https://data-api.binance.vision/api/v3/klines"
FAPI = "https://fapi.binance.com"
BYBIT = "https://api.bybit.com"
UA = {"User-Agent": "Mozilla/5.0 (paper-trading research script)"}
IV_MIN = {"15m": 15, "1h": 60, "4h": 240, "1d": 1440}
FETCH = {"15m": 96, "1h": 720, "4h": 500, "1d": 400}
SHOW = {"15m": 16, "1h": 24, "4h": 30, "1d": 30}
ZZ_K = {"1d": 3.0, "4h": 2.0, "1h": 2.0}   # zigzag donus esigi = k x ATR14 (kendi zaman diliminde)
ERR, BLOCKED = [], set()
# Ek veri alanlari (canli-ozel, TASARIM.md 14 "Ek veri ve kayitcilar"). tur.py rol gorunumunde yalniz o alani alan rol
# bu aciklamalari gorur (token tasarrufu).
LEGEND_EK = {
    "options": "Deribit, per asset: atm_iv_cm/rr25_cm = constant-maturity ATM IV and 25-delta risk reversal "
               "(call25 IV - put25 IV, vol pts; + = calls richer), deltas Black-76 from mark_iv; pc_oi = put/call OI "
               "(contracts); monthly = nearest last-Friday expiry: max_pain, top OI strikes [strike, coins]; "
               "dvol = Deribit vol index (last, 7d chg pts, 30d min/max)",
    "onchain": "Coin Metrics community, daily, latest days may be 'flash' (preliminary): mvrv (market/realized cap), "
               "active_addr, ex_netflow_musd (exchange inflow-outflow USD m; + = net to exchanges), ex_supply_chg_pct",
    "orderbook": "Binance book at snapshot time (~20 min after asof): bands_musd {pct: [bid_usd_m, ask_usd_m]} within "
                 "+-pct of mid, null = book depth did not reach (see reach_pct; futures REST <=1000 levels); "
                 "walls_bid/ask = largest [bucket_price, usd_m] in ~0.1% buckets within 5%",
    "recorded": "from our own recorders (kayit/), 'insufficient history' until enough coverage. liq_clusters: observed "
                "Binance USD-M liquidations, longs_liq = SELL orders (longs liquidated), shorts_liq = BUY; top = "
                "[bucket_price, usd_m, n]; stream sends max 1/sec/symbol so totals are a lower bound. depth_heatmap: "
                "24h avg resting spot+futures liquidity, buckets >1 bucket (~0.5%) away from price "
                "[bucket_price, avg_usd_m, persist_pct = share of 5-min samples "
                ">=2x median bucket]; futures book reaches only ~0.3% (BTC)/0.8% (ETH), far buckets are spot",
    "macro.stablecoin_supply": "DefiLlama total stablecoin circulation, USD bn, 7d/30d % change",
    "macro.extra": "ndx, usdjpy, move (Yahoo; ^MOVE), hy_oas_pct (FRED BAMLH0A0HYM2, ICE BofA US HY OAS %), "
                   "btc_corr rows [vs, corr 30 obs, corr 90 obs, break] on BTC daily vs US daily returns "
                   "(us10y: level change), stress.everything_down and stress.corr_break "
                   "(|c30-c90|>0.4 or sign flip with both |c|>=0.1); thresholds in ofis-ayar.json veri",
}


# ---------------- yardimcilar ----------------
def get(url, params=None, text=False):
    host = urlparse(url).netloc
    if host in BLOCKED:
        return None
    last = None
    for k in range(3):
        try:
            r = requests.get(url, params=params, headers=UA, timeout=20)
            if r.status_code in (403, 451):          # bolge engeli / bot duvari: yeniden deneme bosuna
                BLOCKED.add(host)
                ERR.append(f"{host}: HTTP {r.status_code} (blocked, host skipped)")
                return None
            r.raise_for_status()
            return r.text if text else r.json()
        except Exception as e:  # noqa: BLE001
            last = e
            time.sleep(2 * (k + 1))
    ERR.append(f"{url}: {type(last).__name__} {str(last)[:120]}")
    return None


def r5(x):
    """5 anlamli basamak; NaN/inf -> None."""
    try:
        x = float(x)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(x):
        return None
    if x == 0:
        return 0.0
    d = max(0, 5 - int(math.floor(math.log10(abs(x)))) - 1)
    return round(x, d)


def pct(a, b):
    try:
        return r5((float(a) / float(b) - 1) * 100)
    except (TypeError, ValueError, ZeroDivisionError):
        return None


def ts(t, day=False):
    return t.strftime("%Y-%m-%d" if day else "%Y-%m-%d %H:%M")


def ema(s, n):
    return s.ewm(span=n, adjust=False).mean()


def atr(df, n=14):
    pc = df.close.shift()
    tr = pd.concat([df.high - df.low, (df.high - pc).abs(), (df.low - pc).abs()], axis=1).max(axis=1)
    return tr.ewm(alpha=1 / n, adjust=False).mean()


def rsi(s, n=14):
    d = s.diff()
    up = d.clip(lower=0).ewm(alpha=1 / n, adjust=False).mean()
    dn = (-d.clip(upper=0)).ewm(alpha=1 / n, adjust=False).mean()
    return 100 - 100 / (1 + up / dn)


# ---------------- mumlar ----------------
def klines(sym, iv, asof):
    end = int(asof.timestamp() * 1000) - 1
    data = get(SPOT, dict(symbol=sym, interval=iv, limit=FETCH[iv], endTime=end))
    if not data:
        return None
    df = pd.DataFrame([[r[0], r[1], r[2], r[3], r[4], r[7]] for r in data],
                      columns=["t", "open", "high", "low", "close", "qvol"])
    df.index = pd.to_datetime(df.pop("t"), unit="ms", utc=True)
    df = df.astype(float)
    return df[df.index + pd.Timedelta(minutes=IV_MIN[iv]) <= asof]   # yalniz kapanmis mumlar


def rows(df, iv):
    d = df.tail(SHOW[iv])
    return {"cols": ["open_time_utc", "o", "h", "l", "c", "qvol_musd"],
            "rows": [[ts(t, iv == "1d"), r5(o), r5(h), r5(l), r5(c), r5(v / 1e6)]
                     for t, (o, h, l, c, v) in zip(d.index, d[["open", "high", "low", "close", "qvol"]].to_numpy())]}


# ---------------- yapi ----------------
def zigzag(df, k):
    """Onayli donus noktalari: fiyat asiri noktadan k*ATR geri donunce onaylanir (geriye bakmaz)."""
    a, h, l = atr(df).to_numpy(), df.high.to_numpy(), df.low.to_numpy()
    n, s = len(df), 14
    if n <= s + 2:
        return [], None
    piv, d, ei, hi_i, lo_i = [], 0, s, s, s
    for i in range(s + 1, n):
        th = k * a[i]
        if d == 0:
            if h[i] > h[hi_i]:
                hi_i = i
            if l[i] < l[lo_i]:
                lo_i = i
            if hi_i < i and h[hi_i] - l[i] > th:
                piv.append((hi_i, h[hi_i], "H"))
                d, ei = -1, hi_i + 1 + int(np.argmin(l[hi_i + 1:i + 1]))
            elif lo_i < i and h[i] - l[lo_i] > th:
                piv.append((lo_i, l[lo_i], "L"))
                d, ei = 1, lo_i + 1 + int(np.argmax(h[lo_i + 1:i + 1]))
        elif d == 1:
            if h[i] >= h[ei]:
                ei = i
            elif h[ei] - l[i] > th:
                piv.append((ei, h[ei], "H"))
                d, ei = -1, ei + 1 + int(np.argmin(l[ei + 1:i + 1]))
        else:
            if l[i] <= l[ei]:
                ei = i
            elif h[i] - l[ei] > th:
                piv.append((ei, l[ei], "L"))
                d, ei = 1, ei + 1 + int(np.argmax(h[ei + 1:i + 1]))
    prov = None if d == 0 else (ei, h[ei] if d == 1 else l[ei], "H?" if d == 1 else "L?")
    return piv, prov


def structure(df, iv, keep):
    piv, prov = zigzag(df, ZZ_K[iv])
    h, l, c, idx = df.high.to_numpy(), df.low.to_numpy(), df.close.to_numpy(), df.index
    rs = rsi(df.close).to_numpy()   # pivot anindaki RSI14 (Elliott kursu: dalga 3 en uc RSI, 3-5 uyumsuzlugu)
    out, last = [], {"H": None, "L": None}
    for i, p, t in piv:
        if last[t] is None:
            lab = t
        elif t == "H":
            lab = "HH" if p > last[t] else "LH"
        else:
            lab = "HL" if p > last[t] else "LL"
        last[t] = p
        out.append([i, p, t, lab])
    res = []
    for i, p, t, lab in out[-keep:]:
        cl = np.where(c[i + 1:] > p)[0] if t == "H" else np.where(c[i + 1:] < p)[0]
        wk = (np.where((h[i + 1:] > p) & (c[i + 1:] <= p))[0] if t == "H"
              else np.where((l[i + 1:] < p) & (c[i + 1:] >= p))[0])
        broke = int(cl[0]) if len(cl) else None
        swept = int(wk[0]) if len(wk) and (broke is None or wk[0] < broke) else None
        res.append([ts(idx[i], iv == "1d"), r5(p), lab,
                    None if broke is None else ts(idx[i + 1 + broke], iv == "1d"),
                    None if swept is None else ts(idx[i + 1 + swept], iv == "1d"), r5(round(rs[i], 1))])
    pv = None if prov is None else [ts(idx[prov[0]], iv == "1d"), r5(prov[1]), prov[2]]
    return {"pivots": res, "current_leg_extreme": pv}


def fvgs(df, a_last, look=60, keep=6):
    h, l, idx, n, out = df.high.to_numpy(), df.low.to_numpy(), df.index, len(df), []
    for i in range(max(2, n - look), n):
        if l[i] > h[i - 2] and l[i] - h[i - 2] >= 0.2 * a_last:
            bot, top = h[i - 2], l[i]
            lo = l[i + 1:].min() if i + 1 < n else np.inf
            if lo <= bot:
                continue
            out.append([ts(idx[i - 1]), "bull", r5(bot), r5(top), "partial" if lo < top else "open"])
        elif h[i] < l[i - 2] and l[i - 2] - h[i] >= 0.2 * a_last:
            bot, top = h[i], l[i - 2]
            hi = h[i + 1:].max() if i + 1 < n else -np.inf
            if hi >= top:
                continue
            out.append([ts(idx[i - 1]), "bear", r5(bot), r5(top), "partial" if hi > bot else "open"])
    return out[-keep:]


def equal_levels(df, a_last, iv):
    piv, _ = zigzag(df, ZZ_K[iv])
    h, l, idx, out = df.high.to_numpy(), df.low.to_numpy(), df.index, []
    for typ in "HL":
        ps = [(i, p) for i, p, t in piv if t == typ][-12:]
        for j in range(len(ps)):
            for k in range(j + 1, len(ps)):
                (i1, p1), (i2, p2) = ps[j], ps[k]
                if abs(p1 - p2) > 0.25 * a_last:
                    continue
                lvl = max(p1, p2) if typ == "H" else min(p1, p2)
                after = h[i2 + 1:] if typ == "H" else l[i2 + 1:]
                taken = len(after) > 0 and ((after.max() > lvl) if typ == "H" else (after.min() < lvl))
                if not taken:
                    out.append(["EQH" if typ == "H" else "EQL", r5(lvl), ts(idx[i1]), ts(idx[i2])])
    return out[-6:]


def vprofile(df, bins=50):
    lo, hi = df.low.min(), df.high.max()
    if not hi > lo:
        return None
    w = (hi - lo) / bins
    vol = np.zeros(bins)
    for hh, ll, v in zip(df.high.to_numpy(), df.low.to_numpy(), df.qvol.to_numpy()):
        a, b = int(min(bins - 1, (ll - lo) // w)), int(min(bins - 1, (hh - lo) // w))
        vol[a:b + 1] += v / (b - a + 1)
    poc = int(vol.argmax())
    lo_i = hi_i = poc
    acc, tot = vol[poc], vol.sum()
    while acc < 0.7 * tot and (lo_i > 0 or hi_i < bins - 1):
        up = vol[hi_i + 1] if hi_i < bins - 1 else -1
        dn = vol[lo_i - 1] if lo_i > 0 else -1
        if up >= dn:
            hi_i += 1
            acc += up
        else:
            lo_i -= 1
            acc += dn
    edges = lo + w * np.arange(bins + 1)
    mid = (edges[:-1] + edges[1:]) / 2
    sm = np.convolve(vol, np.ones(3) / 3, mode="same")
    peaks = [i for i in range(1, bins - 1) if sm[i] > sm[i - 1] and sm[i] >= sm[i + 1]]
    troughs = [i for i in range(1, bins - 1) if sm[i] < sm[i - 1] and sm[i] <= sm[i + 1]]
    return {"range": [r5(lo), r5(hi)], "poc": r5(mid[poc]), "vah": r5(edges[hi_i + 1]), "val": r5(edges[lo_i]),
            "hvn": sorted(r5(mid[i]) for i in sorted(peaks, key=lambda i: -sm[i])[:4]),
            "lvn": sorted(r5(mid[i]) for i in sorted(troughs, key=lambda i: sm[i])[:4])}


def avwap(d1, h4):
    """Capali VWAP + 1/2 sigma bantlari (Efe Bulduk ekibinin seviye kaynagi; trader-senaryo). Hacim: spot quote hacmi,
    taban hacim ~ qvol / tipik fiyat. Capalar: 400 gunun zirvesi ve dibi, 365 gun once (yillik rolling),
    son onayli 1d pivotu."""
    tp_all = (d1.high + d1.low + d1.close) / 3
    piv, _ = zigzag(d1, ZZ_K["1d"])
    anchors = {"ath_400d": int(np.argmax(d1.high.to_numpy())), "low_400d": int(np.argmin(d1.low.to_numpy())),
               "rolling_365d": max(0, len(d1) - 365)}
    if piv:
        anchors["last_1d_pivot_" + piv[-1][2]] = piv[-1][0]
    out = {}
    for name, i0 in anchors.items():
        tp, q = tp_all.iloc[i0:], d1.qvol.iloc[i0:]
        w = q / tp
        if w.sum() <= 0:
            continue
        vw = float((tp * w).sum() / w.sum())
        sd = float(np.sqrt((w * (tp - vw) ** 2).sum() / w.sum()))
        out[name] = {"anchor": ts(d1.index[i0], True), "vwap": r5(vw), "b1": [r5(vw - sd), r5(vw + sd)],
                     "b2": [r5(vw - 2 * sd), r5(vw + 2 * sd)],
                     "last_4h_close_vs": "above" if h4.close.iloc[-1] > vw else "below"}
    return out


def weekly_rows(d1, n=12):
    w = d1.resample("W-MON", label="left", closed="left").agg(
        {"open": "first", "high": "max", "low": "min", "close": "last", "qvol": "sum"}).dropna().tail(n)
    return {"cols": ["week_open_utc", "o", "h", "l", "c", "qvol_musd"],
            "rows": [[ts(t, True), r5(o), r5(h), r5(l), r5(c), r5(v / 1e6)]
                     for t, (o, h, l, c, v) in zip(w.index, w[["open", "high", "low", "close", "qvol"]].to_numpy())],
            "note": "built from closed daily candles; last row = current week, incomplete"}


def key_levels(d1, asof):
    day0 = asof.normalize()
    ws = day0 - pd.Timedelta(days=day0.weekday())
    ms = day0.replace(day=1)
    pms = (ms - pd.Timedelta(days=1)).replace(day=1)
    pw, cw = d1[(d1.index >= ws - pd.Timedelta(days=7)) & (d1.index < ws)], d1[d1.index >= ws]
    pm, cm = d1[(d1.index >= pms) & (d1.index < ms)], d1[d1.index >= ms]
    last = d1.iloc[-1]
    out = {"prev_day_hl": [r5(last.high), r5(last.low)],
           "prev_week_hl": [r5(pw.high.max()), r5(pw.low.min())] if len(pw) else None,
           "prev_month_hl": [r5(pm.high.max()), r5(pm.low.min())] if len(pm) else None,
           "week_open": r5(cw.open.iloc[0]) if len(cw) else None,
           "month_open": r5(cm.open.iloc[0]) if len(cm) else None}
    def floor_piv(h, l, c):   # klasik taban pivotlari (TA kursu L207; test edilmedi)
        pp = (h + l + c) / 3
        return {"P": r5(pp), "R1": r5(2 * pp - l), "S1": r5(2 * pp - h), "R2": r5(pp + h - l), "S2": r5(pp - (h - l))}
    out["floor_pivots_day"] = floor_piv(last.high, last.low, last.close)
    if len(pw):
        out["floor_pivots_week"] = floor_piv(pw.high.max(), pw.low.min(), pw.close.iloc[-1])
    p = last.close
    step = 5 * 10 ** (math.floor(math.log10(p)) - 1)
    base = math.floor(p / step) * step
    out["round_levels"] = [r5(base - step), r5(base), r5(base + step), r5(base + 2 * step)]
    return out


def donchian_state(h4, entry=100, exit_=10):
    """paper.py donchian_4h yaklasigi: kapanis onceki 100 mum zirvesini gecince 1, onceki 10 mum dibinin altinda 0."""
    c = h4.close
    hi, lo = h4.high.rolling(entry).max().shift(), h4.low.rolling(exit_).min().shift()
    pos = 0
    for x, a, b in zip(c.to_numpy(), hi.to_numpy(), lo.to_numpy()):
        if pos == 0 and np.isfinite(a) and x > a:
            pos = 1
        elif pos == 1 and np.isfinite(b) and x < b:
            pos = 0
    return pos


def context(fr, btc):
    d1, h4, h1 = fr["1d"], fr["4h"], fr["1h"]
    c, bc = d1.close, btc["1d"].close
    btc_up = bool(bc.iloc[-1] > bc.rolling(200).mean().iloc[-1])
    ema_up = lambda s: bool(ema(s, 10).iloc[-1] > ema(s, 100).iloc[-1])  # noqa: E731
    return {"last_close": r5(h4.close.iloc[-1]),
            "chg_24h_pct": pct(h4.close.iloc[-1], h4.close.iloc[-7]),
            "chg_7d_pct": pct(d1.close.iloc[-1], d1.close.iloc[-8]),
            "sma200_1d": r5(c.rolling(200).mean().iloc[-1]),
            "ema20_50_200_1d": [r5(ema(c, n).iloc[-1]) for n in (20, 50, 200)],
            "ema20_50_4h": [r5(ema(h4.close, n).iloc[-1]) for n in (20, 50)],
            "atr14": {"1d": r5(atr(d1).iloc[-1]), "4h": r5(atr(h4).iloc[-1]), "1h": r5(atr(h1).iloc[-1])},
            "qvol_avg20_musd": {"4h": r5(h4.qvol.tail(20).mean() / 1e6), "1h": r5(h1.qvol.tail(20).mean() / 1e6)},
            "rsi14": {"1d": r5(rsi(c).iloc[-1]), "4h": r5(rsi(h4.close).iloc[-1]), "1h": r5(rsi(h1.close).iloc[-1])},
            "btc_above_sma200_1d": btc_up,
            "paper_systems_now": {
                "donchian_4h": donchian_state(h4),
                "btc_filter_ema_4h": int(ema_up(h4.close) and ema_up(btc["4h"].close)),
                "ema_btcf_1d": int(bool(ema(c, 3).iloc[-1] > ema(c, 17).iloc[-1]) and btc_up)}}


# ---------------- turev ----------------
def liq_est(oi_v, h4):
    d = oi_v.diff().dropna()
    out = []
    for t, dv in d[d > 0].nlargest(3).items():
        p = h4.close.asof(t)
        if not np.isfinite(p):
            continue
        out.append([ts(t), r5(p), r5(dv / 1e6)] + [r5(p * (1 - 1 / L)) for L in (25, 50)]
                   + [r5(p * (1 + 1 / L)) for L in (25, 50)])
    return {"cols": ["time", "price", "oi_add_musd", "long_liq_25x", "long_liq_50x", "short_liq_25x", "short_liq_50x"],
            "rows": out, "note": "ESTIMATE from 4h OI increases, ignores maintenance margin; not observed liquidations"}


def derivs(sym, h4):
    o = {"source": None}
    p = get(f"{FAPI}/fapi/v1/premiumIndex", {"symbol": sym})
    if p:
        o["source"] = "binance_usdm"
        o["mark"] = r5(p["markPrice"])
        o["perp_premium_pct"] = pct(p["markPrice"], p["indexPrice"])
        o["funding_last"] = r5(p["lastFundingRate"])
        fr = get(f"{FAPI}/fapi/v1/fundingRate", {"symbol": sym, "limit": 21})
        if fr:
            rates = [float(x["fundingRate"]) for x in fr]
            o["funding_7d_avg"] = r5(np.mean(rates))
            o["funding_last9"] = [r5(x) for x in rates[-9:]]
        oi = get(f"{FAPI}/futures/data/openInterestHist", {"symbol": sym, "period": "4h", "limit": 42})
        if oi:
            v = pd.Series([float(x["sumOpenInterestValue"]) for x in oi],
                          index=pd.to_datetime([int(x["timestamp"]) for x in oi], unit="ms", utc=True))
            o["oi_usd_bn"] = r5(v.iloc[-1] / 1e9)
            o["oi_chg_24h_pct"] = pct(v.iloc[-1], v.iloc[-7]) if len(v) > 7 else None
            o["oi_chg_7d_pct"] = pct(v.iloc[-1], v.iloc[0])
            o["est_liq_zones"] = liq_est(v, h4)
        for key, path in (("ls_accounts_4h", "globalLongShortAccountRatio"),
                          ("ls_top_positions_4h", "topLongShortPositionRatio")):
            d = get(f"{FAPI}/futures/data/{path}", {"symbol": sym, "period": "4h", "limit": 7})
            if isinstance(d, list) and d:
                o[key] = [r5(x["longShortRatio"]) for x in d]
        t = get(f"{FAPI}/futures/data/takerlongshortRatio", {"symbol": sym, "period": "4h", "limit": 7})
        if isinstance(t, list) and t:
            o["taker_buy_sell_4h"] = [r5(x["buySellRatio"]) for x in t]
        # alts often have no quarterly contract: Binance returns an error dict, not a list
        b = get(f"{FAPI}/futures/data/basis", {"pair": sym, "contractType": "CURRENT_QUARTER", "period": "1d", "limit": 1})
        if isinstance(b, list) and b:
            o["quarterly_basis_rate"] = r5(b[-1].get("basisRate"))
            o["quarterly_basis_annualized"] = r5(b[-1].get("annualizedBasisRate"))
    tk = get(f"{BYBIT}/v5/market/tickers", {"category": "linear", "symbol": sym})
    try:
        x = tk["result"]["list"][0]
        o["bybit"] = {"funding": r5(x["fundingRate"]), "oi_usd_bn": r5(float(x["openInterestValue"]) / 1e9)}
        o["source"] = o["source"] or "bybit"
        ar = get(f"{BYBIT}/v5/market/account-ratio", {"category": "linear", "symbol": sym, "period": "4h", "limit": 7})
        o["bybit"]["buy_ratio_4h"] = [r5(y["buyRatio"]) for y in reversed(ar["result"]["list"])]
    except (TypeError, KeyError, IndexError, ValueError):
        pass
    return o


# ---------------- duygu ve makro ----------------
def fng():
    d = get("https://api.alternative.me/fng/", {"limit": 7, "format": "json"})
    try:
        x = list(reversed(d["data"]))
        return {"last7": [int(y["value"]) for y in x], "label": x[-1]["value_classification"]}
    except (TypeError, KeyError):
        return None


SERIES = {}   # yahoo gunluk kapanislari (1 yil): veri_ek.cross_asset korelasyonlari icin


def yahoo(sym):
    d = get(f"https://query1.finance.yahoo.com/v8/finance/chart/{sym}", {"range": "1y", "interval": "1d"})
    try:
        res = d["chart"]["result"][0]
        c = pd.Series(res["indicators"]["quote"][0]["close"],
                      index=pd.to_datetime(res["timestamp"], unit="s", utc=True)).dropna()
        SERIES[sym] = c
        return {"last": r5(c.iloc[-1]), "bar_date": ts(c.index[-1], True),
                "chg_5d_pct": pct(c.iloc[-1], c.iloc[-6]), "chg_20d_pct": pct(c.iloc[-1], c.iloc[-21])}
    except (TypeError, KeyError, IndexError):
        return None


def fred(series, asof):
    t = get("https://fred.stlouisfed.org/graph/fredgraph.csv",
            {"id": series, "cosd": (asof - pd.Timedelta(days=150)).strftime("%Y-%m-%d")}, text=True)
    try:
        df = pd.read_csv(io.StringIO(t))
        col = df.columns[1]
        df[col] = pd.to_numeric(df[col], errors="coerce")
        df = df.dropna()
        return {"last": r5(df[col].iloc[-1]), "date": str(df.iloc[-1, 0]),
                "chg_over_20_obs": r5(df[col].iloc[-1] - df[col].iloc[-21]) if len(df) > 21 else None}
    except Exception:  # noqa: BLE001
        return None


def coingecko():
    d = get("https://api.coingecko.com/api/v3/global")
    try:
        x = d["data"]
        return {"btc_dominance_pct": r5(x["market_cap_percentage"]["btc"]),
                "eth_dominance_pct": r5(x["market_cap_percentage"]["eth"]),
                "total_mcap_usd_tn": r5(x["total_market_cap"]["usd"] / 1e12),
                "total_mcap_chg_24h_pct": r5(x["market_cap_change_percentage_24h_usd"])}
    except (TypeError, KeyError):
        return None


def calendar(asof):
    d = get("https://nfs.faireconomy.media/ff_calendar_thisweek.json")
    try:
        out = []
        for e in d:
            if e.get("impact") != "High" or e.get("country") != "USD":
                continue
            t = pd.Timestamp(e["date"]).tz_convert("UTC")
            if asof - pd.Timedelta(hours=24) <= t <= asof + pd.Timedelta(hours=72):
                out.append([ts(t), e.get("title"), e.get("forecast"), e.get("previous")])
        return {"cols": ["time_utc", "event", "forecast", "previous"], "rows": out,
                "note": "USD high-impact, -24h..+72h, source covers current week only"}
    except (TypeError, KeyError, ValueError):
        return None


def etf_flows():
    t = get("https://farside.co.uk/bitcoin-etf-flow-all-data/", text=True)
    if not t:
        return None
    try:
        tab = max(pd.read_html(io.StringIO(t)), key=len)
        first, tot = tab.columns[0], tab.columns[-1]
        out = []
        for _, r in tab.iterrows():
            dt = pd.to_datetime(str(r[first]), errors="coerce", dayfirst=True)
            if pd.isna(dt):
                continue
            v = str(r[tot]).replace(",", "").strip()
            neg = v.startswith("(")
            try:
                x = float(v.strip("()")) * (-1 if neg else 1)
            except ValueError:
                x = None
            out.append([ts(dt, True), x])
        return {"unit": "USD m/day, Farside total, US spot BTC ETFs", "last10": out[-10:]} if out else None
    except Exception as e:  # noqa: BLE001
        ERR.append(f"farside parse: {type(e).__name__} {str(e)[:80]}")
        return None


# ---------------- harmonik (kaynak: C:/Users/pc/trader-ofis-egitim/harmonik-kurs/OZET.md bolum 1-6) ----------------
# Oranlar: ab=|B-A|/|A-X|, bc=|C-B|/|B-A|, cd=|D-C|/|C-B|, xd=|D-A|/|A-X|, dxc=|C-D|/|C-X|, abcd=|D-C|/|B-A|.
# Bantlar OZET tablosundaki "code band" (iki kurs sayfasi celisirse genis olan). Shark: XABCD araci (X,A,B,C,D) =
# Shark (0,X,A,B,C). 5-0 alinmadi (kursta stop/hedef yok). "def" = D'yi tanimlayan oran ve ideal degeri.
HARM = {
    "Gartley":   {"ab": (0.58, 0.65), "bc": (0.382, 0.886), "cd": (1.13, 1.618), "xd": (0.618, 0.84), "def": ("xd", 0.786)},
    "Bat":       {"ab": (0.382, 0.52), "bc": (0.382, 0.886), "cd": (1.618, 2.618), "xd": (0.85, 0.90), "def": ("xd", 0.886)},
    "AltBat":    {"ab": (0.35, 0.40), "bc": (0.382, 0.886), "cd": (2.0, 3.618), "xd": (1.10, 1.17), "def": ("xd", 1.13)},
    "Butterfly": {"ab": (0.76, 0.83), "bc": (0.382, 0.886), "cd": (1.618, 2.618), "xd": (1.20, 1.414), "def": ("xd", 1.27)},
    "Crab":      {"ab": (0.382, 0.67), "bc": (0.382, 0.91), "cd": (2.24, 3.618), "xd": (1.55, 1.70), "def": ("xd", 1.618)},
    "DeepCrab":  {"ab": (0.836, 0.93), "bc": (0.382, 0.886), "cd": (2.0, 3.618), "xd": (1.55, 1.70), "def": ("xd", 1.618)},
    "Cypher":    {"ab": (0.382, 0.618), "bc": (1.13, 1.45), "cd": (1.272, 2.0), "dxc": (0.75, 0.886), "def": ("dxc", 0.786)},
    "Shark":     {"bc": (1.13, 1.618), "cd": (1.618, 2.24), "xd": (0.886, 1.18), "def": ("xd", 1.0)},
    "ABCD":      {"bc": (0.587, 0.825), "cd": (1.27, 1.618), "abcd": None, "def": ("abcd", None)},
}
HARM_TF = (("1h", 2.0), ("4h", 2.0), ("4h", 3.5), ("1d", 3.0))   # (zaman dilimi, zigzag k): birden cok olcek
D_TOL = 0.05   # D'ye bagli oranlarda (cd, xd, dxc) bant +-%5 genisler: kursta D bir bolge, fiyat once doner ya da tasar


def _in(r, b, tol=0.0):
    return r is not None and np.isfinite(r) and b[0] * (1 - tol) <= r <= b[1] * (1 + tol)


def _closeness(r, b):
    c, h = (b[0] + b[1]) / 2, (b[1] - b[0]) / 2
    return 1.0 if h <= 0 else 1 - min(1.0, abs(r - c) / h)


def _last_candle(df):
    o, h, l, c = df[["open", "high", "low", "close"]].to_numpy()[-1]
    po, pc = df.open.iloc[-2], df.close.iloc[-2]
    body = abs(c - o)
    if h - l <= 0:
        return None
    if c > o and pc < po and c >= po and o <= pc:
        return "bull_engulf"
    if c < o and pc > po and c <= po and o >= pc:
        return "bear_engulf"
    if min(o, c) - l >= 2 * body and h - max(o, c) <= body:
        return "hammer"
    if h - max(o, c) >= 2 * body and min(o, c) - l <= body:
        return "shooting_star"
    return None


def _confirm(df, d, iB, pB, iD, pD, plo, phi):
    """Kurs bolum 5: RSI uyumsuzlugu (D vs B), TDI benzeri kesisim (RSI21: cizgi SMA2, sinyal SMA7, son 3 mum),
    son kapali mum tipi, son kapanis PRZ icinde mi. d=-1 bogasal (D dip, yukari donus beklenir)."""
    r14, r21 = rsi(df.close), rsi(df.close, 21)
    diff = (r21.rolling(2).mean() - r21.rolling(7).mean()).to_numpy()[-4:]
    up = d < 0
    cross = any((diff[j - 1] <= 0 < diff[j]) if up else (diff[j - 1] >= 0 > diff[j]) for j in range(1, len(diff)))
    beyond = (pD < pB) if up else (pD > pB)
    div = None if not beyond else bool((r14.iloc[iD] > r14.iloc[iB]) if up else (r14.iloc[iD] < r14.iloc[iB]))
    last = df.close.iloc[-1]
    return {"rsi_div_vs_B": div, "tdi_cross_3bars": bool(cross), "last_candle": _last_candle(df),
            "last_close_in_prz": bool(plo <= last <= phi)}


def harmonics(fr, keep=6):
    """Pivot tabanli XABCD adaylari. Kod yalniz olcer; karar trader-harmonik'in.
    live: X,A,B,C onayli + D = suren bacagin ucu (forming / at_prz / overshot). reacted: 5 nokta onayli, D son 10 mumda."""
    out = []
    for iv, k in HARM_TF:
        df = fr[iv]
        piv, prov = zigzag(df, k)
        if len(df) < 30:
            continue
        a, idx = atr(df).iloc[-1], df.index
        sets = []
        if prov and len(piv) >= 4:
            sets.append((piv[-4:] + [prov], "live"))
        if len(piv) >= 5 and len(df) - 1 - piv[-1][0] <= 10:
            sets.append((piv[-5:], "reacted"))
        for pts, kind in sets:
            (iX, X, _), (iA, A, _), (iB, B, _), (iC, C, _), (iD, Dn, tD) = pts
            d = 1 if tD.startswith("H") else -1          # D tepe = ayisal (sat), D dip = bogasal (al)
            xa, ab_, bc_ = abs(A - X), abs(B - A), abs(C - B)
            if min(xa, ab_, bc_) <= 0:
                continue
            r = {"ab": ab_ / xa, "bc": bc_ / ab_, "cd": abs(Dn - C) / bc_, "xd": abs(Dn - A) / xa,
                 "dxc": abs(C - Dn) / abs(C - X) if C != X else float("nan"), "abcd": abs(Dn - C) / ab_}
            for name, P in HARM.items():
                pre = [q for q in ("ab", "bc") if q in P]
                if not all(_in(r[q], P[q]) for q in pre):
                    continue
                cdlo, cdhi = sorted(C + d * x * bc_ for x in P["cd"])
                if name == "ABCD":
                    opts = []
                    for t in (1.0, 1.272, 1.618):
                        lo, hi = sorted(C + d * x * ab_ for x in (t * 0.97, t * 1.03))
                        if hi >= cdlo and lo <= cdhi:
                            opts.append((t, lo, hi))
                    if not opts:
                        continue
                    ideal, plo, phi = opts[0]
                    conflu = True
                else:
                    q, ideal = P["def"]
                    ref, leg = (C, abs(C - X)) if q == "dxc" else (A, xa)
                    plo, phi = sorted(ref + d * x * leg for x in P[q])
                    conflu = phi >= cdlo and plo <= cdhi
                    if conflu:
                        plo, phi = max(plo, cdlo), min(phi, cdhi)
                near, far = (plo, phi) if d > 0 else (phi, plo)
                if kind == "reacted":
                    status = "reacted"
                elif d * (Dn - near) < -0.25 * a:
                    status = "forming"
                elif d * (Dn - far) > 0.5 * a:
                    status = "overshot"
                else:
                    status = "at_prz"
                over = d * (Dn - far) / a
                if status == "overshot" and over > 3:      # PRZ'den 3 ATR'den fazla gecilmis: bayat aday
                    continue
                # dist_prz_atr: + = PRZ'ye daha var, 0 = PRZ icinde, - = uzak kenarin otesinde
                dist = -over if status == "overshot" else max(0.0, -d * (Dn - near)) / a
                if status == "forming" and dist > 3:
                    continue
                dq = [q for q in ("cd", "xd", "dxc") if q in P]
                if status in ("at_prz", "reacted"):
                    if not all(_in(r[q], P[q], D_TOL) for q in dq):
                        continue
                    if name == "ABCD" and abs(r["abcd"] - ideal) / ideal > 0.03 + D_TOL:
                        continue
                cl = [_closeness(r[q], P[q]) for q in pre]
                Dref = Dn if status != "forming" else (plo + phi) / 2
                if status != "forming":
                    dv = r[P["def"][0]]
                    cl.append(1 - min(1.0, abs(dv - ideal) / (0.05 * ideal)))
                lvl = lambda x: A + d * x * xa  # noqa: E731  XA seviyesi
                if name == "ABCD":
                    stop = Dref + d * 0.272 * abs(Dref - A)
                elif name == "Gartley":
                    stop = lvl(0.786)
                elif name == "Butterfly":
                    stop = lvl(1.414)
                elif name in ("Crab", "DeepCrab"):
                    stop = lvl(2.0)
                elif name == "AltBat":
                    stop = Dref + d * 0.272 * abs(C - Dref)
                else:                                    # Bat, Cypher, Shark: D'nin hemen otesi
                    stop = Dref
                stop = max(stop, Dref) if d > 0 else min(stop, Dref)
                hard = X if name in ("Gartley", "Bat", "Cypher") else (
                    lvl(1.414) if name == "Butterfly" else lvl(2.0) if name in ("Crab", "DeepCrab") else None)
                leg = abs(A - Dref) if name == "ABCD" else abs(C - Dref)
                t2r = 0.5 if name == "Shark" else 0.618
                out.append({
                    "pattern": name, "dir": "bear" if d > 0 else "bull", "tf": iv, "zz_k": k, "status": status,
                    "fit": round(100 * float(np.mean(cl))),
                    "XABCD": [[ts(idx[i], iv == "1d"), r5(p)] for i, p, _ in pts],
                    "ratios": {q: r5(r[q]) for q in P if q != "def"},
                    "prz": [r5(plo), r5(phi)], "bc_confluence": bool(conflu),
                    "d_now": r5(Dn), "dist_prz_atr": r5(dist), "atr14_tf": r5(a),
                    "course_stop": r5(stop), "hard_invalid": r5(hard),
                    "t1": r5(Dref - d * 0.382 * leg), "t2": r5(Dref - d * t2r * leg),
                    "confirm": None if status == "forming" else _confirm(df, d, iB, B, iD, Dn, plo, phi)})
    order = {"at_prz": 0, "forming": 1, "reacted": 2, "overshot": 3}
    out.sort(key=lambda x: (order[x["status"]], -x["fit"]))
    return out[:keep]


# ---------------- grafik ----------------
CHART_BARS = {"1d": 120, "4h": 120, "1h": 96}


def charts(sym, fr, lv, vp, outdir):
    """Mum grafigi + onayli pivotlar (etiketli) + onceki hafta H/L + 4h POC. Yalniz kapanmis mumlar.
    1200x650 px: Claude gorsel token maliyeti ~ w*h/750 = ~1.0k token/grafik (Anthropic vision belgesi, bellekten)."""
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError as e:
        ERR.append(f"charts: {e} (pip install matplotlib)")
        return None
    outdir.mkdir(parents=True, exist_ok=True)
    paths = {}
    for iv, nb in CHART_BARS.items():
        df = fr[iv]
        piv, prov = zigzag(df, ZZ_K[iv])
        start = max(0, len(df) - nb)
        d = df.iloc[start:]
        x = np.arange(len(d))
        fig, ax = plt.subplots(figsize=(12, 6.5), dpi=100)
        up = (d.close >= d.open).to_numpy()
        col = np.where(up, "#26a69a", "#ef5350")
        ax.vlines(x, d.low, d.high, color=col, linewidth=0.8)
        ax.bar(x, (d.close - d.open).abs().clip(lower=1e-9), bottom=np.minimum(d.open, d.close), color=col, width=0.7)
        last = {"H": None, "L": None}
        for i, p, t in piv:
            lab = t if last[t] is None else (("HH" if p > last[t] else "LH") if t == "H" else ("HL" if p > last[t] else "LL"))
            last[t] = p
            if i >= start:
                xi = i - start
                ax.annotate(f"{lab}\n{r5(p)}" if t == "H" else f"{r5(p)}\n{lab}", (xi, p),
                            xytext=(0, 12 if t == "H" else -22), textcoords="offset points",
                            ha="center", fontsize=7, color="#1a237e")
                ax.plot(xi, p, "v" if t == "H" else "^", color="#1a237e", markersize=5)
        if prov and prov[0] >= start:
            ax.plot(prov[0] - start, prov[1], "o", mfc="none", color="#ff9800", markersize=8)
        lines = []
        if lv.get("prev_week_hl"):
            lines += [(lv["prev_week_hl"][0], "PWH", "#6d4c41"), (lv["prev_week_hl"][1], "PWL", "#6d4c41")]
        if vp and vp.get("poc"):
            lines.append((vp["poc"], "POC4h", "#7b1fa2"))
        lo, hi = d.low.min(), d.high.max()
        for y, name, c in lines:
            if lo * 0.97 <= y <= hi * 1.03:
                ax.axhline(y, color=c, linestyle="--", linewidth=0.8)
                ax.text(len(d) + 0.5, y, f"{name} {y}", fontsize=7, color=c, va="center")
        step = max(1, len(d) // 8)
        ax.set_xticks(x[::step])
        ax.set_xticklabels([ts(t, iv == "1d") for t in d.index[::step]], fontsize=7)
        ax.set_xlim(-1, len(d) + 8)
        ax.grid(alpha=0.2)
        ax.set_title(f"{sym} {iv} | closed candles to {ts(d.index[-1] + pd.Timedelta(minutes=IV_MIN[iv]))} UTC | "
                     f"pivots k={ZZ_K[iv]}xATR, orange ring = unconfirmed leg extreme", fontsize=9)
        fig.tight_layout()
        f = outdir / f"{sym}_{iv}.png"
        fig.savefig(f)
        plt.close(fig)
        paths[iv] = str(f)
    return paths


# ---------------- akis ----------------
def dump(o, ind=0):
    """Okunur ama kisa JSON: kisa liste/sozluk tek satir, uzun olan satir satir."""
    one = json.dumps(o, separators=(",", ":"), ensure_ascii=False, default=lambda x: x.item())
    if len(one) <= 160 or not isinstance(o, (dict, list)):
        return one
    sp = " " * (ind + 1)
    if isinstance(o, dict):
        return "{\n" + ",\n".join(f"{sp}{json.dumps(k)}: {dump(v, ind + 1)}" for k, v in o.items()) + "\n" + " " * ind + "}"
    if not any(isinstance(x, (list, dict)) for x in o):
        return one
    return "[\n" + ",\n".join(sp + dump(x, ind + 1) for x in o) + "\n" + " " * ind + "]"


def load_assets():
    f = ROOT / "ofis-ayar.json"
    try:
        return json.loads(f.read_text(encoding="utf-8"))["assets"]
    except Exception:  # noqa: BLE001
        return ["BTCUSDT", "ETHUSDT"]


def elliott(fr):
    """Kod Elliott sayimi (elliott_say.py). Hata turu asla bozmaz."""
    try:
        import elliott_say
        return elliott_say.analyze(fr)
    except Exception as e:  # noqa: BLE001
        ERR.append(f"elliott: {type(e).__name__}: {e}")
        return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--asof", help="ISO UTC; verilirse yeniden oynatma (turev/makro bos)")
    ap.add_argument("--out", default=str(OUT))
    ap.add_argument("--assets", help="virgullu sembol listesi; verilirse ofis-ayar.json assets yerine (evren/tarayici secimi)")
    a = ap.parse_args()
    replay = a.asof is not None
    t = pd.Timestamp(a.asof) if replay else pd.Timestamp.now(tz="UTC")
    t = t.tz_localize("UTC") if t.tzinfo is None else t.tz_convert("UTC")
    asof = t.floor("4h")
    assets = [x.strip().upper() for x in a.assets.split(",") if x.strip()] if a.assets else load_assets()
    if "BTCUSDT" in assets:
        assets = ["BTCUSDT"] + [x for x in assets if x != "BTCUSDT"]
    frames = {}
    for s in dict.fromkeys(["BTCUSDT"] + assets):
        try:
            fr = {iv: klines(s, iv, asof) for iv in IV_MIN}
        except Exception as e:  # noqa: BLE001  tek varlik turu durdurmaz
            ERR.append(f"{s}: klines error {type(e).__name__} {str(e)[:100]}")
            continue
        if any(v is None or len(v) < 30 for v in fr.values()):
            ERR.append(f"{s}: klines missing")
            continue
        frames[s] = fr
    snap = {"asof_utc": ts(asof), "generated_utc": ts(pd.Timestamp.now(tz="UTC")),
            "mode": "replay" if replay else "live",
            "legend": {"structure.pivots": "[time, price, HH/HL/LH/LL, first_close_beyond_time, first_wick_sweep_time(before any close beyond), rsi14_at_pivot]; confirmed by k*ATR14 reversal (1d k=3, 4h/1h k=2)",
                       "current_leg_extreme": "unconfirmed extreme of the running leg (H?/L?)",
                       "fvg": "[middle_candle_time, bull/bear, low, high, open/partial]; filled ones dropped",
                       "equal_hl": "untaken equal highs/lows (tolerance 0.25*ATR14 of that tf)",
                       "vp": "volume profile from Binance spot quote volume: poc/vah/val(70%)/hvn/lvn",
                       "candles": "closed candles only, times are open times UTC",
                       "paper_systems_now": "current position (1=long, 0=cash) of our 3 rule-based paper systems",
                       "elliott": "code impulse count (elliott_say.py, 4h+1d multi-degree zigzag): state w3_setup/w3_in_progress/w5_setup/impulse_done/corrective_or_unclear, trigger, invalidation, targets, waves [label,time,price], alts; backtest: no edge, map not signal",
                       **LEGEND_EK},
            "assets": {}}
    sys.modules.setdefault("veri_topla", sys.modules[__name__])   # veri_ek ayni ERR/get'i kullansin
    import veri_ek as X
    C, now = X.cfg(), pd.Timestamp.now(tz="UTC").to_pydatetime()
    btc = frames.get("BTCUSDT")
    for s in assets:
        fr = frames.get(s)
        if fr is None or btc is None:
            snap["assets"][s] = None
            continue
        # denetim 2026-11-21: bir alan/varlik hatasi turu durdurmaz. Cekirdek (ctx/levels/structure/candles)
        # bozulursa varlik None (hatali) olur; yan alan bozulursa yalniz o alan None, nedeni errors'a.
        def opt(name, fn, *args):
            try:
                return fn(*args)
            except Exception as e:  # noqa: BLE001
                ERR.append(f"{s}: {name} error {type(e).__name__} {str(e)[:100]}")
                return None
        try:
            a4, a1 = atr(fr["4h"]).iloc[-1], atr(fr["1h"]).iloc[-1]
            x = {
                "ctx": context(fr, btc),
                "levels": key_levels(fr["1d"], asof),
                "structure": {"1d": structure(fr["1d"], "1d", 12), "4h": structure(fr["4h"], "4h", 12),
                              "1h": structure(fr["1h"], "1h", 10)},
                "fvg": opt("fvg", lambda: {"4h": fvgs(fr["4h"], a4), "1h": fvgs(fr["1h"], a1)}),
                "equal_hl": opt("equal_hl", lambda: {"4h": equal_levels(fr["4h"], a4, "4h"),
                                                     "1h": equal_levels(fr["1h"], a1, "1h")}),
                "vp": opt("vp", lambda: {"4h_all": vprofile(fr["4h"]), "1h_30d": vprofile(fr["1h"]),
                                         "1d_180d": vprofile(fr["1d"].tail(180))}) or {},
                "harmonics": opt("harmonics", harmonics, fr),
                "elliott": opt("elliott", elliott, fr),
                "avwap_1d": opt("avwap_1d", avwap, fr["1d"], fr["4h"]),
                "candles": {"1w": weekly_rows(fr["1d"]), **{iv: rows(fr[iv], iv) for iv in ("1d", "4h", "1h", "15m")}},
                "derivs": None if replay else opt("derivs", derivs, s, fr["4h"]),
            }
        except Exception as e:  # noqa: BLE001
            ERR.append(f"{s}: asset errored (core fields) {type(e).__name__} {str(e)[:120]}")
            snap["assets"][s] = None
            continue
        snap["assets"][s] = x
        if not replay:   # canli-ozel: cekildigi anin degeri (TASARIM.md 14 "Ek veri ve kayitcilar")
            cur = s.replace("USDT", "")
            px = x["ctx"]["last_close"]
            x["options"] = X.safe(f"options {cur}", X.options, cur, now) if cur in ("BTC", "ETH") else None
            x["onchain"] = X.safe(f"onchain {cur}", X.onchain, cur.lower(), asof) if cur in ("BTC", "ETH") else None
            x["orderbook"] = X.safe(f"orderbook {s}", X.orderbook, s)
            x["recorded"] = opt("recorded", X.recorded, s, px, now, C)
        x["charts"] = opt("charts", charts, s, fr, x["levels"], x["vp"].get("4h_all"),
                          ROOT / "grafik" / (asof.strftime("%Y%m%d_%H%M") + ("_replay" if replay else "")))
    if replay:
        snap["sentiment"] = snap["macro"] = "omitted in replay mode (live-only data)"
    else:
        S = X.safe   # her makro alan ayri korunur: biri bozulursa yalniz o alan None (errors'a yazilir)
        snap["sentiment"] = {"fear_greed": S("fng", fng)}
        snap["macro"] = {"dxy": S("dxy", yahoo, "DX-Y.NYB"), "us10y_yield": S("us10y", yahoo, "^TNX"),
                         "spx": S("spx", yahoo, "^GSPC"), "vix": S("vix", yahoo, "^VIX"), "gold": S("gold", yahoo, "GC=F"),
                         "fed_funds_eff": S("DFF", fred, "DFF", asof), "ust2y": S("DGS2", fred, "DGS2", asof),
                         "fed_balance_sheet_musd": S("WALCL", fred, "WALCL", asof),
                         "crypto_global": S("coingecko", coingecko), "calendar_usd_high": S("calendar", calendar, asof),
                         "btc_etf_flows": S("etf_flows", etf_flows),
                         "ndx": S("ndx", yahoo, "^NDX"), "usdjpy": S("usdjpy", yahoo, "JPY=X"),
                         "move": S("move", yahoo, "^MOVE"), "hy_oas_pct": S("hy_oas", fred, "BAMLH0A0HYM2", asof),
                         "stablecoin_supply": X.safe("stablecoins", X.stablecoins, asof)}
        if btc is not None:
            snap["macro"].update(X.safe("cross_asset", X.cross_asset, btc["1d"], C) or {})
    snap["errors"] = ERR
    out = pathlib.Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    text = dump(snap) + "\n"
    f = out / f"snap_{asof.strftime('%Y%m%d_%H%M')}{'_replay' if replay else ''}.json"
    f.write_text(text, encoding="utf-8")
    if not replay:   # yeniden oynatma canli son.json'u ezmesin
        (out / "son.json").write_text(text, encoding="utf-8")
    print(f"{f} | assets={[k for k, v in snap['assets'].items() if v]} | errors={len(ERR)} | ~{len(text) // 4} tokens")


if __name__ == "__main__":
    main()
