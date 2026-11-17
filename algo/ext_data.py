"""Dis veri (anahtarsiz, herkese acik). Ulasilamazsa None doner; strateji o zaman atlanir.
- Korku/Acgozluluk endeksi: api.alternative.me/fng (gunluk, 2018-02'den)
- Binance vadeli fonlama orani: fapi.binance.com/fapi/v1/fundingRate (8 saatte bir, BTCUSDT 2019-09'dan)
Zaman damgasi: degerin YAYINLANDIGI an. Kullanan taraf ayrica gecikme ekler (lab_strategies2.asof)."""
import pathlib
import time

import pandas as pd
import requests

CACHE = pathlib.Path(__file__).parent / "cache"


def fear_greed(refresh=False):
    CACHE.mkdir(exist_ok=True)
    f = CACHE / "fng.csv"
    if f.exists() and not refresh:
        return pd.read_csv(f, index_col=0, parse_dates=True)["fng"]
    try:
        r = requests.get("https://api.alternative.me/fng/", params={"limit": 0, "format": "json"}, timeout=30)
        r.raise_for_status()
        d = pd.DataFrame(r.json()["data"])
    except Exception as e:  # noqa: BLE001
        print("FNG ulasilamadi:", e)
        return None
    s = pd.Series(d["value"].astype(float).to_numpy(),
                  index=pd.to_datetime(d["timestamp"].astype(int), unit="s", utc=True), name="fng").sort_index()
    s = s[~s.index.duplicated()]
    s.to_frame().to_csv(f)
    return s


def funding(symbol="BTCUSDT", refresh=False):
    CACHE.mkdir(exist_ok=True)
    f = CACHE / f"funding_{symbol}.csv"
    if f.exists() and not refresh:
        return pd.read_csv(f, index_col=0, parse_dates=True)["rate"]
    rows, cur = [], int(pd.Timestamp("2019-01-01", tz="UTC").timestamp() * 1000)
    now = int(time.time() * 1000)
    try:
        while cur < now:
            r = requests.get("https://fapi.binance.com/fapi/v1/fundingRate",
                             params={"symbol": symbol, "startTime": cur, "limit": 1000}, timeout=30)
            r.raise_for_status()
            data = r.json()
            if not data:
                break
            rows += data
            cur = data[-1]["fundingTime"] + 1
            if len(data) < 1000:
                break
            time.sleep(0.3)
    except Exception as e:  # noqa: BLE001
        print("Fonlama ulasilamadi:", e)
        return None
    d = pd.DataFrame(rows)
    s = pd.Series(d["fundingRate"].astype(float).to_numpy(),
                  index=pd.to_datetime(d["fundingTime"], unit="ms", utc=True), name="rate").sort_index()
    s = s[~s.index.duplicated()]
    s.to_frame().to_csv(f)
    return s


if __name__ == "__main__":
    a = fear_greed(refresh=True)
    print("fng", None if a is None else (len(a), a.index[0], a.index[-1]))
    b = funding(refresh=True)
    print("funding", None if b is None else (len(b), b.index[0], b.index[-1]))
