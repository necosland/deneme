"""Spot-perp fonlama tasima (funding carry) backtesti.

Pozisyon: spot coin AL + ayni miktarda USDT-M perp SAT (short). Fiyat hareketi birbirini goturur,
kalan: fonlama geliri (negatifse gider) + baz degisimi - maliyet.

Kullanim:  python carry.py            (veri indir/cache, tum grid, rapor tablolari)
           python carry.py --test     (yalniz gelecekten-bilgi (lookahead) kesme testi)
           python carry.py --refresh  (veriyi yeniden indir)

Veri (anahtarsiz, herkese acik):
  Binance Vision aylik dosyalar: spot 1h klines, USDT-M perp 1h klines, perp fundingRate.
  Vision'da olmayan aylar (perp 2019-09..12, icinde bulunulan ay): Binance REST (spot data-api, fapi).
  Bybit v5 funding history (capraz kontrol), FRED DTB3 (ABD 3 aylik hazine bonosu).

Zaman kurali: 1h mum, index = mumun ACILIS zamani. Mum i'nin kapanisi = idx[i] + 1h.
  Fonlama olayi T anindaysa, kapanisi T olan muma (acilis T-1h) yazilir ve o mum boyunca acik olan
  pozisyona odenir. Karar mum i kapanisinda, yalniz <= kapanis(i) zamanli veriyle verilir ve
  ayni kapanis fiyatindan islenir; sonraki getiri i+1'den baslar.
"""
import argparse
import concurrent.futures as cf
import io
import pathlib
import sys
import time
import zipfile

import numpy as np
import pandas as pd
import requests

ROOT = pathlib.Path(__file__).parent
CACHE = ROOT / "cache" / "vision"
OUT = ROOT / "sonuc"
VISION = "https://data.binance.vision/data/"
SPOT_REST = "https://data-api.binance.vision/api/v3/klines"
PERP_REST = "https://fapi.binance.com/fapi/v1/klines"
MARK_REST = "https://fapi.binance.com/fapi/v1/markPriceKlines"
FUND_REST = "https://fapi.binance.com/fapi/v1/fundingRate"
BYBIT = "https://api.bybit.com/v5/market/funding/history"
FRED = "https://fred.stlouisfed.org/graph/fredgraph.csv?id=DTB3"

COINS = ["BTC", "ETH", "SOL", "BNB", "XRP", "DOGE", "ADA", "LTC"]
PRIMARY = ["BTC", "ETH"]
SPLIT = pd.Timestamp("2025-01-01", tz="UTC")   # secim < SPLIT <= sinav (holdout)
H1 = pd.Timedelta(hours=1)

SPOT_FEE, SLIP = 0.0010, 0.0002                 # spot %0.10/taraf, kayma %0.02/bacak
PERP_FEE = {"taker": 0.0005, "maker": 0.0002}   # perp %0.05 taker, %0.02 maker
MMR = 0.005                                     # bakim teminati orani (~%0.5)
DRIFT = 0.05                                    # teminat payi hedeften 5 puan saparsa dengele
EXIT_X = 2.0                                    # esikli kurallarda cikis: 7g ort. yillik fonlama < %2

LOG = []


def log(*a):
    s = " ".join(str(x) for x in a)
    print(s)
    LOG.append(s)


# =============================================================== veri indirme
def _get(url, params=None, tries=4):
    for k in range(tries):
        try:
            r = requests.get(url, params=params, timeout=60)
            if r.status_code == 404:
                return None
            r.raise_for_status()
            return r
        except requests.RequestException:
            if k == tries - 1:
                raise
            time.sleep(2 * (k + 1))


def _vision_path(kind, sym, ym):
    return {"spot": f"spot/monthly/klines/{sym}/1h/{sym}-1h-{ym}.zip",
            "perp": f"futures/um/monthly/klines/{sym}/1h/{sym}-1h-{ym}.zip",
            "mark": f"futures/um/monthly/markPriceKlines/{sym}/1h/{sym}-1h-{ym}.zip",
            "fund": f"futures/um/monthly/fundingRate/{sym}/{sym}-fundingRate-{ym}.zip"}[kind]


def vision_month(kind, sym, ym, cache_404=True):
    path = _vision_path(kind, sym, ym)
    f = CACHE / "raw" / path.replace("/", "_")
    miss = f.with_suffix(".404")
    if f.exists():
        return f.read_bytes()
    if miss.exists():
        return None
    r = _get(VISION + path)
    f.parent.mkdir(parents=True, exist_ok=True)
    if r is None:
        if cache_404:
            miss.touch()
        return None
    f.write_bytes(r.content)
    return r.content


def _rows(b):
    z = zipfile.ZipFile(io.BytesIO(b))
    df = pd.read_csv(io.StringIO(z.read(z.namelist()[0]).decode()), header=None, dtype=str)
    return df[df[0].str.strip().str.isdigit()]          # baslik satiri varsa at


def _ts(ms):
    ms = ms.astype("int64").to_numpy()
    ms = np.where(ms > 10 ** 14, ms // 1000, ms)          # spot 2025+: mikrosaniye
    return pd.to_datetime(ms, unit="ms", utc=True)


def parse_klines(b):
    d = _rows(b)
    return pd.DataFrame({k: d[j].astype(float).to_numpy() for k, j in
                         (("open", 1), ("high", 2), ("low", 3), ("close", 4))}, index=_ts(d[0]))


def parse_fund(b):
    d = _rows(b)
    iv = d[1].astype(float).to_numpy() if d.shape[1] >= 3 else np.full(len(d), np.nan)
    rate = d[d.columns[-1]].astype(float).to_numpy()
    return pd.DataFrame({"rate": rate, "interval": iv}, index=_ts(d[0]))


def rest_klines(kind, sym, a, b):
    url, lim = {"spot": (SPOT_REST, 1000), "perp": (PERP_REST, 1500), "mark": (MARK_REST, 1500)}[kind]
    now = int(time.time() * 1000)
    rows, cur = [], a
    while cur < b:
        r = _get(url, dict(symbol=sym, interval="1h", startTime=cur, endTime=b, limit=lim))
        data = r.json() if r is not None else []
        if not data:
            break
        rows += [x for x in data if int(x[6]) < now]      # yalniz kapanmis mumlar
        cur = int(data[-1][0]) + 1
        if len(data) < lim:
            break
        time.sleep(0.2)
    if not rows:
        return None
    d = pd.DataFrame(rows)
    return pd.DataFrame({k: d[j].astype(float).to_numpy() for k, j in
                         (("open", 1), ("high", 2), ("low", 3), ("close", 4))},
                        index=pd.to_datetime(d[0].astype("int64"), unit="ms", utc=True))


def rest_funding(sym, a, b):
    rows, cur = [], a
    while cur < b:
        r = _get(FUND_REST, dict(symbol=sym, startTime=cur, endTime=b, limit=1000))
        data = r.json() if r is not None else []
        if not data:
            break
        rows += data
        cur = int(data[-1]["fundingTime"]) + 1
        if len(data) < 1000:
            break
        time.sleep(0.3)
    if not rows:
        return None
    d = pd.DataFrame(rows)
    return pd.DataFrame({"rate": d["fundingRate"].astype(float).to_numpy(), "interval": np.nan},
                        index=pd.to_datetime(d["fundingTime"].astype("int64"), unit="ms", utc=True))


def raw_series(kind, c, refresh=False):
    """kind: spot|perp|mark|fund. Vision aylik + eksik aylar ve bu ay icin REST. CSV cache."""
    sym = c + "USDT"
    f = CACHE / f"{kind}_{sym}.csv"
    if f.exists() and not refresh:
        return pd.read_csv(f, index_col=0, parse_dates=True)
    CACHE.mkdir(parents=True, exist_ok=True)
    now = pd.Timestamp.now(tz="UTC")
    last_full = (now.tz_localize(None).to_period("M") - 1)
    first = "2019-01" if kind == "spot" else "2019-09"
    ms = [str(p) for p in pd.period_range(first, last_full, freq="M")]
    with cf.ThreadPoolExecutor(12) as ex:
        blobs = list(ex.map(lambda m: vision_month(kind, sym, m, cache_404=(m != str(last_full))), ms))
    parse = parse_fund if kind == "fund" else parse_klines
    parts, src = [], {"vision": 0, "rest": 0}
    missing = []
    for m, b in zip(ms, blobs):
        if b is None:
            missing.append(m)
        else:
            parts.append(parse(b))
            src["vision"] += 1
    spans = [(pd.Period(m, "M").start_time.tz_localize("UTC"), pd.Period(m, "M").end_time.tz_localize("UTC"))
             for m in missing]
    spans.append((pd.Period(now.tz_localize(None), "M").start_time.tz_localize("UTC"), now))
    for a, b in spans:
        a_ms, b_ms = int(a.timestamp() * 1000), int(b.timestamp() * 1000)
        p = rest_funding(sym, a_ms, b_ms) if kind == "fund" else rest_klines(kind, sym, a_ms, b_ms)
        if p is not None and len(p):
            parts.append(p)
            src["rest"] += 1
    df = pd.concat(parts).sort_index()
    df = df[~df.index.duplicated(keep="last")]
    if kind != "fund":                                    # Vision dosyalarindaki gun bosluklarini REST ile doldur
        d = df.index.to_series().diff()
        for t, g in d[d > pd.Timedelta(hours=6)].items():
            a_ms, b_ms = int((t - g).timestamp() * 1000) + 1, int(t.timestamp() * 1000) - 1
            p = rest_klines(kind, sym, a_ms, b_ms)
            if p is not None and len(p):
                parts.append(p)
                src["rest"] += 1
        df = pd.concat(parts).sort_index()
        df = df[~df.index.duplicated(keep="last")]
    df.to_csv(f)
    log(f"veri {kind:4s} {sym:9s} {df.index[0]:%Y-%m-%d} -> {df.index[-1]:%Y-%m-%d %H:%M} "
        f"satir={len(df)} kaynak={src}")
    return df


def bybit_funding(c, refresh=False):
    sym = c + "USDT"
    f = CACHE / f"bybit_fund_{sym}.csv"
    if f.exists() and not refresh:
        return pd.read_csv(f, index_col=0, parse_dates=True)["rate"]
    rows, end = [], int(time.time() * 1000)
    try:
        while True:
            r = _get(BYBIT, dict(category="linear", symbol=sym, endTime=end, limit=200))
            lst = (r.json().get("result") or {}).get("list") or [] if r is not None else []
            if not lst:
                break
            rows += lst
            oldest = min(int(x["fundingRateTimestamp"]) for x in lst)
            if oldest >= end:
                break
            end = oldest - 1
            time.sleep(0.15)
    except Exception as e:  # noqa: BLE001
        log("Bybit ulasilamadi:", sym, e)
        return None
    if not rows:
        return None
    d = pd.DataFrame(rows)
    s = pd.Series(d["fundingRate"].astype(float).to_numpy(),
                  index=pd.to_datetime(d["fundingRateTimestamp"].astype("int64"), unit="ms", utc=True),
                  name="rate").sort_index()
    s = s[~s.index.duplicated()]
    s.to_frame().to_csv(f)
    return s


def tbill(refresh=False):
    """FRED DTB3 (%, gunluk). Ulasilamazsa None."""
    f = CACHE / "DTB3.csv"
    if not f.exists() or refresh:
        try:
            r = _get(FRED)
            CACHE.mkdir(parents=True, exist_ok=True)
            f.write_bytes(r.content)
        except Exception as e:  # noqa: BLE001
            log("FRED ulasilamadi:", e)
            return None
    d = pd.read_csv(f)
    s = pd.Series(pd.to_numeric(d.iloc[:, 1], errors="coerce").to_numpy(),
                  index=pd.to_datetime(d.iloc[:, 0]).dt.tz_localize("UTC"))
    s = s.reindex(pd.date_range(s.index[0], pd.Timestamp.now(tz="UTC").normalize(), freq="D")).ffill()
    return s


def tbill_ret(tb, a, b):
    """[a, b) araliginda T-bill getirisi (gunluk bilesik, yield/365)."""
    if tb is None:
        return np.nan
    d = tb[(tb.index >= a.normalize()) & (tb.index < b)]
    days = (b - a) / pd.Timedelta(days=1)
    if not len(d):
        return np.nan
    return float((1 + d.mean() / 100 / 365) ** days - 1)


# =============================================================== panel
def build(coins, end=None, refresh=False):
    """Saatlik panel. end verilirse: acilisi < end olan mumlar, zamani <= end olan fonlamalar (kesme testi)."""
    raw = {}
    for c in coins:
        sp, pp, mk, fu = (raw_series(k, c, refresh) for k in ("spot", "perp", "mark", "fund"))
        if end is not None:
            sp, pp, mk, fu = sp[sp.index < end], pp[pp.index < end], mk[mk.index < end], fu[fu.index.round("h") <= end]
        raw[c] = (sp, pp, fu, mk)
    starts = {c: max(r[0].index[0], r[1].index[0]) for c, r in raw.items()}
    stops = {c: min(r[0].index[-1], r[1].index[-1]) for c, r in raw.items()}
    idx = pd.date_range(min(starts.values()), max(stops.values()), freq="h")
    D = {"idx": idx, "coins": coins, "S": {}, "F": {}, "Hi": {}, "Hm": {}, "R": {}, "A7": {}, "valid": {},
         "start": starts, "iv": {}, "gaps": {}, "spot_raw": {c: raw[c][0] for c in coins}}
    for c in coins:
        sp, pp, fu, mk = raw[c]
        rng = (idx >= starts[c]) & (idx <= stops[c])
        D["gaps"][c] = (int(rng.sum() - sp.index.isin(idx[rng]).sum()), int(rng.sum() - pp.index.isin(idx[rng]).sum()))
        S = sp["close"].reindex(idx).ffill().where(rng)
        F = pp["close"].reindex(idx).ffill().where(rng)
        Hi = pp["high"].reindex(idx).where(rng)
        Hi = Hi.fillna(F)                                   # eksik mumda high yok -> kapanis
        Hm = mk["high"].reindex(idx).where(rng).fillna(Hi)  # isaret (mark) fiyati yuksegi; yoksa son fiyat
        D["Hm"][c] = Hm.to_numpy()
        ev = fu["rate"].copy()
        ev.index = ev.index.round("h") - H1                 # olay T -> kapanisi T olan mum
        ev = ev.groupby(level=0).last()
        R = ev.reindex(idx).fillna(0.0)
        a7 = R.rolling(168, min_periods=168).sum() * 365 / 7 * 100      # % yillik, gecmis 7 gun
        first_ev = ev.index[0] if len(ev) else idx[-1]
        ok = rng & (idx >= max(starts[c], first_ev) + pd.Timedelta(days=7))
        D["S"][c], D["F"][c], D["Hi"][c] = S.to_numpy(), F.to_numpy(), Hi.to_numpy()
        D["R"][c] = R.where(rng, 0.0).to_numpy()
        D["A7"][c] = a7.where(ok).to_numpy()
        D["valid"][c] = ok
        D["iv"][c] = fu["interval"]
        D["fund_events"] = D.get("fund_events", {})
        D["fund_events"][c] = fu["rate"]
    D["dec"] = (idx.hour == 23)                             # karar: 00:00 UTC kapanisi (gunde bir)
    return D


# =============================================================== motor
def simulate(D, coins, N=1, X=-np.inf, Xexit=-np.inf, L=1, fee="taker", rebalance="saat", liq_px="mark"):
    """N slot, her slot C/N ile bagimsiz. Slot ya bos (USDT, %0) ya da tek coinde carry.
    Giris: bos slot, tutulmayan ve 7g yillik fonlamasi > X olan en yuksek coine girer.
    Cikis: tutulan coinin 7g yillik fonlamasi < Xexit. X=Xexit=-inf -> hep acik.
    rebalance: "saat" (her saat kapanisinda kontrol), "gun" (yalniz 00:00 kapanisinda), "yok".
    liq_px: tasfiye kontrolunde mum ici en yuksek fiyat: "mark" (Binance isaret fiyati, borsanin kullandigi)
            ya da "last" (son islem fiyati; ince tahtada fitil yapar, daha sert stres testi)."""
    idx = D["idx"]
    T = len(idx)
    ci = list(range(len(coins)))
    S = [D["S"][c].tolist() for c in coins]
    F = [D["F"][c].tolist() for c in coins]
    Hi = [D["Hm" if liq_px == "mark" else "Hi"][c].tolist() for c in coins]
    R = [D["R"][c].tolist() for c in coins]
    A7 = [np.nan_to_num(D["A7"][c], nan=-np.inf).tolist() for c in coins]
    dec = D["dec"].tolist()
    cs, cp = SPOT_FEE + SLIP, PERP_FEE[fee] + SLIP
    tgt = 1.0 / (L + 1)
    # slot: [k, q, m, cash, fp]
    slots = [[-1, 0.0, 0.0, 1.0 / N, 0.0] for _ in range(N)]
    eq = np.empty(T)
    inm = np.zeros(T)
    ent, reb, liq = np.zeros(T), np.zeros(T), np.zeros(T)
    fin, fout, cost = np.zeros(T), np.zeros(T), np.zeros(T)
    liqs = []
    for i in range(T):
        e_tot, n_in = 0.0, 0
        for sl in slots:
            k = sl[0]
            if k >= 0:
                q, m, fp = sl[1], sl[2], sl[4]
                s, f, h = S[k][i], F[k][i], Hi[k][i]
                if m - q * (h - fp) < MMR * q * h:          # mum ici en yuksek fiyatta tasfiye
                    liqs.append((idx[i], coins[k], m, q * s + m))
                    sl[3] = q * s * (1 - cs)                # teminat tamamen gider, spot kapanistan satilir
                    cost[i] += q * s * cs
                    sl[0], sl[1], sl[2] = -1, 0.0, 0.0
                    liq[i] += 1
                else:
                    m -= q * (f - fp)
                    r = R[k][i]
                    if r != 0.0:
                        pay = q * f * r                     # short: r>0 alir, r<0 oder
                        m += pay
                        if pay >= 0:
                            fin[i] += pay
                        else:
                            fout[i] -= pay
                    sl[2], sl[4] = m, f
        if dec[i]:
            held = {sl[0] for sl in slots if sl[0] >= 0}
            for sl in slots:                                 # cikislar
                k = sl[0]
                if k >= 0 and not (A7[k][i] >= Xexit):
                    q, m, s, f = sl[1], sl[2], S[k][i], F[k][i]
                    c_ = q * s * cs + q * f * cp
                    sl[3] = q * s + m - c_
                    cost[i] += c_
                    sl[0], sl[1], sl[2] = -1, 0.0, 0.0
                    held.discard(k)
            free = [sl for sl in slots if sl[0] < 0]
            if free:
                cand = sorted((j for j in ci if j not in held and A7[j][i] > X and A7[j][i] > -np.inf),
                              key=lambda j: -A7[j][i])
                for sl, j in zip(free, cand):
                    E, s, f = sl[3], S[j][i], F[j][i]
                    q = E * L / (L + 1) / s
                    c_ = q * s * cs + q * f * cp
                    sl[0], sl[1], sl[2], sl[3], sl[4] = j, q, E - q * s - c_, 0.0, f
                    cost[i] += c_
                    ent[i] += 1
        if rebalance == "saat" or (rebalance == "gun" and dec[i]):
            for sl in slots:
                k = sl[0]
                if k < 0:
                    continue
                q, m, s, f = sl[1], sl[2], S[k][i], F[k][i]
                E = q * s + m
                if abs(m / E - tgt) > DRIFT or m < 0.5 * q * f / L:
                    qn = E * L / (L + 1) / s
                    dq = abs(qn - q)
                    c_ = dq * (s * cs + f * cp)
                    sl[1], sl[2] = qn, E - qn * s - c_
                    cost[i] += c_
                    reb[i] += 1
        for sl in slots:
            k = sl[0]
            if k >= 0:
                e_tot += sl[1] * S[k][i] + sl[2]
                n_in += 1
            else:
                e_tot += sl[3]
        eq[i] = e_tot
        inm[i] = n_in / N
    return dict(eq=eq, inm=inm, ent=ent, reb=reb, liq=liq, fin=fin, fout=fout, cost=cost, liqs=liqs)


# =============================================================== metrikler
def t0_of(D, coins):
    return min(D["idx"][D["valid"][c]][0] for c in coins if D["valid"][c].any())


def period(D, res, t0, a, b, tb):
    idx = D["idx"]
    m = (idx >= max(a, t0)) & (idx < b)
    if m.sum() < 24:
        return None
    pos = np.flatnonzero(m)
    i0, i1 = pos[0], pos[-1]
    e0 = res["eq"][i0 - 1] if i0 > 0 and idx[i0 - 1] >= t0 else 1.0
    eq = pd.Series(res["eq"][m], index=idx[m] + H1)          # kapanis zamani
    first = idx[i0]
    full = pd.concat([pd.Series([e0], index=[first]), eq])
    ret = eq.iloc[-1] / e0 - 1
    days = (eq.index[-1] - first) / pd.Timedelta(days=1)
    dd = (full / full.cummax() - 1).min()
    full_o = full.copy()
    full_o.index = full_o.index - H1                          # acilis zamani: gun = o gunun 00:00 kapanisi
    dly = full_o.resample("1D").last().dropna()
    dr = dly.pct_change().dropna()
    rf = (tb.reindex(dr.index.normalize()).ffill().fillna(0).to_numpy() / 100 / 365) if tb is not None else 0.0
    ex = dr - rf
    wk = full_o.resample("W").last().dropna()
    wk = pd.concat([pd.Series([e0], index=[first]), wk]).pct_change().dropna()
    return {
        "baslangic": f"{first:%Y-%m-%d}", "bitis": f"{eq.index[-1]:%Y-%m-%d}", "gun": round(days, 1),
        "net_getiri_%": round(ret * 100, 2),
        "yillik_%": round(((1 + ret) ** (365.25 / days) - 1) * 100, 2) if days > 0 and ret > -1 else -100.0,
        "maxDD_%": round(dd * 100, 2),
        "sharpe": round(dr.mean() / dr.std() * np.sqrt(365), 2) if dr.std() > 0 else np.nan,
        "sharpe_tbill_fazlasi": round(ex.mean() / dr.std() * np.sqrt(365), 2) if dr.std() > 0 else np.nan,
        "en_kotu_hafta_%": round(wk.min() * 100, 2) if len(wk) else np.nan,
        "piyasada_%": round(res["inm"][m].mean() * 100, 1),
        "giris": int(res["ent"][m].sum()), "rebalans_sayisi": int(res["reb"][m].sum()), "tasfiye": int(res["liq"][m].sum()),
        "fonlama_gelir_%": round(res["fin"][m].sum() / e0 * 100, 2),
        "fonlama_odenen_%": round(res["fout"][m].sum() / e0 * 100, 2),
        "maliyet_%": round(res["cost"][m].sum() / e0 * 100, 2),
        "tbill_%": round(tbill_ret(tb, first, eq.index[-1]) * 100, 2),
        "tbill_yillik_%": round(((1 + tbill_ret(tb, first, eq.index[-1])) ** (365.25 / days) - 1) * 100, 2) if days > 0 else np.nan,
    }


def periods_for(D, res, coins, tb):
    t0 = t0_of(D, coins)
    end = D["idx"][-1] + H1
    out = {}
    for y in range(t0.year, end.year + 1):
        r = period(D, res, t0, pd.Timestamp(f"{y}-01-01", tz="UTC"), pd.Timestamp(f"{y + 1}-01-01", tz="UTC"), tb)
        if r:
            out[str(y)] = r
    out["secim"] = period(D, res, t0, t0, SPLIT, tb)
    out["sinav"] = period(D, res, t0, SPLIT, end, tb)
    out["tum"] = period(D, res, t0, t0, end, tb)
    return out


# =============================================================== grid
RULES = {"hep_acik": (-np.inf, -np.inf), "esik5": (5.0, EXIT_X), "esik8": (8.0, EXIT_X), "esik10": (10.0, EXIT_X)}


def run_grid(D, tb):
    rows, liq_rows = [], []
    configs = []
    for c in COINS:
        for rule, (X, Xe) in RULES.items():
            configs.append(("tek", [c], c, rule, X, Xe, 1))
    for X in (5.0, 8.0, 10.0):
        for N in (1, 2):
            configs.append(("coklu", COINS, "8coin", f"esik{int(X)}_top{N}", X, EXIT_X, N))
    t_start = time.time()
    for fam, cs_, name, rule, X, Xe, N in configs:
        for L in (1, 2, 3):
            for fee in ("taker", "maker"):
                for rb in ("saat", "gun", "yok"):
                    res = simulate(D, cs_, N=N, X=X, Xexit=Xe, L=L, fee=fee, rebalance=rb)
                    for (t, coin, m, e) in res["liqs"]:
                        liq_rows.append(dict(aile=fam, coin=name, kural=rule, L=L, ucret=fee, rebalans=rb,
                                             zaman=f"{t:%Y-%m-%d %H:%M}", tasfiye_coin=coin,
                                             kaybedilen_teminat=round(m, 4), slot_degeri=round(e, 4)))
                    for p, r in periods_for(D, res, cs_, tb).items():
                        if r is None:
                            continue
                        rows.append(dict(tablo="grid", aile=fam, coin=name, kural=rule, X=X, N=N, L=L, ucret=fee,
                                         rebalans=rb, donem=p, **r))
    log(f"grid: {len(configs) * 18} calisma, {time.time() - t_start:.0f} sn")
    return pd.DataFrame(rows), pd.DataFrame(liq_rows)


def select(G):
    """Secim: yalniz secim donemi (<2025), taker ucret, secimde tasfiye 0; en yuksek yillik net getiri."""
    all_ = G[(G.donem == "secim") & (G.ucret == "taker")]
    out = []
    for name in ["BTC", "ETH", "8coin"] + [c for c in COINS if c not in PRIMARY]:
        s0 = all_[all_.coin == name]
        for label, sub0 in (("en_iyi_kural", s0), ("en_iyi_hep_acik", s0[s0.kural == "hep_acik"])):
            sub, note = sub0[sub0.tasfiye == 0], "tasfiyesiz"
            if not len(sub):                                  # tasfiyesiz yoksa: en az tasfiyeli olanlar arasindan
                sub, note = sub0[sub0.tasfiye == sub0.tasfiye.min()], f"en_az_tasfiye={sub0.tasfiye.min()}"
            if not len(sub):
                continue
            best = sub.sort_values("yillik_%", ascending=False).iloc[0]
            out.append(dict(grup=name, secim=label, kural=best.kural, L=best.L, rebalans=best.rebalans,
                            secim_yillik=best["yillik_%"], secim_notu=note))
    return pd.DataFrame(out)


# =============================================================== fonlama piyasa istatistikleri
def funding_stats(D):
    rows = []
    for c in COINS:
        ev = D["fund_events"][c].copy()
        ev.index = ev.index.round("h")
        ev = ev.groupby(level=0).last()
        iv = D["iv"][c]
        hrs = pd.Series(ev.index.to_series().diff().dt.total_seconds().div(3600).fillna(8).to_numpy(), index=ev.index)
        by = None
        if c in BY:
            by = BY[c].copy()
            by.index = by.index.round("h")
            by = by.groupby(level=0).last()
        # negatif seriler tum seri uzerinde (yil sinirinda kesilmez); seri bittigi yila yazilir
        neg_all = ev < 0
        rid = (neg_all != neg_all.shift()).cumsum()
        runs = pd.DataFrame({"neg": neg_all, "rid": rid, "h": hrs}).groupby("rid").agg(
            neg=("neg", "first"), n=("neg", "size"), h=("h", "sum"))
        runs["end"] = ev.index.to_series().groupby(rid.to_numpy()).last().to_numpy()
        runs = runs[runs.neg]
        groups = list(ev.groupby(ev.index.year)) + [("tum", ev)]
        for y, e in groups:
            days = (e.index[-1] - e.index[0]).total_seconds() / 86400 + hrs[e.index].median() / 24
            neg = (e < 0).astype(int).to_numpy()
            ry = runs if y == "tum" else runs[runs.end.dt.year == y]
            best = int(ry.n.max()) if len(ry) else 0
            run_days = float(ry.h.max() / 24) if len(ry) else 0.0
            ivy = (iv if y == "tum" else iv[iv.index.year == y]).dropna()
            row = dict(tablo="fonlama", coin=c, donem=str(y), olay=len(e),
                       ort_yillik_fonlama_binance_pct=round(e.sum() / days * 365 * 100, 2),
                       negatif_olay_pct=round(neg.mean() * 100, 1),
                       en_uzun_negatif_seri_olay=best, en_uzun_negatif_seri_gun=round(run_days, 1),
                       aralik_saat=",".join(str(int(x)) for x in sorted(ivy.unique())) if len(ivy) else "8(REST)")
            if by is not None:
                b = by[(by.index >= e.index[0]) & (by.index <= e.index[-1])]
                if len(b) > 30:
                    bd = (b.index[-1] - b.index[0]).total_seconds() / 86400 + 8 / 24
                    j = e.index.intersection(b.index)
                    e_ov = e[(e.index >= b.index[0])]
                    ed = (e_ov.index[-1] - e_ov.index[0]).total_seconds() / 86400 + 8 / 24 if len(e_ov) > 1 else np.nan
                    row.update(bybit_baslangic=f"{b.index[0]:%Y-%m-%d}",
                               ort_yillik_fonlama_binance_ortak_pct=round(e_ov.sum() / ed * 365 * 100, 2) if ed else np.nan,
                               ort_yillik_fonlama_bybit_pct=round(b.sum() / bd * 365 * 100, 2),
                               korelasyon_ayni_saat=round(e[j].corr(b[j]), 2) if len(j) > 30 else np.nan)
            rows.append(row)
    return pd.DataFrame(rows)


# =============================================================== BIS fikri: risk azaltma filtresi
def ema(x, n):
    return x.ewm(span=n, adjust=False, min_periods=n).mean()


def sma(x, n):
    return x.rolling(n).mean()


EMA_COINS = ["BTC", "ETH", "BNB", "SOL", "XRP", "ADA"]
EMA_COST = 0.0015


def riskoff_positions(D):
    """ema_btcf (paper.py ile ayni kural): coinde EMA3>EMA17 (gunluk) ve BTC > SMA200.
    Filtre: BTC 30g ort. fonlama > kendi gecmis 365 gunluk %90 dilimi -> pozisyon yarim.
    Gunluk mum etiketi = acilis gunu; kapanis = ertesi gun 00:00. Pozisyon t kapanisinda, getiri t+1."""
    close = {}
    for c in EMA_COINS:
        s = D["spot_raw"][c]["close"]
        d = s.resample("1D").last()                       # o gunun son saatlik kapanisi
        close[c] = d.ffill()
    C = pd.DataFrame(close)
    b = C["BTC"]
    gate = (b > sma(b, 200)).astype(float)
    sig = pd.DataFrame({c: (ema(C[c], 3) > ema(C[c], 17)).astype(float) * gate for c in EMA_COINS})
    elig = C.notna().cumsum() >= 200
    sig = sig.where(elig, 0.0)
    R = pd.Series(D["R"]["BTC"], index=D["idx"])
    R = R[D["idx"] >= D["start"]["BTC"]]
    fd = R.resample("1D").sum().reindex(C.index)          # o gunun mumlarinin kapanisindaki olaylar
    f30 = fd.rolling(30, min_periods=30).mean()
    q90 = f30.rolling(365, min_periods=365).quantile(0.9)
    flag = (f30 > q90) & q90.notna()
    n = elig.sum(axis=1).replace(0, np.nan)
    w = sig.div(n, axis=0).fillna(0.0)
    w_f = (sig.mul(np.where(flag, 0.5, 1.0), axis=0)).div(n, axis=0).fillna(0.0)
    return C, w, w_f, flag, f30, q90


def port_returns(C, w):
    r = C.pct_change(fill_method=None).fillna(0.0)
    held = w.shift(1).fillna(0.0)
    turn = w.diff().abs().sum(axis=1).fillna(w.abs().sum(axis=1))
    return (held * r).sum(axis=1) - turn.shift(1).fillna(0.0) * EMA_COST


def pm(r):
    r = r.dropna()
    eq = (1 + r).cumprod()
    yrs = len(r) / 365
    return dict(gun=len(r), yillik_pct=round((eq.iloc[-1] ** (1 / yrs) - 1) * 100, 2),
                sharpe=round(r.mean() / r.std() * np.sqrt(365), 3), maxDD_pct=round((eq / eq.cummax() - 1).min() * 100, 2),
                net_getiri_pct=round((eq.iloc[-1] - 1) * 100, 2))


def riskoff(D):
    C, w, w_f, flag, f30, q90 = riskoff_positions(D)
    base, filt = port_returns(C, w), port_returns(C, w_f)
    first = q90.first_valid_index()
    end = C.index[-1]
    rows = []
    for p, a, b_ in (("secim", first, SPLIT - pd.Timedelta(days=1)), ("sinav", SPLIT, end)):
        m = (base.index >= a) & (base.index <= b_)
        r0, r1 = pm(base[m]), pm(filt[m])
        rows.append(dict(tablo="riskoff", donem=p, baslangic=f"{base.index[m][0]:%Y-%m-%d}",
                         bitis=f"{base.index[m][-1]:%Y-%m-%d}",
                         filtre_acik_gun_pct=round(flag[m].mean() * 100, 1),
                         **{f"ema_btcf_{k}": v for k, v in r0.items()},
                         **{f"filtreli_{k}": v for k, v in r1.items()}))
    # dogrudan tahmin testi: bayrak acikken BTC'nin sonraki 30 gunu
    b = C["BTC"]
    fwd = b.shift(-30) / b - 1
    fdd = pd.Series([np.nan] * len(b), index=b.index)
    vals = b.to_numpy()
    for i in range(len(vals) - 30):
        fdd.iloc[i] = np.nanmin(vals[i + 1:i + 31]) / vals[i] - 1
    pr = []
    for p, a, b_ in (("secim", first, SPLIT - pd.Timedelta(days=31)), ("sinav", SPLIT, end)):
        m = (b.index >= a) & (b.index <= b_) & fwd.notna()
        for fl in (True, False):
            mm = m & (flag == fl)
            pr.append(dict(tablo="fonlama_tahmin", donem=p, bayrak="yuksek_fonlama" if fl else "normal",
                           gun=int(mm.sum()), btc_sonraki30g_getiri_ort_pct=round(fwd[mm].mean() * 100, 2),
                           btc_sonraki30g_en_derin_dusus_ort_pct=round(fdd[mm].mean() * 100, 2),
                           sonraki30g_dusus_10pct_ustu_olasilik=round((fdd[mm] < -0.10).mean() * 100, 1)))
    return pd.DataFrame(rows), pd.DataFrame(pr), (C, w, w_f)


# =============================================================== gelecekten-bilgi testi
def lookahead_test(D_full, n_cuts=3, seed=7):
    rng = np.random.default_rng(seed)
    idx = D_full["idx"]
    cuts = sorted(idx[rng.integers(len(idx) // 4, len(idx) - 500, n_cuts)])
    cfgs = [(["BTC"], dict(N=1, X=8.0, Xexit=EXIT_X, L=3, fee="taker", rebalance="saat")),
            (["ETH"], dict(N=1, X=-np.inf, Xexit=-np.inf, L=2, fee="maker", rebalance="yok")),
            (COINS, dict(N=2, X=5.0, Xexit=EXIT_X, L=3, fee="taker", rebalance="gun"))]
    full = [simulate(D_full, cs_, **kw)["eq"] for cs_, kw in cfgs]
    _, w_full, wf_full = riskoff_positions(D_full)[:3]
    ok = True
    for cut in cuts:
        Dc = build(COINS, end=cut)
        assert (Dc["idx"] == idx[:len(Dc["idx"])]).all()
        for (cs_, kw), ef in zip(cfgs, full):
            ec = simulate(Dc, cs_, **kw)["eq"]
            diff = np.nanmax(np.abs(ec - ef[:len(ec)]))
            log(f"  kesme {cut:%Y-%m-%d %H:%M} {'+'.join(cs_) if len(cs_) < 3 else '8coin'} {kw} fark={diff:.2e}")
            ok &= diff < 1e-12
        _, wc, wfc = riskoff_positions(Dc)[:3]
        dd = (wfc - wf_full.reindex(wfc.index)).abs().max().max()
        d0 = (wc - w_full.reindex(wc.index)).abs().max().max()
        # son gun kesimde eksik olabilir: tam gunleri karsilastir
        dd2 = (wfc.iloc[:-1] - wf_full.reindex(wfc.index[:-1])).abs().max().max()
        log(f"  kesme {cut:%Y-%m-%d %H:%M} riskoff pozisyon farki (son gun haric)={dd2:.2e} (son gun dahil={dd:.2e}, filtresiz={d0:.2e})")
        ok &= dd2 < 1e-12
    log("LOOKAHEAD TESTI:", "GECTI" if ok else "KALDI")
    return ok


# =============================================================== ana akis
BY = {}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--refresh", action="store_true")
    ap.add_argument("--test", action="store_true")
    a = ap.parse_args()
    D = build(COINS, refresh=a.refresh)
    log(f"panel: {D['idx'][0]} -> {D['idx'][-1]} ({len(D['idx'])} saat)")
    for c in COINS:
        bas = np.abs(D["F"][c] / D["S"][c] - 1)
        log(f"  {c}: baslangic {D['start'][c]:%Y-%m-%d}, eksik saat spot/perp={D['gaps'][c]}, "
            f"|perp/spot-1|>%2 saat={int(np.nansum(bas > 0.02))}, max={np.nanmax(bas) * 100:.1f}%")
    if a.test:
        lookahead_test(D)
        return
    tb = tbill(a.refresh)
    if tb is not None:
        log("T-bill (FRED DTB3) yillik ort %:", {y: round(v, 2) for y, v in tb.groupby(tb.index.year).mean().items() if y >= 2019})
    for c in COINS:
        b = bybit_funding(c, a.refresh)
        if b is not None:
            BY[c] = b
    # Vision vs REST fonlama capraz kontrol (BTC, eski cache varsa)
    old = ROOT / "cache" / "funding_BTCUSDT.csv"
    if old.exists():
        o = pd.read_csv(old, index_col=0, parse_dates=True)["rate"]
        v = D["fund_events"]["BTC"]
        j = o.index.round("s").intersection(v.index.round("s"))
        vv = v.copy()
        vv.index = vv.index.round("s")
        log(f"Vision vs REST fonlama (BTC, {len(j)} ortak olay): max fark {np.abs(o.reindex(j) - vv.reindex(j)).max():.2e}")
    for c in COINS:
        iv = D["iv"][c].dropna()
        non8 = iv[iv != 8]
        if len(non8):
            log(f"  fonlama araligi {c}: 8 saat disi {len(non8)} olay, {non8.index[0]:%Y-%m-%d} -> {non8.index[-1]:%Y-%m-%d}, degerler {sorted(non8.unique())}")
        else:
            log(f"  fonlama araligi {c}: hep 8 saat (Vision dosyalarinda)")

    ok = lookahead_test(D)
    G, LQ = run_grid(D, tb)
    FS = funding_stats(D)
    SEL = select(G)
    RO, PR, _ = riskoff(D)

    log("\n=== SECIM (yalniz <2025, taker, secimde tasfiye yok) ===")
    stress = []
    for _, s in SEL.iterrows():
        g = G[(G.coin == s.grup) & (G.kural == s.kural) & (G.L == s.L) & (G.rebalans == s.rebalans) & (G.ucret == "taker")]
        sv, hv = g[g.donem == "secim"].iloc[0], g[g.donem == "sinav"].iloc[0]
        log(f"{s.grup:6s} {s.secim:16s} {s.kural:14s} L={s.L} reb={s.rebalans:5s} ({s.secim_notu}) | secim yillik {sv['yillik_%']:6.2f}% "
            f"DD {sv['maxDD_%']:6.2f}% tbill/yil {sv['tbill_yillik_%']:5.2f}% | sinav net {hv['net_getiri_%']:6.2f}% yillik {hv['yillik_%']:6.2f}% "
            f"DD {hv['maxDD_%']:6.2f}% tasfiye {hv.tasfiye} tbill/yil {hv['tbill_yillik_%']:5.2f}%")
        log("    yil yil net %: " + ", ".join(f"{r.donem}:{r['net_getiri_%']:.2f}" for _, r in g.iterrows() if r.donem[:2] == "20"))
        # stres: tasfiye kontrolu son islem fiyatiyla (fitiller dahil)
        cs_ = COINS if s.grup == "8coin" else [s.grup]
        X, Xe = (float(s.kural[4:].split("_")[0]), EXIT_X) if s.kural.startswith("esik") else (-np.inf, -np.inf)
        N = int(s.kural.split("top")[1]) if "top" in s.kural else 1
        res = simulate(D, cs_, N=N, X=X, Xexit=Xe, L=int(s.L), fee="taker", rebalance=s.rebalans, liq_px="last")
        pr = periods_for(D, res, cs_, tb)
        stress.append(dict(tablo="stres_son_fiyat", grup=s.grup, secim=s.secim, kural=s.kural, L=s.L, rebalans=s.rebalans,
                           tasfiye_tum=pr["tum"]["tasfiye"], secim_yillik_pct=pr["secim"]["yillik_%"],
                           sinav_yillik_pct=pr["sinav"]["yillik_%"], tum_maxDD_pct=pr["tum"]["maxDD_%"]))
        log(f"    stres (son fiyat fitili ile tasfiye): tasfiye {pr['tum']['tasfiye']}, secim yillik {pr['secim']['yillik_%']:.2f}%, "
            f"sinav yillik {pr['sinav']['yillik_%']:.2f}%, maxDD {pr['tum']['maxDD_%']:.2f}%")
    log("\n=== tasfiyeler (grid toplam) ===")
    if len(LQ):
        log(LQ.groupby(["coin", "L", "rebalans"]).size().to_string())
    log("\n=== risk azaltma filtresi ===")
    log(RO.to_string())
    log(PR.to_string())

    SEL["tablo"] = "secim"
    LQ["tablo"] = "tasfiye"
    out = pd.concat([G, SEL, pd.DataFrame(stress), LQ, FS, RO, PR], ignore_index=True)
    OUT.mkdir(exist_ok=True)
    out.to_csv(OUT / "carry_sonuc.csv", index=False)
    (OUT / "carry_log.txt").write_text("\n".join(LOG) + "\n", encoding="utf-8")
    log("yazildi:", OUT / "carry_sonuc.csv", "satir", len(out), "| lookahead", "GECTI" if ok else "KALDI")


if __name__ == "__main__":
    main()
