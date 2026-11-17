"""Vektorel backtest. Kural: t kapanisinda verilen sinyal, t+1 mumunun getirisini kazanir.
Her pozisyon degisiminde komisyon + slippage kesilir."""
import numpy as np
import pandas as pd

BARS_PER_DAY = {"1h": 24, "4h": 6, "1d": 1}
PER_YEAR = 6 * 365  # varsayilan: 4 saatlik mum


def per_year(interval):
    return BARS_PER_DAY[interval] * 365
FEE = 0.001         # taraf basi %0.1 (borsana gore degistir)
SLIP = 0.0005       # taraf basi %0.05 slippage varsayimi


def run(df, pos, fee=FEE, slip=SLIP):
    held = pos.reindex(df.index).fillna(0.0).shift(1).fillna(0.0)
    ret = df["close"].pct_change().fillna(0.0)
    turnover = held.diff().abs().fillna(held.abs())
    return held * ret - turnover * (fee + slip), held


def metrics(r, held=None, periods=PER_YEAR):
    r = r.dropna()
    if len(r) < 2:
        return {}
    eq = (1 + r).cumprod()
    years = len(r) / periods
    sd = r.std()
    out = {
        "getiri_%": round((eq.iloc[-1] - 1) * 100, 1),
        "yillik_%": round((eq.iloc[-1] ** (1 / years) - 1) * 100, 1) if years > 0 else np.nan,
        "sharpe": round(r.mean() / sd * np.sqrt(periods), 2) if sd > 0 else 0.0,
        "maxDD_%": round((eq / eq.cummax() - 1).min() * 100, 1),
    }
    if held is not None:
        h = held.reindex(r.index).fillna(0.0)
        out["islem"] = int((h.diff().fillna(h) > 0).sum())
        out["piyasada_%"] = round(h.mean() * 100, 1)
    return out
