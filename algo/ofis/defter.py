"""Trader ofisi sahte defteri. LLM yok; sinirlar burada KODLA uygulanir (ofis-ayar.json).

- apply_decisions: Riza'nin (trader-risk) kararlarini sinir denetimiyle deftere isler.
  Kodla: validate_open (R1 oy gecerliligi + esik, R2 catisma, R3 >=2 oy + seviye uzmani, R4 rejime karsi >=3 oy,
  R6 iki karsi baglam, R7 seviyeler oylardan), R:R (maliyet dahil), stop/giris mesafesi, R5 takvim (veri yoksa
  kapali), R9 gunluk stop + dusus, acik risk, toplam kaldirac, ayni yon altcoin, net beta.
  Kodla degil: R5 `CONTEXT: event-risk` etiketi, R8 buyutme kosullari (risk_pct_max = default oldugundan etkisiz), R10.
- add_shadow: her gecerli uzman long/short blogu icin 1R'lik golge islem (risk karari ne olursa olsun).
- process_candles: 1m mumlarla dolum, stop, hedef, sure dolumu, fonlama (kontrol.py ve tur.py cagirir).
- write_reports: defter/*.csv, puan.json, bloklar.csv (blok puani), DURUM.md (Turkce ozet).
- mark_failed_round / clear_failed_round: DURUM.md basina basarisiz tur satiri.
- save_state: her yazimdan sonra defter/_yedek/state_<YYYYMMDD_HH>.json (saatlik, son N).

Kullanim: python algo/ofis/defter.py rapor    # raporlari state.json'dan yeniden yazar
"""
import csv
import datetime as dt
import io
import json
import shutil
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
# Neco'nun sabit kararlari (2026-11-21): ayar daha gevsek yazilsa da kod bunlari asmaz
OWNER_CAPS = {"risk_pct_max": 1.0, "max_leverage": 2.0, "max_open_risk_pct": 3.0, "max_same_dir_alts": 2}
# altyapi hatasi (uzmanin hatasi degil): golge sayaci dusmez, tur sayilmaz
INFRA_ERR = ("cli error", "timeout", "claude CLI not found", "non-json output", "no result")


def cap(R, k):
    return min(R.get(k, OWNER_CAPS[k]), OWNER_CAPS[k])


def is_infra_error(errors):
    return bool(errors) and all(any(str(e).startswith(p) for p in INFRA_ERR) for e in errors)


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
    backup_state()


def backup_state(keep=None):
    """state.json'un saatlik kopyasi (ayni saatte uzerine yazar), en yeni `keep` tanesi kalir. Hata defteri durdurmaz."""
    try:
        if keep is None:
            keep = int(O.ayar().get("measure", {}).get("state_backups_keep", 30))
        d = O.DEFTER / "_yedek"
        d.mkdir(parents=True, exist_ok=True)
        tmp = d / "state.tmp"
        shutil.copyfile(STATE, tmp)
        tmp.replace(d / f"state_{O.now_utc().strftime('%Y%m%d_%H')}.json")
        for f in sorted(d.glob("state_*.json"))[:-keep]:
            f.unlink()
    except Exception as e:  # noqa: BLE001
        O.log("defter.log", f"state backup failed: {type(e).__name__} {e}")


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
    return sum(trade_risk(t) for t in live(st, "ofis"))


def trade_risk(t):
    if t["status"] == "pending":
        return t["risk_usdt"]
    return max(0.0, sgn(t["side"]) * (t["fill_px"] - t["stop"]) * t["qty"])


def beta_w(asset, beta, clip=None):
    """BTC riski esdegeri carpani: BTC 1; altcoin 30g beta, kararsiz tahmine karsi risk.beta_clip araliginda."""
    if asset == "BTCUSDT":
        return 1.0
    lo, hi = clip or O.ayar()["risk"].get("beta_clip", [0.5, 2.0])
    return min(hi, max(lo, beta if isinstance(beta, (int, float)) else 1.0))


def trade_notional(st, t):
    """Acik: miktar x son fiyat. Bekleyen (dolarsa): plan riski / stop mesafesi x giris."""
    if t["status"] == "open":
        return abs(t["qty"] or 0) * (st["last_px"].get(t["asset"]) or t["fill_px"])
    e = t["entry_price"] or st["last_px"].get(t["asset"])
    if not e or e == t["stop"]:
        return 0.0
    return t["risk_usdt"] / abs(e - t["stop"]) * e


def open_notional(st, exclude=None):
    """Ofisin toplam pozisyon buyuklugu (acik + dolacak bekleyen), USDT."""
    return sum(trade_notional(st, t) for t in live(st, "ofis") if t is not exclude)


def net_beta_risk_usdt(st):
    """Isaretli BTC-beta riski: long +, short -, her islem riski x beta (TASARIM.md 13)."""
    clip = O.ayar()["risk"].get("beta_clip", [0.5, 2.0])
    return sum(sgn(t["side"]) * beta_w(t["asset"], t.get("beta"), clip) * trade_risk(t) for t in live(st, "ofis"))


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
            "gross_leverage_x": round(open_notional(st) / eq, 3) if eq > 0 else None,
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
    # tur varliklari: snapshot'taki analiz edilen coinler (evren/tarayici acikken secilenler; BTC baglam blogu haric)
    round_assets = [s for s, x in (snap.get("assets") or {}).items() if not (x or {}).get("_context_only")]
    for s, x in (snap.get("assets") or {}).items():   # BTC baglamdayken de al-tut fiyati guncellensin
        lc = ((x or {}).get("ctx") or {}).get("last_close")
        if lc and s not in round_assets and not live(st, None, s):
            st["last_px"][s] = lc
    for asset in round_assets or cfg["assets"]:
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


def event_blackout(snap, hours, required=True):
    """Takvimde yakin yuksek etkili USD olayi -> neden metni. Takvim verisi yoksa (required) kapali kalir: yeni acilis yok."""
    macro = snap.get("macro") if isinstance(snap.get("macro"), dict) else None
    cal = (macro or {}).get("calendar_usd_high")
    if not isinstance(cal, dict) or not isinstance(cal.get("rows"), list):
        return "no calendar/macro data in snapshot (fail closed)" if required else None
    now = O.now_utc()
    for row in cal["rows"]:
        try:
            t = O.parse_utc(row[0])
        except (ValueError, TypeError, IndexError):
            continue
        if now - dt.timedelta(hours=1) <= t <= now + dt.timedelta(hours=hours):
            return f"{row[0]} {row[1]}"
    return None


def context_tag(b):
    """Flat blogun CONTEXT etiketi (rationale ilk maddesi): 'against-long' / 'against-short' / 'event-risk' / 'neutral' / None."""
    r = (b.get("rationale") or [""])[0] if isinstance(b.get("rationale"), list) and b.get("rationale") else ""
    if not isinstance(r, str) or not r.strip().upper().startswith("CONTEXT:"):
        return None
    body = r.split(":", 1)[1].strip().lower()
    for tag in ("against-long", "against-short", "event-risk", "neutral"):
        if body.startswith(tag):
            return tag
    return None


def _age_h(a, b):
    try:
        return (O.parse_utc(a) - O.parse_utc(b)).total_seconds() / 3600
    except (TypeError, ValueError):
        return None


def vote_check(b, asset, asof, cfg, snap):
    """Blok bu varlikta gecerli oy mu (R1): bu turun asof'u (makro: son macro_vote_max_age_h saat), long/short,
    new/keep, geometri + R:R (maliyet dahil), oy esigi (vote_rule). Donus (oy_mu, neden)."""
    R = cfg["risk"]
    if not isinstance(b, dict) or b.get("asset") != asset:
        return False, "other asset"
    if b.get("bias") not in ("long", "short") or b.get("action") not in ("new", "keep"):
        return False, f"{b.get('expert')}: not a directional new/keep block"
    age = _age_h(asof, b.get("asof_utc"))
    max_age = R.get("macro_vote_max_age_h", 12) if b.get("expert") == "trader-makro" else 0
    if age is None or age < 0 or age > max_age + 1e-9:
        return False, f"{b.get('expert')}: block asof {b.get('asof_utc')} not this round ({asof})"
    ctx = (((snap or {}).get("assets") or {}).get(asset) or {}).get("ctx") or {}
    last, atr4 = ctx.get("last_close"), (ctx.get("atr14") or {}).get("4h")
    if last is None:
        return False, f"{b.get('expert')}: no snapshot last_close for {asset}"
    g = O.geometry_errors(b["bias"], b.get("entry"), b.get("stop"), b.get("targets") or [], last, atr4, R)
    if g:
        return False, f"{b.get('expert')}: " + "; ".join(g)
    rr, cost_r, _ = O.rr_cost(b["bias"], b["entry"], b["stop"], b["targets"][0], last, R)
    ok, why = O.vote_passes(b.get("confidence"), rr, cost_r, R)
    return ok, f"{b.get('expert')}: {why}"


def validate_open(decision, blocks, cfg, snap=None, log=True):
    """Riza'nin 'open' kararini bu turun bloklariyla kodla yeniden denetler (R1-R4, R6, R7).
    decision: sema 'decision' nesnesi; blocks: bu turun karar bloklari (gecerli + yeniden kullanilan; tur.py dec_blocks);
    cfg: O.ayar() (tur.py'de assets guncellenmis hali); snap: tur snapshot'i (market giris / ATR / rejim icin gerekli).
    Donus (ok: bool, reason: str). Red defter.log'a yazilir (log=True)."""
    R = cfg["risk"]
    d = decision or {}
    asset, side, asof = d.get("asset"), d.get("side"), d.get("asof_utc")
    rej, info = None, ""
    if d.get("decision") != "open":
        rej = f"not an open decision ({d.get('decision')})"
    elif side not in ("long", "short") or not d.get("entry") or d.get("stop") is None or not d.get("targets"):
        rej = "open without side/entry/stop/targets"
    if not rej:
        ctx = (((snap or {}).get("assets") or {}).get(asset) or {}).get("ctx") or {}
        last, atr4 = ctx.get("last_close"), (ctx.get("atr14") or {}).get("4h")
        votes, dropped = [], []
        for b in blocks or []:
            if isinstance(b, dict) and b.get("asset") == asset:
                ok, why = vote_check(b, asset, asof, cfg, snap)
                (votes if ok else dropped).append(b if ok else why)
        same = {b["expert"]: b for b in votes if b["bias"] == side}
        opp = sorted({b["expert"] for b in votes if b["bias"] != side})
        sup_ids = set(d.get("supporting") or [])
        sup = [b for ex, b in same.items() if ex in sup_ids]
        need = R.get("min_votes", 2)
        if counter_regime(side, ctx):
            need = max(need, R.get("min_votes_counter_regime", 3))
        lvl = set(R.get("level_experts") or [])
        def fresh(b):
            a = _age_h(asof, b.get("asof_utc"))
            return a is not None and 0 <= a <= (R.get("macro_vote_max_age_h", 12) if b.get("expert") == "trader-makro" else 0)
        flat_ctx = [b for b in blocks or [] if isinstance(b, dict) and b.get("asset") == asset and b.get("bias") == "flat"
                    and b.get("expert") in ("trader-turev", "trader-makro") and context_tag(b) == f"against-{side}"
                    and fresh(b)]
        if opp:
            rej = f"R2-conflict: valid {'short' if side == 'long' else 'long'} votes {opp}"
        elif len(sup) < need:
            rej = (f"R3/R4-support: {len(sup)} valid {side} supporting votes {sorted(x['expert'] for x in sup)} < {need}"
                   f"{' (counter-regime)' if need > R.get('min_votes', 2) else ''}; listed {sorted(sup_ids)}"
                   + (f"; not votes: {' | '.join(dropped)[:200]}" if dropped else ""))
        elif lvl and not any(b["expert"] in lvl for b in sup):
            rej = "R3-support: no level expert among supporting votes"
        elif len({b["expert"] for b in flat_ctx}) >= 2:
            rej = f"R6-context: both derivatives and macro CONTEXT against-{side}"
        else:
            px = O.entry_px(d["entry"], last)
            if px is None:
                rej = "R7-levels: cannot price decision entry (no last_close)"
            else:
                tol = max(R.get("level_tol_pct", 0.1) / 100 * px, R.get("level_tol_atr4h", 0.1) * (atr4 or 0))
                near = lambda x, xs: any(y is not None and abs(x - y) <= tol + 1e-12 for y in xs)  # noqa: E731
                ents = [O.entry_px(b["entry"], last) for b in sup]
                if not near(px, ents):
                    rej = f"R7-levels: entry {px} not within {tol:.4g} of a supporting vote entry {ents}"
                elif not near(float(d["stop"]), [b["stop"] for b in sup]):
                    rej = f"R7-levels: stop {d['stop']} not within {tol:.4g} of a supporting vote stop {[b['stop'] for b in sup]}"
                else:
                    tg = [x for b in sup for x in b["targets"]]
                    bad = [x for x in d["targets"] if not near(float(x), tg)]
                    if bad:
                        rej = f"R7-levels: targets {bad} not within {tol:.4g} of supporting vote targets {tg}"
            info = f"votes {sorted(b['expert'] for b in sup)} (need {need})"
    if rej:
        if log:
            O.log("defter.log", f"validate_open REJECT {asset} {side}: {rej}")
        return False, rej
    return True, info


def open_order(st, d, asset, last, atr4, snap, stamp, blocks, cfg):
    R = cfg["risk"]
    side, entry, stop, targets = d.get("side"), d.get("entry"), d.get("stop"), d.get("targets") or []
    ctx = ((snap.get("assets") or {}).get(asset) or {}).get("ctx") or {}
    min_room = R.get("min_room_pct", 0.25)
    rej = None
    if side not in ("long", "short") or entry is None or stop is None or not targets:
        rej = "open without side/entry/stop/targets"
    elif last is None:
        rej = "no last_close in snapshot"
    else:
        g = O.geometry_errors(side, entry, stop, targets, last, atr4, R)
        if g:
            rej = "; ".join(g)
    if not rej:   # Riza'nin kurallari kodla (tur.py ayrica cagirmasa da)
        ok, why = validate_open(d, blocks, cfg, snap, log=False)
        if not ok:
            rej = why
    if not rej and len(live(st, "ofis", asset)) >= R["max_positions_per_asset"]:
        rej = f"max_positions_per_asset {R['max_positions_per_asset']} reached"
    if not rej and stops_today(st) >= R.get("max_stops_per_day", 2):
        rej = f"R9 breaker: {R.get('max_stops_per_day', 2)} losing stops today (UTC)"
    ev = None if rej else event_blackout(snap, R["event_blackout_h"], R.get("calendar_required", True))
    if ev:
        rej = f"R5 event blackout: {ev}"
    eq = mark_equity(st)
    rp = min(float(d.get("risk_pct") or 0), cap(R, "risk_pct_max"))
    notes = []
    if not rej and rp <= 0:
        rej = "risk_pct 0"
    if not rej and counter_regime(side, ctx) and rp > R["risk_pct_counter_regime"]:
        notes.append(f"counter-regime risk {rp}->{R['risk_pct_counter_regime']}")
        rp = R["risk_pct_counter_regime"]
    dd = 100 * (1 - eq / st["peak"]) if st["peak"] else 0
    if not rej and dd >= R.get("dd_halving_pct", 10.0):
        notes.append(f"drawdown {dd:.1f}% >= {R.get('dd_halving_pct', 10.0)}: risk halved")
        rp /= 2
    bw = beta_w(asset, ctx.get("beta_btc_30d"), R.get("beta_clip"))
    if not rej and asset != "BTCUSDT":     # korelasyon: ayni yonde en cok N altcoin (acik + bekleyen)
        same = [t["asset"] for t in live(st, "ofis") if t["asset"] not in ("BTCUSDT", asset) and t["side"] == side]
        if len(same) >= cap(R, "max_same_dir_alts"):
            rej = f"R11 correlation: already {len(same)} {side} alt positions {same} (max {cap(R, 'max_same_dir_alts')})"
    if not rej and R.get("max_net_beta_risk_pct"):   # altcoin = beta x BTC riski; net yonlu BTC-beta riski sinirli
        nb = 100 * sgn(side) * net_beta_risk_usdt(st) / eq     # bu yondeki mevcut net beta riski (%)
        room_b = (R["max_net_beta_risk_pct"] - nb) / bw
        if room_b < rp:
            if room_b < min_room:
                rej = f"R11 BTC-beta exposure full ({nb:.2f}% of {R['max_net_beta_risk_pct']}% {side}, beta {bw})"
            else:
                notes.append(f"risk {rp}->{room_b:.2f} to fit max_net_beta_risk_pct (beta {bw})")
                rp = room_b
    if not rej:
        mo = cap(R, "max_open_risk_pct")
        room = mo - 100 * open_risk_usdt(st) / eq
        if room < rp:
            if room < min_room:
                rej = f"open risk full ({mo - room:.2f}% of {mo}%)"
            else:
                notes.append(f"risk {rp}->{room:.2f} to fit max_open_risk_pct")
                rp = room
    if not rej:   # toplam kaldirac: yeni buyukluk <= max_leverage x ozsermaye - mevcut (acik + bekleyen) buyukluk
        lev = cap(R, "max_leverage")
        e = O.entry_px(entry, last)
        dist = abs(e - float(stop))
        room_n = lev * eq - open_notional(st)
        new_n = eq * rp / 100 / dist * e
        if new_n > room_n:
            rp_fit = max(0.0, room_n) * dist / e / eq * 100
            if rp_fit < min_room:
                rej = f"leverage full: total notional {open_notional(st) / eq:.2f}x + new would exceed {lev}x"
            else:
                notes.append(f"risk {rp:.2f}->{rp_fit:.2f} to fit total {lev}x leverage")
                rp = rp_fit
    if rej:
        t = {"id": None, "book": "ofis", "asset": asset, "side": side, "entry_type": (entry or {}).get("type"),
             "entry_price": (entry or {}).get("price"), "stop": stop, "targets": targets, "risk_usdt": 0}
        event(st, t, "red", rej)
        O.log("defter.log", f"open REJECT {asset} {side}: {rej}")
        return False, rej, None
    hz = [b["horizon_h"] for b in blocks if b["asset"] == asset and b["bias"] == side and b["expert"] in d.get("supporting", [])]
    horizon = max(hz) if hz else R.get("default_horizon_h", 72)
    t = new_trade(st, "ofis", asset, side, entry, stop, targets[:2], horizon, eq * rp / 100, stamp,
                  R["pending_order_expiry_runs"], src="trader-risk")
    t["risk_pct"] = round(rp, 3)
    t["beta"] = ctx.get("beta_btc_30d")
    t["note"] = "; ".join(notes)
    event(st, t, "emir", f"risk {rp:.2f}% {'; '.join(notes)}")
    return True, f"risk {rp:.2f}% " + "; ".join(notes), t


# ---------------- golge islemler ----------------
def errored_experts(stamp):
    """sinyaller.jsonl'den: bu turda tum satirlari altyapi hatasi (CLI/oturum siniri/zaman asimi) olan uzmanlar."""
    rows = [r for r in O.read_jsonl(O.DEFTER / "sinyaller.jsonl") if r.get("run") == stamp and not r.get("reused")]
    by = {}
    for r in rows:
        by.setdefault(r.get("expert"), []).append(r)
    return {ex for ex, rs in by.items() if rs and all(not r.get("valid") and is_infra_error(r.get("errors")) for r in rs)}


def add_shadow(st, blocks, called, stamp, snap, errored=None):
    """blocks: bu tur uretilen gecerli bloklar; called: bu tur cagrilan uzmanlar (gecersiz/zaman asimi dahil).
    errored: cagrisi altyapi hatasiyla dusen uzmanlar (tur.py: results[ex]['error'] dolu olanlar); bunlarin bekleyen
    golge emirlerinin sayaci dusmez. None ise sinyaller.jsonl'den cikarilir (errored_experts)."""
    R = O.ayar()["risk"]
    if errored is None:
        errored = errored_experts(stamp)
    errored = set(errored or ())
    lr = st.setdefault("ledger_runs", [])
    if stamp not in lr:
        lr.append(stamp)
        del lr[:-500]
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
        if ex in errored:                     # altyapi hatasi uzmanin emri sayilmaz (DENETIM 2026-11-21 #4)
            continue
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
                if t["book"] == "ofis":   # toplam kaldirac: diger acik + bekleyen buyuklukler dusulur
                    lev = cap(R, "max_leverage")
                    qcap = (lev * mark_equity(st) - open_notional(st, exclude=t)) / (fill * (1 + lev * fee))  # giris ucreti dahil
                    if qcap * fill < 1.0:
                        cancel(st, t, f"total leverage {lev}x full at fill")
                        n += 1
                        continue
                    if qty > qcap:
                        t["note"] = (t["note"] + f"; qty capped by total {lev}x").strip("; ")
                        qty = qcap
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


def counted_runs(sig, st):
    """Olcume giren turlar: her asof icin bir tur (deftere islenen tur varsa o, yoksa son kosu); tum uzmanlari
    altyapi hatasiyla dusen (basarisiz) tur sayilmaz. Test tekrar kosulari boylece elenir."""
    ledger = set(st.get("ledger_runs") or []) | {t.get("run") for t in st["trades"]}
    by_asof = {}
    for r in sig:
        if r.get("reused"):
            continue
        runs = by_asof.setdefault(r.get("asof_utc"), [])
        if r.get("run") not in runs:
            runs.append(r.get("run"))
    out = set()
    for asof, runs in by_asof.items():
        lr = [x for x in runs if x in ledger]
        pick = (lr or runs)[-1]
        rows = [r for r in sig if r.get("run") == pick and not r.get("reused")]
        if any(not is_infra_error(r.get("errors")) for r in rows):
            out.add(pick)
    return out


def scores(st):
    cfg = O.ayar()
    sig = O.read_jsonl(O.DEFTER / "sinyaller.jsonl")
    keep = counted_runs(sig, st)
    bks = (cfg.get("measure") or {}).get("conf_buckets") or [[55, 62], [63, 72], [73, 80]]
    out = {}
    for e in cfg["experts"]:
        ex = e["id"]
        rows = [s for s in sig if s.get("expert") == ex and not s.get("reused") and s.get("run") in keep
                and not is_infra_error(s.get("errors"))]
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
        hr = sum(1 for t in closed if t["hit"]) / len(closed) if closed else None
        # referans: hep gerceklesen isabet oranini soyleyen beceriksiz tahminci (Brier = p(1-p)); 0,25 degil
        brier_ref = round(hr * (1 - hr), 4) if hr is not None else None
        be = [1 / (1 + abs(t["targets"][0] - t["fill_px"]) / abs(t["fill_px"] - t["stop0"]))
              for t in closed if t["fill_px"] and t["fill_px"] != t["stop0"]]
        buckets = {}
        for lo, hi in bks:
            b = [t for t in closed if lo <= (t["confidence"] or 0) <= hi]
            buckets[f"{lo}-{hi}"] = [len(b), round(sum(1 for t in b if t["hit"]) / len(b), 3) if b else None]
        hold = [(t["exit_ms"] - t["fill_ms"]) / 3.6e6 for t in closed]
        runs = len({s.get("run") for s in rows})
        exp_blocks = len(rows)   # tur basina varlik satiri (gecersiz/eksik dahil); varlik sayisi turdan tura degisir
        out[ex] = {"name": e["name"], "enabled": e["enabled"], "rounds": runs, "valid_blocks": len(blocks),
                   "brier_ref": brier_ref, "breakeven_hit": round(float(np.mean(be)), 3) if be else None,
                   "invalid_rate": round(1 - len(blocks) / exp_blocks, 3) if exp_blocks else None,
                   "flat_rate": round(len(flat) / len(blocks), 3) if blocks else None,
                   "shadow_trades": len(sh), "fill_rate": round(len(filled) / len(decided), 3) if decided else None,
                   "closed": len(closed), "hit_rate": round(hr, 3) if hr is not None else None,
                   "avg_r": round(float(np.mean(rs)), 3) if rs else None, "total_r": round(float(np.sum(rs)), 3) if rs else 0.0,
                   "ev_r_ci90": bootstrap_ci(rs) if len(rs) >= 30 else [None, None],
                   "max_dd_r": round(dd, 3), "avg_hold_h": round(float(np.mean(hold)), 1) if hold else None,
                   "brier": round(float(np.mean(brier)), 4) if brier else None, "conf_buckets": buckets}
    return out


# ---------------- blok puani (her blok, islem degil; LLM yok) ----------------
BCOLS = ["key", "expert", "asset", "asof_utc", "horizon_h", "bias", "tag", "setup", "confidence", "kind", "p0", "p_end",
         "atr4h", "ret_pct", "ret_atr", "dir_atr", "hit", "path", "scored_utc"]


def fetch_klines(sym, interval, start_ms, end_ms):
    """[start_ms, end_ms) arasinda acilan kapanmis mumlar: [[open_ms, o, h, l, c], ...]."""
    r = requests.get(O.SPOT_KLINES, params={"symbol": sym, "interval": interval, "startTime": start_ms,
                                             "endTime": end_ms - 1, "limit": 1000}, headers=O.UA, timeout=20)
    r.raise_for_status()
    now = O.ms(O.now_utc())
    return [[int(x[0]), float(x[1]), float(x[2]), float(x[3]), float(x[4])] for x in r.json() if x[6] < now]


KLINES = fetch_klines    # testte degistirilebilir


def score_one(b, c1h, atr, band):
    """b: blok; c1h: asof'tan baslayan 1h mumlar (ufuk kadar). Donus satir sozlugu."""
    p0, pe = c1h[0][1], c1h[-1][4]
    bias, tag = b.get("bias"), context_tag(b) if b.get("bias") == "flat" else None
    d = 1 if bias == "long" else -1 if bias == "short" else -1 if tag == "against-long" else 1 if tag == "against-short" else 0
    kind = "dir" if bias in ("long", "short") else "context" if d else "flat"
    ret_atr = (pe - p0) / atr if atr else None
    row = {"p0": p0, "p_end": pe, "atr4h": round(atr, 8) if atr else None, "ret_pct": round(100 * (pe / p0 - 1), 3),
           "ret_atr": round(ret_atr, 3) if ret_atr is not None else None, "kind": kind, "tag": tag or "", "path": ""}
    if d:
        row["hit"] = int(d * (pe - p0) > 0)
        row["dir_atr"] = round(d * ret_atr, 3) if ret_atr is not None else None
    else:
        row["hit"] = int(ret_atr is not None and abs(ret_atr) < band)
        row["dir_atr"] = None
    if kind == "dir" and b.get("stop") is not None and b.get("targets"):
        s, st_, t1, path = d, b["stop"], b["targets"][0], "none"
        for _, o, h, l, c in c1h:      # asof'tan: ayni mumda ikisi -> stop (muhafazakar)
            hit_s = (l <= st_) if s > 0 else (h >= st_)
            hit_t = (h >= t1) if s > 0 else (l <= t1)
            if hit_s or hit_t:
                path = "stop" if hit_s else "t1"
                break
        row["path"] = path
    return row


def score_blocks(st, now=None):
    """Ufku dolan her gecerli uzman blogunu (olcume giren turlar, yeniden kullanilan haric, ayni blok bir kez)
    gerceklesen fiyatla puanlar -> defter/bloklar.csv. Ag hatasinda sonraki cagrida yeniden dener."""
    cfg = O.ayar()
    M = cfg.get("measure") or {}
    band, max_g = M.get("flat_band_atr4h", 1.0), M.get("block_score_max_groups", 40)
    now = now or O.now_utc()
    f = O.DEFTER / "bloklar.csv"
    done = set()
    if f.exists():
        with open(f, encoding="utf-8") as fh:
            done = {r["key"] for r in csv.DictReader(fh)}
    sig = O.read_jsonl(O.DEFTER / "sinyaller.jsonl")
    keep = counted_runs(sig, st)
    due = {}
    for r in sig:
        b = r.get("block")
        if r.get("reused") or not r.get("valid") or r.get("run") not in keep or not isinstance(b, dict):
            continue
        key = f"{b.get('expert')}|{b.get('asset')}|{b.get('asof_utc')}"
        if key in done:
            continue
        done.add(key)
        try:
            t0 = O.parse_utc(b["asof_utc"])
        except (KeyError, TypeError, ValueError):
            continue
        if now < t0 + dt.timedelta(hours=int(b.get("horizon_h") or 4), minutes=5):
            continue
        due.setdefault((b["asset"], b["asof_utc"]), []).append((key, b))
    rows, n = [], 0
    for (asset, asof), items in list(due.items())[:max_g]:
        t0 = O.parse_utc(asof)
        hmax = max(int(b.get("horizon_h") or 4) for _, b in items)
        try:
            c4 = KLINES(asset, "4h", O.ms(t0 - dt.timedelta(hours=4 * 15)), O.ms(t0))
            c1 = KLINES(asset, "1h", O.ms(t0), O.ms(t0 + dt.timedelta(hours=hmax)))
        except Exception as e:  # noqa: BLE001
            O.log("defter.log", f"block score klines {asset} {asof}: {type(e).__name__} {str(e)[:80]}")
            continue
        atr = None
        if len(c4) >= 15:
            trs = [max(c4[i][2], c4[i - 1][4]) - min(c4[i][3], c4[i - 1][4]) for i in range(1, len(c4))]
            atr = float(np.mean(trs[-14:]))
        for key, b in items:
            h = int(b.get("horizon_h") or 4)
            cs = [c for c in c1 if c[0] < O.ms(t0 + dt.timedelta(hours=h))]
            if len(cs) < h or not cs or cs[0][0] != O.ms(t0):
                continue                      # eksik veri: sonra yeniden
            row = score_one(b, cs, atr, band)
            row.update(key=key, expert=b.get("expert"), asset=asset, asof_utc=asof, horizon_h=h, bias=b.get("bias"),
                       setup=b.get("setup") or "", confidence=b.get("confidence"), scored_utc=O.fmt(now))
            rows.append(row)
            n += 1
    if rows:
        new = not f.exists()
        O.DEFTER.mkdir(parents=True, exist_ok=True)
        with open(f, "a", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=BCOLS)
            if new:
                w.writeheader()
            for r in rows:
                w.writerow({k: r.get(k) for k in BCOLS})
    return n


def block_stats():
    """bloklar.csv havuz ozeti: uzman basina ve kurulum turune gore."""
    f = O.DEFTER / "bloklar.csv"
    if not f.exists():
        return {}, {}
    with open(f, encoding="utf-8") as fh:
        rs = list(csv.DictReader(fh))
    num = lambda v: float(v) if v not in (None, "") else None  # noqa: E731

    def agg(xs):
        dirs = [x for x in xs if x["kind"] == "dir"]
        ctxs = [x for x in xs if x["kind"] == "context"]
        flats = [x for x in xs if x["kind"] == "flat"]
        da = [num(x["dir_atr"]) for x in dirs if num(x["dir_atr"]) is not None]
        pt = [x for x in dirs if x["path"] in ("t1", "stop")]
        rate = lambda ys: round(sum(int(y["hit"]) for y in ys) / len(ys), 3) if ys else None  # noqa: E731
        return {"dir_n": len(dirs), "dir_hit": rate(dirs), "dir_atr": round(float(np.mean(da)), 3) if da else None,
                "t1_first": round(sum(1 for x in pt if x["path"] == "t1") / len(pt), 3) if pt else None,
                "ctx_n": len(ctxs), "ctx_hit": rate(ctxs), "flat_n": len(flats), "flat_in_band": rate(flats)}
    by_ex, by_setup = {}, {}
    for x in rs:
        by_ex.setdefault(x["expert"], []).append(x)
        if x["kind"] == "dir":
            by_setup.setdefault(x["setup"] or "-", []).append(x)
    return {k: agg(v) for k, v in by_ex.items()}, {k: agg(v) for k, v in by_setup.items()}


# ---------------- maruziyet ----------------
def exposure_stats(st, now_ms=None):
    """Ofis baslangicindan bu yana: piyasada kalma orani (en az bir acik pozisyon) ve ortalama brut buyukluk /
    baslangic ozsermayesi (T1 kismi kapanis yok sayilir, yaklasik)."""
    if not st.get("start_utc"):
        return None, None
    s0 = O.ms(O.parse_utc(st["start_utc"]))
    now_ms = now_ms or O.ms(O.now_utc())
    tot = now_ms - s0
    if tot <= 0:
        return None, None
    iv, notional_ms = [], 0.0
    for t in st["trades"]:
        if t["book"] != "ofis" or not t["fill_ms"]:
            continue
        a, b = max(t["fill_ms"], s0), min(t["exit_ms"] or now_ms, now_ms)
        if b > a:
            iv.append((a, b))
            notional_ms += (t["qty0"] or 0) * t["fill_px"] * (b - a)
    iv.sort()
    cov, cur_a, cur_b = 0, None, None
    for a, b in iv:
        if cur_b is None or a > cur_b:
            if cur_b is not None:
                cov += cur_b - cur_a
            cur_a, cur_b = a, b
        else:
            cur_b = max(cur_b, b)
    if cur_b is not None:
        cov += cur_b - cur_a
    eq0 = O.ayar()["risk"]["start_equity_usdt"]
    return cov / tot, notional_ms / tot / eq0


# ---------------- basarisiz tur isareti ----------------
FAIL_MARK = "son_tur_hata.json"
FAIL_PREFIX = "**SON TUR BAŞARISIZ (LAST ROUND FAILED):**"


def _fail_line():
    f = O.DEFTER / FAIL_MARK
    if not f.exists():
        return None
    try:
        m = json.loads(f.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return None
    return f"{FAIL_PREFIX} {m.get('utc')} UTC, tur {m.get('stamp') or '-'}: {m.get('reason')}"


def _patch_durum(line):
    p = O.ROOT / "DURUM.md"
    if not p.exists():
        return
    ls = [x for x in p.read_text(encoding="utf-8").split("\n") if not x.startswith(FAIL_PREFIX)]
    if line:
        ls[1:1] = ["", line]
    while len(ls) > 2 and ls[1] == "" and ls[2] == "":
        del ls[1]
    tmp = p.with_suffix(".md.tmp")
    tmp.write_text("\n".join(ls), encoding="utf-8")
    tmp.replace(p)


def mark_failed_round(reason, stamp=None):
    """tur.py: tur basarisiz bitince (kilit disinda da olur) cagirir. defter/son_tur_hata.json yazar ve DURUM.md
    basina 'SON TUR BAŞARISIZ (LAST ROUND FAILED): <neden>' satirini koyar. Defter durumuna dokunmaz."""
    O.write_json(O.DEFTER / FAIL_MARK, {"utc": O.fmt(O.now_utc()), "stamp": stamp, "reason": str(reason)[:300]})
    _patch_durum(_fail_line())
    O.log("defter.log", f"round marked FAILED {stamp}: {str(reason)[:200]}")


def clear_failed_round():
    """tur.py: basarili turun sonunda cagirir; isaret silinir, DURUM.md satiri kalkar."""
    f = O.DEFTER / FAIL_MARK
    if f.exists():
        f.unlink()
    _patch_durum(None)


def prune_last_decisions(st):
    """Son karar listesinden evrende olmayan coinleri ve last_decision_max_age_h'den eski kararlari siler."""
    ld = st.get("last_decisions") or {}
    age = (O.ayar().get("measure") or {}).get("last_decision_max_age_h", 24)
    uni = None
    try:
        uni = set(json.loads((O.VERI / "evren.json").read_text(encoding="utf-8")).get("assets") or []) or None
    except (OSError, ValueError):
        pass
    now = O.now_utc()
    for a in list(ld):
        try:
            old = (now - O.parse_utc(ld[a].get("asof_utc"))).total_seconds() / 3600 > age
        except (TypeError, ValueError):
            old = True
        if old or (uni is not None and a not in uni):
            del ld[a]
    st["last_decisions"] = ld
    return ld


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
    try:
        score_blocks(st)
    except Exception as e:  # noqa: BLE001
        O.log("defter.log", f"block scoring failed: {type(e).__name__} {e}")
    prune_last_decisions(st)
    cfg = O.ayar()
    L = ledger_summary(st)
    start_eq = cfg["risk"]["start_equity_usdt"]
    lines = ["# Trader ofisi durumu (sahte para)", ""]
    fl = _fail_line()
    if fl:
        lines += [fl, ""]
    lines += [f"Son güncelleme: {O.fmt(O.now_utc())} UTC. Başlangıç: {st['start_utc'] or '-'} UTC, "
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
    ld = st.get("last_decisions") or {}
    latest = max((d.get("asof_utc") or "" for d in ld.values()), default=None)
    for a, d in ld.items():
        if d.get("asof_utc") == latest:      # yalniz son turun coinleri
            lines.append(f"- {a} ({d.get('asof_utc')}): **{d.get('decision')}** — {d.get('neco_tr')}")
    if not ld:
        lines.append("Yok.")
    lines += ["", "## Karşılaştırma (ofis başlangıcından bu yana)", "", "| Ölçü | Getiri |", "|---|---|",
              f"| Ofis | %{tr(100 * (L['equity_usdt'] / start_eq - 1))} |"]
    sp, lp = st.get("start_px") or {}, st.get("last_px") or {}
    bh = {}
    for a in ("BTCUSDT",):   # karsilastirma: yalniz BTC al-tut + paper sistemler (2026-11-21 karari)
        if sp.get(a) and lp.get(a):
            bh[a] = 100 * (lp[a] / sp[a] - 1)
            lines.append(f"| {a[:3]} al-tut | %{tr(bh[a])} |")
    tim, gx = exposure_stats(st)
    if tim is not None:
        lines.append(f"| Ofisin piyasada kaldığı süre (getiri değil) | %{tr(100 * tim, 1)} |")
        if "BTCUSDT" in bh:
            lines.append(f"| BTC al-tut, ofisin ortalama büyüklüğüyle ({tr(gx, 2)}x) | %{tr(gx * bh['BTCUSDT'])} |")
    for k, v in (st.get("paper_cache") or {}).items():
        lines.append(f"| Paper: {k} | %{tr(v['ret_pct'])} (son kayıt {v['asof']}) |")
    lines += ["", "## Uzmanlar (gölge işlem, her biri 1R sabit risk)", "",
              "| Uzman | Tur | Geçerli | Flat oranı | Gölge işlem | Kapanan | İsabet (başabaş) | Ort. R | Toplam R | Brier (referans) |",
              "|---|---|---|---|---|---|---|---|---|---|"]
    pct = lambda v: "-" if v is None else f"%{tr(100 * v, 0)}"  # noqa: E731
    for ex, s in sc.items():
        if not s["rounds"] and not s["enabled"]:
            continue
        lines.append(f"| {s['name']} ({ex.replace('trader-', '')}) | {s['rounds']} | {s['valid_blocks']} | {pct(s['flat_rate'])} | "
                     f"{s['shadow_trades']} | {s['closed']} | {pct(s['hit_rate'])}"
                     f"{'' if s.get('breakeven_hit') is None else ' (' + pct(s['breakeven_hit']) + ')'} | {tr(s['avg_r'])} | "
                     f"{tr(s['total_r'])} | {tr(s['brier'], 3)}{'' if s.get('brier_ref') is None else ' (' + tr(s['brier_ref'], 3) + ')'} |")
    lines += ["", "Not: Tur = sayılan tur (her 4 saatte bir; test tekrarı ve başarısız tur sayılmaz). İsabet = ilk hedef "
              "stoptan önce geldi; parantezde R:R'ye göre başabaş isabet. Brier, parantezdeki referanstan (hep gerçekleşen "
              "isabet oranını söyleyen tahmin) küçükse güven sayıları bilgi taşıyor. "
              "Hiçbir uzman 30 kapanmış işlem ve 3 ay dolmadan değerlendirilmez (TASARIM.md bölüm 5).", ""]
    bx, bs = block_stats()
    if bx:
        lines += ["## Blok puanı (her görüş ufkunun sonunda fiyat; işlem değil)", "",
                  "| Uzman | Yönlü | Yön tuttu | Ort. hareket (ATR) | T1 önce | Bağlam | Tuttu | Flat | Bant içi |",
                  "|---|---|---|---|---|---|---|---|---|"]
        names = {e["id"]: e["name"] for e in cfg["experts"]}
        for ex, s in sorted(bx.items()):
            lines.append(f"| {names.get(ex, ex)} | {s['dir_n']} | {pct(s['dir_hit'])} | {tr(s['dir_atr'])} | {pct(s['t1_first'])} | "
                         f"{s['ctx_n']} | {pct(s['ctx_hit'])} | {s['flat_n']} | {pct(s['flat_in_band'])} |")
        top = sorted(bs.items(), key=lambda kv: -kv[1]["dir_n"])[:8]
        if top:
            lines += ["", "| Kurulum (yönlü, tüm uzmanlar) | Blok | Yön tuttu | Ort. hareket (ATR) | T1 önce |", "|---|---|---|---|---|"]
            for k, s in top:
                lines.append(f"| {k} | {s['dir_n']} | {pct(s['dir_hit'])} | {tr(s['dir_atr'])} | {pct(s['t1_first'])} |")
        band = (cfg.get("measure") or {}).get("flat_band_atr4h", 1.0)
        lines += ["", f"Not: Görüş zamanındaki fiyattan ufuk sonuna (1 saatlik mum). Bağlam = flat + CONTEXT against-long/short "
                  f"(tuttu = fiyat o yöne gitmedi). Bant içi = flat sonrası hareket {tr(band, 1)} ATR(4h) altında. "
                  "T1 önce = giriş beklenmeden T1 stoptan önce geldi. Ayrıntı: defter/bloklar.csv.", ""]
    p = O.ROOT / "DURUM.md"
    tmp = p.with_suffix(".md.tmp")
    tmp.write_text("\n".join(lines), encoding="utf-8")
    tmp.replace(p)


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
