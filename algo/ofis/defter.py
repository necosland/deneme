"""Trader ofisi sahte defteri. LLM yok; sinirlar burada KODLA uygulanir (ofis-ayar.json).

- apply_decisions: Riza'nin (trader-risk) kararlarini sinir denetimiyle deftere isler.
- add_shadow: her gecerli uzman long/short blogu icin 1R'lik golge islem (risk karari ne olursa olsun).
- process_candles: 1m mumlarla dolum, stop, hedef, sure dolumu, fonlama (kontrol.py ve tur.py cagirir).
- write_reports: defter/*.csv, puan.json, DURUM.md (Turkce ozet).

Kullanim: python algo/ofis/defter.py rapor    # raporlari state.json'dan yeniden yazar
"""
import csv
import datetime as dt
import io
import json
import subprocess
import sys

import numpy as np
import requests

import ortak as O

STATE = O.DEFTER / "state.json"
SHADOW_RISK = 100.0          # golge islem 1R = 100 USDT (yalniz R olcusu icin)
H4 = 4 * 3600 * 1000
PAPER_REF = "origin/claude/python-libraries-setup-i3y7ok"
PAPER_FETCH = "+refs/heads/claude/python-libraries-setup-i3y7ok:refs/remotes/origin/claude/python-libraries-setup-i3y7ok"


# ---------------- state ----------------
def load_state():
    if STATE.exists():
        return json.loads(STATE.read_text(encoding="utf-8"))
    r = O.ayar()["risk"]
    return {"version": 1, "start_utc": None, "start_px": {}, "cash": float(r["start_equity_usdt"]),
            "peak": float(r["start_equity_usdt"]), "last_check_ms": {}, "last_px": {}, "trades": [],
            "funding_cache": {}, "next_id": 1, "paper_cache": None, "last_decisions": {}}


def save_state(st):
    O.write_json(STATE, st)


def sgn(side):
    return 1 if side == "long" else -1


def live(st, book=None, asset=None, statuses=("pending", "open")):
    return [t for t in st["trades"] if t["status"] in statuses
            and (book is None or (t["book"] == book if book != "shadow" else t["book"] != "ofis"))
            and (asset is None or t["asset"] == asset)]


def event(st, t, ev, note=""):
    """Ofis emir olaylari emirler.csv'ye (golge islemler yalniz golge.csv'de)."""
    if t["book"] != "ofis":
        return
    f = O.DEFTER / "emirler.csv"
    new = not f.exists()
    O.DEFTER.mkdir(parents=True, exist_ok=True)
    with open(f, "a", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        if new:
            w.writerow(["zaman_utc", "id", "varlik", "olay", "yon", "tip", "giris", "stop", "hedefler", "risk_usdt",
                        "miktar", "fiyat", "not"])
        w.writerow([O.fmt(O.now_utc()), t["id"], t["asset"], ev, t["side"], t["entry_type"], t["entry_price"],
                    t["stop"], "/".join(str(x) for x in t["targets"]), round(t.get("risk_usdt") or 0, 2),
                    t.get("qty"), t.get("_evpx"), note])


def mark_equity(st):
    eq = st["cash"]
    for t in live(st, "ofis", statuses=("open",)):
        px = st["last_px"].get(t["asset"])
        if px:
            eq += sgn(t["side"]) * (px - t["fill_px"]) * t["qty"]
    return eq


def open_risk_usdt(st):
    """Acik pozisyonlarin stopa kadar riski (T1 sonrasi girise cekilen stopta 0) + bekleyen emirlerin plan riski."""
    tot = 0.0
    for t in live(st, "ofis"):
        if t["status"] == "pending":
            tot += t["risk_usdt"]
        else:
            tot += max(0.0, sgn(t["side"]) * (t["fill_px"] - t["stop"]) * t["qty"])
    return tot


def stops_today(st):
    day = O.now_utc().strftime("%Y-%m-%d")
    return sum(1 for t in st["trades"] if t["book"] == "ofis" and t["status"] == "closed"
               and (t.get("exit_reason") or "").startswith("stop") and (t.get("r_mult") or 0) < 0
               and (t.get("exit_utc") or "").startswith(day))


def ledger_summary(st):
    eq = mark_equity(st)
    st["peak"] = max(st["peak"], eq)
    return {"equity_usdt": round(eq, 2), "cash_usdt": round(st["cash"], 2),
            "open_risk_pct": round(100 * open_risk_usdt(st) / eq, 3) if eq > 0 else None,
            "stops_today_utc": stops_today(st), "drawdown_from_peak_pct": round(100 * (1 - eq / st["peak"]), 2),
            "start_utc": st["start_utc"]}


def open_summary(st):
    out = []
    for t in live(st, "ofis"):
        out.append({k: t.get(k) for k in ("id", "asset", "side", "status", "entry_type", "entry_price", "fill_px",
                                          "stop", "targets", "qty", "t1_done", "created_utc", "fill_utc", "runs_left")})
    return out


def new_trade(st, book, asset, side, entry, stop, targets, horizon_h, risk_usdt, stamp, runs, conf=None, src=None):
    now = O.now_utc()
    t = {"id": st["next_id"], "book": book, "asset": asset, "side": side, "status": "pending",
         "entry_type": entry["type"], "entry_price": entry.get("price"), "stop": float(stop), "stop0": float(stop),
         "targets": [float(x) for x in targets], "horizon_h": int(horizon_h), "risk_usdt": float(risk_usdt),
         "confidence": conf, "run": stamp, "src": src, "created_utc": O.fmt(now), "created_ms": O.ms(now),
         "runs_left": runs, "expires_ms": O.ms(now) + (runs + 1) * H4, "qty": None, "qty0": None, "fill_px": None,
         "fill_ms": None, "fill_utc": None, "fees": 0.0, "funding": 0.0, "realized": 0.0, "t1_done": False,
         "exit_ms": None, "exit_utc": None, "exit_reason": None, "exit_px": None, "r_mult": None, "hit": None,
         "init_risk": None, "close_req_ms": None, "funding_missing": False, "note": ""}
    st["next_id"] += 1
    st["trades"].append(t)
    return t


def cancel(st, t, why):
    t["status"], t["note"] = "cancelled", why
    t["exit_utc"] = O.fmt(O.now_utc())
    event(st, t, "iptal", why)


# ---------------- ofis kararlari ----------------
def apply_decisions(st, decisions, snap, stamp, blocks):
    """decisions: sema-gecerli karar listesi. blocks: bu turun gecerli uzman bloklari (ufuk icin). Sonuc: [(asset, durum, not)]."""
    cfg = O.ayar()
    R = cfg["risk"]
    res = []
    by_asset = {d["asset"]: d for d in decisions}
    for asset in cfg["assets"]:
        a = (snap.get("assets") or {}).get(asset) or {}
        ctx = a.get("ctx") or {}
        last, atr4 = ctx.get("last_close"), (ctx.get("atr14") or {}).get("4h")
        if last and not live(st, None, asset):      # aktif islem varsa kontrol'un 1m fiyati daha yeni
            st["last_px"][asset] = last
        d = by_asset.get(asset) or {"decision": "none"}
        kind = d["decision"]
        # bekleyen emirler: keep degilse sayac duser, cancel_pending/open ise hemen iptal
        for t in live(st, "ofis", asset, ("pending",)):
            if kind == "keep":
                t["runs_left"] = R["pending_order_expiry_runs"]
                t["expires_ms"] = O.ms(O.now_utc()) + (t["runs_left"] + 1) * H4
            elif kind in ("cancel_pending", "open"):
                cancel(st, t, f"decision {kind}")
            else:
                t["runs_left"] -= 1
                if t["runs_left"] <= 0:
                    cancel(st, t, "expired (no keep)")
        if kind == "tighten_stop":
            for t in live(st, "ofis", asset):
                ns = d.get("stop")
                ref = st["last_px"].get(asset, last)
                ok = ns is not None and sgn(t["side"]) * (ns - t["stop"]) > 0 and sgn(t["side"]) * (ref - ns) > 0
                if ok:
                    old, t["stop"] = t["stop"], float(ns)
                    event(st, t, "stop_sikilastir", f"{old} -> {ns}")
                    res.append((asset, "tighten_stop", f"{old}->{ns}"))
                else:
                    event(st, t, "red", f"tighten_stop {ns} does not reduce risk (stop {t['stop']}, px {ref})")
                    res.append((asset, "rejected", f"tighten_stop {ns} not risk-reducing"))
        elif kind == "close":
            for t in live(st, "ofis", asset, ("open",)):
                t["close_req_ms"] = O.ms(O.now_utc())
                event(st, t, "kapat_istegi", d.get("reason", "")[:120])
                res.append((asset, "close", "at next 1m open"))
        elif kind == "open":
            ok, why, t = open_order(st, d, asset, last, atr4, snap, stamp, blocks, cfg)
            res.append((asset, "open" if ok else "rejected", why))
        else:
            res.append((asset, kind, ""))
    return res


def counter_regime(side, ctx):
    up = ctx.get("btc_above_sma200_1d")
    return up is not None and ((side == "long") != bool(up))


def event_blackout(snap, hours):
    cal = ((snap.get("macro") or {}).get("calendar_usd_high") or {}) if isinstance(snap.get("macro"), dict) else {}
    now = O.now_utc()
    for row in cal.get("rows") or []:
        try:
            t = O.parse_utc(row[0])
        except (ValueError, TypeError, IndexError):
            continue
        if now - dt.timedelta(hours=1) <= t <= now + dt.timedelta(hours=hours):
            return f"{row[0]} {row[1]}"
    return None


def open_order(st, d, asset, last, atr4, snap, stamp, blocks, cfg):
    R = cfg["risk"]
    side, entry, stop, targets = d.get("side"), d.get("entry"), d.get("stop"), d.get("targets") or []
    ctx = ((snap.get("assets") or {}).get(asset) or {}).get("ctx") or {}
    rej = None
    if side not in ("long", "short") or entry is None or stop is None or not targets:
        rej = "open without side/entry/stop/targets"
    elif last is None:
        rej = "no last_close in snapshot"
    else:
        g = O.geometry_errors(side, entry, stop, targets, last, atr4, R)
        if g:
            rej = "; ".join(g)
    if not rej and len(live(st, "ofis", asset)) >= R["max_positions_per_asset"]:
        rej = f"max_positions_per_asset {R['max_positions_per_asset']} reached"
    if not rej and stops_today(st) >= 2:
        rej = "R9 breaker: 2 losing stops today (UTC)"
    ev = None if rej else event_blackout(snap, R["event_blackout_h"])
    if ev:
        rej = f"R5 event blackout: {ev}"
    eq = mark_equity(st)
    rp = min(float(d.get("risk_pct") or 0), R["risk_pct_max"])
    notes = []
    if not rej and rp <= 0:
        rej = "risk_pct 0"
    if not rej and counter_regime(side, ctx) and rp > R["risk_pct_counter_regime"]:
        notes.append(f"counter-regime risk {rp}->{R['risk_pct_counter_regime']}")
        rp = R["risk_pct_counter_regime"]
    dd = 100 * (1 - eq / st["peak"]) if st["peak"] else 0
    if not rej and dd >= 10:
        notes.append(f"drawdown {dd:.1f}% >= 10: risk halved")
        rp /= 2
    if not rej:
        room = R["max_open_risk_pct"] - 100 * open_risk_usdt(st) / eq
        if room < rp:
            if room < 0.25:
                rej = f"open risk full ({R['max_open_risk_pct'] - room:.2f}% of {R['max_open_risk_pct']}%)"
            else:
                notes.append(f"risk {rp}->{room:.2f} to fit max_open_risk_pct")
                rp = room
    if rej:
        t = {"id": None, "book": "ofis", "asset": asset, "side": side, "entry_type": (entry or {}).get("type"),
             "entry_price": (entry or {}).get("price"), "stop": stop, "targets": targets, "risk_usdt": 0}
        event(st, t, "red", rej)
        return False, rej, None
    hz = [b["horizon_h"] for b in blocks if b["asset"] == asset and b["bias"] == side and b["expert"] in d.get("supporting", [])]
    horizon = max(hz) if hz else 72
    t = new_trade(st, "ofis", asset, side, entry, stop, targets[:2], horizon, eq * rp / 100, stamp,
                  R["pending_order_expiry_runs"], src="trader-risk")
    t["risk_pct"] = round(rp, 3)
    t["note"] = "; ".join(notes)
    event(st, t, "emir", f"risk {rp:.2f}% {'; '.join(notes)}")
    return True, f"risk {rp:.2f}% " + "; ".join(notes), t


# ---------------- golge islemler ----------------
def add_shadow(st, blocks, called, stamp, snap):
    """blocks: bu tur uretilen gecerli bloklar; called: bu tur cagrilan uzmanlar (gecersiz/zaman asimi dahil)."""
    R = O.ayar()["risk"]
    seen = set()
    for b in blocks:
        ex, asset = b["expert"], b["asset"]
        seen.add((ex, asset))
        ctx = ((snap.get("assets") or {}).get(asset) or {}).get("ctx") or {}
        cur = live(st, ex, asset)
        pend = [t for t in cur if t["status"] == "pending"]
        opn = [t for t in cur if t["status"] == "open"]
        if b["bias"] in ("long", "short") and b["action"] in ("new", "keep"):
            if opn:
                continue                      # acik golge islem varken yeni islem acilmaz
            if pend and b["action"] == "keep":
                for t in pend:
                    t["runs_left"] = R["pending_order_expiry_runs"]
                    t["expires_ms"] = O.ms(O.now_utc()) + (t["runs_left"] + 1) * H4
                continue
            for t in pend:
                cancel(st, t, "replaced by new block")
            new_trade(st, ex, asset, b["bias"], b["entry"], b["stop"], b["targets"], b["horizon_h"], SHADOW_RISK,
                      stamp, R["pending_order_expiry_runs"], conf=b["confidence"],
                      src={"setup": b.get("setup"), "tf": b.get("timeframe"), "last_close": ctx.get("last_close")})
        else:
            for t in pend:
                cancel(st, t, f"block {b['action']}/{b['bias']}")
    for ex in called:                         # cagrildi ama o varlik icin gecerli blok yok: keep sayilmaz
        for t in live(st, ex, statuses=("pending",)):
            if (ex, t["asset"]) not in seen:
                t["runs_left"] -= 1
                if t["runs_left"] <= 0:
                    cancel(st, t, "expired (no valid block)")


# ---------------- 1m mum isleme ----------------
def funding_rate(st, sym, fms):
    key = f"{sym}|{fms}"
    if key in st["funding_cache"]:
        return st["funding_cache"][key]
    try:
        r = requests.get(f"{O.FAPI}/fapi/v1/fundingRate", params={"symbol": sym, "startTime": fms - 60000,
                                                                   "endTime": fms + 60000, "limit": 5},
                         headers=O.UA, timeout=15)
        r.raise_for_status()
        rows = r.json()
        rate = float(rows[0]["fundingRate"]) if rows else None
    except Exception:  # noqa: BLE001
        rate = None
    if rate is not None:
        st["funding_cache"][key] = rate
    return rate


def close_part(st, t, qty, px, fee, reason, when_ms):
    pnl = sgn(t["side"]) * (px - t["fill_px"]) * qty - fee * px * qty
    t["realized"] += pnl
    t["fees"] += fee * px * qty
    t["qty"] -= qty
    t["_exits"] = t.get("_exits", []) + [[qty, px]]
    if t["book"] == "ofis":
        st["cash"] += pnl
        t["_evpx"] = round(px, 6)
        event(st, t, reason, f"qty {qty:.6g} @ {px:.6g}")
    if t["qty"] <= 1e-12:
        q = sum(e[0] for e in t["_exits"])
        t["exit_px"] = sum(e[0] * e[1] for e in t["_exits"]) / q if q else px
        t["status"], t["exit_ms"], t["exit_utc"] = "closed", when_ms, O.fmt(O.from_ms(when_ms))
        t["exit_reason"] = reason
        t["r_mult"] = round(t["realized"] / t["init_risk"], 4) if t["init_risk"] else None
        if t["hit"] is None:
            t["hit"] = bool(t["t1_done"])


def process_candles(st, sym, candles, funding_ok=True):
    """candles: [[open_ms, o, h, l, c], ...] kapanmis 1m mumlar, artan sirada. Donus: olay sayisi."""
    R = O.ayar()["risk"]
    slip, ft, fm, frac = R["slippage"], R["fee_taker"], R["fee_maker"], R["t1_close_fraction"]
    n = 0
    trades = [t for t in st["trades"] if t["asset"] == sym and t["status"] in ("pending", "open")]
    for om, o, h, l, c in candles:
        for t in trades:
            if t["status"] not in ("pending", "open"):
                continue
            s = sgn(t["side"])
            # fonlama (00/08/16 UTC), mumun acilisinda acik pozisyon
            if t["status"] == "open" and om % (8 * 3600 * 1000) == 0 and t["fill_ms"] < om:
                rate = funding_rate(st, sym, om) if funding_ok else None
                if rate is None:
                    t["funding_missing"] = True
                else:
                    f = rate * o * t["qty"] * s          # long pozitif oranda oder
                    t["funding"] += f
                    t["realized"] -= f
                    if t["book"] == "ofis":
                        st["cash"] -= f
            if t["status"] == "pending":
                if om < t["created_ms"]:
                    continue
                if om >= t["expires_ms"]:
                    cancel(st, t, "expired (time)")
                    n += 1
                    continue
                P, typ, fill, fee = t["entry_price"], t["entry_type"], None, ft
                if typ == "market":
                    fill = o * (1 + s * slip)
                elif typ == "limit":
                    if s * (P - o) >= 0:
                        fill, fee = o, fm
                    elif (l <= P * (1 - slip)) if s > 0 else (h >= P * (1 + slip)):
                        fill, fee = P, fm
                else:  # stop giris
                    if s * (o - P) >= 0:
                        fill = o * (1 + s * slip)
                    elif (h >= P) if s > 0 else (l <= P):
                        fill = P * (1 + s * slip)
                if fill is None:
                    continue
                dist = s * (fill - t["stop"])
                if dist <= 0:
                    cancel(st, t, f"fill {fill:.6g} beyond stop {t['stop']}")
                    n += 1
                    continue
                qty = t["risk_usdt"] / dist
                if t["book"] == "ofis":
                    cap = R["max_leverage"] * mark_equity(st) / fill
                    if qty > cap:
                        t["note"] = (t["note"] + f"; qty capped by {R['max_leverage']}x").strip("; ")
                        qty = cap
                t.update(status="open", fill_px=fill, fill_ms=om, fill_utc=O.fmt(O.from_ms(om)), qty=qty, qty0=qty,
                         init_risk=qty * dist)
                t["fees"] += fee * fill * qty
                t["realized"] -= fee * fill * qty
                if t["book"] == "ofis":
                    st["cash"] -= fee * fill * qty
                    t["_evpx"] = round(fill, 6)
                    event(st, t, "dolum", f"fee {'maker' if fee == fm else 'taker'}")
                n += 1
            # acik pozisyon: once acilista kapanis (sure doldu / karar), sonra stop, T1, T2
            if t["status"] != "open":
                continue
            if t["close_req_ms"] and om >= t["close_req_ms"]:
                close_part(st, t, t["qty"], o * (1 - s * slip), ft, "karar_kapat", om)
                n += 1
                continue
            if om >= t["fill_ms"] + t["horizon_h"] * 3600 * 1000:
                close_part(st, t, t["qty"], o * (1 - s * slip), ft, "sure_doldu", om)
                n += 1
                continue
            stop = t["stop"]
            if (l <= stop) if s > 0 else (h >= stop):
                px = (min(stop, o) if s > 0 else max(stop, o)) * (1 - s * slip)
                close_part(st, t, t["qty"], px, ft, "stop_giris" if t["t1_done"] else "stop", om)
                n += 1
                continue
            tg = t["targets"]
            if not t["t1_done"] and ((h >= tg[0]) if s > 0 else (l <= tg[0])):
                t["hit"] = True
                if len(tg) == 1:
                    close_part(st, t, t["qty"], tg[0], fm, "hedef1", om)
                    n += 1
                    continue
                close_part(st, t, t["qty"] * frac, tg[0], fm, "hedef1_kismi", om)
                t["t1_done"] = True
                if R["move_stop_to_entry_after_t1"]:
                    t["stop"] = t["fill_px"]
                n += 1
            if t["t1_done"] and len(tg) > 1 and ((h >= tg[1]) if s > 0 else (l <= tg[1])):
                close_part(st, t, t["qty"], tg[1], fm, "hedef2", om)
                n += 1
        if candles:
            st["last_px"][sym] = c
    for t in trades:
        t.pop("_evpx", None)
    return n


# ---------------- puan ----------------
def bootstrap_ci(x, q=(5, 95), n=2000):
    x = np.asarray(x, float)
    if len(x) < 2:
        return [None, None]
    rng = np.random.default_rng(7)
    m = rng.choice(x, (n, len(x))).mean(axis=1)
    return [round(float(np.percentile(m, q[0])), 3), round(float(np.percentile(m, q[1])), 3)]


def scores(st):
    cfg = O.ayar()
    sig = O.read_jsonl(O.DEFTER / "sinyaller.jsonl")
    out = {}
    for e in cfg["experts"]:
        ex = e["id"]
        rows = [s for s in sig if s.get("expert") == ex and not s.get("reused")]
        blocks = [s for s in rows if s.get("valid")]
        flat = [s for s in blocks if (s.get("block") or {}).get("bias") == "flat"]
        sh = [t for t in st["trades"] if t["book"] == ex]
        closed = [t for t in sh if t["status"] == "closed" and t["r_mult"] is not None]
        filled = [t for t in sh if t["fill_ms"]]
        decided = [t for t in sh if t["status"] in ("closed", "cancelled") or t["fill_ms"]]
        rs = [t["r_mult"] for t in closed]
        cum = np.cumsum(rs) if rs else np.array([0.0])
        dd = float((np.maximum.accumulate(np.concatenate([[0], cum])) - np.concatenate([[0], cum])).max())
        brier = [((t["confidence"] or 0) / 100 - (1 if t["hit"] else 0)) ** 2 for t in closed]
        buckets = {}
        for lo, hi in ((55, 62), (63, 72), (73, 80)):
            b = [t for t in closed if lo <= (t["confidence"] or 0) <= hi]
            buckets[f"{lo}-{hi}"] = [len(b), round(sum(1 for t in b if t["hit"]) / len(b), 3) if b else None]
        hold = [(t["exit_ms"] - t["fill_ms"]) / 3.6e6 for t in closed]
        runs = len({s.get("run") for s in rows})
        exp_blocks = runs * len(cfg["assets"])
        out[ex] = {"name": e["name"], "enabled": e["enabled"], "rounds": runs, "valid_blocks": len(blocks),
                   "invalid_rate": round(1 - len(blocks) / exp_blocks, 3) if exp_blocks else None,
                   "flat_rate": round(len(flat) / len(blocks), 3) if blocks else None,
                   "shadow_trades": len(sh), "fill_rate": round(len(filled) / len(decided), 3) if decided else None,
                   "closed": len(closed), "hit_rate": round(sum(1 for t in closed if t["hit"]) / len(closed), 3) if closed else None,
                   "avg_r": round(float(np.mean(rs)), 3) if rs else None, "total_r": round(float(np.sum(rs)), 3) if rs else 0.0,
                   "ev_r_ci90": bootstrap_ci(rs) if len(rs) >= 30 else [None, None],
                   "max_dd_r": round(dd, 3), "avg_hold_h": round(float(np.mean(hold)), 1) if hold else None,
                   "brier": round(float(np.mean(brier)), 4) if brier else None, "conf_buckets": buckets}
    return out


# ---------------- karsilastirma ----------------
def refresh_paper(st):
    """Paper sistemlerin ozsermaye.csv'si GitHub dalindan (git fetch + git show); hata olursa onbellek kalir."""
    try:
        kw = dict(cwd=str(O.REPO), capture_output=True, text=True, timeout=60,
                  creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        subprocess.run(["git", "fetch", "-q", "origin", PAPER_FETCH], **kw)
        r = subprocess.run(["git", "show", f"{PAPER_REF}:algo/paper/ozsermaye.csv"], **kw)
        if r.returncode != 0:
            return
        rows = list(csv.DictReader(io.StringIO(r.stdout)))
        start = st["start_utc"]
        res = {}
        for sysname in dict.fromkeys(x["sistem"] for x in rows):
            xs = [x for x in rows if x["sistem"] == sysname]
            base = [x for x in xs if start and x["zaman_utc"] <= start] or xs[:1]
            b, l = float(base[-1]["paper"]), float(xs[-1]["paper"])
            res[sysname] = {"ret_pct": round(100 * (l / b - 1), 2), "asof": xs[-1]["zaman_utc"],
                            "open": xs[-1].get("acik", "")}
        st["paper_cache"] = res
    except Exception as e:  # noqa: BLE001
        O.log("defter.log", f"paper refresh failed: {type(e).__name__} {e}")


# ---------------- raporlar ----------------
TCOLS = ["id", "book", "asset", "side", "status", "entry_type", "entry_price", "fill_px", "stop0", "stop", "targets",
         "confidence", "horizon_h", "created_utc", "fill_utc", "exit_utc", "exit_reason", "exit_px", "qty0",
         "risk_usdt", "fees", "funding", "realized", "r_mult", "hit", "funding_missing", "note"]


def write_csv(path, trades):
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(TCOLS)
        for t in trades:
            row = []
            for k in TCOLS:
                v = t.get(k)
                if k == "targets":
                    v = "/".join(f"{x:g}" for x in v)
                elif isinstance(v, float):
                    v = round(v, 6)
                row.append(v)
            w.writerow(row)


def append_equity(st):
    f = O.DEFTER / "ozsermaye.csv"
    new = not f.exists()
    with open(f, "a", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        if new:
            w.writerow(["zaman_utc", "ozsermaye", "nakit", "acik_risk_pct", "btc", "eth"])
        L = ledger_summary(st)
        w.writerow([O.fmt(O.now_utc()), L["equity_usdt"], L["cash_usdt"], L["open_risk_pct"],
                    st["last_px"].get("BTCUSDT"), st["last_px"].get("ETHUSDT")])


def tr(x, d=2):
    if x is None:
        return "-"
    s = f"{x:,.{d}f}"
    return s.replace(",", "X").replace(".", ",").replace("X", ".")


def write_reports(st):
    O.DEFTER.mkdir(parents=True, exist_ok=True)
    write_csv(O.DEFTER / "islemler.csv", [t for t in st["trades"] if t["book"] == "ofis" and t["status"] != "pending"])
    write_csv(O.DEFTER / "golge.csv", [t for t in st["trades"] if t["book"] != "ofis"])
    sc = scores(st)
    O.write_json(O.DEFTER / "puan.json", sc)
    cfg = O.ayar()
    L = ledger_summary(st)
    start_eq = cfg["risk"]["start_equity_usdt"]
    lines = ["# Trader ofisi durumu (sahte para)", "",
             f"Son güncelleme: {O.fmt(O.now_utc())} UTC. Başlangıç: {st['start_utc'] or '-'} UTC, "
             f"{tr(start_eq, 0)} sahte USDT. Gerçek emir yok, borsa anahtarı yok.", ""]
    lines += ["## Ofis", "", "| Öz sermaye | Getiri | Tepeden düşüş | Açık risk | Bugün stop | Kapanan işlem |",
              "|---|---|---|---|---|---|"]
    closed = [t for t in st["trades"] if t["book"] == "ofis" and t["status"] == "closed"]
    lines.append(f"| {tr(L['equity_usdt'])} | %{tr(100 * (L['equity_usdt'] / start_eq - 1))} | "
                 f"%{tr(L['drawdown_from_peak_pct'])} | %{tr(L['open_risk_pct'])} | {L['stops_today_utc']} | {len(closed)} |")
    lines += ["", "### Açık pozisyon ve bekleyen emir", ""]
    lv = live(st, "ofis")
    if not lv:
        lines.append("Yok.")
    else:
        lines += ["| Varlık | Yön | Durum | Giriş | Stop | Hedefler | Açılış |", "|---|---|---|---|---|---|---|"]
        for t in lv:
            lines.append(f"| {t['asset']} | {t['side']} | {'açık' if t['status'] == 'open' else 'bekliyor'} | "
                         f"{tr(t['fill_px'] or t['entry_price'] or 0)}{'' if t['fill_px'] or t['entry_type'] != 'market' else ' (piyasa)'} | "
                         f"{tr(t['stop'])} | {' / '.join(tr(x) for x in t['targets'])} | {t['fill_utc'] or t['created_utc']} |")
    lines += ["", "### Son karar (Rıza)", ""]
    for a, d in (st.get("last_decisions") or {}).items():
        lines.append(f"- {a} ({d.get('asof_utc')}): **{d.get('decision')}** — {d.get('neco_tr')}")
    lines += ["", "## Karşılaştırma (ofis başlangıcından bu yana)", "", "| Ölçü | Getiri |", "|---|---|",
              f"| Ofis | %{tr(100 * (L['equity_usdt'] / start_eq - 1))} |"]
    sp, lp = st.get("start_px") or {}, st.get("last_px") or {}
    bh = {}
    for a in ("BTCUSDT", "ETHUSDT"):
        if sp.get(a) and lp.get(a):
            bh[a] = 100 * (lp[a] / sp[a] - 1)
            lines.append(f"| {a[:3]} al-tut | %{tr(bh[a])} |")
    if len(bh) == 2:
        lines.append(f"| 50/50 BTC-ETH | %{tr(sum(bh.values()) / 2)} |")
    for k, v in (st.get("paper_cache") or {}).items():
        lines.append(f"| Paper: {k} | %{tr(v['ret_pct'])} (son kayıt {v['asof']}) |")
    lines += ["", "## Uzmanlar (gölge işlem, her biri 1R sabit risk)", "",
              "| Uzman | Tur | Geçerli | Flat oranı | Gölge işlem | Kapanan | İsabet | Ort. R | Toplam R | Brier |",
              "|---|---|---|---|---|---|---|---|---|---|"]
    for ex, s in sc.items():
        if not s["rounds"] and not s["enabled"]:
            continue
        pct = lambda v: "-" if v is None else f"%{tr(100 * v, 0)}"  # noqa: E731
        lines.append(f"| {s['name']} ({ex.replace('trader-', '')}) | {s['rounds']} | {s['valid_blocks']} | {pct(s['flat_rate'])} | "
                     f"{s['shadow_trades']} | {s['closed']} | {pct(s['hit_rate'])} | {tr(s['avg_r'])} | {tr(s['total_r'])} | "
                     f"{tr(s['brier'], 3)} |")
    lines += ["", "Not: İsabet = ilk hedef stoptan önce geldi. Brier 0,25 altı yazı-turadan iyi. "
              "Hiçbir uzman 30 kapanmış işlem ve 3 ay dolmadan değerlendirilmez (TASARIM.md bölüm 5).", ""]
    (O.ROOT / "DURUM.md").write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "rapor":
        with O.Kilit(wait_s=60) as k:
            if not k.ok:
                sys.exit("defter kilitli")
            s = load_state()
            refresh_paper(s)
            write_reports(s)
            save_state(s)
            print("ok")
