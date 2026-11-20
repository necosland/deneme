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
Butce: veri 4 dk + uzmanlar 5 dk (paralel) + risk 4 dk < 15 dk.

Kullanim: python algo/ofis/tur.py [--force] [--skip-data] [--only trader-a,trader-b] [--no-risk] [--no-ledger]
"""
import argparse
import concurrent.futures as cf
import hashlib
import json
import os
import subprocess
import sys
import time

import ortak as O

NOWIN = getattr(subprocess, "CREATE_NO_WINDOW", 0)
T_DATA, T_EXPERT, T_RISK, T_TOTAL = 240, 300, 240, 15 * 60
VIEW_OF = {"trader-likidite": "fiyat", "trader-elliott": "fiyat", "trader-seviye": "fiyat", "trader-senaryo": "senaryo",
           "trader-turev": "turev", "trader-makro": "makro", "trader-risk": "risk", "trader-harmonik": "harmonik"}
LOGF = "tur.log"
T0 = time.time()


def say(msg):
    O.log(LOGF, msg)


# ---------------- gorunumler ----------------
def make_view(snap, role):
    from veri_topla import dump
    keep_top = ("asof_utc", "generated_utc", "mode", "legend")
    v = {k: snap.get(k) for k in keep_top}
    macro = snap.get("macro") if isinstance(snap.get("macro"), dict) else {}
    cal = {"calendar_usd_high": macro.get("calendar_usd_high")}
    omitted = []
    v["assets"] = {}
    for sym, a in (snap.get("assets") or {}).items():
        if a is None:
            v["assets"][sym] = None
            continue
        if role in ("fiyat", "senaryo"):
            x = {k: val for k, val in a.items() if k not in ("derivs", "harmonics")}
            x["candles"] = {k: val for k, val in a["candles"].items() if k != "15m"}
            omitted = ["assets.*.derivs", "assets.*.harmonics", "assets.*.candles.15m", "sentiment",
                       "macro except calendar_usd_high"]
            if role == "senaryo":   # Bora'nin OI filtresi icin turev ozeti
                dv = a.get("derivs") or {}
                x["derivs_lite"] = {k: dv.get(k) for k in ("source", "oi_usd_bn", "oi_chg_24h_pct", "oi_chg_7d_pct",
                                                           "funding_7d_avg", "funding_last")}
                omitted[0] = "assets.*.derivs (except derivs_lite)"
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
                 "derivs": a.get("derivs"), "charts": a.get("charts")}
            omitted = ["structure.1d", "fvg", "equal_hl", "vp", "candles except last 12x4h", "macro except calendar_usd_high"]
        elif role == "makro":
            x = {"ctx": a["ctx"], "levels": a["levels"], "structure": {"1d": a["structure"]["1d"]},
                 "candles": {"1d": a["candles"]["1d"]}, "charts": a.get("charts")}
            omitted = ["structure 4h/1h", "fvg", "equal_hl", "vp", "candles 4h/1h/15m", "derivs"]
        elif role == "risk":
            x = {"ctx": a["ctx"], "levels": a["levels"]}
            omitted = ["everything except ctx, levels, macro.calendar_usd_high"]
        else:
            x = a
        v["assets"][sym] = x
    if role == "makro":
        v["sentiment"], v["macro"] = snap.get("sentiment"), snap.get("macro")
    elif role == "turev":
        v["sentiment"], v["macro"] = snap.get("sentiment"), cal
    elif role in ("fiyat", "risk", "harmonik", "senaryo"):
        v["macro"] = cal
    else:
        v["sentiment"], v["macro"] = snap.get("sentiment"), snap.get("macro")
    v["errors"] = snap.get("errors")
    if omitted:
        v["_view"] = (f"Trimmed snapshot for role '{role}' to save tokens. Omitted ON PURPOSE (not missing data, "
                      f"do not list in data_gaps): {', '.join(omitted)}.")
    return dump(v) + "\n"


# ---------------- claude ----------------
def run_claude(agent, prompt, timeout, rundir, tools="Read", allowed=("Read",)):
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
    (rundir / f"{agent}.out.json").write_text(out, encoding="utf-8")
    if err.strip():
        (rundir / f"{agent}.err.txt").write_text(err, encoding="utf-8")
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


# ---------------- dosyalar ----------------
def last_blocks(expert, before_run):
    rows = [r for r in O.read_jsonl(O.DEFTER / "sinyaller.jsonl")
            if r.get("expert") == expert and r.get("valid") and not r.get("reused") and r.get("run") != before_run]
    if not rows:
        return []
    last = rows[-1]["run"]
    return [r["block"] for r in rows if r["run"] == last]


def limits_line(R):
    return " ".join(f"{k}={R[k]}" for k in ("min_rr_t1", "min_stop_atr4h", "max_confidence", "event_blackout_h"))


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


def validate_blocks(expert, parsed, snap, cfg, v):
    R = cfg["risk"]
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
            if b["bias"] in ("long", "short"):
                ctx = ((snap["assets"].get(asset) or {}).get("ctx") or {})
                errs += O.geometry_errors(b["bias"], b["entry"], b["stop"], b["targets"], ctx.get("last_close"),
                                          (ctx.get("atr14") or {}).get("4h"), R)
        seen.add(asset)
        rows.append({"asset": asset, "valid": not errs, "errors": errs, "block": b, "normalized": fixes})
    for a in cfg["assets"]:
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
    a = ap.parse_args()
    cfg = O.ayar()
    R = cfg["risk"]
    stamp = O.now_utc().strftime("%Y%m%d_%H%M")
    rundir = O.LOG / stamp
    rundir.mkdir(parents=True, exist_ok=True)
    say(f"=== round {stamp} start (claude={O.find_claude()})")

    # 1. veri
    if a.skip_data:
        snap_path = O.VERI / "son.json"
    else:
        p = subprocess.run([str(O.PY), str(O.ROOT / "veri_topla.py")], cwd=str(O.REPO), capture_output=True,
                           text=True, encoding="utf-8", errors="replace", timeout=T_DATA, creationflags=NOWIN)
        say(f"veri_topla rc={p.returncode} {p.stdout.strip()[-300:]}")
        if p.returncode != 0:
            say("veri_topla FAILED: " + p.stderr.strip()[-800:])
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

    # 2. gorunumler
    views = {}
    for role in set(VIEW_OF.values()):
        f = rundir / f"view_{role}.json"
        f.write_text(make_view(snap, role), encoding="utf-8")
        views[role] = f
    say("views ~tokens: " + ", ".join(f"{r}={f.stat().st_size // 4}" for r, f in sorted(views.items())))

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
    jobs = {}
    lim = limits_line(R)
    for e in call:
        ex = e["id"]
        prev = last_blocks(ex, stamp)
        prev_f = "none"
        if prev:
            prev_f = rundir / f"prev_{ex}.json"
            O.write_json(prev_f, prev)
        lines = [f"SNAPSHOT={views[VIEW_OF.get(ex, 'full')] if ex in VIEW_OF else snap_path}",
                 f"CHARTS={charts_line(snap)}", f"PREV={prev_f}",
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
        lines.append(f"ASSETS={','.join(cfg['assets'])}. Follow your agent instructions. "
                     "Your final message must be only the ```json array (one block per asset). "
                     "Every field is required (horizon_h too when flat); each rationale item <= 200 chars.")
        prompt = "\n".join(str(x) for x in lines)
        (rundir / f"prompt_{ex}.txt").write_text(prompt, encoding="utf-8")
        tools, allowed = ("Read", ("Read",))
        if ex == "trader-makro":
            tools, allowed = "Read,WebFetch", ("Read", "WebFetch(domain:farside.co.uk)",   # ETF akisi yedegi
                                               "WebFetch(domain:www.coindesk.com)",       # manset kontrolu (beklenmeyen sok)
                                               "WebFetch(domain:feeds.bbci.co.uk)")       # manset yedegi
        jobs[ex] = (prompt, tools, allowed)
    results = {}
    with cf.ThreadPoolExecutor(max_workers=max(1, len(jobs))) as pool:
        futs = {pool.submit(run_claude, ex, p, T_EXPERT, rundir, t, al): ex for ex, (p, t, al) in jobs.items()}
        for f in cf.as_completed(futs):
            results[futs[f]] = f.result()

    # 4. dogrulama + sinyaller.jsonl
    vb = O.validator("expert_block")
    valid_blocks, called, summary = [], [e["id"] for e in call], {}
    for ex in called:
        r = results.get(ex, {"error": "no result"})
        parsed = O.extract_json(r.get("text")) if not r.get("error") else None
        rows = validate_blocks(ex, parsed, snap, cfg, vb) if not r.get("error") else \
            [{"asset": x, "valid": False, "errors": [r["error"]], "block": None} for x in cfg["assets"]]
        for row in rows:
            O.append_jsonl(O.DEFTER / "sinyaller.jsonl", {"run": stamp, "asof_utc": asof, "expert": ex, **row,
                                                         "reused": False, "snapshot_sha256": sha})
            if row["valid"]:
                valid_blocks.append(row["block"])
        summary[ex] = {"secs": r.get("secs"), "turns": r.get("turns"), "cost_usd": r.get("cost_usd"),
                       "tok_in": r.get("tok_in"), "tok_cache_w": r.get("tok_cache_w"), "tok_cache_r": r.get("tok_cache_r"),
                       "tok_out": r.get("tok_out"), "error": r.get("error"),
                       "blocks": [f"{(x['block'] or {}).get('asset', x['asset'])}:"
                                  f"{(x['block'] or {}).get('bias', '?')}{'' if x['valid'] else '(INVALID: ' + '; '.join(x['errors'])[:160] + ')'}"
                                  for x in rows]}
        say(f"{ex}: {summary[ex]}")
    reused = []
    for e in reuse:
        prev = last_blocks(e["id"], stamp)
        if prev:
            reused += prev
            for b in prev:
                O.append_jsonl(O.DEFTER / "sinyaller.jsonl", {"run": stamp, "asof_utc": asof, "expert": e["id"],
                                                             "asset": b["asset"], "valid": True, "errors": [],
                                                             "block": b, "reused": True, "snapshot_sha256": sha})
            say(f"{e['id']}: reused blocks from {prev[0]['asof_utc']}")

    # 4b. komite (TASARIM.md 12, ofis-ayar.json committee): kapaliysa km None, kor bloklar aynen
    import komite as KM
    km = KM.toplanti(cfg, a, snap, stamp, rundir, valid_blocks, reused, views, VIEW_OF, run_claude,
                     lambda ex, p: validate_blocks(ex, p, snap, cfg, vb), say)
    dec_blocks = km.blocks() if km and km.held else valid_blocks + reused

    # 5. risk
    decisions, dec_ok = [], False
    if not a.no_risk:
        experts_f = rundir / "experts.json"
        O.write_json(experts_f, dec_blocks)
        ledger_f, scores_f = rundir / "ledger.json", rundir / "scores.json"
        O.write_json(ledger_f, D.ledger_summary(st))
        sc = D.scores(st)
        O.write_json(scores_f, {k: {x: v[x] for x in ("closed", "hit_rate", "avg_r", "ev_r_ci90", "brier")} for k, v in sc.items()})
        rlim = " ".join(f"{k}={v}" for k, v in R.items() if isinstance(v, (int, float)) and not isinstance(v, bool))
        prompt = "\n".join([f"EXPERTS={experts_f}", f"SNAPSHOT={views['risk']}", gundem_line(),
                            f"OPEN={open_f if D.open_summary(st) else 'none'}", f"LEDGER={ledger_f}",
                            f"SCORES={scores_f}", f"LIMITS={rlim}", *(km.risk_lines() if km else []),
                            f"ASSETS={','.join(cfg['assets'])}. Follow your agent instructions. "
                            "Your final message must be only the ```json array (one decision per asset)."])
        (rundir / "prompt_trader-risk.txt").write_text(prompt, encoding="utf-8")
        left = max(60, min(T_RISK, T_TOTAL - (time.time() - T0) - 60))
        r = run_claude("trader-risk", prompt, left, rundir)
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
            O.append_jsonl(O.DEFTER / "kararlar.jsonl", {"run": stamp, "asof_utc": asof, "valid": True, **d})
        if errs:
            O.append_jsonl(O.DEFTER / "kararlar.jsonl", {"run": stamp, "asof_utc": asof, "valid": False, "errors": errs})
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
                res = D.apply_decisions(st, decisions, snap, stamp, dec_blocks) if dec_ok else []
                say(f"applied: {res}")
                D.add_shadow(st, valid_blocks, called, stamp, snap)
                if km:
                    km.shadow(D, st, stamp, snap)
                for d in decisions:
                    st["last_decisions"][d["asset"]] = {"asof_utc": asof, "decision": d["decision"], "neco_tr": d["neco_tr"]}
                D.refresh_paper(st)
                D.append_equity(st)
                D.write_reports(st)
                D.save_state(st)

    tot = {k: sum((s.get(k) or 0) for s in summary.values()) for k in ("tok_in", "tok_cache_w", "tok_cache_r", "tok_out", "cost_usd")}
    summary["_total"] = {**tot, "secs": round(time.time() - T0)}
    O.write_json(rundir / "ozet.json", summary)
    say(f"=== round {stamp} done in {round(time.time() - T0)}s tokens={tot}")
    return 0


if __name__ == "__main__":
    os.chdir(O.ROOT)
    sys.path.insert(0, str(O.ROOT))
    try:
        sys.exit(main())
    except Exception:  # noqa: BLE001
        import traceback
        say("CRASH " + traceback.format_exc().replace("\n", " | ")[:2000])
        sys.exit(3)
