"""Point-in-time universe. Source: CoinMarketCap historical snapshots (first Sunday of each January),
read 2026-11-21 via web fetch. Rule: CMC top-20 by market cap, excluding stablecoins and wrapped tokens,
listed in rank order. A coin is tradable only while it has Binance USDT spot data (exchange-only tokens
like LEO/HT/CRO/OKB and BSV after 2019-04, XEM, TON before 2024-08 simply have no data).
Membership is active from the day AFTER the snapshot date until the day after the next snapshot."""
import pandas as pd

SNAP = {  # snapshot date: top-20 non-stable, non-wrapped, CMC rank order
    "2019-01-06": ["BTC", "ETH", "XRP", "BCH", "EOS", "LTC", "XLM", "BSV", "TRX", "ADA", "IOTA", "XMR", "BNB",
                   "DASH", "XEM", "ETC", "NEO", "MKR", "ZEC", "WAVES"],
    "2020-01-05": ["BTC", "ETH", "XRP", "BCH", "LTC", "EOS", "BNB", "BSV", "XMR", "XLM", "TRX", "ADA", "XTZ",
                   "LEO", "ATOM", "HT", "NEO", "999", "LINK", "ETC"],
    "2021-01-03": ["BTC", "ETH", "LTC", "XRP", "DOT", "BCH", "ADA", "BNB", "LINK", "BSV", "XLM", "EOS", "XMR",
                   "THETA", "TRX", "XEM", "VET", "XTZ", "CEL", "UNI"],
    "2022-01-02": ["BTC", "ETH", "BNB", "SOL", "ADA", "XRP", "LUNA", "DOT", "AVAX", "DOGE", "SHIB", "MATIC", "CRO",
                   "UNI", "ALGO", "LTC", "LINK", "NEAR", "BCH", "ATOM"],
    "2023-01-01": ["BTC", "ETH", "BNB", "XRP", "DOGE", "ADA", "MATIC", "LTC", "TRX", "DOT", "SHIB", "UNI", "SOL",
                   "AVAX", "LEO", "LINK", "TON", "XMR", "ATOM", "ETC"],
    "2024-01-07": ["BTC", "ETH", "BNB", "SOL", "XRP", "ADA", "AVAX", "DOGE", "TRX", "DOT", "MATIC", "TON", "LINK",
                   "SHIB", "ICP", "LTC", "BCH", "LEO", "ATOM", "UNI"],
    "2025-01-05": ["BTC", "ETH", "XRP", "SOL", "BNB", "DOGE", "ADA", "TRX", "AVAX", "SUI", "LINK", "TON", "SHIB",
                   "XLM", "DOT", "HBAR", "BCH", "UNI", "LTC", "PEPE"],
    "2026-01-04": ["BTC", "ETH", "XRP", "BNB", "SOL", "TRX", "DOGE", "ADA", "BCH", "LINK", "HYPE", "ZEC", "LEO",
                   "XMR", "XLM", "SUI", "LTC", "AVAX", "CC", "HBAR"],
}
# no Binance USDT spot market at any time (checked by download: empty) -> never tradable
NOT_ON_BINANCE = {"LEO", "HT", "999", "CRO", "CEL", "CC"}

# coin -> Binance spot symbol(s). List = concatenated in time order (ticker changes).
SPOT = {c: [c + "USDT"] for s in SNAP.values() for c in s}
SPOT.update({"BCH": ["BCHABCUSDT", "BCHUSDT"], "BSV": ["BCHSVUSDT"]})
for c in NOT_ON_BINANCE:
    SPOT.pop(c, None)
# coin -> USDT-M perp symbol (funding). None = never had one.
PERP = {c: s[-1] for c, s in SPOT.items()}
PERP.update({"SHIB": "1000SHIBUSDT", "PEPE": "1000PEPEUSDT", "BSV": None})


def membership(index):
    """bool DataFrame (time x coin): coin is in the point-in-time universe at bar t."""
    coins = sorted({c for s in SNAP.values() for c in s if c in SPOT})
    m = pd.DataFrame(False, index=index, columns=coins)
    dates = sorted(SNAP)
    for i, d in enumerate(dates):
        a = pd.Timestamp(d, tz="UTC") + pd.Timedelta(days=1)
        b = pd.Timestamp(dates[i + 1], tz="UTC") + pd.Timedelta(days=1) if i + 1 < len(dates) else index[-1] + pd.Timedelta(days=1)
        cols = [c for c in SNAP[d] if c in coins]
        m.loc[(index >= a) & (index < b), cols] = True
    return m
