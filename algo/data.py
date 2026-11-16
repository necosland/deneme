"""Veri katmani. Borsadan bagimsiz: baska kaynak eklemek icin ayni imzayi koru
(fetch_ohlcv -> index=UTC datetime, kolonlar open/high/low/close/volume)."""
import pathlib
import time

import pandas as pd
import requests

BASE = "https://data-api.binance.vision/api/v3/klines"  # sadece herkese acik veri, anahtar yok
CACHE = pathlib.Path(__file__).parent / "cache"
COLS = ["open_time", "open", "high", "low", "close", "volume", "close_time",
        "quote_vol", "trades", "tb_base", "tb_quote", "ignore"]


def fetch_ohlcv(symbol="BTCUSDT", interval="4h", start="2019-01-01", refresh=False):
    CACHE.mkdir(exist_ok=True)
    f = CACHE / f"{symbol}_{interval}.csv"
    if f.exists() and not refresh:
        return pd.read_csv(f, index_col=0, parse_dates=True)

    cur = int(pd.Timestamp(start, tz="UTC").timestamp() * 1000)
    now = int(time.time() * 1000)
    rows = []
    while cur < now:
        r = requests.get(BASE, params=dict(symbol=symbol, interval=interval,
                                           startTime=cur, limit=1000), timeout=30)
        r.raise_for_status()
        data = r.json()
        if not data:
            break
        rows += data
        cur = data[-1][0] + 1
        if len(data) < 1000:
            break
        time.sleep(0.2)

    df = pd.DataFrame(rows, columns=COLS)
    df["open_time"] = pd.to_datetime(df["open_time"], unit="ms", utc=True)
    df = df.set_index("open_time")[["open", "high", "low", "close", "volume"]].astype(float)
    df = df[~df.index.duplicated()].sort_index()
    df = df.iloc[:-1]  # son mum henuz kapanmamis olabilir
    df.to_csv(f)
    return df
