"""Test verisi: yfinance (FX/emtia/endeks) + Binance (BTC) gunluk OHLC -> ham/<tk>.csv. Yalniz bu test icin."""
import pathlib, sys, time
import pandas as pd, requests, yfinance as yf

HAM = pathlib.Path(__file__).parent / "ham"
HAM.mkdir(exist_ok=True)
YF = ["EURUSD=X", "EURGBP=X", "GC=F", "CL=F", "GBPUSD=X", "AUDUSD=X", "SI=F", "^GDAXI", "AUDNZD=X", "^NDX",
      "ZAR=X", "DX-Y.NYB", "CAD=X"]


def binance(sym="BTCUSDT"):
    out, start = [], 1502928000000
    while True:
        r = requests.get("https://data-api.binance.vision/api/v3/klines",
                         params=dict(symbol=sym, interval="1d", startTime=start, limit=1000), timeout=30).json()
        if not r:
            break
        out += r
        start = r[-1][0] + 86400000
        if len(r) < 1000 or start > 1577836800000:
            break
    df = pd.DataFrame([[x[0], *map(float, x[1:5])] for x in out], columns=["t", "open", "high", "low", "close"])
    df.index = pd.to_datetime(df.pop("t"), unit="ms").dt.normalize()
    return df


if __name__ == "__main__":
    for tk in YF:
        df = yf.download(tk, start="2003-01-01", end="2021-12-31", interval="1d", auto_adjust=False, progress=False)
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        df = df.rename(columns=str.lower)[["open", "high", "low", "close"]].dropna()
        df.index = pd.to_datetime(df.index).tz_localize(None)
        df.to_csv(HAM / f"{tk.replace('^', '').replace('=', '_')}.csv")
        print(tk, len(df), df.index[0].date(), df.index[-1].date())
        time.sleep(0.5)
    b = binance()
    b.to_csv(HAM / "BTCUSDT.csv")
    print("BTCUSDT", len(b), b.index[0].date(), b.index[-1].date())
