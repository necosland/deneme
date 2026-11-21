"""Gevsek golge defter (Neco 2026-11-21; TASARIM.md 5). LLM yok, gercek defteri etkilemez.

Ayni turun uzman bloklarindan: bir coinde >= 1 gecerli oy (vote_rule 'ev' ise EV >= loose.min_ev_r, 'min_conf' ise
guven >= loose.min_conf) varsa acar. Rejim yasagi, R2 catisma, R3 seviye uzmani, R6 baglam yok; iki yonde oy varsa
cogunluk, esitse acmaz. Takvim yasagi (R5), miktar, sinirlar, cikislar, maliyet gercek defterle ayni
(defter.open_order strict=False; process_candles). Giris/stop/hedef = o yondeki en yuksek EV'li oy.
Durum defter/gevsek.json (ayri), emir olaylari defter/gevsek_emirler.csv, ozsermaye defter/gevsek_ozsermaye.csv.
Karsilastirma: DURUM.md + haftalik rapor; karar 4 hafta sonra (loose.compare_after).
"""
import copy
import csv
import json

import ortak as O

DEF = {"enabled": True, "min_conf": 50, "min_ev_r": 0.0}


def lcfg(cfg=None):
    g = dict(DEF)
    g.update((cfg or O.ayar()).get("loose") or {})
    return g


def state_f():
    return O.DEFTER / "gevsek.json"


def load():
    f = state_f()
    if f.exists():
        return json.loads(f.read_text(encoding="utf-8"))
    r = O.ayar()["risk"]   # gercek defterle ayni baslangic (state.json'a dokunmaz)
    st = {"version": 1, "start_utc": None, "start_px": {}, "cash": float(r["start_equity_usdt"]),
          "peak": float(r["start_equity_usdt"]), "last_check_ms": {}, "last_px": {}, "trades": [],
          "funding_cache": {}, "next_id": 1, "paper_cache": None, "last_decisions": {},
          "label": "gevsek", "events_file": "gevsek_emirler.csv"}
    return st


def save(st):
    O.write_json(state_f(), st)


def loose_cfg(cfg):
    """Oy esigi gevsek: ayni vote_rule, gevsek esik."""
    c = copy.deepcopy(cfg)
    L = lcfg(cfg)
    c["risk"]["min_confidence"] = L["min_conf"]
    c["risk"]["min_ev_r"] = L["min_ev_r"]
    return c


def ev_r(b, last, R):
    rr, cost_r, _ = O.rr_cost(b["bias"], b["entry"], b["stop"], b["targets"][0], last, R)
    p = (b.get("confidence") or 0) / 100
    return p * rr - (1 - p) - cost_r


def tur(st, blocks, snap, stamp, cfg, log=print):
    """Bir tur: gevsek oylardan emir. blocks: Riza'nin gordugu bloklar (dec_blocks). Donus [(asset, durum, not)]."""
    import defter as D
    L = lcfg(cfg)
    if not L.get("enabled"):
        return []
    lc = loose_cfg(cfg)
    R = cfg["risk"]
    asof = snap["asof_utc"]
    if not st.get("start_utc"):
        st["start_utc"] = snap.get("generated_utc") or O.fmt(O.now_utc())
        st["start_px"] = {s: ((x or {}).get("ctx") or {}).get("last_close") for s, x in (snap.get("assets") or {}).items()}
    res = []
    round_assets = [s for s, x in (snap.get("assets") or {}).items() if x and not x.get("_context_only")]
    for asset in round_assets:
        ctx = (snap["assets"][asset] or {}).get("ctx") or {}
        last, atr4 = ctx.get("last_close"), (ctx.get("atr14") or {}).get("4h")
        if last and not D.live(st, None, asset):
            st["last_px"][asset] = last
        votes = []
        for b in blocks or []:
            if isinstance(b, dict) and b.get("asset") == asset:
                ok, _ = D.vote_check(b, asset, asof, lc, snap)
                if ok:
                    votes.append(b)
        longs = [b for b in votes if b["bias"] == "long"]
        shorts = [b for b in votes if b["bias"] == "short"]
        side = "long" if len(longs) > len(shorts) else "short" if len(shorts) > len(longs) else None
        pend = D.live(st, "ofis", asset, ("pending",))
        if side is None:
            for t in pend:
                t["runs_left"] -= 1
                if t["runs_left"] <= 0:
                    D.cancel(st, t, "expired (no loose signal)")
            if votes:
                res.append((asset, "none", f"tie {len(longs)} long / {len(shorts)} short"))
            continue
        if D.live(st, "ofis", asset, ("open",)):
            res.append((asset, "hold", "open position"))
            continue
        for t in pend:
            D.cancel(st, t, "replaced by new loose signal")
        sv = longs if side == "long" else shorts
        best = max(sv, key=lambda b: ev_r(b, last, R))
        d = {"asset": asset, "asof_utc": asof, "decision": "open", "side": side, "entry": best["entry"],
             "stop": best["stop"], "targets": best["targets"][:2], "risk_pct": R["risk_pct_default"],
             "supporting": sorted({b["expert"] for b in sv})}
        ok, why, t = D.open_order(st, d, asset, last, atr4, snap, stamp, blocks, lc, strict=False)
        if t:
            t["src"] = {"book": "gevsek", "setup": best.get("setup"), "expert": best["expert"],
                        "votes": d["supporting"], "ev_r": round(ev_r(best, last, R), 3)}
            t["confidence"] = best.get("confidence")
        res.append((asset, "open" if ok else "rejected", why))
    if res:
        log(f"loose book: {res}")
    return res


def append_equity(st):
    import defter as D
    f = O.DEFTER / "gevsek_ozsermaye.csv"
    new = not f.exists()
    with open(f, "a", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        if new:
            w.writerow(["zaman_utc", "ozsermaye", "nakit", "acik_risk_pct"])
        L = D.ledger_summary(st)
        w.writerow([O.fmt(O.now_utc()), L["equity_usdt"], L["cash_usdt"], L["open_risk_pct"]])


def ozet(st):
    """Defter ozeti: ozsermaye, getiri %, kapanan, ort R, isabet, acik/bekleyen."""
    import defter as D
    if st is None:
        return None
    eq0 = O.ayar()["risk"]["start_equity_usdt"]
    eq = D.mark_equity(st)
    cl = [t for t in st["trades"] if t["book"] == "ofis" and t["status"] == "closed" and t.get("r_mult") is not None]
    rs = [t["r_mult"] for t in cl]
    return {"equity": round(eq, 2), "ret_pct": round(100 * (eq / eq0 - 1), 2), "closed": len(cl),
            "avg_r": round(sum(rs) / len(rs), 3) if rs else None,
            "hit": round(sum(1 for t in cl if t.get("hit")) / len(cl), 3) if cl else None,
            "live": len(D.live(st, "ofis")), "start_utc": st.get("start_utc")}


def load_if_exists():
    f = state_f()
    if not f.exists():
        return None
    try:
        return json.loads(f.read_text(encoding="utf-8"))
    except ValueError:
        return None
