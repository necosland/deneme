"""Paper trading (sahte para). Kullanim: python paper.py
Her calistirmada: son kapanmis mumlarla sinyal hesaplar, sinyal degistiyse o anki
canli fiyattan sahte alim/satim yapar, sonuclari algo/paper/ altina yazar.
Gercek emir YOK, API anahtari YOK; yalnizca Binance'in herkese acik fiyat verisi.

Her sistem: 6 coin, her coine ayri 1/6 sermaye (kova). Kovalar birbirini dengelemez.
"Golge" = ayni sinyallerin backtest muhasebesiyle (mum kapanisindan dolum, %0.15 maliyet)
sonucu. Paper ile golge arasindaki fark = gercek hayattaki gecikme + kayma.
Parametreler deneme suresince SABIT (turnuvalarin son walk-forward secimi).
"""
import datetime as dt
import json
import pathlib
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


def klines(symbol, iv, now):
    data = get(KLINES, dict(symbol=symbol, interval=iv, limit=1000))[-FETCH_BARS[iv]:]
    df = pd.DataFrame([r[:6] for r in data], columns=["t", "open", "high", "low", "close", "volume"])
    df.index = pd.to_datetime(df.pop("t"), unit="ms", utc=True)
    df = df.astype(float)
    return df[df.index + IV[iv] <= now]   # yalniz kapanmis mumlar


def prices(symbols):
    data = get(TICKER, dict(symbols=json.dumps(symbols, separators=(",", ":"))))
    return {d["symbol"]: float(d["price"]) for d in data}


# ---------------- kayit ----------------
def append_csv(path, row):
    df = pd.DataFrame([row])
    df.to_csv(path, mode="a", header=not path.exists(), index=False)


def iso(t):
    return pd.Timestamp(t).strftime("%Y-%m-%d %H:%M")


# ---------------- ana akis ----------------
def main():
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
        st["tepe"] = max(st["tepe"], paper)
        dd = (paper / st["tepe"] - 1) * 100
        st["son_mum"] = iso(last_bar)
        open_pos = [c.replace("USDT", "") for c, k in st["kova"].items() if k["adet"] > 0]
        dead = dd < KILL_MULT * ref_dd
        append_csv(eq_f, {
            "zaman_utc": iso(now), "sistem": name, "paper": round(paper, 2), "golge": round(golge, 2),
            "al_tut": round(bh, 2), "dusus_%": round(dd, 2), "acik": " ".join(open_pos) or "-",
        })
        status.append((name, desc, st, paper, golge, bh, dd, ref_dd, open_pos, dead))

    state_f.write_text(json.dumps(state, indent=1, ensure_ascii=False))
    write_status(now, status)
    for s in status:
        print(f"{s[0]:20s} paper={s[3]:8.2f} golge={s[4]:8.2f} al_tut={s[5]:8.2f} dd={s[6]:6.2f}% acik={s[8]}")


def write_status(now, status):
    L = [f"# Paper trading durumu", "",
         f"Son guncelleme: {iso(now)} UTC. Her sistem {CAPITAL:.0f} sahte USDT ile basladi. Gercek para yok.", "",
         "| Sistem | Basladi | Paper | Golge (backtest) | Al-tut | Tepeden dusus | Olum siniri | Acik pozisyon |",
         "|---|---|---|---|---|---|---|---|"]
    for name, desc, st, paper, golge, bh, dd, ref_dd, open_pos, dead in status:
        flag = " **OLDU**" if dead else ""
        L.append(f"| {name} | {st['baslangic'][:10]} | {paper:.0f} | {golge:.0f} | {bh:.0f} | %{dd:.1f}{flag} | "
                 f"%{KILL_MULT * ref_dd:.0f} | {' '.join(open_pos) or '-'} |")
    L += ["", "Sistemler:"] + [f"- **{s[0]}**: {s[1]}" for s in status]
    L += ["", "Paper ile golge arasindaki fark gercek hayattaki gecikme ve kaymayi gosterir. "
          "Islemler: `islemler.csv`, zaman serisi: `ozsermaye.csv`."]
    (DIR / "DURUM.md").write_text("\n".join(L) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
