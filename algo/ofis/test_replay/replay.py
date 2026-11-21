"""Replay test of the trader office on history after the expert model's knowledge cutoff (pre-registration: plan.md).
Paper only, no keys. Never touches the live ledger (defter/), live veri/ or log/: office modules are imported with
their paths redirected to test_replay/_sandbox and the clock patched to the replay time.

  python replay.py slots                      # rounds.json: 45 slots, run order, regime label
  python replay.py run --n 2 --cap 40         # next n rounds in run order (resumable; time gate xx:10-xx:35 TR)
  python replay.py score                      # sonuc.json (no LLM)
"""
import argparse
import concurrent.futures as cf
import copy
import datetime as dt
import io
import json
import math
import os
import pathlib
import re
import subprocess
import sys
import time
import zipfile

import numpy as np
import pandas as pd
import requests

HERE = pathlib.Path(__file__).resolve().parent
OFIS = HERE.parent
sys.path.insert(0, str(OFIS))
import ortak as O  # noqa: E402

# ---- sandbox: office modules must not write to live folders ----
SB = HERE / "_sandbox"
O.DEFTER, O.LOG, O.VERI, O.GRAFIK = SB / "defter", SB / "log", SB / "veri", SB / "grafik"
FROZEN = json.loads((HERE / "ayar_frozen.json").read_text(encoding="utf-8"))
O.ayar = lambda: copy.deepcopy(FROZEN)
SIM_NOW = [None]
_REAL_NOW = O.now_utc
O.now_utc = lambda: SIM_NOW[0] or _REAL_NOW()
import defter as D  # noqa: E402
D.STATE = O.DEFTER / "state.json"
D.event = lambda *a, **k: None
D.backup_state = lambda *a, **k: None
_CANCEL = D.cancel


def _cancel(st, t, why):   # time expiry: stamp the expiry time, not the wall clock (cosmetic, csv only)
    _CANCEL(st, t, why)
    if why.startswith("expired (time)"):
        t["exit_utc"] = O.fmt(O.from_ms(t["expires_ms"]))


D.cancel = _cancel
import veri_topla as V  # noqa: E402
sys.modules.setdefault("veri_topla", V)
import veri_ek as X  # noqa: E402
import tur as T  # noqa: E402

ASSETS = ["BTCUSDT", "ETHUSDT"]
SHIFT = dt.timedelta(days=1820)          # 260 weeks: weekday and hour kept
WIN0 = pd.Timestamp("2026-07-01 00:00", tz="UTC")
NSLOT = 45
ROUNDS, RAW, SNAPS, CACHE = HERE / "rounds", HERE / "raw", HERE / "snaps", HERE / "cache"
LOGF = HERE / "calisma.json"
NOWIN = getattr(subprocess, "CREATE_NO_WINDOW", 0)
UA = {"User-Agent": "Mozilla/5.0 (paper-trading research script)"}
INFRA = ("session limit", "usage limit", "rate limit", "overloaded", "credit balance")
T_EXPERT, T_RISK = 420, 300
EXPERTS = [e["id"] for e in FROZEN["experts"] if e["enabled"]]
HEADER = ("REPLAY TEST (paper research): this is a past market moment. All dates are shifted by a whole number of "
          "weeks (weekday and hour kept); prices and symbols are real. Use only the files given, not any memory of "
          "market history. Data that cannot be rebuilt for a past moment is absent (order book, our recorded "
          "liquidations/depth, options, Bybit, quarterly basis, crypto_global, gundem, headline check): write "
          "'replay: live-only data absent' once in data_gaps instead of listing each.")
# pilot R22: the data_gaps sentence made Riza answer in the expert-block shape (schema fail) -> own header
HEADER_RISK = ("REPLAY TEST (paper research): this is a past market moment. All dates are shifted by a whole number "
               "of weeks (weekday and hour kept); prices and symbols are real. Use only the files given, not any "
               "memory of market history. Answer in your usual decision schema (decision, asof_utc = SNAPSHOT "
               "asof_utc, ...), exactly as in a live round.")


def say(*a):
    print(time.strftime("%H:%M:%S"), *a, flush=True)


# ---------------- dates ----------------
DATE_RE = re.compile(r"(?<!\d)(20\d\d)-(\d\d)-(\d\d)(?: (\d\d):(\d\d))?(?!\d)")


def shift_text(t, sign=1):
    def f(m):
        if m.group(4):
            d = dt.datetime(int(m[1]), int(m[2]), int(m[3]), int(m[4]), int(m[5])) + sign * SHIFT
            return d.strftime("%Y-%m-%d %H:%M")
        return (dt.date(int(m[1]), int(m[2]), int(m[3])) + sign * SHIFT).strftime("%Y-%m-%d")
    return DATE_RE.sub(f, t)


def shift_obj(o, sign=1):
    return json.loads(shift_text(json.dumps(o, ensure_ascii=False), sign))


def fmt(t):
    return pd.Timestamp(t).strftime("%Y-%m-%d %H:%M")


# ---------------- slots ----------------
def vdc_order(n):
    seq, i = [], 0
    while len(seq) < n:
        x, f, j = 0.0, 0.5, i
        while j:
            x += f * (j & 1)
            j >>= 1
            f /= 2
        k = int(x * n)
        if k not in seq:
            seq.append(k)
        i += 1
    return seq


def slots():
    out = {}
    btc = V.klines("BTCUSDT", "1d", pd.Timestamp("2026-11-21", tz="UTC"))
    for k in range(NSLOT):
        t = WIN0 + pd.Timedelta(hours=4 * (18 * k + k % 6))
        c = btc[btc.index + pd.Timedelta(days=1) <= t].close
        r20 = float(c.iloc[-1] / c.iloc[-21] - 1) * 100
        reg = "trend-up" if r20 > 7 else "trend-down" if r20 < -7 else "range"
        out[f"R{k:02d}"] = {"slot": k, "asof": fmt(t), "btc_ret20d_pct": round(r20, 2), "regime": reg}
    order = [f"R{k:02d}" for k in vdc_order(NSLOT)]
    O.write_json(HERE / "rounds.json", {"order": order, "slots": out})
    say("order", order[:10], "regimes", {r: sum(1 for x in out.values() if x["regime"] == r)
                                         for r in ("trend-up", "range", "trend-down")})


# ---------------- cached history sources ----------------
def cget(name, fn):
    f = CACHE / name
    if f.exists():
        return json.loads(f.read_text(encoding="utf-8"))
    v = fn()
    if v is not None:
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(json.dumps(v), encoding="utf-8")
    return v


def http(url, params=None, text=False):
    for k in range(3):
        try:
            r = requests.get(url, params=params, headers=UA, timeout=30)
            if r.status_code in (403, 404, 451):
                return None
            r.raise_for_status()
            return r.text if text else r.json()
        except Exception:  # noqa: BLE001
            time.sleep(2 * (k + 1))
    return None


def yahoo_full(sym):
    def get():
        d = http(f"https://query1.finance.yahoo.com/v8/finance/chart/{sym}",
                 {"period1": 1735689600, "period2": 1763740800 + 86400 * 400, "interval": "1d"})
        try:
            res = d["chart"]["result"][0]
            return [[t, c] for t, c in zip(res["timestamp"], res["indicators"]["quote"][0]["close"]) if c is not None]
        except (TypeError, KeyError, IndexError):
            return None
    return cget(f"yahoo_{sym.replace('^', '_').replace('=', '_')}.json", get)


def yahoo_at(sym, asof):
    """Daily bar counted once 24h after its timestamp (conservative: never before that session closed)."""
    rows = yahoo_full(sym)
    if not rows:
        return None
    c = pd.Series([x[1] for x in rows], index=pd.to_datetime([x[0] for x in rows], unit="s", utc=True))
    c = c[c.index + pd.Timedelta(hours=24) <= asof]
    if len(c) < 25:
        return None
    V.SERIES[sym] = c
    return {"last": V.r5(c.iloc[-1]), "bar_date": V.ts(c.index[-1], True),
            "chg_5d_pct": V.pct(c.iloc[-1], c.iloc[-6]), "chg_20d_pct": V.pct(c.iloc[-1], c.iloc[-21])}


def fred_at(series, asof, lag_days=1):
    t = cget(f"fred_{series}.json", lambda: http("https://fred.stlouisfed.org/graph/fredgraph.csv",
                                                 {"id": series, "cosd": "2025-06-01"}, text=True))
    try:
        df = pd.read_csv(io.StringIO(t))
        col = df.columns[1]
        df[col] = pd.to_numeric(df[col], errors="coerce")
        df = df.dropna()
        df = df[pd.to_datetime(df.iloc[:, 0]).dt.date <= (asof - pd.Timedelta(days=lag_days)).date()]
        return {"last": V.r5(df[col].iloc[-1]), "date": str(df.iloc[-1, 0]),
                "chg_over_20_obs": V.r5(df[col].iloc[-1] - df[col].iloc[-21]) if len(df) > 21 else None}
    except Exception:  # noqa: BLE001
        return None


def fng_at(asof):
    d = cget("fng.json", lambda: http("https://api.alternative.me/fng/", {"limit": 0, "format": "json"}))
    try:
        x = sorted(((int(y["timestamp"]), int(y["value"]), y["value_classification"]) for y in d["data"]))
        x = [y for y in x if y[0] <= asof.timestamp()][-7:]
        return {"last7": [y[1] for y in x], "label": x[-1][2]}
    except (TypeError, KeyError, IndexError):
        return None


def etf_at(asof):
    def get():
        t = http("https://farside.co.uk/bitcoin-etf-flow-all-data/", text=True)
        if not t:
            return None
        try:
            tab = max(pd.read_html(io.StringIO(t)), key=len)
            first, tot = tab.columns[0], tab.columns[-1]
            out = []
            for _, r in tab.iterrows():
                d = pd.to_datetime(str(r[first]), errors="coerce", dayfirst=True)
                if pd.isna(d):
                    continue
                v = str(r[tot]).replace(",", "").strip()
                try:
                    x = float(v.strip("()")) * (-1 if v.startswith("(") else 1)
                except ValueError:
                    x = None
                out.append([V.ts(d, True), x])
            return out or None
        except Exception:  # noqa: BLE001
            return None
    rows = cget("farside.json", get)
    if not rows:
        return None
    # day D flows counted from D+1 06:00 UTC (published after the US close)
    rows = [r for r in rows if pd.Timestamp(r[0], tz="UTC") + pd.Timedelta(hours=30) <= asof]
    return {"unit": "USD m/day, Farside total, US spot BTC ETFs", "last10": rows[-10:]} if rows else None


def stable_at(asof):
    d = cget("llama.json", lambda: http(X.LLAMA))
    if not d:
        return None
    s = pd.Series({pd.Timestamp(int(x["date"]), unit="s", tz="UTC"): sum((x.get("totalCirculatingUSD") or {}).values())
                   for x in d}).sort_index()
    s = s[(s.index + pd.Timedelta(days=1) <= asof) & (s > 0)]
    return {"date": V.ts(s.index[-1], True), "total_usd_bn": V.r5(s.iloc[-1] / 1e9),
            "chg_7d_pct": V.pct(s.iloc[-1], s.iloc[-8]), "chg_30d_pct": V.pct(s.iloc[-1], s.iloc[-31])}


# USD high-impact events, UTC. Sources read 2026-11-21: federalreserve.gov/monetarypolicy/fomccalendars.htm (FOMC
# 2026: Jul 28-29, Sep 15-16, Oct 27-28; statement 14:00 ET, press conference 14:30 ET), bls.gov/schedule/2026
# (CPI, PPI, Employment Situation 8:30 ET; JOLTS 10:00 ET). EDT = UTC-4 until 2026-11-01, then EST = UTC-5.
CAL = [("2026-07-02 12:30", "Non-Farm Employment Change"), ("2026-07-14 12:30", "CPI m/m"),
       ("2026-07-15 12:30", "PPI m/m"), ("2026-07-29 18:00", "FOMC Statement / Federal Funds Rate"),
       ("2026-07-29 18:30", "FOMC Press Conference"), ("2026-08-04 14:00", "JOLTS Job Openings"),
       ("2026-08-07 12:30", "Non-Farm Employment Change"), ("2026-08-12 12:30", "CPI m/m"),
       ("2026-08-13 12:30", "PPI m/m"), ("2026-09-01 14:00", "JOLTS Job Openings"),
       ("2026-09-04 12:30", "Non-Farm Employment Change"), ("2026-09-10 12:30", "PPI m/m"),
       ("2026-09-11 12:30", "CPI m/m"), ("2026-09-16 18:00", "FOMC Statement / Federal Funds Rate"),
       ("2026-09-16 18:30", "FOMC Press Conference"), ("2026-09-29 14:00", "JOLTS Job Openings"),
       ("2026-10-02 12:30", "Non-Farm Employment Change"), ("2026-10-14 12:30", "CPI m/m"),
       ("2026-10-15 12:30", "PPI m/m"), ("2026-10-28 18:00", "FOMC Statement / Federal Funds Rate"),
       ("2026-10-28 18:30", "FOMC Press Conference"), ("2026-11-03 15:00", "JOLTS Job Openings"),
       ("2026-11-06 13:30", "Non-Farm Employment Change"), ("2026-11-10 13:30", "CPI m/m"),
       ("2026-11-13 13:30", "PPI m/m")]


def calendar_at(asof):
    rows = [[t, e, None, None] for t, e in CAL
            if asof - pd.Timedelta(hours=24) <= pd.Timestamp(t, tz="UTC") <= asof + pd.Timedelta(hours=72)]
    return {"cols": ["time_utc", "event", "forecast", "previous"], "rows": rows,
            "note": "USD high-impact, -24h..+72h, rebuilt from official schedules (FOMC, CPI, PPI, jobs, JOLTS); "
                    "forecast/previous not available"}


def metrics_day(sym, day):
    def get():
        r = None
        for k in range(3):
            try:
                r = requests.get(f"https://data.binance.vision/data/futures/um/daily/metrics/{sym}/{sym}-metrics-"
                                 f"{day}.zip", headers=UA, timeout=30)
                break
            except Exception:  # noqa: BLE001
                time.sleep(2)
        if r is None or r.status_code != 200:
            return None
        z = zipfile.ZipFile(io.BytesIO(r.content))
        return z.read(z.namelist()[0]).decode()
    return cget(f"metrics/{sym}_{day}.json", get)


def hist_derivs(sym, asof, h4):
    """Binance USD-M history as of asof: funding, premium index, mark, taker buy/sell (futures klines), OI and
    long/short ratios (data.binance.vision daily metrics, 5-min). Basis and Bybit not rebuilt."""
    end = int(asof.timestamp() * 1000) - 1
    o = {"source": "binance_usdm"}
    fr = http(f"{V.FAPI}/fapi/v1/fundingRate", {"symbol": sym, "startTime": end - 8 * 86400000, "endTime": end,
                                               "limit": 100})
    if fr:
        rates = [float(x["fundingRate"]) for x in fr]
        o["funding_last"] = V.r5(rates[-1])
        o["funding_7d_avg"] = V.r5(np.mean(rates[-21:]))
        o["funding_last9"] = [V.r5(x) for x in rates[-9:]]
    mk = http(f"{V.FAPI}/fapi/v1/markPriceKlines", {"symbol": sym, "interval": "4h", "endTime": end, "limit": 1})
    pk = http(f"{V.FAPI}/fapi/v1/premiumIndexKlines", {"symbol": sym, "interval": "4h", "endTime": end, "limit": 1})
    if mk:
        o["mark"] = V.r5(mk[-1][4])
    if pk:
        o["perp_premium_pct"] = V.r5(float(pk[-1][4]) * 100)
    days = pd.date_range((asof - pd.Timedelta(days=8)).normalize(), asof.normalize(), freq="D")
    parts = [metrics_day(sym, d.strftime("%Y-%m-%d")) for d in days]
    rows = []
    for p in parts:
        if p:
            rows += p.splitlines()[1:]
    if rows:
        df = pd.read_csv(io.StringIO("\n".join(rows)), header=None,
                         names=["t", "sym", "oi", "oiv", "c_top", "s_top", "c_ls", "taker"])
        df.index = pd.to_datetime(df.t, utc=True)
        df = df[(df.index <= asof) & (df.index.hour % 4 == 0) & (df.index.minute == 0)].sort_index()
        df = df[~df.index.duplicated()]
        if len(df) > 7:
            v = df.oiv.astype(float).tail(42)
            o["oi_usd_bn"] = V.r5(v.iloc[-1] / 1e9)
            o["oi_chg_24h_pct"] = V.pct(v.iloc[-1], v.iloc[-7])
            o["oi_chg_7d_pct"] = V.pct(v.iloc[-1], v.iloc[0])
            o["est_liq_zones"] = V.liq_est(v, h4)
            o["ls_accounts_4h"] = [V.r5(x) for x in df.c_ls.astype(float).tail(7)]
            o["ls_top_positions_4h"] = [V.r5(x) for x in df.s_top.astype(float).tail(7)]
    fk = http(f"{V.FAPI}/fapi/v1/klines", {"symbol": sym, "interval": "4h", "endTime": end, "limit": 7})
    if fk:
        o["taker_buy_sell_4h"] = [V.r5(float(k[9]) / max(1e-12, float(k[5]) - float(k[9]))) for k in fk]
    o["replay_note"] = "rebuilt from Binance history; quarterly basis and bybit not available for past moments"
    return o


def onchain_at(cur, asof):
    """veri_ek.onchain with an end date: Coin Metrics returns the newest page without it. Day D counted from
    D+1 04:00 UTC (published ~03:00)."""
    orig = V.get
    def g(url, params=None, text=False):
        if url == X.CM:
            params = {**params, "end_time": (asof - pd.Timedelta(hours=28)).strftime("%Y-%m-%d")}
        return orig(url, params, text)
    V.get = g
    try:
        return X.onchain(cur, asof)
    finally:
        V.get = orig


# ---------------- snapshot ----------------
def build(code, asof):
    """Real-dated snapshot -> snaps/<code>.json (hidden); date-shifted views + charts -> rounds/<code>/."""
    rdir = ROUNDS / code
    rdir.mkdir(parents=True, exist_ok=True)
    V.ERR.clear()
    V.SERIES.clear()
    frames = {}
    for s in ASSETS:
        frames[s] = {iv: V.klines(s, iv, asof) for iv in V.IV_MIN}
        if any(v is None or len(v) < 30 for v in frames[s].values()):
            raise RuntimeError(f"{s}: klines missing at {asof}")
    legend = json.loads((HERE / "legend.json").read_text(encoding="utf-8"))
    snap = {"asof_utc": V.ts(asof), "generated_utc": V.ts(asof + pd.Timedelta(minutes=20)), "mode": "replay_test",
            "legend": legend, "assets": {}}
    C = X.cfg()
    btc = frames["BTCUSDT"]
    for s in ASSETS:
        fr = frames[s]
        a4, a1 = V.atr(fr["4h"]).iloc[-1], V.atr(fr["1h"]).iloc[-1]
        def opt(name, fn, *args):
            try:
                return fn(*args)
            except Exception as e:  # noqa: BLE001
                V.ERR.append(f"{s}: {name} error {type(e).__name__} {str(e)[:100]}")
                return None
        x = {"ctx": V.context(fr, btc), "levels": V.key_levels(fr["1d"], asof),
             "structure": {"1d": V.structure(fr["1d"], "1d", 12), "4h": V.structure(fr["4h"], "4h", 12),
                           "1h": V.structure(fr["1h"], "1h", 10)},
             "fvg": opt("fvg", lambda: {"4h": V.fvgs(fr["4h"], a4), "1h": V.fvgs(fr["1h"], a1)}),
             "equal_hl": opt("equal_hl", lambda: {"4h": V.equal_levels(fr["4h"], a4, "4h"),
                                                  "1h": V.equal_levels(fr["1h"], a1, "1h")}),
             "vp": opt("vp", lambda: {"4h_all": V.vprofile(fr["4h"]), "1h_30d": V.vprofile(fr["1h"]),
                                      "1d_180d": V.vprofile(fr["1d"].tail(180))}) or {},
             "harmonics": opt("harmonics", V.harmonics, fr),
             "elliott": opt("elliott", V.elliott, fr),
             "avwap_1d": opt("avwap_1d", V.avwap, fr["1d"], fr["4h"]),
             "candles": {"1w": V.weekly_rows(fr["1d"]), **{iv: V.rows(fr[iv], iv) for iv in ("1d", "4h", "1h", "15m")}},
             "derivs": opt("derivs", hist_derivs, s, asof, fr["4h"])}
        cur = s.replace("USDT", "")
        x["options"] = None
        x["onchain"] = opt("onchain", onchain_at, cur.lower(), asof)
        x["orderbook"] = None
        x["recorded"] = None
        sh = {iv: df.set_axis(df.index + pd.Timedelta(SHIFT)) for iv, df in fr.items()}
        lv_sh = shift_obj(x["levels"])
        x["charts"] = opt("charts", V.charts, s, sh, lv_sh, x["vp"].get("4h_all"), rdir / "charts")
        snap["assets"][s] = x
    snap["sentiment"] = {"fear_greed": fng_at(asof)}
    m = {"dxy": yahoo_at("DX-Y.NYB", asof), "us10y_yield": yahoo_at("^TNX", asof), "spx": yahoo_at("^GSPC", asof),
         "vix": yahoo_at("^VIX", asof), "gold": yahoo_at("GC=F", asof),
         "fed_funds_eff": fred_at("DFF", asof), "ust2y": fred_at("DGS2", asof),
         "fed_balance_sheet_musd": fred_at("WALCL", asof, 2), "crypto_global": None,
         "calendar_usd_high": calendar_at(asof), "btc_etf_flows": etf_at(asof),
         "ndx": yahoo_at("^NDX", asof), "usdjpy": yahoo_at("JPY=X", asof), "move": yahoo_at("^MOVE", asof),
         "hy_oas_pct": fred_at("BAMLH0A0HYM2", asof), "stablecoin_supply": stable_at(asof)}
    try:
        m.update(X.cross_asset(btc["1d"], C) or {})
    except Exception as e:  # noqa: BLE001
        V.ERR.append(f"cross_asset: {type(e).__name__} {e}")
    snap["macro"] = m
    snap["errors"] = list(V.ERR)
    SNAPS.mkdir(exist_ok=True)
    (SNAPS / f"{code}.json").write_text(V.dump(snap) + "\n", encoding="utf-8")
    sshift = shift_obj(snap)
    views = {}
    for role in set(T.VIEW_OF.values()):
        f = rdir / f"view_{role}.json"
        f.write_text(T.make_view(sshift, role), encoding="utf-8")
        views[role] = f
    return snap, sshift, views


def load_round(code):
    snap = json.loads((SNAPS / f"{code}.json").read_text(encoding="utf-8"))
    rdir = ROUNDS / code
    return snap, shift_obj(snap), {r: rdir / f"view_{r}.json" for r in set(T.VIEW_OF.values())}


# ---------------- claude ----------------
def run_agent(agent, prompt, code, timeout):
    exe = O.find_claude()
    raw = RAW / code
    raw.mkdir(parents=True, exist_ok=True)
    (raw / f"prompt_{agent}.txt").write_text(prompt, encoding="utf-8")
    if not exe:
        return {"agent": agent, "error": "claude CLI not found"}
    cmd = [exe, "-p", "--agent", agent, "--output-format", "json", "--permission-mode", "dontAsk",
           "--tools", "Read", "--allowedTools", "Read", "--add-dir", str(O.AGENT_BILGI), "--no-session-persistence"]
    env = {k: v for k, v in os.environ.items() if k not in ("CLAUDECODE", "CLAUDE_CODE_ENTRYPOINT")}
    t0 = time.time()
    p = subprocess.Popen(cmd, cwd=str(ROUNDS / code), stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                         stderr=subprocess.PIPE, env=env, creationflags=NOWIN)
    try:
        out, err = p.communicate(prompt.encode("utf-8"), timeout=timeout)
    except subprocess.TimeoutExpired:
        subprocess.run(["taskkill", "/T", "/F", "/PID", str(p.pid)], capture_output=True, creationflags=NOWIN)
        return {"agent": agent, "error": f"timeout {timeout}s", "secs": round(time.time() - t0), "cost_usd": 0}
    out, err = out.decode("utf-8", "replace"), err.decode("utf-8", "replace")
    (raw / f"{agent}.out.json").write_text(out, encoding="utf-8")
    res = {"agent": agent, "secs": round(time.time() - t0)}
    try:
        j = json.loads(out)
    except json.JSONDecodeError:
        res["error"] = f"non-json output rc={p.returncode}: {(out or err)[:200]}"
        res["cost_usd"] = 0
        return res
    u = j.get("usage") or {}
    res.update(text=j.get("result") or "", turns=j.get("num_turns"), cost_usd=j.get("total_cost_usd") or 0,
               models=list((j.get("modelUsage") or {}).keys()), tok_out=u.get("output_tokens", 0),
               tok_cache_w=u.get("cache_creation_input_tokens", 0), tok_cache_r=u.get("cache_read_input_tokens", 0))
    if j.get("is_error"):
        res["error"] = f"cli error: {str(j.get('result'))[:200]}"
    return res


def log_calls(code, results):
    old = json.loads(LOGF.read_text(encoding="utf-8")) if LOGF.exists() else []
    for r in results:
        old.append({"round": code, "agent": r["agent"], "cost_usd": r.get("cost_usd") or 0, "secs": r.get("secs"),
                    "turns": r.get("turns"), "models": r.get("models"), "error": r.get("error"),
                    "utc": fmt(pd.Timestamp.now(tz="UTC"))})
    O.write_json(LOGF, old)


def spent():
    return sum(x.get("cost_usd") or 0 for x in json.loads(LOGF.read_text(encoding="utf-8"))) if LOGF.exists() else 0.0


def round_costs():
    by = {}
    if LOGF.exists():
        for x in json.loads(LOGF.read_text(encoding="utf-8")):
            by[x["round"]] = by.get(x["round"], 0) + (x.get("cost_usd") or 0)
    return by


def infra(r):
    e = str(r.get("error") or "").lower()
    return any(p in e for p in INFRA)


def gate():
    """No calls between xx:10 and xx:35 local (TR) time: live round + shared usage quota."""
    while True:
        m = dt.datetime.now().minute
        if not (10 <= m < 35):
            return
        say(f"time gate: minute {m}, waiting until xx:35")
        time.sleep((35 - m) * 60 + 5)


def play(code, meta):
    R = FROZEN["risk"]
    raw = RAW / code
    if (raw / "done.json").exists():
        return "done", 0
    asof = pd.Timestamp(meta["asof"], tz="UTC")
    if (SNAPS / f"{code}.json").exists():
        snap, ss, views = load_round(code)
    else:
        snap, ss, views = build(code, asof)
    asof_s = ss["asof_utc"]
    cfg = copy.deepcopy(FROZEN)
    cfg["assets"] = list(ASSETS)
    lim = T.limits_line(R)
    call = list(EXPERTS)
    auto = []
    if not T.harmonic_candidates(ss, ASSETS):
        call.remove("trader-harmonik")
        auto = [T.auto_flat("trader-harmonik", asof_s, s, "no at_prz/reacted harmonic candidate in snapshot")
                for s in ASSETS]
    jobs = {}
    for ex in call:
        lines = [HEADER, f"SNAPSHOT={views[T.VIEW_OF[ex]]}", f"CHARTS={T.charts_line(ss)}", "PREV=none", "OPEN=none",
                 f"LIMITS={lim}"]
        if ex == "trader-senaryo":
            lines.append("RECENT=none")
        if ex == "trader-makro":
            lines.append("GUNDEM=none (WebFetch is not available in this test)")
        lines.append(f"ASSETS={','.join(ASSETS)}. Follow your agent instructions. "
                     "Your final message must be only the ```json array (one block per asset). "
                     "Every field is required (horizon_h too when flat); each rationale item <= 200 chars.")
        jobs[ex] = "\n".join(lines)
    results = {}
    old = json.loads((raw / "experts_res.json").read_text(encoding="utf-8")) if (raw / "experts_res.json").exists() else {}
    for ex, r in old.items():      # resume: keep finished non-infra calls
        if ex in jobs and not infra(r) and not r.get("error"):
            results[ex] = r
    todo = {ex: p for ex, p in jobs.items() if ex not in results}
    if todo:
        with cf.ThreadPoolExecutor(max_workers=len(todo)) as pool:
            futs = {pool.submit(run_agent, ex, p, code, T_EXPERT): ex for ex, p in todo.items()}
            new = [f.result() for f in cf.as_completed(futs)]
        log_calls(code, new)
        for r in new:
            results[r["agent"]] = r
        O.write_json(raw / "experts_res.json", results)
    if any(infra(r) for r in results.values()):
        return "infra:" + next(r["error"] for r in results.values() if infra(r)), 0
    vb = O.validator("expert_block")
    valid, rows = [], []
    for ex in call:
        r = results.get(ex, {"error": "no result"})
        parsed = O.extract_json(r.get("text")) if not r.get("error") else None
        rr = T.validate_blocks(ex, parsed, ss, cfg, vb) if not r.get("error") else \
            [{"asset": a, "valid": False, "errors": [r["error"]], "block": None} for a in ASSETS]
        for x in rr:
            x["expert"] = ex
            rows.append(x)
            if x["valid"]:
                valid.append(x["block"])
    O.write_json(raw / "blocks.json", {"asof_shifted": asof_s, "rows": rows, "auto": auto, "called": call})
    say(code, "blocks", [f"{x['expert'][7:]}:{x['asset'][:3]}:{(x['block'] or {}).get('bias', '?')}"
                         f"{'' if x['valid'] else '(INVALID ' + '; '.join(x['errors'])[:80] + ')'}" for x in rows])
    # Riza
    dec = valid + auto
    rdir = ROUNDS / code
    O.write_json(rdir / "experts.json", dec)
    SIM_NOW[0] = (asof + pd.Timedelta(minutes=20)).to_pydatetime()
    st = fresh_state()
    O.write_json(rdir / "ledger.json", shift_obj(D.ledger_summary(st)))
    O.write_json(rdir / "scores.json", {e: {"closed": 0, "hit_rate": None, "avg_r": None, "ev_r_ci90": [None, None],
                                            "brier": None} for e in EXPERTS})
    SIM_NOW[0] = None
    rlim = " ".join(f"{k}={v}" for k, v in R.items() if isinstance(v, (int, float)) and not isinstance(v, bool))
    prompt = "\n".join([HEADER_RISK, f"EXPERTS={rdir / 'experts.json'}", f"SNAPSHOT={views['risk']}", "GUNDEM=none",
                        "OPEN=none", f"LEDGER={rdir / 'ledger.json'}", f"SCORES={rdir / 'scores.json'}",
                        f"LIMITS={rlim}", f"ASSETS={','.join(ASSETS)}. Follow your agent instructions. "
                        "Your final message must be only the ```json array (one decision per asset)."])
    r = run_agent("trader-risk", prompt, code, T_RISK)
    log_calls(code, [r])
    if infra(r):
        return "infra:" + r["error"], 0
    vd = O.validator("decision")
    parsed = O.extract_json(r.get("text")) if not r.get("error") else None
    decisions, errs = [], []
    if isinstance(parsed, list):
        for d in parsed:
            e = O.schema_errors(vd, d)
            if not e and d["asof_utc"] != asof_s:
                e = [f"asof {d['asof_utc']} != {asof_s}"]
            (errs.append(f"{(d or {}).get('asset') if isinstance(d, dict) else '?'}: {'; '.join(e)}") if e
             else decisions.append(d))
    else:
        errs.append(r.get("error") or "no parseable json array")
    O.write_json(raw / "decisions.json", {"decisions": decisions, "errors": errs})
    say(code, "riza", [f"{d['asset'][:3]}:{d['decision']}:{d.get('side')}" for d in decisions], errs[:2])
    O.write_json(raw / "done.json", {"utc": fmt(pd.Timestamp.now(tz="UTC")), "cost_usd": round_costs().get(code)})
    return "ok", round_costs().get(code, 0)


def fresh_state():
    r = FROZEN["risk"]
    return {"version": 1, "start_utc": None, "start_px": {}, "cash": float(r["start_equity_usdt"]),
            "peak": float(r["start_equity_usdt"]), "last_check_ms": {}, "last_px": {}, "trades": [],
            "funding_cache": {}, "next_id": 1, "paper_cache": None, "last_decisions": {}}


def run(n, cap):
    meta = json.loads((HERE / "rounds.json").read_text(encoding="utf-8"))
    todo = [c for c in meta["order"] if not (RAW / c / "done.json").exists()][:n]
    for code in todo:
        rc = [v for v in round_costs().values() if v > 0]
        est = max(rc) if rc else 2.5
        if spent() + 1.3 * est > cap:
            say(f"cost cap: spent ${spent():.2f} + 1.3 x ${est:.2f} > ${cap}: stop")
            return 0
        gate()
        say(f"round {code} asof(real) {meta['slots'][code]['asof']} regime {meta['slots'][code]['regime']}; "
            f"spent ${spent():.2f}")
        st, c = play(code, meta["slots"][code])
        say(code, st, f"round ${c:.3f}; total ${spent():.2f}")
        if st.startswith("infra"):
            O.write_json(HERE / "STOP.json", {"utc": fmt(pd.Timestamp.now(tz="UTC")), "round": code, "why": st})
            say("infra error (session/usage limit?): stopped, progress saved; rerun 'run' later to resume")
            return 7
    return 0


# ---------------- score (no LLM) ----------------
KL = {}


def klines_c(sym, iv, a_ms, b_ms):
    key = (sym, iv, a_ms, b_ms)
    if key not in KL:
        f = CACHE / "kl" / f"{sym}_{iv}_{a_ms}_{b_ms}.json"
        if f.exists():
            KL[key] = json.loads(f.read_text(encoding="utf-8"))
            return KL[key]
        out, s = [], a_ms
        while s < b_ms:
            for k in range(6):      # transient DNS/network errors
                try:
                    part = D.fetch_klines(sym, iv, s, b_ms)
                    break
                except Exception:  # noqa: BLE001
                    if k == 5:
                        raise
                    time.sleep(5 * (k + 1))
            if not part:
                break
            out += part
            s = part[-1][0] + 1
            if len(part) < 1000:
                break
        KL[key] = out
        if out and b_ms < int(time.time() * 1000) - 3600000:
            f.parent.mkdir(parents=True, exist_ok=True)
            f.write_text(json.dumps(out), encoding="utf-8")
    return KL[key]


def m1_day(sym, day):
    a = int(pd.Timestamp(day, tz="UTC").timestamp() * 1000)
    rows = cget(f"1m/{sym}_{day}.json", lambda: klines_c(sym, "1m", a, a + 86400000) or None)
    return rows or []


def advance(st, sym, ptr, to_ms):
    if to_ms <= ptr[sym]:
        return
    if not ptr[sym]:
        ptr[sym] = to_ms
        return
    if D.live(st, None, sym):
        d = pd.Timestamp(ptr[sym], unit="ms", tz="UTC").normalize()
        while int(d.timestamp() * 1000) < to_ms:
            c = [x for x in m1_day(sym, d.strftime("%Y-%m-%d")) if ptr[sym] <= x[0] < to_ms]
            if c:
                D.process_candles(st, sym, c)
            d += pd.Timedelta(days=1)
            if not D.live(st, None, sym):
                break
    ptr[sym] = to_ms


def wilson(k, n, z=1.645):
    if not n:
        return [None, None]
    p = k / n
    den = 1 + z * z / n
    c = (p + z * z / (2 * n)) / den
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / den
    return [round(c - h, 3), round(c + h, 3)]


def score():
    meta = json.loads((HERE / "rounds.json").read_text(encoding="utf-8"))
    done = sorted([c for c in meta["order"] if (RAW / c / "done.json").exists()],
                  key=lambda c: meta["slots"][c]["asof"])
    cfg = copy.deepcopy(FROZEN)
    cfg["assets"] = list(ASSETS)
    M = cfg.get("measure") or {}
    band = M.get("flat_band_atr4h", 1.0)
    brows, rounds_out = [], []
    st = fresh_state()
    ptr = {s: 0 for s in ASSETS}
    for code in done:
        snap = json.loads((SNAPS / f"{code}.json").read_text(encoding="utf-8"))
        bj = json.loads((RAW / code / "blocks.json").read_text(encoding="utf-8"))
        dj = json.loads((RAW / code / "decisions.json").read_text(encoding="utf-8"))
        asof = pd.Timestamp(meta["slots"][code]["asof"], tz="UTC")
        asof_s = fmt(asof)
        unsh = lambda b: shift_obj(b, -1)  # noqa: E731
        valid = [unsh(x["block"]) for x in bj["rows"] if x["valid"]]
        auto = [unsh(b) for b in bj["auto"]]
        decisions = [unsh(d) for d in dj["decisions"]]
        # block scoring (office score_one) + vote check
        t0 = int(asof.timestamp() * 1000)
        inval = [unsh(x["block"]) for x in bj["rows"] if not x["valid"] and isinstance(x["block"], dict)
                 and x["block"].get("bias") in ("long", "short") and x["block"].get("asset") in ASSETS]
        for kind, b in [("valid", b) for b in valid] + [("auto", b) for b in auto] + [("invalid", b) for b in inval]:
            h = int(b.get("horizon_h") or 4)
            c4 = klines_c(b["asset"], "4h", t0 - 15 * 4 * 3600000, t0)
            c1 = klines_c(b["asset"], "1h", t0, t0 + h * 3600000)
            if len(c1) < h or not c1 or c1[0][0] != t0:
                continue
            trs = [max(c4[i][2], c4[i - 1][4]) - min(c4[i][3], c4[i - 1][4]) for i in range(1, len(c4))]
            atr = float(np.mean(trs[-14:])) if len(c4) >= 15 else None
            row = D.score_one(b, c1, atr, band)
            try:
                ok, why = D.vote_check(b, b["asset"], asof_s, cfg, snap) if b["bias"] in ("long", "short") else (False, "")
            except Exception as e:  # noqa: BLE001  malformed invalid block
                ok, why = False, f"{type(e).__name__}"
            rr = None
            if b["bias"] in ("long", "short") and b.get("stop") is not None and b.get("targets") and b.get("entry"):
                last = snap["assets"][b["asset"]]["ctx"]["last_close"]
                rr = O.rr_cost(b["bias"], b["entry"], b["stop"], b["targets"][0], last, FROZEN["risk"])[0]
            brows.append({**row, "round": code, "regime": meta["slots"][code]["regime"], "expert": b["expert"],
                          "asset": b["asset"], "asof": asof_s, "horizon_h": h, "bias": b["bias"],
                          "conf": b.get("confidence"), "setup": b.get("setup"), "auto": kind == "auto",
                          "valid": kind != "invalid",
                          "vote_ok": ok, "vote_why": why, "rr_gross": rr,
                          "up": int(row["p_end"] > row["p0"])})
        # forward ledger: office code, replay clock
        created = asof + pd.Timedelta(minutes=20)
        for s in ASSETS:
            advance(st, s, ptr, int(created.timestamp() * 1000))
        SIM_NOW[0] = created.to_pydatetime()
        if not st["start_utc"]:
            st["start_utc"] = fmt(asof)
            st["start_px"] = {s: snap["assets"][s]["ctx"]["last_close"] for s in ASSETS}
        res = D.apply_decisions(st, decisions, snap, code, valid + auto) if decisions else []
        D.add_shadow(st, valid, bj["called"], code, snap, errored=set())
        rounds_out.append({"round": code, "asof": asof_s, "regime": meta["slots"][code]["regime"],
                           "decisions": [f"{d['asset']}:{d['decision']}:{d.get('side')}" for d in decisions],
                           "applied": res, "decision_errors": dj["errors"]})
        SIM_NOW[0] = None
    if not done:
        print("no finished rounds")
        return
    last = pd.Timestamp(meta["slots"][done[-1]]["asof"], tz="UTC")
    end = min(last + pd.Timedelta(hours=96), pd.Timestamp.now(tz="UTC") - pd.Timedelta(hours=1)).floor("h")
    for s in ASSETS:
        advance(st, s, ptr, int(end.timestamp() * 1000))
    for s in ASSETS:     # mark open office positions at the end price
        c = klines_c(s, "1h", int(end.timestamp() * 1000) - 3600000, int(end.timestamp() * 1000))
        if c:
            st["last_px"][s] = c[-1][4]
    SIM_NOW[0] = end.to_pydatetime()
    eq = D.mark_equity(st)
    SIM_NOW[0] = None
    rep = summarize(brows, st, done, meta, eq, end)
    rep["rounds_detail"] = rounds_out
    O.write_json(HERE / "sonuc.json", rep)
    pd.DataFrame(brows).to_csv(HERE / "bloklar.csv", index=False)
    pd.DataFrame([{k: t.get(k) for k in ("id", "book", "asset", "side", "status", "entry_type", "entry_price",
                                         "fill_px", "stop0", "targets", "horizon_h", "confidence", "created_utc",
                                         "fill_utc", "exit_utc", "exit_reason", "r_mult", "hit", "risk_usdt", "note")}
                  for t in st["trades"]]).to_csv(HERE / "islemler.csv", index=False)
    print(json.dumps({k: v for k, v in rep.items() if k != "rounds_detail"}, indent=1, ensure_ascii=False))


def summarize(brows, st, done, meta, eq, end):
    df = pd.DataFrame(brows)
    out = {"plan": "plan.md", "rounds": len(done), "cost_usd": round(spent(), 2),
           "regimes": {r: sum(1 for c in done if meta["slots"][c]["regime"] == r) for r in ("trend-up", "range", "trend-down")},
           "window_real": [meta["slots"][done[0]]["asof"], fmt(end)], "experts": {}}
    out["base_rates"] = {"up_share_all_blocks": round(float(df.up.mean()), 3) if len(df) else None}
    for ex in EXPERTS:
        xa = df[(df.expert == ex) & (~df.auto)] if len(df) else df
        x = xa[xa.valid] if len(xa) else xa
        da = xa[xa.kind == "dir"] if len(xa) else xa
        d = x[x.kind == "dir"]
        fl = x[x.kind == "flat"]
        cx = x[x.kind == "context"]
        k, n = int(d.hit.sum()) if len(d) else 0, len(d)
        sh = [t for t in st["trades"] if t["book"] == ex]
        closed = [t["r_mult"] for t in sh if t["status"] == "closed" and t["r_mult"] is not None]
        filled = [t for t in sh if t["fill_ms"]]
        pt = d[d.path.isin(["t1", "stop"])] if len(d) else d
        e = {"blocks": len(x), "dir_n": n, "dir_hit": round(k / n, 3) if n else None, "dir_hit_ci90": wilson(k, n),
             "always_long_same_windows": round(float(d.up.mean()), 3) if n else None,
             "dir_atr_mean": round(float(d.dir_atr.mean()), 3) if n else None,
             "dir_incl_geom_invalid_n": len(da), "dir_incl_geom_invalid_hit": round(float(da.hit.mean()), 3) if len(da) else None,
             "auto_flat_blocks": int(((df.expert == ex) & df.auto).sum()) if len(df) else 0,
             "t1_before_stop": round(float((pt.path == "t1").mean()), 3) if len(pt) else None,
             "flat_n": len(fl), "flat_in_band": round(float(fl.hit.mean()), 3) if len(fl) else None,
             "ctx_n": len(cx), "ctx_hit": round(float(cx.hit.mean()), 3) if len(cx) else None,
             "vote_pass_rate": round(float(d.vote_ok.mean()), 3) if n else None,
             "shadow_n": len(sh), "shadow_filled": len(filled), "shadow_closed": len(closed),
             "shadow_avg_r": round(float(np.mean(closed)), 3) if closed else None,
             "shadow_total_r": round(float(np.sum(closed)), 2) if closed else 0.0,
             "shadow_r_ci90": D.bootstrap_ci(closed) if len(closed) >= 2 else [None, None]}
        if n:
            cal = {}
            for lo, hi in ((0, 54), (55, 62), (63, 72), (73, 80)):
                b = pt[(pt.conf >= lo) & (pt.conf <= hi)] if len(pt) else pt
                if len(b):
                    be = (1 / (1 + b.rr_gross)).mean()
                    cal[f"{lo}-{hi}"] = {"n": len(b), "t1_first": round(float((b.path == "t1").mean()), 3),
                                         "breakeven": round(float(be), 3)}
            e["calibration"] = cal
        lo_ci, hi_ci = e["dir_hit_ci90"]
        sci = e["shadow_r_ci90"]
        if n >= 15 and lo_ci is not None and lo_ci > 0.5 and len(closed) >= 10 and e["shadow_avg_r"] > 0:
            v = "edge signal"
        elif (hi_ci is not None and n >= 5 and hi_ci < 0.5) or (len(closed) >= 10 and sci[1] is not None and sci[1] < 0):
            v = "negative signal"
        else:
            v = "inconclusive"
        e["verdict"] = v
        out["experts"][ex] = e
    ofis = [t for t in st["trades"] if t["book"] == "ofis"]
    oc = [t for t in ofis if t["status"] == "closed" and t["r_mult"] is not None]
    s0 = pd.Timestamp(meta["slots"][done[0]]["asof"], tz="UTC")
    span = (end - s0).total_seconds()
    iv = sorted((t["fill_ms"], t["exit_ms"] or int(end.timestamp() * 1000)) for t in ofis if t["fill_ms"])
    inm, cur = 0, None
    for a, b in iv:
        if cur is None or a > cur[1]:
            if cur:
                inm += cur[1] - cur[0]
            cur = [a, b]
        else:
            cur[1] = max(cur[1], b)
    if cur:
        inm += cur[1] - cur[0]
    tim = inm / 1000 / span if span > 0 else 0
    p0 = st["start_px"].get("BTCUSDT")
    p1 = klines_c("BTCUSDT", "1h", int(end.timestamp() * 1000) - 3600000, int(end.timestamp() * 1000))[-1][4]
    btc = (p1 / p0 - 1) * 100 if p0 else None
    out["office"] = {"orders": len(ofis), "filled": sum(1 for t in ofis if t["fill_ms"]), "closed": len(oc),
                     "r_list": [round(t["r_mult"], 3) for t in oc],
                     "total_r": round(float(np.sum([t["r_mult"] for t in oc])), 3) if oc else 0.0,
                     "equity_end": round(eq, 2), "return_pct": round((eq / FROZEN["risk"]["start_equity_usdt"] - 1) * 100, 3),
                     "time_in_market_pct": round(100 * tim, 2), "btc_buyhold_pct": round(btc, 2) if btc is not None else None,
                     "btc_exposure_matched_pct": round(btc * tim, 3) if btc is not None else None,
                     "verdict": ("positive so far" if len(oc) >= 5 and sum(t["r_mult"] for t in oc) > 0 else "inconclusive")}
    return out


def tablo():
    """Markdown table for SONUC.md from sonuc.json."""
    r = json.loads((HERE / "sonuc.json").read_text(encoding="utf-8"))
    names = {e["id"]: e["name"] for e in FROZEN["experts"]}
    pc = lambda v: "-" if v is None else f"%{round(100 * v)}"  # noqa: E731
    print("| Uzman | Blok | Yönlü | Yön isabeti (%90 aralık) | Aynı anlarda hep-long | Düz isabet | Gölge işlem (kapanan) | Ort. R (%90 aralık) | EV kuralından geçen | Karar |")
    print("|---|---|---|---|---|---|---|---|---|---|")
    for ex, e in r["experts"].items():
        ci = e["dir_hit_ci90"]
        sci = e["shadow_r_ci90"]
        print(f"| {names.get(ex, ex)} | {e['blocks']} | {e['dir_n']} | {pc(e['dir_hit'])}"
              f"{'' if ci[0] is None else f' ({pc(ci[0])}-{pc(ci[1])})'} | {pc(e['always_long_same_windows'])} | "
              f"{pc(e['flat_in_band'])} ({e['flat_n']}) | {e['shadow_closed']} | "
              f"{'-' if e['shadow_avg_r'] is None else e['shadow_avg_r']}"
              f"{'' if sci[0] is None else f' ({sci[0]} / {sci[1]})'} | {pc(e['vote_pass_rate'])} | {e['verdict']} |")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("mode", choices=["slots", "run", "score", "build", "tablo"])
    ap.add_argument("--n", type=int, default=2)
    ap.add_argument("--cap", type=float, default=40.0)
    ap.add_argument("--code")
    a = ap.parse_args()
    if a.mode == "slots":
        slots()
    elif a.mode == "build":     # snapshot only (no LLM), for checking
        m = json.loads((HERE / "rounds.json").read_text(encoding="utf-8"))
        build(a.code, pd.Timestamp(m["slots"][a.code]["asof"], tz="UTC"))
    elif a.mode == "run":
        sys.exit(run(a.n, a.cap))
    elif a.mode == "tablo":
        tablo()
    else:
        score()
