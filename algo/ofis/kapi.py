"""Trader ofisi tur kapisi (LLM yok; Neco 2026-11-21: acik). Uzmanlar cagrilmadan once kod, secilen her coin icin
son tam uzman analizinden bu yana onemli bir sey degisti mi diye bakar. Esikler ofis-ayar.json -> gate.

Genel (tum coinler tam tur): sabit tam tur saati (full_slots_utc, makro saatleri), son tam turdan force_full_h saat
gecti, takvimde event_h icinde olay, rejim degisimi (BTC 1d/4h CHoCH, everything_down / corr_break yeni,
ATR(4h) / 30g medyan sicramasi, fonlama / OI 24s soku yeni, tarayici secimi degisti).
Coin basina: hic analiz edilmedi / force_full_h'den eski, ofis pozisyonu ya da bekleyen emri, fiyat anahtar seviyeye /
deger alani kenarina <= level_atr x ATR(4h), harmonik PRZ, Elliott tetigi, son analizden beri yeni 4h BOS/supurme,
son analizden beri |hareket| >= move_atr x ATR(4h).
Hicbiri yoksa o coin icin uzman cagrilmaz: onceki bloklar 'auto/gated' satiri olarak yazilir (golge ve puana girmez).
Hicbir coin gecmezse tur ucuz biter (veri + defter guncellemesi). Kararlar log/kapi.jsonl, durum defter/kapi.json.
"""
import datetime as dt
import json

import numpy as np

import ortak as O

DEF = {"enabled": False, "full_slots_utc": ["08:00", "16:00"], "force_full_h": 12, "level_atr": 0.5, "move_atr": 1.0,
       "harm_prz_atr": 0.5, "ew_trigger_atr": 0.5, "event_h": 12, "atr_jump_x": 1.5, "atr_jump_step": 1.25,
       "atr_median_bars": 180, "oi_shock_pct": 8.0, "funding_shock": 0.0005, "pick_change_forces_full": True,
       "cost_lookback_rounds": 12}
TF_H = {"1d": 24, "4h": 4, "1h": 1}


def gcfg(cfg=None):
    g = dict(DEF)
    g.update((cfg or O.ayar()).get("gate") or {})
    return g


def state_f():
    return O.DEFTER / "kapi.json"


def load_state():
    f = state_f()
    if f.exists():
        try:
            return json.loads(f.read_text(encoding="utf-8"))
        except ValueError:
            pass
    return {"last_full": None, "assets": {}, "last": None}


def _closes_after(t, tf, ref):
    """Mum acilis zamani t (metin) olan tf mumu ref'ten (asof metni) sonra mi kapandi (yeni mi)."""
    if not t or not ref:
        return False
    try:
        t0 = dt.datetime.strptime(t, "%Y-%m-%d" if tf == "1d" and len(t) == 10 else "%Y-%m-%d %H:%M")
    except ValueError:
        return False
    return (t0.replace(tzinfo=dt.timezone.utc) + dt.timedelta(hours=TF_H[tf])) > O.parse_utc(ref)


def _hours(a, b):
    return (O.parse_utc(a) - O.parse_utc(b)).total_seconds() / 3600


def key_levels(a):
    lv, vp, st = a.get("levels") or {}, a.get("vp") or {}, a.get("structure") or {}
    out = []
    for k in ("prev_week_hl", "prev_month_hl"):
        out += [(k, x) for x in (lv.get(k) or []) if isinstance(x, (int, float))]
    for k in ("4h_all", "1d_180d"):
        for e in ("vah", "val", "poc"):
            x = (vp.get(k) or {}).get(e)
            if isinstance(x, (int, float)):
                out.append((f"{k}.{e}", x))
    for tf, n in (("4h", 3), ("1d", 2)):
        for p in ((st.get(tf) or {}).get("pivots") or [])[-n:]:
            if isinstance(p, list) and len(p) > 2 and isinstance(p[1], (int, float)):
                out.append((f"{tf} pivot {p[2]}", p[1]))
    return out


def asset_triggers(sym, a, g, ast, live_ofis, asof):
    """Coin basina tetikler (bos liste = degisiklik yok)."""
    ctx = a.get("ctx") or {}
    last, atr = ctx.get("last_close"), (ctx.get("atr14") or {}).get("4h")
    trg = []
    if live_ofis:
        trg.append("office position/pending order")
    prev = ast.get(sym)
    if not prev:
        trg.append("never analysed")
    elif _hours(asof, prev["asof"]) >= g["force_full_h"] - 1e-9:
        trg.append(f"last analysis {prev['asof']} >= {g['force_full_h']}h ago")
    if not last or not atr:
        trg.append("no last_close/ATR (fail open)")
        return trg
    near = [(k, x, abs(last - x) / atr) for k, x in key_levels(a)]
    near = [n for n in near if n[2] <= g["level_atr"] + 1e-12]
    if near:
        k, x, d = min(near, key=lambda n: n[2])
        trg.append(f"near level {k} {x} ({d:.2f} ATR)")
    ph = (prev or {}).get("harm") or {}
    for h in a.get("harmonics") or []:
        if not isinstance(h, dict):
            continue
        dp, stt = h.get("dist_prz_atr"), h.get("status")
        # PRZ'de ya da PRZ'ye yakin forming; 'reacted' yalniz son analizden sonra yeniyse (kalici durum her turu acmaz)
        if (stt == "at_prz" or (stt == "forming" and isinstance(dp, (int, float)) and 0 <= dp <= g["harm_prz_atr"])
                or (stt == "reacted" and ph.get(harm_key(h)) != "reacted")):
            trg.append(f"harmonic {h.get('pattern')} {stt}")
            break
    el = a.get("elliott") or {}
    if isinstance(el, dict):
        tp, pe = el.get("trigger"), (prev or {}).get("ew")
        if isinstance(tp, (int, float)) and abs(last - tp) / atr <= g["ew_trigger_atr"]:
            trg.append(f"elliott trigger {tp} ({abs(last - tp) / atr:.2f} ATR)")
        elif el.get("actionable") and pe != [el.get("state"), True]:   # yeni actionable (son analizde degildi)
            trg.append(f"elliott actionable {el.get('state')} (new)")
    if prev:
        for p in ((a.get("structure") or {}).get("4h") or {}).get("pivots") or []:
            if not isinstance(p, list) or len(p) < 5:
                continue
            if _closes_after(p[3], "4h", prev["asof"]):
                trg.append(f"new 4h BOS of {p[2]} {p[1]}")
                break
            if _closes_after(p[4], "4h", prev["asof"]):
                trg.append(f"new 4h sweep of {p[2]} {p[1]}")
                break
        if prev.get("px"):
            mv = abs(last - prev["px"]) / atr
            if mv >= g["move_atr"] - 1e-12:
                trg.append(f"move {mv:.2f} ATR since {prev['asof']}")
    return trg


def harm_key(h):
    return f"{h.get('pattern')}|{h.get('dir')}|{h.get('tf')}|{((h.get('XABCD') or [[None]])[0] or [None])[0]}"


def asset_memo(a):
    """Son analizde ne gorulduyse (bir sonraki turda 'yeni mi' icin): harmonik durumlari, Elliott durumu."""
    el = a.get("elliott") if isinstance(a.get("elliott"), dict) else {}
    return {"harm": {harm_key(h): h.get("status") for h in a.get("harmonics") or [] if isinstance(h, dict)},
            "ew": [el.get("state"), bool(el.get("actionable"))]}


def atr_ratio(snap, g, klines=None):
    """BTC ATR14(4h) son / son atr_median_bars mumun ATR medyani (Binance 4h mum; snapshot'ta yalniz 30 mum var)."""
    import defter as D
    kl = klines or D.KLINES
    t0 = O.parse_utc(snap["asof_utc"])
    n = int(g["atr_median_bars"]) + 15
    c = kl("BTCUSDT", "4h", O.ms(t0 - dt.timedelta(hours=4 * n)), O.ms(t0))
    if len(c) < 30:
        return None
    tr = [max(c[i][2], c[i - 1][4]) - min(c[i][3], c[i - 1][4]) for i in range(1, len(c))]
    atr = np.convolve(tr, np.ones(14) / 14, mode="valid")
    med = float(np.median(atr[-int(g["atr_median_bars"]):]))
    return round(float(atr[-1]) / med, 3) if med else None


def regime(snap, sel, g, klines=None):
    """Rejim bayraklari (tam turda kaydedilir, sonraki turda 'yeni' olani tetik olur)."""
    macro = snap.get("macro") if isinstance(snap.get("macro"), dict) else {}
    stress = macro.get("stress") or {}
    btc = (snap.get("assets") or {}).get("BTCUSDT") or {}
    dv = btc.get("derivs") or (btc.get("derivs_lite") or {})
    oi, fu = dv.get("oi_chg_24h_pct"), dv.get("funding_last")
    try:
        ar = atr_ratio(snap, g, klines)
    except Exception as e:  # noqa: BLE001
        ar = None
        O.log("tur.log", f"gate: atr ratio failed {type(e).__name__} {str(e)[:80]}")
    return {"everything_down": bool(stress.get("everything_down")),
            "corr_break": sorted(str(x[0] if isinstance(x, list) and x else x) for x in (stress.get("corr_break") or [])),
            "deriv_shock": bool((isinstance(oi, (int, float)) and abs(oi) >= g["oi_shock_pct"])
                                or (isinstance(fu, (int, float)) and abs(fu) >= g["funding_shock"])),
            "oi_chg_24h_pct": oi, "funding_last": fu, "atr_ratio": ar,
            "picked": sorted((sel or {}).get("picked") or [])}


def global_triggers(snap, g, gst, reg, asof):
    import defter as D
    trg = []
    if asof[-5:] in (g.get("full_slots_utc") or []):
        trg.append(f"full slot {asof[-5:]} UTC")
    lf = gst.get("last_full")
    if not lf:
        trg.append("no previous full round")
    elif _hours(asof, lf["asof"]) >= g["force_full_h"] - 1e-9:
        trg.append(f"last full round {lf['asof']} >= {g['force_full_h']}h ago")
    ev = D.event_blackout(snap, g["event_h"], required=False)
    if ev:
        trg.append(f"calendar event within {g['event_h']}h: {ev}")
    btc = (snap.get("assets") or {}).get("BTCUSDT") or {}
    ref = (lf or {}).get("asof")
    if ref:
        for tf in ("1d", "4h"):
            for p in ((btc.get("structure") or {}).get(tf) or {}).get("pivots") or []:
                if isinstance(p, list) and len(p) > 3 and p[2] in ("LH", "HL") and _closes_after(p[3], tf, ref):
                    trg.append(f"BTC {tf} CHoCH: close beyond {p[2]} {p[1]}")
                    break
    old = (lf or {}).get("regime") or {}
    if reg["everything_down"] and not old.get("everything_down"):
        trg.append("everything_down flag new")
    new_cb = set(reg["corr_break"]) - set(old.get("corr_break") or [])
    if new_cb:
        trg.append(f"corr_break new: {sorted(new_cb)}")
    if reg["deriv_shock"] and not old.get("deriv_shock"):
        trg.append(f"BTC funding/OI shock new (OI 24h {reg['oi_chg_24h_pct']}%, funding {reg['funding_last']})")
    ar, oar = reg.get("atr_ratio"), old.get("atr_ratio")
    if ar is not None and ar >= g["atr_jump_x"] and (oar is None or oar < g["atr_jump_x"] or ar >= oar * g["atr_jump_step"]):
        trg.append(f"BTC ATR(4h) jump {ar}x 30d median (prev full {oar})")
    if g.get("pick_change_forces_full") and lf and reg["picked"] != sorted(lf.get("picked") or []):
        trg.append(f"screener picks changed {lf.get('picked')} -> {reg['picked']}")
    return trg


def avg_round_cost(n):
    """Son n tam/kismi turun ortalama maliyeti ve coin sayisi (log/<stamp>/ozet.json)."""
    xs = []
    for d in sorted(O.LOG.glob("2*_*"), reverse=True):
        f = d / "ozet.json"
        if not d.is_dir() or not f.exists() or "_replay" in d.name:
            continue
        try:
            j = json.loads(f.read_text(encoding="utf-8"))
        except ValueError:
            continue
        c, na = (j.get("_total") or {}).get("cost_usd"), len((j.get("kapi") or {}).get("run") or []) or None
        if c:
            xs.append((c, na))
        if len(xs) >= n:
            break
    if not xs:
        return None
    return round(float(np.mean([c for c, _ in xs])), 3)


def karar(cfg, snap, sel, st, asof, log=print, klines=None):
    """Donus: {"run": [...], "gated": [...], "global": [...], "assets": {sym: [...]}, "regime": {...}, "est_saving_usd"}."""
    import defter as D
    g = gcfg(cfg)
    gst = load_state()
    assets = list(cfg["assets"])
    reg = regime(snap, sel, g, klines)
    glob = global_triggers(snap, g, gst, reg, asof)
    per = {}
    for s in assets:
        a = (snap.get("assets") or {}).get(s) or {}
        per[s] = asset_triggers(s, a, g, gst.get("assets") or {}, bool(D.live(st, "ofis", s)), asof)
    run = assets if glob else [s for s in assets if per[s]]
    gated = [s for s in assets if s not in run]
    avg = avg_round_cost(int(g["cost_lookback_rounds"]))
    est = round(avg * len(gated) / len(assets), 3) if avg and assets else None
    res = {"asof": asof, "run": run, "gated": gated, "global": glob, "assets": per, "regime": reg,
           "est_saving_usd": est, "avg_round_cost_usd": avg}
    log(f"gate: run={run} gated={gated} global={glob or '-'} per-asset="
        + "; ".join(f"{s}: {', '.join(t) if t else 'no change'}" for s, t in per.items())
        + f" est_saving_usd={est}")
    return res


def trim(snap, gated):
    """Kapidan gecmeyen coinler bu tur uzmanlara gitmez: BTC kucuk baglam blogu olur, digerleri cikar."""
    import tarayici as TR
    sa = snap.get("assets") or {}
    for s in gated:
        if s == "BTCUSDT":
            sa[s] = TR.btc_context(sa.get(s))
        else:
            sa.pop(s, None)
    return snap


def prev_block(expert, asset, before_run):
    """Uzmanin bu coin icin son gecerli, cagrilarak yazilmis blogu (yeniden kullanilan/auto haric)."""
    best = None
    for r in O.read_jsonl(O.DEFTER / "sinyaller.jsonl"):
        if (r.get("expert") == expert and r.get("asset") == asset and r.get("valid") and not r.get("reused")
                and not r.get("auto") and r.get("run") != before_run):
            best = r
    return best


def gated_rows(cfg, gated, stamp, asof, sha):
    """Atlanan coin icin 'degisiklik yok' satirlari: onceki blok aynen (auto, gated, reused -> golge/puan disi)."""
    n = 0
    for e in cfg["experts"]:
        if not e.get("enabled"):
            continue
        for s in gated:
            r = prev_block(e["id"], s, stamp)
            if not r:
                continue
            O.append_jsonl(O.DEFTER / "sinyaller.jsonl", {"run": stamp, "asof_utc": asof, "expert": e["id"], "asset": s,
                                                         "valid": True, "errors": [], "block": r["block"], "reused": True,
                                                         "auto": True, "gated": True, "prev_run": r.get("run"),
                                                         "snapshot_sha256": sha})
            n += 1
    return n


def kaydet(res, snap, run_assets, asof, stamp, full, test=False):
    """Uzmanlar basariyla calistiktan sonra: analiz edilen coinlerin asof/fiyati; tam turda rejim. test: yazmaz."""
    gst = load_state()
    if not test:
        for s in run_assets:
            a = (snap.get("assets") or {}).get(s) or {}
            gst.setdefault("assets", {})[s] = {"asof": asof, "px": (a.get("ctx") or {}).get("last_close"), "run": stamp,
                                               **asset_memo(a)}
        if full:   # kapi calismadiysa (--no-gate, hata) onceki rejim kalir
            reg = (res or {}).get("regime") or ((gst.get("last_full") or {}).get("regime") or {})
            gst["last_full"] = {"asof": asof, "run": stamp, "regime": reg, "picked": reg.get("picked") or []}
        O.write_json(state_f(), gst)


def kayit(res, stamp, test=False):
    """Kapi karari: log/kapi.jsonl (her zaman) + defter/kapi.json 'last' (DURUM.md satiri; test degilse)."""
    O.append_jsonl(O.LOG / "kapi.jsonl", {"run": stamp, "utc": O.fmt(O.now_utc()), "test": test, **(res or {})})
    if not test:
        gst = load_state()
        gst["last"] = {"run": stamp, "asof": (res or {}).get("asof"), "run_assets": (res or {}).get("run"),
                       "gated": (res or {}).get("gated"), "est_saving_usd": (res or {}).get("est_saving_usd")}
        O.write_json(state_f(), gst)


def durum_satiri():
    """DURUM.md icin Turkce tek satir (son tur kapidan atlandiysa)."""
    try:
        last = load_state().get("last") or {}
    except Exception:  # noqa: BLE001
        return None
    if not last.get("gated"):
        return None
    if not last.get("run_assets"):
        return (f"Son tur ({last.get('asof')} UTC): kod kapısı — son tam analizden beri önemli değişiklik yok, "
                "uzmanlar çağrılmadı (gated: no change). Veri ve defter güncellendi.")
    return (f"Son tur ({last.get('asof')} UTC): yalnız {', '.join(last['run_assets'])} analiz edildi; "
            f"{', '.join(last['gated'])} için değişiklik yok (gated).")
