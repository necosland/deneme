"""Tum semboller ve araliklar icin veriyi indirip cache'e yazar."""
from data import fetch_ohlcv

SYMS = ["BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT", "XRPUSDT", "ADAUSDT",
        "LINKUSDT", "AVAXUSDT", "DOGEUSDT", "LTCUSDT"]
for iv in ["4h", "1d"]:
    for s in SYMS:
        df = fetch_ohlcv(s, iv)
        print(s, iv, len(df), df.index[0].date(), df.index[-1].date(), flush=True)
