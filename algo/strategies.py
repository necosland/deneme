"""Stratejiler: mum KAPANISINDA bilinen bilgiyle 0/1 pozisyon uretir (long-only, spot)."""
import numpy as np
import pandas as pd


def donchian(df, entry=55, exit=20):
    """Trend takibi: entry mumluk zirveyi yukari kirinca al, exit mumluk dibi kirinca sat."""
    hh = df["high"].rolling(entry).max().shift(1).to_numpy()
    ll = df["low"].rolling(exit).min().shift(1).to_numpy()
    c = df["close"].to_numpy()
    pos = np.zeros(len(df))
    p = 0.0
    for i in range(len(df)):
        if p == 0.0 and c[i] > hh[i]:
            p = 1.0
        elif p == 1.0 and c[i] < ll[i]:
            p = 0.0
        pos[i] = p
    return pd.Series(pos, index=df.index)


def ema_cross(df, fast=20, slow=100):
    f = df["close"].ewm(span=fast, adjust=False).mean()
    s = df["close"].ewm(span=slow, adjust=False).mean()
    pos = (f > s).astype(float)
    pos.iloc[:slow] = 0.0  # isinma donemi
    return pos


STRATEGIES = {
    "donchian": (donchian, {"entry": [20, 40, 60, 80, 100], "exit": [10, 20, 30, 40]}),
    "ema_cross": (ema_cross, {"fast": [10, 20, 30, 50], "slow": [60, 100, 150, 200]}),
}
