"""Trader ofisi 4 saatlik tur kosucusu (sahte para; gercek emir yok, borsa anahtari yok).

Akis (TASARIM.md bolum 2):
 1. veri_topla.py -> veri/snap_<asof>.json (+ grafikler)
 2. rol basina kirpilmis snapshot gorunumleri (token tasarrufu) -> log/<stamp>/view_<rol>.json
 3. uzmanlar paralel, birbirini gormeden: her biri ayri `claude -p --agent trader-X` sureci, yalniz Read araci
    (makro: Read + farside WebFetch), --permission-mode dontAsk (izin sorusu yok, izinsiz arac reddedilir)
 4. her blok sema.json + geometri/LIMITS ile kodla dogrulanir -> defter/sinyaller.jsonl
 5. trader-risk (Riza) -> sema ile dogrulanir -> defter/kararlar.jsonl
 6. defter.py: once 1m mumlarla deftere yetisir, sonra karari KOD sinirlariyla uygular, golge islemleri acar,
    raporlari (defter/*.csv, puan.json, DURUM.md) yazar.
Butce (2026-11-21, tum evren 10 coin): veri 8 dk (+5 dk akissiz tekrar) + uzmanlar 10 dk (paralel) + komite 8 dk +
risk 7 dk; tur siniri T_TOTAL 40 dk, zamanlanmis gorev siniri 75 dk (altyapi hatasinda 30 dk bekleme + tekrar dahil).

Kullanim: python algo/ofis/tur.py [--force] [--skip-data] [--only trader-a,trader-b] [--no-risk] [--no-ledger]
"""
import argparse
import concurrent.futures as cf
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time

import ortak as O

NOWIN = getattr(subprocess, "CREATE_NO_WINDOW", 0)
# 2026-11-21 tum evren (10 coin): veri_topla 10 coinde ~225 sn olculdu (4 coinde ~120 sn); uzman istemi ~2,5 kat
T_DATA, T_EXPERT, T_RISK, T_TOTAL = 480, 600, 420, 40 * 60
T_DATA_RETRY = 300   # veri_topla zaman asiminda emir akissiz tek tekrar
# denetim 2026-11-21: altyapi hatasi (kullanim limiti, cli) -> 30 dk sonra tek yeniden deneme; 4h kapanisindan
# 90 dk sonrasi bayat (gec baslayan telafi turu atlanir, yeniden deneme bu siniri asmaz)
RETRY_WAIT_S, STALE_MAX_S = 30 * 60, 90 * 60
INFRA_PAT = ("session limit", "usage limit", "rate limit", "overloaded", "cli error", "claude cli not found",
             "non-json output", "credit balance", "api error", "529", "503")
LOG_KEEP_DAYS = 30
TUR_KILIT = O.LOG / ".tur_kilit"
VIEW_OF = {"trader-likidite": "fiyat", "trader-elliott": "elliott", "trader-seviye": "fiyat", "trader-senaryo": "senaryo",
           "trader-turev": "turev", "trader-makro": "makro", "trader-risk": "risk", "trader-harmonik": "harmonik"}
# ek veri (TASARIM.md 14 "Ek veri ve kayitcilar"): varlik alanlari ve hangi rolun hangi aciklamayi gordugu
EK_ASSET = ("options", "onchain", "orderbook", "recorded")
LEGEND_OF = {"turev": ("options", "onchain", "orderbook", "recorded", "macro.stablecoin_supply"),
             "senaryo": ("options", "orderbook", "recorded", "orderflow"), "makro": ("onchain", "macro.stablecoin_supply", "macro.extra")}
LOGF = "tur.log"
T0 = time.time()


def say(msg):
    O.log(LOGF, msg)


def elapsed():
    return round(time.time() - T0)


# ---------------- gorunumler ----------------
def make_view(snap, role):
    from veri_topla import LEGEND_EK, dump
    keep_top = ("asof_utc", "generated_utc", "mode", "legend")
    v = {k: snap.get(k) for k in keep_top}
    if isinstance(v.get("legend"), dict):   # ek veri aciklamalari yalniz o alani alan role
        v["legend"] = {k: x for k, x in v["legend"].items() if k not in LEGEND_EK or k in LEGEND_OF.get(role, ())}
    macro = snap.get("macro") if isinstance(snap.get("macro"), dict) else {}
    cal = {"calendar_usd_high": macro.get("calendar_usd_high")}
    omitted = []
    v["assets"] = {}
    for sym, a in (snap.get("assets") or {}).items():
        if a is None or a.get("_context_only"):   # tarayici: secilmeyen BTC yalniz kucuk baglam blogu
            v["assets"][sym] = a
            continue
        if role in ("fiyat", "senaryo", "elliott"):
            # elliott_say.py output only to Ekrem (role "elliott" = fiyat view + elliott field)
            drop = ("derivs", "harmonics", "orderflow") + EK_ASSET + (() if role == "elliott" else ("elliott",))
            x = {k: val for k, val in a.items() if k not in drop}
            x["candles"] = {k: val for k, val in a["candles"].items() if k != "15m"}
            omitted = ["assets.*.derivs", "assets.*.harmonics", "assets.*.candles.15m", "sentiment",
                       "macro except calendar_usd_high", "assets.*.options/onchain/orderbook/recorded/orderflow"]
            if role == "senaryo":   # Bora'nin OI filtresi icin turev ozeti
                dv = a.get("derivs") or {}
                x["derivs_lite"] = {k: dv.get(k) for k in ("source", "oi_usd_bn", "oi_chg_24h_pct", "oi_chg_7d_pct",
                                                           "funding_7d_avg", "funding_last")}
                omitted[0] = "assets.*.derivs (except derivs_lite)"
                op = a.get("options")   # opsiyon ozeti (vade tablosu yok) + defter + kayitlar
                x["options_lite"] = None if not isinstance(op, dict) else {
                    k: op.get(k) for k in ("dvol", "atm_iv_cm", "rr25_cm", "pc_oi_ratio_all", "monthly")}
                x["orderbook"], x["recorded"] = a.get("orderbook"), a.get("recorded")
                x["orderflow"] = a.get("orderflow")   # footprint/delta, balon, duvar: yalniz Bora (senaryo-akis.md)
                omitted[-1] = "assets.*.onchain, assets.*.options.term (options_lite given)"
        elif role == "harmonik":
            c4 = dict(a["candles"]["4h"])
            c4["rows"] = c4["rows"][-12:]
            x = {"ctx": a["ctx"], "levels": a["levels"], "harmonics": a.get("harmonics"),
                 "structure": {k: a["structure"][k] for k in ("1d", "4h")},
                 "candles": {"4h": c4, "1h": a["candles"]["1h"]}, "charts": a.get("charts")}
            omitted = ["structure.1h", "fvg", "equal_hl", "vp", "candles 1d/15m and 4h older than 12 bars", "derivs",
                       "sentiment", "macro except calendar_usd_high"]
        elif role == "turev":
            c4 = dict(a["candles"]["4h"])
            c4["rows"] = c4["rows"][-12:]
            x = {"ctx": a["ctx"], "levels": a["levels"],
                 "structure": {k: a["structure"][k] for k in ("4h", "1h")}, "candles": {"4h": c4},
                 "derivs": a.get("derivs"), "charts": a.get("charts"),
                 **{k: a.get(k) for k in EK_ASSET}}
            omitted = ["structure.1d", "fvg", "equal_hl", "vp", "candles except last 12x4h",
                       "macro except calendar_usd_high and stablecoin_supply"]
        elif role == "makro":
            x = {"ctx": a["ctx"], "levels": a["levels"], "structure": {"1d": a["structure"]["1d"]},
                 "candles": {"1d": a["candles"]["1d"]}, "charts": a.get("charts"), "onchain": a.get("onchain")}
            omitted = ["structure 4h/1h", "fvg", "equal_hl", "vp", "candles 4h/1h/15m", "derivs",
                       "options", "orderbook", "recorded"]
        elif role == "risk":
            x = {"ctx": a["ctx"], "levels": a["levels"]}
            omitted = ["everything except ctx, levels, macro.calendar_usd_high"]
        else:
            x = a
        v["assets"][sym] = x
    if role == "makro":
        v["sentiment"], v["macro"] = snap.get("sentiment"), snap.get("macro")
    elif role == "turev":
        v["sentiment"], v["macro"] = snap.get("sentiment"), {**cal, "stablecoin_supply": macro.get("stablecoin_supply")}
    elif role in ("fiyat", "risk", "harmonik", "senaryo", "elliott"):
        v["macro"] = cal
    else:
        v["sentiment"], v["macro"] = snap.get("sentiment"), snap.get("macro")
    v["errors"] = snap.get("errors")
    if omitted:
        v["_view"] = (f"Trimmed snapshot for role '{role}' to save tokens. Omitted ON PURPOSE (not missing data, "
                      f"do not list in data_gaps): {', '.join(omitted)}.")
    return dump(v) + "\n"


# ---------------- claude ----------------
def run_claude(agent, prompt, timeout, rundir, tools="Read", allowed=("Read",), tag=None):
    exe = O.find_claude()
    if not exe:
        return {"agent": agent, "error": "claude CLI not found"}
    cmd = [exe, "-p", "--agent", agent, "--output-format", "json", "--permission-mode", "dontAsk",
           "--tools", tools, "--allowedTools", *allowed, "--add-dir", str(O.AGENT_BILGI), "--add-dir", str(O.ROOT),
           "--no-session-persistence"]
    env = {k: v for k, v in os.environ.items() if k not in ("CLAUDECODE", "CLAUDE_CODE_ENTRYPOINT")}
    t0 = time.time()
    p = subprocess.Popen(cmd, cwd=str(O.ROOT), stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                         env=env, creationflags=NOWIN)
    try:
        out, err = p.communicate(prompt.encode("utf-8"), timeout=timeout)
    except subprocess.TimeoutExpired:
        subprocess.run(["taskkill", "/T", "/F", "/PID", str(p.pid)], capture_output=True, creationflags=NOWIN)
        try:
            out, err = p.communicate(timeout=20)
        except Exception:  # noqa: BLE001
            out, err = b"", b""
        return {"agent": agent, "error": f"timeout {timeout}s", "secs": round(time.time() - t0)}
    out, err = out.decode("utf-8", "replace"), err.decode("utf-8", "replace")
    (rundir / f"{tag or agent}.out.json").write_text(out, encoding="utf-8")
    if err.strip():
        (rundir / f"{tag or agent}.err.txt").write_text(err, encoding="utf-8")
    res = {"agent": agent, "secs": round(time.time() - t0), "rc": p.returncode}
    try:
        j = json.loads(out)
    except json.JSONDecodeError:
        res["error"] = f"non-json output rc={p.returncode}: {(out or err)[:200]}"
        return res
    u = j.get("usage") or {}
    res.update(text=j.get("result") or "", is_error=j.get("is_error"), turns=j.get("num_turns"),
               cost_usd=j.get("total_cost_usd"), models=list((j.get("modelUsage") or {}).keys()),
               tok_in=u.get("input_tokens", 0), tok_cache_w=u.get("cache_creation_input_tokens", 0),
               tok_cache_r=u.get("cache_read_input_tokens", 0), tok_out=u.get("output_tokens", 0))
    if j.get("is_error"):
        res["error"] = f"cli error: {str(j.get('result'))[:200]}"
    return res


def infra_error(r):
    """Altyapi hatasi mi (uzmanin isi degil): kullanim limiti, cli hatasi, json disi cikti."""
    e = str((r or {}).get("error") or "").lower()
    return bool(e) and any(p in e for p in INFRA_PAT)


def can_retry(asof, a):
    """Bekleme sonunda hala 4h kapanisindan STALE_MAX_S icinde miyiz (test/--no-retry turunda hayir)."""
    if getattr(a, "no_retry", False):
        return False
    return (time.time() + RETRY_WAIT_S - O.parse_utc(asof).timestamp()) <= STALE_MAX_S


def run_parallel(jobs, outdir):
    """jobs: is anahtari ('trader-x' ya da parti 'trader-x#2') -> (istem, araclar, izinler)."""
    results = {}
    if not jobs:
        return results
    with cf.ThreadPoolExecutor(max_workers=max(1, len(jobs))) as pool:
        futs = {pool.submit(run_claude, key.split("#")[0], p, T_EXPERT, outdir, t, al,
                            key.replace("#", "_b") if "#" in key else None): key for key, (p, t, al) in jobs.items()}
        for f in cf.as_completed(futs):
            results[futs[f]] = f.result()
    return results


def harmonic_candidates(snap, assets):
    """Kodun buldugu PRZ'de ya da tepki vermis harmonik aday var mi (yoksa Hakan cagrilmaz)."""
    for s in assets:
        for h in (((snap.get("assets") or {}).get(s) or {}).get("harmonics") or []):
            if isinstance(h, dict) and h.get("status") in ("at_prz", "reacted"):
                return True
    return False


def auto_flat(expert, asof, asset, why):
    """Uzmanin flat bloguyla ayni sema; kod yazdi (AUTO), LLM cagrilmadi."""
    return {"expert": expert, "asof_utc": asof, "asset": asset, "action": "none", "bias": "flat", "timeframe": "4h",
            "setup": None, "entry": None, "stop": None, "targets": [], "invalidation": "n/a", "confidence": 50,
            "horizon_h": 4, "rationale": [f"AUTO (code, expert not called): {why}"], "data_gaps": []}


def stale_macro(b):
    """Onceki turdan yeniden kullanilan blok: event-risk etiketi yasak etkisi tasimaz (yalniz bu turun taze blogu)."""
    b = json.loads(json.dumps(b))
    rat = b.get("rationale") or []
    for i, x in enumerate(rat):
        if isinstance(x, str) and "event-risk" in x:
            rat[i] = x.replace("CONTEXT: event-risk", f"CONTEXT: regime-risk (REUSED from {b.get('asof_utc')}, "
                                                      "not this round: context only, no event ban)")[:200]
    return b


def mark_failed(stamp, asof, reason):
    """Basarisiz tur isareti: DURUM.md ust satiri defter.py'de (diger ajan); burada log + son_hata.json."""
    say(f"ROUND FAILED: {reason}")
    try:
        import defter as D
        D.mark_failed_round(reason, stamp=stamp)   # DURUM.md ust satiri
    except Exception as e:  # noqa: BLE001
        say(f"mark_failed_round failed: {type(e).__name__} {e}")
    try:
        O.write_json(O.LOG / "son_hata.json", {"run": stamp, "asof_utc": asof, "utc": O.fmt(O.now_utc()),
                                               "reason": reason})
    except Exception:  # noqa: BLE001
        pass


def cleanup_old(days=LOG_KEEP_DAYS):
    """log/<stamp> ve grafik/<stamp> klasorlerinden `days` gunden eski olanlari sil (mtime; replay grafikleri dahil)."""
    lim, n = time.time() - days * 86400, 0
    for base in (O.LOG, O.ROOT / "grafik"):
        try:
            for d in base.iterdir():
                if d.is_dir() and d.name[:8].isdigit() and d.stat().st_mtime < lim:
                    shutil.rmtree(d, ignore_errors=True)
                    n += 1
        except Exception:  # noqa: BLE001
            pass
    return n


class TurKilit:
    """Tur duzeyi kilit: elle ve zamanli tur ic ice gecmesin. Bayat sayma 2 saat (30 dk bekleme dahil tur < 1 saat)."""
    def __init__(self, stale_s=7200):
        self.stale_s, self.ok = stale_s, False

    def __enter__(self):
        TUR_KILIT.parent.mkdir(parents=True, exist_ok=True)
        for _ in range(2):
            try:
                fd = os.open(TUR_KILIT, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                os.write(fd, f"{os.getpid()} {O.fmt(O.now_utc())}".encode())
                os.close(fd)
                self.ok = True
                break
            except FileExistsError:
                try:
                    if time.time() - TUR_KILIT.stat().st_mtime > self.stale_s:
                        TUR_KILIT.unlink()
                        continue
                except FileNotFoundError:
                    continue
                break
        return self

    def __exit__(self, *x):
        if self.ok:
            try:
                TUR_KILIT.unlink()
            except FileNotFoundError:
                pass


# ---------------- dosyalar ----------------
def last_blocks(expert, before_run, assets=None):
    """Uzmanin son cagrildigi turun bloklari. assets verilirse coin basina en son blok (kod kapisi coin atlayabilir)."""
    rows = [r for r in O.read_jsonl(O.DEFTER / "sinyaller.jsonl")
            if r.get("expert") == expert and r.get("valid") and not r.get("reused") and not r.get("auto")
            and r.get("run") != before_run]
    if not rows:
        return []
    if assets is not None:
        by = {r.get("asset"): r["block"] for r in rows if r.get("asset") in assets}
        return [by[x] for x in assets if x in by]
    last = rows[-1]["run"]
    return [r["block"] for r in rows if r["run"] == last]


def limits_line(R):
    return " ".join(f"{k}={R[k]}" for k in ("min_rr_t1", "min_stop_atr4h", "max_confidence", "event_blackout_h", "fee_taker", "fee_maker", "slippage"))


def charts_line(snap):
    parts = []
    for sym, a in (snap.get("assets") or {}).items():
        ch = (a or {}).get("charts") or {}
        parts.append(f"{sym}: " + " ".join(f"{k}={v}" for k, v in ch.items()))
    return " | ".join(parts)


def normalize_block(b):
    """Yalniz bicimsel duzeltme (2026-11-20 ilk turda 4 blok bu yuzden dustu): uzun metin kirpilir, flat blokta
    eksik horizon_h = 4. Sayi, yon, seviye asla degistirilmez; yapilan duzeltme kaydedilir."""
    fixes = []
    if not isinstance(b, dict):
        return fixes
    if isinstance(b.get("rationale"), list):
        for i, x in enumerate(b["rationale"]):
            if isinstance(x, str) and len(x) > 200:
                b["rationale"][i] = x[:197] + "..."
                fixes.append(f"rationale/{i} cut {len(x)}->200")
        if len(b["rationale"]) > 3:
            b["rationale"] = b["rationale"][:3]
            fixes.append("rationale >3 items cut")
    for k, n in (("invalidation", 160), ("setup", 60)):
        if isinstance(b.get(k), str) and len(b[k]) > n:
            b[k] = b[k][:n - 3] + "..."
            fixes.append(f"{k} cut")
    if isinstance(b.get("data_gaps"), list):
        for i, x in enumerate(b["data_gaps"]):
            if isinstance(x, str) and len(x) > 80:
                b["data_gaps"][i] = x[:77] + "..."
                fixes.append(f"data_gaps/{i} cut")
    if b.get("bias") == "flat" and "horizon_h" not in b:
        b["horizon_h"] = 4
        fixes.append("flat horizon_h missing -> 4")
    return fixes


def wall_warnings(b, snap):
    """Bora blogunun rationale'inde "wall" + sayi var ama o varlikta orderflow.walls fiyatlarindan hicbirine %0.1 yakin degilse uyari
    (yalniz log; blok reddedilmez)."""
    import re
    out = []
    try:
        w = (((snap.get("assets") or {}).get(b.get("asset")) or {}).get("orderflow") or {}).get("walls") or {}
        prices = [r[0] for side in ("bids", "asks") for r in (w.get(side) or []) if isinstance(r, list) and r]
        for x in b.get("rationale") or []:
            if not isinstance(x, str) or "wall" not in x.lower():
                continue
            for m in re.finditer(r"\d[\d,]*\.?\d*", x):
                n = float(m.group().replace(",", ""))
                if n >= 1000 and not any(abs(n - p) <= 0.001 * p for p in prices):
                    out.append(f"{b.get('asset')}: wall {m.group()} not in orderflow.walls")
    except Exception:  # noqa: BLE001
        return []
    return out


def batches(assets, size):
    """Uzman cagrisini coin partilerine boler (universe.expert_batch; 0 = tek cagri). 10 coin, 5 -> 5+5."""
    if not size or len(assets) <= size:
        return [list(assets)]
    n = -(-len(assets) // size)
    k = -(-len(assets) // n)
    return [list(assets[i:i + k]) for i in range(0, len(assets), k)]


def sub_snap(snap, chunk):
    """Partinin snapshot'i: yalniz partinin coinleri; BTC partide yoksa kucuk baglam blogu (rejim/beta referansi)."""
    import tarayici as TR
    sa = snap.get("assets") or {}
    sub = {s: sa.get(s) for s in chunk}
    if "BTCUSDT" not in chunk and isinstance(sa.get("BTCUSDT"), dict):
        b = sa["BTCUSDT"]
        sub = {"BTCUSDT": b if b.get("_context_only") else TR.btc_context(b), **sub}
    return {**snap, "assets": sub}


def validate_blocks(expert, parsed, snap, cfg, v, assets=None):
    R = cfg["risk"]
    assets = list(cfg["assets"] if assets is None else assets)
    rows, seen = [], set()
    if not isinstance(parsed, list):
        return [{"asset": None, "valid": False, "errors": ["no parseable json array"], "block": parsed}]
    for b in parsed:
        fixes = normalize_block(b)
        errs = O.schema_errors(v, b)
        asset = b.get("asset") if isinstance(b, dict) else None
        if not errs:
            if b["expert"] != expert:
                errs.append(f"expert {b['expert']} != {expert}")
            if b["asof_utc"] != snap["asof_utc"]:
                errs.append(f"asof {b['asof_utc']} != {snap['asof_utc']}")
            if asset in seen:
                errs.append("duplicate asset")
            if asset not in assets:
                errs.append(f"asset {asset} not in this call's ASSETS")
            if b["bias"] in ("long", "short"):
                ctx = ((snap["assets"].get(asset) or {}).get("ctx") or {})
                errs += O.geometry_errors(b["bias"], b["entry"], b["stop"], b["targets"], ctx.get("last_close"),
                                          (ctx.get("atr14") or {}).get("4h"), R)
        if expert == "trader-senaryo" and not errs:
            for wmsg in wall_warnings(b, snap):
                say(f"WARNING unlisted wall (Bora): {wmsg}")
        seen.add(asset)
        rows.append({"asset": asset, "valid": not errs, "errors": errs, "block": b, "normalized": fixes})
    for a in assets:
        if a not in seen:
            rows.append({"asset": a, "valid": False, "errors": ["missing block"], "block": None})
    return rows


def due(expert_cfg, asof):
    r = expert_cfg["runs"]
    return r == "every" or (isinstance(r, list) and asof[-5:] in r)


def gundem_line():
    """Gundem ozeti (gundem/ozetle.py, trader-gundem Defne): son_kisa.json <= 4 gunluk ise yolu, degilse none.
    Kerem ve Riza'ya baglam; hata turu asla durdurmaz."""
    try:
        f = O.ROOT / "gundem" / "ozet" / "son_kisa.json"
        age_h = (time.time() - f.stat().st_mtime) / 3600
        if age_h > 96:
            return "GUNDEM=none"
        d = json.loads(f.read_text(encoding="utf-8"))
        return (f"GUNDEM={f} (digest of public commentary by analysts Neco trusts, dated {d.get('date')}, "
                f"{age_h:.0f}h old, ~1.5k tokens: per-source bias, consensus/divergence, crowd expectation, levels "
                "they watch. Context only: never a setup trigger or a level source by itself; SNAPSHOT wins on "
                "conflict; a one-sided consensus can be contrarian. Read it once; cite as 'GUNDEM:' if it moved you.)")
    except Exception:  # noqa: BLE001
        return "GUNDEM=none"


def loose_step(snap, stamp, cfg, blocks, run_round=True):
    """Gevsek golge defter (gevsek.py): deftere yetisir, tur oylarindan acar. Hata turu bozmaz."""
    if not (cfg.get("loose") or {}).get("enabled"):
        return
    try:
        import gevsek as G
        import kontrol as K
        lz = G.load()
        ev, note = K.run(lz)
        if run_round:
            G.tur(lz, blocks, snap, stamp, cfg, log=say)
        G.append_equity(lz)
        G.save(lz)
        if ev:
            say(f"loose catch-up: events={ev} {note}")
    except Exception as e:  # noqa: BLE001
        say(f"loose book FAILED (round unaffected): {type(e).__name__} {e}")


def ledger_tick(snap, stamp, cfg):
    """Uzmansiz tur (kod kapisi: degisiklik yok): 1m mumlarla deftere yetisme, gevsek defter, ozsermaye, raporlar."""
    import defter as D
    import kontrol as K
    with O.Kilit(wait_s=180) as k:
        if not k.ok:
            say("ledger lock busy: gated ledger tick skipped")
            return
        st = D.load_state()
        ev, note = K.run(st)
        say(f"catch-up: events={ev} {note}")
        loose_step(snap, stamp, cfg, [], run_round=False)
        D.refresh_paper(st)
        D.append_equity(st)
        D.write_reports(st)
        D.save_state(st)


# ---------------- ana akis ----------------
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true", help="bu asof icin karar varsa bile yeniden kos")
    ap.add_argument("--skip-data", action="store_true", help="veri_topla yerine veri/son.json")
    ap.add_argument("--only", help="yalniz bu uzmanlar (virgulle)")
    ap.add_argument("--no-risk", action="store_true")
    ap.add_argument("--no-ledger", action="store_true")
    ap.add_argument("--komite", action="store_true", help="komiteyi ayardan bagimsiz ac (deneme)")
    ap.add_argument("--no-komite", action="store_true")
    ap.add_argument("--evren", action="store_true", help="evren+tarayiciyi ayardan bagimsiz ac (deneme)")
    ap.add_argument("--stale-ok", action="store_true", help="4h kapanisindan 90 dk sonra da kos (elle telafi)")
    ap.add_argument("--no-retry", action="store_true", help="altyapi hatasinda 30 dk bekleyip yeniden deneme")
    ap.add_argument("--no-gate", action="store_true", help="kod kapisini atla (tum secilen coinler uzmana)")
    a = ap.parse_args()
    cfg = O.ayar()
    R = cfg["risk"]
    now = O.now_utc()
    close4h = now.replace(hour=now.hour - now.hour % 4, minute=0, second=0, microsecond=0)
    if not (a.force or a.stale_ok or a.skip_data) and (now - close4h).total_seconds() > STALE_MAX_S:
        say(f"stale start: {int((now - close4h).total_seconds() // 60)} min after 4h close {O.fmt(close4h)} > "
            f"{STALE_MAX_S // 60}: skip (use --stale-ok)")
        return 0
    stamp = O.now_utc().strftime("%Y%m%d_%H%M")
    rundir = O.LOG / stamp
    rundir.mkdir(parents=True, exist_ok=True)
    if a.no_ledger:
        O.TESTDIR = rundir   # test satirlari (sinyaller/kararlar) canli defter/ yerine bu kosunun log klasorune
    say(f"=== round {stamp} start (claude={O.find_claude()})")

    # 0. evren + tarayici (TASARIM.md 13; ofis-ayar.json universe): LLM'siz secim, uzmanlar yalniz secilenleri gorur
    sel = None
    if a.evren or (cfg.get("universe") or {}).get("enabled"):
        try:
            import tarayici as TR
            sel = TR.secim(cfg, log=say)
            O.write_json(rundir / "tarama.json", sel)
        except Exception as e:  # noqa: BLE001  tarama bozulursa eski sabit liste ile devam
            say(f"tarama FAILED, fallback to assets {cfg['assets']}: {type(e).__name__} {e}")
    # 1. veri
    if a.skip_data:
        snap_path = O.VERI / "son.json"
    else:
        # 2026-11-21: zaman asimi turu dusurmez; bir kez emir akissiz (--no-orderflow) ve kisa sureyle tekrar,
        # o da asarsa basarisiz tur isareti (mark_failed) ile cikar
        args = [str(O.PY), str(O.ROOT / "veri_topla.py"), *(["--assets", ",".join(sel["fetch"])] if sel else [])]
        p = None
        for extra, tmo in (([], T_DATA), (["--no-orderflow"], T_DATA_RETRY)):
            try:
                p = subprocess.run(args + extra, cwd=str(O.REPO), capture_output=True, text=True, encoding="utf-8",
                                   errors="replace", timeout=tmo, creationflags=NOWIN)
                break
            except subprocess.TimeoutExpired:
                say(f"veri_topla timeout {tmo}s {' '.join(extra)}".rstrip() + ("" if extra else "; retry once --no-orderflow"))
        if p is None:
            mark_failed(stamp, None, f"veri_topla timeout ({T_DATA}s, retry {T_DATA_RETRY}s)")
            return 2
        say(f"veri_topla rc={p.returncode} {p.stdout.strip()[-300:]}")
        if p.returncode != 0:
            say("veri_topla FAILED: " + p.stderr.strip()[-800:])
            mark_failed(stamp, None, f"veri_topla rc={p.returncode}")
            return 2
        snap_path = O.pathlib.Path(p.stdout.strip().splitlines()[-1].split(" | ")[0])
    raw = snap_path.read_bytes()
    snap = json.loads(raw.decode("utf-8"))
    sha = hashlib.sha256(raw).hexdigest()
    asof = snap["asof_utc"]
    if snap.get("mode") != "live":
        say(f"snapshot mode {snap.get('mode')} is not live: stop")
        return 2
    done = [k for k in O.read_jsonl(O.DEFTER / "kararlar.jsonl") if k.get("asof_utc") == asof and k.get("valid")]
    if done and not a.force:
        say(f"asof {asof} already decided: skip (use --force)")
        return 0
    say(f"snapshot {snap_path.name} asof={asof} sha={sha[:12]} errors={len(snap.get('errors') or [])}")
    if sel:   # snapshot bellekte kirpilir (SHA tam dosyanin); bu turun varliklari = secilenler
        snap, cfg["assets"] = TR.uygula(snap, sel, log=say)
        say(f"round assets={cfg['assets']} context={sel['context']}")
        if not cfg["assets"]:
            say("no selected asset in snapshot: stop")
            return 2

    # 1b. kod kapisi (kapi.py, ofis-ayar.json gate; TASARIM.md 15): son tam analizden beri degisiklik yoksa uzman yok
    gate = None
    if (cfg.get("gate") or {}).get("enabled") and not (a.no_gate or a.only):
        try:
            import kapi as KP
            import defter as D0
            gate = KP.karar(cfg, snap, sel, D0.load_state(), asof, log=say)
            KP.kayit(gate, stamp, test=a.no_ledger)
        except Exception as e:  # noqa: BLE001  kapi bozulursa tam tur
            say(f"gate FAILED -> full round: {type(e).__name__} {e}")
            gate = None
    if gate and gate["gated"]:
        n = KP.gated_rows(cfg, gate["gated"], stamp, asof, sha)
        say(f"gate: {n} 'no change' rows (auto, gated, not scored) for {gate['gated']}")
        if not gate["run"]:
            if not a.no_ledger:
                ledger_tick(snap, stamp, cfg)
            O.write_json(rundir / "ozet.json", {"_total": {"cost_usd": 0.0, "secs": elapsed(), "gated": True,
                                                           "errored": []}, "kapi": gate})
            say(f"=== round {stamp} gated: no change, experts not called (est saving {gate['est_saving_usd']} USD)")
            return 0
        snap = KP.trim(snap, gate["gated"])
        cfg["assets"] = gate["run"]
        say(f"gate: round assets={cfg['assets']}")

    # 2. gorunumler
    views = {}
    for role in set(VIEW_OF.values()):
        f = rundir / f"view_{role}.json"
        f.write_text(make_view(snap, role), encoding="utf-8")
        views[role] = f
    say("views ~tokens: " + ", ".join(f"{r}={f.stat().st_size // 4}" for r, f in sorted(views.items())))
    # uzman partileri (universe.expert_batch, 0 = tek cagri): istem cok buyurse uzman cagrisi coin partilerine
    # bolunur; parti gorunumu yalniz o coinler (+ BTC baglami). Komite ve Riza tam gorunumu kullanir.
    parts = batches(cfg["assets"], int((cfg.get("universe") or {}).get("expert_batch") or 0))
    pviews = [views]
    if len(parts) > 1:
        pviews = []
        for i, chunk in enumerate(parts, 1):
            sub = sub_snap(snap, chunk)
            pv = {}
            for role in set(VIEW_OF.values()) - {"risk"}:
                f = rundir / f"view_{role}_b{i}.json"
                f.write_text(make_view(sub, role), encoding="utf-8")
                pv[role] = f
            pviews.append(pv)
        say(f"expert batches: {parts} views ~tokens: " + "; ".join(
            ", ".join(f"{r}={f.stat().st_size // 4}" for r, f in sorted(pv.items())) for pv in pviews))

    # 3. uzmanlar
    import defter as D
    st = D.load_state()
    open_f = rundir / "open.json"
    O.write_json(open_f, D.open_summary(st))
    experts = [e for e in cfg["experts"] if e["enabled"]]
    if a.only:
        experts = [e for e in experts if e["id"] in a.only.split(",")]
    def fresh_prev(ex):   # son gecerli blok 12 saatten yeni mi (trader-risk R1 makroyu 12 saate kadar sayar)
        pb = last_blocks(ex, stamp)
        return bool(pb) and (O.parse_utc(asof) - O.parse_utc(pb[0]["asof_utc"])).total_seconds() <= 12 * 3600
    # sirasi gelmeyen uzman (makro) son blogu yoksa ya da bayatsa yine cagrilir (ilk tur, kacirilan tur)
    call = [e for e in experts if due(e, asof) or not fresh_prev(e["id"])]
    reuse = [e for e in experts if e not in call]
    # Hakan: kodda PRZ'de/tepki vermis aday yoksa cagrilmaz, kod ayni semada flat blok yazar (denetim: tur basi ~%9)
    auto = []
    if any(e["id"] == "trader-harmonik" for e in call) and not harmonic_candidates(snap, cfg["assets"]):
        call = [e for e in call if e["id"] != "trader-harmonik"]
        auto = [auto_flat("trader-harmonik", asof, s, "no at_prz/reacted harmonic candidate in snapshot")
                for s in cfg["assets"]]
        say("trader-harmonik: no at_prz/reacted candidate -> auto flat blocks, not called")
    jobs = {}
    lim = limits_line(R)
    for e, (bi, chunk) in [(e, x) for e in call for x in enumerate(parts, 1)]:
        ex = e["id"]
        key, sfx = (ex, "") if len(parts) == 1 else (f"{ex}#{bi}", f"_b{bi}")
        pv, psnap = pviews[bi - 1], (snap if len(parts) == 1 else sub_snap(snap, chunk))
        prev = last_blocks(ex, stamp, chunk)
        prev_f = "none"
        if prev:
            prev_f = rundir / f"prev_{ex}{sfx}.json"
            O.write_json(prev_f, prev)
        lines = [f"SNAPSHOT={pv[VIEW_OF.get(ex, 'full')] if ex in VIEW_OF else snap_path}",
                 f"CHARTS={charts_line(psnap)}", f"PREV={prev_f}",
                 f"OPEN={open_f if D.open_summary(st) else 'none'}", f"LIMITS={lim}"]
        if ex == "trader-senaryo":
            rec = [t for t in st["trades"] if t["book"] == ex and t["status"] == "closed"][-5:]
            rec_f = "none"
            if rec:
                rec_f = rundir / "recent_trader-senaryo.json"
                O.write_json(rec_f, [{k: t[k] for k in ("asset", "side", "exit_utc", "exit_reason", "r_mult")} for t in rec])
            lines.append(f"RECENT={rec_f}")
        if ex == "trader-makro":
            lines.append(gundem_line())
        lines.append(f"ASSETS={','.join(chunk)}. Follow your agent instructions. "
                     "Your final message must be only the ```json array (one block per asset). "
                     "Flat is the normal answer where your named setup is not fully met; never force a direction. "
                     "Every field is required (horizon_h too when flat); each rationale item <= 200 chars.")
        prompt = "\n".join(str(x) for x in lines)
        (rundir / f"prompt_{ex}{sfx}.txt").write_text(prompt, encoding="utf-8")
        tools, allowed = ("Read", ("Read",))
        if ex == "trader-makro":
            tools, allowed = "Read,WebFetch", ("Read", "WebFetch(domain:farside.co.uk)",   # ETF akisi yedegi
                                               "WebFetch(domain:www.coindesk.com)",       # manset kontrolu (beklenmeyen sok)
                                               "WebFetch(domain:feeds.bbci.co.uk)")       # manset yedegi
        jobs[key] = (prompt, tools, allowed)
    # kor tur: uzman ciktilari tur bitene dek ofis klasoru disinda (uzmanlar --add-dir ile ROOT'u okuyabilir)
    priv = O.pathlib.Path(tempfile.gettempdir()) / "trader-ofis-kor" / stamp
    priv.mkdir(parents=True, exist_ok=True)
    results = run_parallel(jobs, priv)
    bad = [k for k, r in results.items() if infra_error(r)]
    if bad and can_retry(asof, a):
        say(f"infra error {bad}: {results[bad[0]].get('error')}; retry once in {RETRY_WAIT_S // 60} min")
        time.sleep(RETRY_WAIT_S)
        global T0   # bekleme tur butcesinden (T_TOTAL) sayilmaz; yoksa Riza'ya 60 sn kalir
        T0 += RETRY_WAIT_S
        results.update(run_parallel({k: jobs[k] for k in bad}, priv))
    for f in priv.iterdir():
        shutil.move(str(f), str(rundir / f.name))
    shutil.rmtree(priv, ignore_errors=True)

    # 4. dogrulama + sinyaller.jsonl
    vb = O.validator("expert_block")
    valid_blocks, called, summary = [], [e["id"] for e in call], {}
    pkeys = {ex: ([ex] if len(parts) == 1 else [f"{ex}#{i}" for i in range(1, len(parts) + 1)]) for ex in called}
    # uzmanin butun partileri hata verdiyse uzman 'errored'; tek parti hatasi yalniz o partinin coinlerini dusurur
    errored = [ex for ex in called if all(results.get(k, {"error": "no result"}).get("error") for k in pkeys[ex])]
    total_fail = bool(called) and len(errored) == len(called)
    for b in auto:
        O.append_jsonl(O.ledger_file("sinyaller.jsonl"), {"run": stamp, "asof_utc": asof, "expert": b["expert"],
                                                     "asset": b["asset"], "valid": True, "errors": [], "block": b,
                                                     "reused": False, "auto": True, "snapshot_sha256": sha})
    for ex in called:
        rows, rs = [], []
        for k, chunk in zip(pkeys[ex], parts):
            r = results.get(k, {"error": "no result"})
            rs.append(r)
            parsed = O.extract_json(r.get("text")) if not r.get("error") else None
            rows += validate_blocks(ex, parsed, snap, cfg, vb, chunk) if not r.get("error") else \
                [{"asset": x, "valid": False, "errors": [r["error"]], "block": None} for x in chunk]
        if len(rs) > 1:   # partiler paralel: sure en uzunu, maliyet ve token toplam
            r = {"secs": max((x.get("secs") or 0) for x in rs),
                 **{f: sum((x.get(f) or 0) for x in rs) for f in ("turns", "cost_usd", "tok_in", "tok_cache_w",
                                                                 "tok_cache_r", "tok_out")},
                 "error": "; ".join(f"b{i}: {x['error']}" for i, x in enumerate(rs, 1) if x.get("error")) or None}
        for row in rows:
            O.append_jsonl(O.ledger_file("sinyaller.jsonl"), {"run": stamp, "asof_utc": asof, "expert": ex, **row,
                                                         "reused": False, "snapshot_sha256": sha})
            if row["valid"]:
                valid_blocks.append(row["block"])
        summary[ex] = {"secs": r.get("secs"), "turns": r.get("turns"), "cost_usd": r.get("cost_usd"),
                       "tok_in": r.get("tok_in"), "tok_cache_w": r.get("tok_cache_w"), "tok_cache_r": r.get("tok_cache_r"),
                       "tok_out": r.get("tok_out"), "error": r.get("error"),
                       **({"batches": [x.get("secs") for x in rs]} if len(rs) > 1 else {}),
                       "blocks": [f"{(x['block'] or {}).get('asset', x['asset'])}:"
                                  f"{(x['block'] or {}).get('bias', '?')}{'' if x['valid'] else '(INVALID: ' + '; '.join(x['errors'])[:160] + ')'}"
                                  for x in rows]}
        say(f"{ex}: {summary[ex]}")
    if not total_fail:   # kod kapisi durumu: bu tur analiz edilen coinler (+ tam turda rejim)
        try:
            import kapi as KP
            KP.kaydet(gate, snap, cfg["assets"], asof, stamp, full=not (gate and gate["gated"]),
                      test=bool(a.no_ledger or a.only))
        except Exception as e:  # noqa: BLE001
            say(f"gate state save failed: {type(e).__name__} {e}")
    reused = []
    for e in reuse:
        prev = [b for b in last_blocks(e["id"], stamp) if b.get("asset") in cfg["assets"]]   # tarayici: bu turun coinleri
        if prev:
            reused += [stale_macro(b) for b in prev]   # yalniz kapsadigi coinler; yasak etkisi yok (R5 taze ister)
            for b in prev:
                O.append_jsonl(O.ledger_file("sinyaller.jsonl"), {"run": stamp, "asof_utc": asof, "expert": e["id"],
                                                             "asset": b["asset"], "valid": True, "errors": [],
                                                             "block": b, "reused": True, "snapshot_sha256": sha})
            say(f"{e['id']}: reused blocks from {prev[0]['asof_utc']}")

    # 4b. komite (TASARIM.md 12, ofis-ayar.json committee): kapaliysa km None, kor bloklar aynen
    reused += auto   # kodun yazdigi Hakan flat'i: Riza gorur, golge defteri etkilemez
    import komite as KM
    km = None
    if total_fail:
        mark_failed(stamp, asof, f"all {len(called)} experts errored: {summary.get(errored[0], {}).get('error')}")
    else:
        km = KM.toplanti(cfg, a, snap, stamp, rundir, valid_blocks, reused, views, VIEW_OF, run_claude,
                         lambda ex, p: validate_blocks(ex, p, snap, cfg, vb), say)
    dec_blocks = km.blocks() if km and km.held else valid_blocks + reused

    # 5. risk
    decisions, dec_ok, risk_fail = [], False, False
    if not a.no_risk and not total_fail:
        experts_f = rundir / "experts.json"
        O.write_json(experts_f, dec_blocks)
        ledger_f, scores_f = rundir / "ledger.json", rundir / "scores.json"
        O.write_json(ledger_f, D.ledger_summary(st))
        sc = D.scores(st)
        O.write_json(scores_f, {k: {x: v[x] for x in ("closed", "hit_rate", "avg_r", "ev_r_ci90", "brier")} for k, v in sc.items()})
        rlim = " ".join(f"{k}={str(v).lower() if isinstance(v, bool) else v}" for k, v in R.items() if not k.startswith('_') and isinstance(v, (int, float, str)))
        try:
            import durdurma as DD
            off = sorted(DD.disabled(cfg))
        except Exception:  # noqa: BLE001
            off = []
        prompt = "\n".join([f"EXPERTS={experts_f}", f"SNAPSHOT={views['risk']}", gundem_line(),
                            f"OPEN={open_f if D.open_summary(st) else 'none'}", f"LEDGER={ledger_f}",
                            f"SCORES={scores_f}", f"LIMITS={rlim}", *(km.risk_lines() if km else []),
                            *([f"DISABLED_SETUPS={','.join(off)} (pre-registered stop rule: votes with these setups do "
                               "not count; code rejects opens relying on them)"] if off else []),
                            f"ASSETS={','.join(cfg['assets'])}. Follow your agent instructions. "
                            "Your final message must be only the ```json array (one decision per asset)."])
        (rundir / "prompt_trader-risk.txt").write_text(prompt, encoding="utf-8")
        left = max(60, min(T_RISK, T_TOTAL - (time.time() - T0) - 60))
        r = run_claude("trader-risk", prompt, left, rundir)
        if infra_error(r) and can_retry(asof, a):
            say(f"trader-risk infra error: {r.get('error')}; retry once in {RETRY_WAIT_S // 60} min")
            time.sleep(RETRY_WAIT_S)
            r = run_claude("trader-risk", prompt, T_RISK, rundir)
        risk_fail = bool(r.get("error"))
        if risk_fail:
            mark_failed(stamp, asof, f"trader-risk errored: {r.get('error')}")
        vd = O.validator("decision")
        parsed = O.extract_json(r.get("text")) if not r.get("error") else None
        errs = []
        if isinstance(parsed, list):
            for d in parsed:
                e = O.schema_errors(vd, d)
                if not e and d["asof_utc"] != asof:
                    e = [f"asof {d['asof_utc']} != {asof}"]
                if e:
                    errs.append(f"{(d or {}).get('asset') if isinstance(d, dict) else '?'}: {'; '.join(e)}")
                else:
                    decisions.append(d)
        else:
            errs.append(r.get("error") or "no parseable json array")
        dec_ok = bool(decisions)
        for d in decisions:
            O.append_jsonl(O.ledger_file("kararlar.jsonl"), {"run": stamp, "asof_utc": asof, "valid": True, **d})
        if errs:
            O.append_jsonl(O.ledger_file("kararlar.jsonl"), {"run": stamp, "asof_utc": asof, "valid": False, "errors": errs})
        summary["trader-risk"] = {"secs": r.get("secs"), "turns": r.get("turns"), "cost_usd": r.get("cost_usd"),
                                  "tok_in": r.get("tok_in"), "tok_cache_w": r.get("tok_cache_w"),
                                  "tok_cache_r": r.get("tok_cache_r"), "tok_out": r.get("tok_out"),
                                  "error": r.get("error"), "invalid": errs,
                                  "decisions": [f"{d['asset']}:{d['decision']}:{d['side']}" for d in decisions]}
        say(f"trader-risk: {summary['trader-risk']}")

    if km:
        km.close(decisions, [] if dec_ok else ["no valid decision"], test=a.no_ledger)
        summary["komite"] = km.summary()

    # 6. defter
    if not a.no_ledger:
        import kontrol as K
        with O.Kilit(wait_s=180) as k:
            if not k.ok:
                say("ledger lock busy: decisions logged but NOT applied")
            else:
                st = D.load_state()
                if not st["start_utc"]:
                    st["start_utc"] = snap["generated_utc"]
                    st["start_px"] = {s: (x or {}).get("ctx", {}).get("last_close") for s, x in snap["assets"].items()}
                ev, note = K.run(st)
                say(f"catch-up: events={ev} {note}")
                ok_dec = []
                for d in decisions:   # kod Riza'nin 'open' kararini bu turun bloklariyla yeniden denetler
                    if d.get("decision") == "open":
                        ok, why = D.validate_open(d, dec_blocks, cfg, snap)
                        if not ok:
                            say(f"open REJECTED by code {d.get('asset')}: {why}")
                            continue
                    ok_dec.append(d)
                res = D.apply_decisions(st, ok_dec, snap, stamp, dec_blocks) if dec_ok else []
                say(f"applied: {res}")
                # hata veren uzmanin bekleyen golge emri sure dolmus sayilmaz (altyapi hatasi != dolmayan emir)
                D.add_shadow(st, valid_blocks, called, stamp, snap, errored=errored,
                             hold_assets=tuple(gate["gated"]) if gate else ())
                if km:
                    km.shadow(D, st, stamp, snap)
                loose_step(snap, stamp, cfg, dec_blocks, run_round=not total_fail)
                for d in decisions:
                    st["last_decisions"][d["asset"]] = {"asof_utc": asof, "decision": d["decision"], "neco_tr": d["neco_tr"]}
                D.refresh_paper(st)
                D.append_equity(st)
                D.write_reports(st)
                D.save_state(st)

    tot = {k: sum((s.get(k) or 0) for s in summary.values()) for k in ("tok_in", "tok_cache_w", "tok_cache_r", "tok_out", "cost_usd")}
    summary["_total"] = {**tot, "secs": round(time.time() - T0)}
    summary["_total"]["errored"] = errored
    if gate:
        summary["kapi"] = gate
    O.write_json(rundir / "ozet.json", summary)
    try:
        n = cleanup_old()
        if n:
            say(f"cleanup: removed {n} log/grafik dirs older than {LOG_KEEP_DAYS} days")
    except Exception as e:  # noqa: BLE001
        say(f"cleanup failed: {e}")
    if not (total_fail or risk_fail) and not a.no_ledger:
        try:
            D.clear_failed_round()
        except Exception as e:  # noqa: BLE001
            say(f"clear_failed_round failed: {e}")
    say(f"=== round {stamp} done in {round(time.time() - T0)}s tokens={tot} errored={errored}")
    return 4 if (total_fail or risk_fail) else 0


def elliott_ileri_hook():
    """Elliott k=4 3. dalga ileri sahte para testi (test_ekrem/ileri_plan.md): ayri defter, LLM yok. Turu asla bozmaz."""
    try:
        p = subprocess.run([str(O.PY), "-W", "ignore", str(O.ROOT / "elliott_ileri.py")], cwd=str(O.REPO),
                           capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=240,
                           creationflags=NOWIN)
        say(f"elliott_ileri rc={p.returncode}" + ("" if p.returncode == 0 else f" {p.stderr.strip()[-400:]}"))
    except Exception as e:  # noqa: BLE001
        say(f"elliott_ileri FAILED (round unaffected): {type(e).__name__} {e}")


def rapor_hook():
    """Haftalik rapor (rapor.py): son pazar 21:00 TR'den sonraki ilk turda bir kez. Turu asla bozmaz."""
    try:
        import rapor
        rapor.zamani_geldiyse(log=say)
    except Exception as e:  # noqa: BLE001
        say(f"weekly report FAILED (round unaffected): {type(e).__name__} {e}")


def grafik_hook():
    """Islem grafikleri sayfasi (islem_grafik.py -> islemler.html). Turu asla bozmaz; en fazla 90 sn."""
    try:
        p = subprocess.run([str(O.PY), "-W", "ignore", str(O.ROOT / "islem_grafik.py")], cwd=str(O.REPO),
                           capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=90,
                           creationflags=NOWIN)
        say(f"islem_grafik rc={p.returncode}" + ("" if p.returncode == 0 else f" {p.stderr.strip()[-300:]}"))
    except Exception as e:  # noqa: BLE001
        say(f"islem_grafik FAILED (round unaffected): {type(e).__name__} {e}")


if __name__ == "__main__":
    os.chdir(O.ROOT)
    sys.path.insert(0, str(O.ROOT))
    with TurKilit() as _k:
        if not _k.ok:
            say(f"round lock busy ({TUR_KILIT}): another round is running, skip")
            sys.exit(5)
        rc = 3
        try:
            rc = main()
        except SystemExit as _e:
            rc = _e.code
        except Exception:  # noqa: BLE001
            import traceback
            say("CRASH " + traceback.format_exc().replace("\n", " | ")[:2000])
            rc = 3
        elliott_ileri_hook()
        rapor_hook()
        grafik_hook()
        sys.exit(rc)
