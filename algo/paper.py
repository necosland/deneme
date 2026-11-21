"""Paper trading (sahte para). Kullanim: python paper.py
Her calistirmada: son kapanmis mumlarla sinyal hesaplar, sinyal degistiyse o anki
canli fiyattan sahte alim/satim yapar, sonuclari algo/paper/ altina yazar.
Gercek emir YOK, API anahtari YOK; yalnizca Binance'in herkese acik fiyat verisi.

Her sistem: 6 coin, her coine ayri 1/6 sermaye (kova). Kovalar birbirini dengelemez.
"Golge" = ayni sinyallerin backtest muhasebesiyle (mum kapanisindan dolum, %0.15 maliyet)
sonucu. Paper ile golge arasindaki fark = gercek hayattaki gecikme + kayma.
Parametreler deneme suresince SABIT (turnuvalarin son walk-forward secimi).
cekirdek_v1 ayri bir portfoy sistemidir (kova yok): kurallar cekirdek/paper_spec.md, ileri test cekirdek/ileri_plan.md.
Deneme calistirmasi (hicbir dosya yazilmaz): python paper.py --dry [--dir baska/paper]
"""
import argparse
import copy
import datetime as dt
import json
import pathlib
import sys
import time

import numpy as np
import pandas as pd
import requests

from lab_strategies import donchian, ema, sma

KLINES = "https://data-api.binance.vision/api/v3/klines"
TICKER = "https://data-api.binance.vision/api/v3/ticker/price"
COINS = ["BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT", "XRPUSDT", "ADAUSDT"]
DIR = pathlib.Path(__file__).parent / "paper"
CAPITAL = 1000.0          # sistem basina sahte USDT
FEE = 0.001               # paper dolumunda borsa komisyonu (kayma gercek fiyattan gelir)
SHADOW_COST = 0.0015      # golge backtest: komisyon + varsayilan kayma
IV = {"4h": pd.Timedelta(hours=4), "1d": pd.Timedelta(days=1)}
FETCH_BARS = {"4h": 900, "1d": 450}


# ---------------- sistemler (pozisyon 0/1, t kapanisinda bilinen veriyle) ----------------
def sys_donchian(dfs, coin):
    return donchian(dfs[coin], None, entry=100, exit=10)


def sys_btc_filter_ema(dfs, coin):
    def up(df):
        c = df["close"]
        return (ema(c, 10) > ema(c, 100)).astype(float)
    return up(dfs[coin]) * up(dfs["BTCUSDT"]).reindex(dfs[coin].index).fillna(0.0)


def sys_ema_btcf(dfs, coin):
    c, b = dfs[coin]["close"], dfs["BTCUSDT"]["close"]
    gate = (b > sma(b, 200)).astype(float).reindex(c.index).fillna(0.0)
    return (ema(c, 3) > ema(c, 17)).astype(float) * gate


# ad: (fonksiyon, mum, aciklama, referans backtest maxDD %)
SYSTEMS = {
    "donchian_4h": (sys_donchian, "4h", "100 mum zirvesi kirilinca al, 10 mum dibi kirilinca sat", -18.6),
    "btc_filter_ema_4h": (sys_btc_filter_ema, "4h", "EMA10>EMA100 hem coinde hem BTC'de", -48.9),
    "ema_btcf_1d": (sys_ema_btcf, "1d", "EMA3>EMA17 gunluk, BTC 200 gun ortalamasinin ustundeyken", -44.8),
}
KILL_MULT = 1.5   # paper dususu referans maxDD x 1.5'i asarsa: strateji olu sayilir
DRY = False       # --dry: hesapla ve yazdir, state/csv/DURUM yazma

# ---------------- cekirdek_v1: Faz 1 dondurulmus secim (cekirdek/secim.json), spot, portfoy ----------------
sys.path.insert(0, str(pathlib.Path(__file__).parent / "cekirdek"))
import motor as CM  # noqa: E402  dondurulmus motor: ayni sinyal, esit agirlik, %50 tavan, bant kodu

CEK = "cekirdek_v1"
CEK_DESC = ("btc_filter_ema_4h portfoy: coinde ve BTC'de EMA10>EMA100 (4s) ise long, yalniz spot; uygun coin basina 1/N; "
            "portfoy oynakligi %50/yil ustundeyse tum defter kucultulur; evren CMC ilk 20 (Binance spot USDT). Kanitsiz aday")
CEK_REF_DD = -31.0   # holdout 2024-01-01..2026-11-20 spot maxDD (-30.96%); olum siniri KILL_MULT x bu
# CMC tarihsel anlik goruntu tarihi -> ilk 20 (stablecoin, sarili/LST haric) icinden Binance spot USDT'de islenenler,
# CMC sirasiyla. Tarih+1 gunden itibaren gecerli. Yenileme: her ocak ilk pazar goruntusu eklenir (paper_spec.md).
CEK_UNIVERSE = {
    "2026-11-15": ["BTC", "ETH", "BNB", "XRP", "SOL", "TRX", "HYPE", "ZEC", "DOGE", "LINK", "ADA", "XLM", "BCH",
                   "NEAR", "LTC", "AVAX", "UNI"],   # disarida: LEO, CC (Binance'te yok), XMR (Binance spot kapali)
}


# ---------------- veri ----------------
def get(url, params):
    for k in range(4):
        try:
            r = requests.get(url, params=params, timeout=30)
            r.raise_for_status()
            return r.json()
        except requests.RequestException:
            if k == 3:
                raise
            time.sleep(3 * (k + 1))


def klines(symbol, iv, now, n=None):
    data = get(KLINES, dict(symbol=symbol, interval=iv, limit=1000))[-(n or FETCH_BARS[iv]):]
    df = pd.DataFrame([r[:6] for r in data], columns=["t", "open", "high", "low", "close", "volume"])
    df.index = pd.to_datetime(df.pop("t"), unit="ms", utc=True)
    df = df.astype(float)
    return df[df.index + IV[iv] <= now]   # yalniz kapanmis mumlar


def prices(symbols):
    data = get(TICKER, dict(symbols=json.dumps(symbols, separators=(",", ":"))))
    return {d["symbol"]: float(d["price"]) for d in data}


# ---------------- kayit ----------------
def append_csv(path, row):
    if DRY:
        return
    df = pd.DataFrame([row])
    df.to_csv(path, mode="a", header=not path.exists(), index=False)


def iso(t):
    return pd.Timestamp(t).strftime("%Y-%m-%d %H:%M")


# ---------------- ana akis ----------------
def main():
    if not DRY:
        DIR.mkdir(exist_ok=True)
    now = pd.Timestamp.now(tz="UTC")
    state_f = DIR / "state.json"
    state = json.loads(state_f.read_text()) if state_f.exists() else {"systems": {}}
    data = {iv: {c: klines(c, iv, now) for c in COINS} for iv in IV}
    px = prices(COINS)
    trades_f, eq_f = DIR / "islemler.csv", DIR / "ozsermaye.csv"
    status = []

    for name, (fn, iv, desc, ref_dd) in SYSTEMS.items():
        dfs = data[iv]
        pos = {c: fn(dfs, c) for c in COINS}
        last_bar = min(dfs[c].index[-1] for c in COINS)
        if now - last_bar > IV[iv] * 3:
            raise RuntimeError(f"{name}: veri bayat, son mum {last_bar}")

        st = state["systems"].get(name)
        if st is None:  # ilk calistirma: sermaye kovalara bolunur
            st = {
                "baslangic": iso(now), "son_mum": iso(last_bar), "tepe": CAPITAL,
                "baslangic_fiyat": {c: px[c] for c in COINS},
                "kova": {c: {"nakit": CAPITAL / len(COINS), "adet": 0.0} for c in COINS},
                "golge": {c: {"deger": CAPITAL / len(COINS), "poz": 0.0} for c in COINS},
            }
            state["systems"][name] = st
            new_bars = [last_bar]
        else:
            prev = pd.Timestamp(st["son_mum"], tz="UTC")
            new_bars = [t for t in dfs["BTCUSDT"].index if prev < t <= last_bar]

        # golge backtest: her yeni mum icin backtest muhasebesi
        for c in COINS:
            g, close, p = st["golge"][c], dfs[c]["close"], pos[c]
            for t in new_bars:
                if t not in close.index:
                    continue
                i = close.index.get_loc(t)
                if g["poz"] and i > 0 and pd.Timestamp(st["son_mum"], tz="UTC") < t:
                    g["deger"] *= 1 + g["poz"] * (close.iloc[i] / close.iloc[i - 1] - 1)
                newp = float(p.loc[t])
                g["deger"] *= 1 - abs(newp - g["poz"]) * SHADOW_COST
                g["poz"] = newp

        # paper: son kapanmis mumun sinyaline gore canli fiyattan dolum
        for c in COINS:
            k, target = st["kova"][c], float(pos[c].loc[last_bar]) if last_bar in pos[c].index else 0.0
            held = k["adet"] > 0
            bar_close = float(dfs[c]["close"].iloc[-1])
            fill = px[c]
            if target > 0 and not held:
                k["adet"] = k["nakit"] * (1 - FEE) / fill
                tutar, k["nakit"], yon = k["nakit"], 0.0, "AL"
                slip = fill / bar_close - 1
            elif target == 0 and held:
                tutar = k["adet"] * fill * (1 - FEE)
                k["nakit"], k["adet"], yon = tutar, 0.0, "SAT"
                slip = bar_close / fill - 1
            else:
                continue
            append_csv(trades_f, {
                "zaman_utc": iso(now), "sistem": name, "coin": c.replace("USDT", ""), "yon": yon,
                "sinyal_mumu_utc": iso(dfs[c].index[-1]), "mum_kapanis": bar_close, "dolum": fill,
                "kayma_%": round(slip * 100, 3), "tutar_usdt": round(tutar, 2),
            })

        paper = sum(k["nakit"] + k["adet"] * px[c] for c, k in st["kova"].items())
        golge = sum(g["deger"] for g in st["golge"].values())
        bh = CAPITAL * np.mean([px[c] / st["baslangic_fiyat"][c] for c in COINS])
        bh_btc = CAPITAL * px["BTCUSDT"] / st["baslangic_fiyat"]["BTCUSDT"]
        st["tepe"] = max(st["tepe"], paper)
        dd = (paper / st["tepe"] - 1) * 100
        st["son_mum"] = iso(last_bar)
        open_pos = [c.replace("USDT", "") for c, k in st["kova"].items() if k["adet"] > 0]
        dead = dd < KILL_MULT * ref_dd
        append_csv(eq_f, {
            "zaman_utc": iso(now), "sistem": name, "paper": round(paper, 2), "golge": round(golge, 2),
            "al_tut_6coin": round(bh, 2), "al_tut_btc": round(bh_btc, 2),
            "dusus_%": round(dd, 2), "acik": " ".join(open_pos) or "-",
        })
        status.append((name, desc, st, paper, golge, bh, bh_btc, dd, ref_dd, open_pos, dead))

    errors = []
    try:  # cekirdek_v1 hatasi digerlerini durdurmaz; durumu DURUM.md'de gorunur
        status.append(cekirdek(state, now, trades_f, eq_f))
    except Exception as e:  # noqa: BLE001
        errors.append(f"{CEK}: {type(e).__name__}: {e}")
        print("HATA", errors[-1])

    if not DRY:
        state_f.write_text(json.dumps(state, indent=1, ensure_ascii=False))
        write_status(now, status, errors)
    for s in status:
        print(f"{s[0]:20s} paper={s[3]:8.2f} golge={s[4]:8.2f} al_tut6={s[5]:8.2f} al_tut_btc={s[6]:8.2f} "
              f"dd={s[7]:6.2f}% acik={s[9]}")


# ---------------- cekirdek_v1 ----------------
def cek_membership(index, cols, universe):
    """Zaman x coin: coin o mumda evrende mi. Ilk goruntu pencerenin basindan, sonrakiler tarih+1 gunden gecerli."""
    m = pd.DataFrame(False, index=index, columns=cols)
    dates = sorted(universe)
    for i, d in enumerate(dates):
        a = pd.Timestamp(d, tz="UTC") + pd.Timedelta(days=1) if i else index[0]
        b = pd.Timestamp(dates[i + 1], tz="UTC") + pd.Timedelta(days=1) if i + 1 < len(dates) \
            else index[-1] + pd.Timedelta(days=1)
        m.loc[(index >= a) & (index < b), [c for c in universe[d] if c in cols]] = True
    return m


def cek_panel(frames, iv):
    """motor.load ile ayni panel: coin sutunlari, <= 1 gunluk delikler son kapanisla duz mum."""
    P = {f: pd.DataFrame({c: d[f] for c, d in frames.items() if len(d)}).sort_index()
         for f in ("open", "high", "low", "close")}
    lim = 1 if iv == "1d" else 6
    c0 = P["close"]
    alive = c0.ffill().notna() & c0.bfill().notna()
    cf = c0.ffill(limit=lim).where(alive)
    hole = c0.isna() & cf.notna()
    for f in ("open", "high", "low"):
        P[f] = P[f].mask(hole, cf)
    P["close"] = cf
    P["perp_live"] = pd.DataFrame(False, index=cf.index, columns=cf.columns)   # yalniz long: kisa yok
    return P


def cek_weights(P4, Pd, universe):
    """Hedef agirliklar (zaman x coin), motor.eligibility + motor.weights ile ayni kural."""
    c = P4["close"]
    avail = c.notna()
    el = (avail & (avail.cumsum() > CM.WARMUP_DAYS * CM.BPD["4h"]) & avail.shift(-1, fill_value=True)
          & cek_membership(c.index, c.columns, universe))
    return CM.weights(P4, "4h", CM.sig_btc_filter_ema(P4, False), el, "ew", True, Pd)


def cek_band(h, tgt):
    """motor.simulate bant kurali: isaret degisirse ya da fark hedefin %25'ini asarsa yeniden boyutla."""
    trade = (np.sign(tgt) != np.sign(h)) | (np.abs(tgt - h) > CM.BAND * np.abs(tgt))
    new = np.where(trade, tgt, h)
    if np.abs(new).sum() > 1.0 + 1e-9 or np.abs(new).sum() > 1.10 * np.abs(tgt).sum() + 1e-12:
        new = tgt
    return new


def cek_shadow(g, W, r, new_bars, first):
    """Golge: backtest muhasebesi (mum kapanisindan dolum, %0.15/yon, fonlama yok), motor.simulate adimi."""
    cols = list(W.columns)
    h = np.array([g["h"].get(c, 0.0) for c in cols])
    for k, t in enumerate(new_bars):
        R = 0.0
        if not (first and k == 0):
            rt = r.loc[t, cols].to_numpy()
            R = float(h @ rt)
            h = h * (1 + rt) / (1 + R) if 1 + R > 0 else np.zeros(len(cols))
        new = cek_band(h, W.loc[t, cols].to_numpy())
        g["deger"] *= 1 + R - np.abs(new - h).sum() * CM.SPOT_COST
        h = new
    g["h"] = {c: float(v) for c, v in zip(cols, h) if v != 0}


def cekirdek(state, now, trades_f, eq_f, universe=CEK_UNIVERSE):
    st0 = state["systems"].get(CEK)
    st = copy.deepcopy(st0)
    held = list(st["adet"]) + list(st["golge"]["h"]) if st else []
    snap = max(d for d in universe if pd.Timestamp(d, tz="UTC") + pd.Timedelta(days=1) <= now)
    coins = list(dict.fromkeys(universe[snap] + held + [c.replace("USDT", "") for c in COINS]))
    P4 = cek_panel({c: klines(c + "USDT", "4h", now, 1000) for c in coins}, "4h")
    Pd = cek_panel({c: klines(c + "USDT", "1d", now, 200) for c in coins}, "1d")
    last_bar = P4["close"]["BTC"].dropna().index[-1]
    if now - last_bar > IV["4h"] * 3:
        raise RuntimeError(f"veri bayat, son mum {last_bar}")
    W = cek_weights(P4, Pd, universe)
    cols = list(W.columns)
    closes = P4["close"].ffill().loc[last_bar]
    fresh = [c for c in cols if pd.notna(P4["close"].loc[last_bar, c])]
    live = prices([c + "USDT" for c in fresh])
    px = {c: live.get(c + "USDT", float(closes[c])) for c in cols}   # bayat coin: son kapanis

    first = st is None
    if first:
        st = {"baslangic": iso(now), "son_mum": iso(last_bar), "tepe": CAPITAL, "evren": snap,
              "baslangic_fiyat": {c: px[c.replace("USDT", "")] for c in COINS},
              "nakit": CAPITAL, "adet": {}, "golge": {"deger": CAPITAL, "h": {}}}
        new_bars = [last_bar]
    else:
        prev = pd.Timestamp(st["son_mum"], tz="UTC")
        new_bars = [t for t in P4["close"].index if prev < t <= last_bar]
    cek_shadow(st["golge"], W, P4["close"].pct_change(fill_method=None).fillna(0.0), new_bars, first)

    # paper: son kapanmis mumun hedef agirligi, canli fiyattan dolum, ayni bant kurali
    rows = []
    if new_bars:
        p = np.array([px[c] for c in cols])
        units = np.array([st["adet"].get(c, 0.0) for c in cols])
        V = st["nakit"] + float(units @ p)
        hp = units * p / V
        new = cek_band(hp, W.loc[last_bar, cols].to_numpy())
        want = np.where(new != hp, new * V / p, units)
        want = np.where(new == 0, 0.0, want)

        def log(i, yon, qty):
            bc = float(closes[cols[i]])
            rows.append({"zaman_utc": iso(now), "sistem": CEK, "coin": cols[i], "yon": yon,
                         "sinyal_mumu_utc": iso(last_bar), "mum_kapanis": bc, "dolum": p[i],
                         "kayma_%": round(((p[i] / bc - 1) if yon == "AL" else (bc / p[i] - 1)) * 100, 3),
                         "tutar_usdt": round(qty * p[i], 2)})
        for i in np.where(want < units)[0]:              # once satislar
            q = units[i] - want[i]
            st["nakit"] += q * p[i] * (1 - FEE)
            units[i] = want[i]
            log(i, "SAT", q)
        buy = np.clip(want - units, 0, None)
        need = float((buy * p).sum()) * (1 + FEE)
        if need > 0:
            buy *= min(1.0, st["nakit"] / need)            # ucret yuzunden nakit yetmezse orantili kucult
            for i in np.where(buy > 0)[0]:
                st["nakit"] -= buy[i] * p[i] * (1 + FEE)
                units[i] += buy[i]
                log(i, "AL", buy[i])
        st["nakit"] = max(st["nakit"], 0.0)
        st["adet"] = {c: float(u) for c, u in zip(cols, units) if u > 0}
        st["son_mum"] = iso(last_bar)

    paper = st["nakit"] + sum(u * px[c] for c, u in st["adet"].items())
    golge = st["golge"]["deger"]
    bh = CAPITAL * np.mean([px[c.replace("USDT", "")] / st["baslangic_fiyat"][c] for c in COINS])
    bh_btc = CAPITAL * px["BTC"] / st["baslangic_fiyat"]["BTCUSDT"]
    st["tepe"] = max(st["tepe"], paper)
    dd = (paper / st["tepe"] - 1) * 100
    wts = {c: u * px[c] / paper for c, u in st["adet"].items()}
    open_pos = [f"{c}:{w * 100:.0f}%" for c, w in sorted(wts.items(), key=lambda x: -x[1])]
    dead = dd < KILL_MULT * CEK_REF_DD

    tw = W.loc[last_bar]
    print(f"{CEK} son mum {iso(last_bar)} evren {snap} long coin {int((tw != 0).sum())} hedef:",
          {c: round(float(v), 4) for c, v in tw[tw != 0].items()} or "hepsi nakit")
    for row in rows:
        print("  islem", row)
    for row in rows:
        append_csv(trades_f, row)
    append_csv(eq_f, {
        "zaman_utc": iso(now), "sistem": CEK, "paper": round(paper, 2), "golge": round(golge, 2),
        "al_tut_6coin": round(bh, 2), "al_tut_btc": round(bh_btc, 2),
        "dusus_%": round(dd, 2), "acik": " ".join(open_pos) or "-",
    })
    state["systems"][CEK] = st
    return (CEK, CEK_DESC, st, paper, golge, bh, bh_btc, dd, CEK_REF_DD, open_pos, dead)


def write_status(now, status, errors=()):
    L = [f"# Paper trading durumu", "",
         f"Son guncelleme: {iso(now)} UTC. Her sistem {CAPITAL:.0f} sahte USDT ile basladi. Gercek para yok.", "",
         "| Sistem | Basladi | Paper | Golge (backtest) | Al-tut 6 coin | Al-tut BTC | Tepeden dusus | Olum siniri | Acik pozisyon |",
         "|---|---|---|---|---|---|---|---|---|"]
    for name, desc, st, paper, golge, bh, bh_btc, dd, ref_dd, open_pos, dead in status:
        flag = " **OLDU**" if dead else ""
        L.append(f"| {name} | {st['baslangic'][:10]} | {paper:.0f} | {golge:.0f} | {bh:.0f} | {bh_btc:.0f} | %{dd:.1f}{flag} | "
                 f"%{KILL_MULT * ref_dd:.0f} | {' '.join(open_pos) or '-'} |")
    if errors:
        L += [""] + [f"- **HATA** {e}" for e in errors]
    L += ["", "Sistemler:"] + [f"- **{s[0]}**: {s[1]}" for s in status]
    L += ["", "Paper ile golge arasindaki fark gercek hayattaki gecikme ve kaymayi gosterir. "
          "Islemler: `islemler.csv`, zaman serisi: `ozsermaye.csv`."]
    (DIR / "DURUM.md").write_text("\n".join(L) + "\n", encoding="utf-8")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry", action="store_true", help="hesapla, hicbir dosya yazma")
    ap.add_argument("--dir", help="state/csv klasoru (varsayilan algo/paper)")
    a = ap.parse_args()
    DRY = a.dry
    if a.dir:
        DIR = pathlib.Path(a.dir)
    main()
