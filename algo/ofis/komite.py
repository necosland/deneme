"""Trader ofisi komitesi (sahte para): kor turdan sonra Riza baskanliginda tartisma.

Akis (TASARIM.md bolum 12):
 1. Tur 1 kor: uzman bloklari tur.py'de her zamanki gibi (bagimsizlik; suru etkisi yok). sinyaller.jsonl bunlardir.
 2. Tetik: gecerli bir long/short blok varsa toplanti; hepsi flat ise atlanir, tek satir tutanak yazilir.
 3. Tur 2: Riza gundem yazar (adli uzmana soru) -> sorulan uzmanlar (+ karsi yondekiler) paralel yanitlar:
    cevap, itiraz/katilma, hold | revise (yeni blok) | withdraw.
 4. Tur 3 (istege bagli): tur 2'de gorus degistiyse ya da yeni catisma ciktiysa, etkilenen varliktaki
    degismeyen uzmanlar bir kez daha konusur (baskan cagrisi yok, maliyet).
 5. Kapanis: tur.py'nin risk adimi, EXPERTS = toplanti sonrasi bloklar + MEETING = tutanak (Ingilizce, ic).
 6. Tutanak (Turkce, Neco icin, <=15 satir): toplanti/YYYY-MM-DD_HHMM.md. Olcum: defter/toplanti.jsonl
    (kor ve toplanti sonrasi gorusler, degisiklikler, maliyet) + degisen gorusler icin golge defter "komite:<uzman>".
Ayar: ofis-ayar.json "committee". Kapaliyken tur.py eskisi gibi calisir.
"""
import concurrent.futures as cf
import json
import time

import ortak as O

TOPLANTI = O.ROOT / "toplanti"
DIRS = ("long", "short")
TR_BIAS = {"long": "yükseliş", "short": "düşüş", "flat": "beklemede"}
TR_DEC = {"open": "işlem açılıyor", "keep": "pozisyon korunuyor", "tighten_stop": "zarar durdur sıkılaştırıldı",
          "close": "pozisyon kapatılıyor", "cancel_pending": "bekleyen emir iptal", "none": "işlem yok"}
DEFAULTS = {"enabled": False, "max_rounds": 3, "max_questions": 6, "max_speakers_r2": 6, "max_speakers_r3": 3,
            "reply_words": 60, "t_chair": 150, "t_reply": 150, "max_secs": 480, "max_cost_usd": 1.2}
NOTE = O.AGENT_BILGI / "ortak" / "toplanti.md"


def conf(cfg):
    return {**DEFAULTS, **(cfg.get("committee") or {})}


def names(cfg):
    m = {e["id"]: e["name"] for e in cfg["experts"]}
    m[cfg["head"]["id"]] = cfg["head"]["name"]
    return m


def short(a):
    return a.replace("USDT", "")


def vline(b, nm):
    """Bir blogun tek satir ozeti (ajanlara giden tablo)."""
    who = f"{nm.get(b['expert'], b['expert'])}({b['expert'].replace('trader-', '')})"
    s = f"{who} {short(b['asset'])} {b['bias'].upper()}"
    if b["bias"] in DIRS:
        e = b.get("entry") or {}
        s += (f" {e.get('type')}@{e.get('price') or 'mkt'} stop {b['stop']} T {'/'.join(str(t) for t in b['targets'])}"
              f" conf {b['confidence']} h{b['horizon_h']} setup '{b.get('setup')}' inval '{b.get('invalidation')}'")
    elif b.get("asof_utc"):
        s += f" conf {b['confidence']}"
    rat = b.get("rationale") or []
    if b["bias"] not in DIRS:   # flat: tek gerekce yeter (token)
        rat = [r[:200] for r in rat[:1]]
    return s + " | " + " ; ".join(rat)


def conflicts(blocks):
    """varlik -> {long:[uzman], short:[uzman]}; yalniz iki yon de varsa."""
    out = {}
    for a in {b["asset"] for b in blocks}:
        d = {k: [b["expert"] for b in blocks if b["asset"] == a and b["bias"] == k] for k in DIRS}
        if d["long"] and d["short"]:
            out[a] = d
    return out


def key(b):
    return (b["expert"], b["asset"])


class Toplanti:
    def __init__(self, cfg, args, snap, stamp, rundir, blocks, reused, views, view_of, run_claude, validate, say):
        self.cfg, self.c, self.nm = cfg, conf(cfg), names(cfg)
        self.snap, self.asof, self.stamp, self.say = snap, snap["asof_utc"], stamp, say
        self.dir = rundir / "komite"
        self.views, self.view_of, self.run_claude, self.validate = views, view_of, run_claude, validate
        self.pre = {key(b): b for b in blocks + reused}
        self.cur = dict(self.pre)
        self.reused_keys = {key(b) for b in reused}
        self.t0, self.calls, self.lines, self.changes, self.talk = time.time(), [], [], [], []
        self.rounds, self.agenda_tr, self.skipped = 1, "", None
        self.transcript_f = self.dir / "toplanti.md"

    # ---------- yardimcilar ----------
    def cost(self):
        return sum(c.get("cost_usd") or 0 for c in self.calls)

    def w(self, s=""):
        self.lines.append(s)
        self.transcript_f.write_text("\n".join(self.lines) + "\n", encoding="utf-8")

    def views_table(self, d):
        return "\n".join(vline(b, self.nm) for b in sorted(d.values(), key=lambda b: (b["asset"], b["expert"])))

    def call(self, agent, prompt, timeout, sub):
        d = self.dir / sub
        d.mkdir(parents=True, exist_ok=True)
        (d / f"prompt_{agent}.txt").write_text(prompt, encoding="utf-8")
        r = self.run_claude(agent, prompt, timeout, d)
        self.calls.append({"agent": agent, "sub": sub, **{k: r.get(k) for k in ("secs", "cost_usd", "tok_in",
                           "tok_cache_w", "tok_cache_r", "tok_out", "error")}})
        return r

    def resolve(self, to):
        """Baskanin 'to' alani: kimlik, 'trader-<ad>' ya da ad (2026-11-21 ilk denemede 'trader-selin' yazdi)."""
        fold = str.maketrans("ıİşŞğĞüÜöÖçÇ", "iissgguuoocc")
        t = str(to or "").strip().lower().translate(fold).replace("trader-", "")
        for ex in {b["expert"] for b in self.cur.values()}:
            if t in (ex.replace("trader-", ""), self.nm.get(ex, "").lower().translate(fold)):
                return ex
        return None

    def ids_line(self):
        return "IDS (use exactly in 'to'): " + ", ".join(
            f"{self.nm.get(ex, ex)}={ex}" for ex in sorted({b['expert'] for b in self.cur.values()}))

    def directional(self, d=None):
        return [b for b in (d or self.cur).values() if b["bias"] in DIRS]

    def vote_ok(self, b, bump=0):
        """Oy esigini geciyor mu (bump: guvene eklenen puan, 'esige 3 puan yakin' icin)."""
        R = self.cfg["risk"]
        conf = (b.get("confidence") or 0) + bump
        try:
            last = (((self.snap.get("assets") or {}).get(b["asset"]) or {}).get("ctx") or {}).get("last_close")
            if hasattr(O, "vote_passes") and hasattr(O, "rr_cost") and b.get("targets"):
                rr, cost_r, _ = O.rr_cost(b["bias"], b["entry"], b["stop"], b["targets"][0], last, R)
                return O.vote_passes(conf, rr, cost_r, R)[0]
        except Exception:  # noqa: BLE001
            pass
        return conf >= R.get("min_confidence", 55)

    def can_change(self):
        """Toplanti sonucu degistirebilir mi (denetim 2026-11-21): bir coinde ayni yonde >=2 oy esikte ya da
        esige 3 puan yakin, veya gecerli (esigi gecen) oylar arasinda gercek long/short catismasi. Degilse sonuc
        zaten 'none': toplanti yapilmaz (~%16 tasarruf)."""
        dirs = self.directional()
        for a in {b["asset"] for b in dirs}:
            for s in DIRS:
                if sum(1 for b in dirs if b["asset"] == a and b["bias"] == s and self.vote_ok(b, 3)) >= 2:
                    return f"{a} {s}: >=2 votes at/near threshold"
            if all(any(b["asset"] == a and b["bias"] == s and self.vote_ok(b) for b in dirs) for s in DIRS):
                return f"{a}: long/short conflict between valid votes"
        return None

    # ---------- tur 2: gundem ----------
    def agenda(self):
        c = self.c
        prompt = "\n".join([
            "MEETING MODE: you chair the trader committee (round 2). Do NOT run your decision workflow; no decision now.",
            f"Read {NOTE} section 'Chair' only if unsure. SNAPSHOT={self.views['risk']} (only to verify a number).",
            f"ASOF={self.asof}. Blind round-1 views (one line each):", self.views_table(self.cur),
            f"CONFLICTS={json.dumps(conflicts(list(self.cur.values())))}", self.ids_line(),
            f"Task: find the crux per asset and ask <= {c['max_questions']} questions to NAMED experts (ids above). "
            "Each question <= 40 words, terse telegraphic English, numbers > prose, cite the other expert's claim "
            "(e.g. 'Selin: Tolga expects sweep >60.5k before drop; does your short survive?'). "
            "Every long/short view must face >= 1 challenge (ask its owner, or ask an opposing/flat expert whether "
            "they support or refute it). Use your rules: R2 conflict, R3 needs >=2 same-side votes incl. a level "
            "expert, R6 CONTEXT tags. Seek evidence, not consensus; never ask anyone to agree.",
            "Final message only ```json {\"agenda\":[{\"q\":1,\"to\":\"trader-x\",\"asset\":\"BTCUSDT\",\"text\":\"...\"}],"
            "\"tr\":\"<=15 Turkish words for Neco: what the meeting is about\"}"])
        r = self.call(self.cfg["head"]["id"], prompt, c["t_chair"], "r2_gundem")
        j = O.extract_json(r.get("text")) if not r.get("error") else None
        qs = []
        if isinstance(j, dict) and isinstance(j.get("agenda"), list):
            self.agenda_tr = str(j.get("tr") or "")[:160]
            for q in j["agenda"]:
                to = self.resolve(q.get("to")) if isinstance(q, dict) else None
                if to and q.get("text") and len(qs) < c["max_questions"]:
                    qs.append({"q": len(qs) + 1, "to": to, "asset": q.get("asset"), "text": str(q["text"])[:400], "by": "chair"})
                elif isinstance(q, dict):
                    self.say(f"komite: agenda item to={q.get('to')!r} dropped")
        if not qs:   # baskan cagrisi bozuksa kodla gundem: her yonlu gorus sahibi savunur
            self.say(f"komite: chair agenda unusable ({r.get('error') or 'no json'}) -> auto agenda")
            for i, b in enumerate(self.directional()[:c["max_questions"]], 1):
                opp = [vline(x, self.nm) for x in self.cur.values() if x["asset"] == b["asset"] and x["expert"] != b["expert"]]
                qs.append({"q": i, "to": b["expert"], "asset": b["asset"], "by": "auto",
                           "text": f"Defend your {b['bias']} on {short(b['asset'])} vs others: " + " || ".join(o[:120] for o in opp[:4])})
        return qs

    # ---------- yanit ----------
    def reply_prompt(self, ex, qs, rnd):
        own = {k: v for k, v in self.cur.items() if k[0] == ex}
        view = self.views.get(self.view_of.get(ex, "fiyat"))
        qtxt = "\n".join(f"Q{q['q']} [{q.get('asset')}] {q['text']}" for q in qs) or \
            "No direct question: you hold an opposing/affected view. Rebut or support briefly, or hold."
        return "\n".join([
            f"MEETING MODE (committee round {rnd}, chair Rıza). Do NOT run your round workflow or re-read INDEX/method files.",
            f"Read {NOTE} (reply rules) first. SNAPSHOT={view} (open only to verify a number). ASOF={self.asof}.",
            f"LIMITS={' '.join(f'{k}={self.cfg['risk'][k]}' for k in ('min_rr_t1', 'min_stop_atr4h', 'max_confidence'))}",
            "YOUR CURRENT VIEW:", self.views_table(own) or "none",
            "ALL CURRENT VIEWS:", self.views_table(self.cur),
            "TRANSCRIPT SO FAR:", "\n".join(self.lines[self._tstart:]) or "(none)",
            "QUESTIONS TO YOU:", qtxt,
            f"Reply terse telegraphic English, <= {self.c['reply_words']} words total in answers. Change view only on evidence. "
            "Final message only ```json {\"answers\":[{\"q\":1,\"stance\":\"agree|rebut|answer\",\"text\":\"...\"}],"
            "\"view\":\"hold|revise|withdraw\",\"assets\":[\"BTCUSDT\"],\"reason\":\"<=25 words\","
            "\"tr\":\"<=15 Turkish words\",\"blocks\":[]}"])

    def apply_reply(self, ex, r, rnd):
        name = self.nm.get(ex, ex)
        j = O.extract_json(r.get("text")) if not r.get("error") else None
        if not isinstance(j, dict):
            self.w(f"- {name}: no valid reply ({r.get('error') or 'no json'}) -> hold")
            return
        for a in j.get("answers") or []:
            if isinstance(a, dict):
                self.w(f"- {name} Q{a.get('q', '?')} {a.get('stance', '')}: {str(a.get('text', ''))[:600]}")
        view, reason = j.get("view", "hold"), str(j.get("reason") or "")[:300]
        self.talk.append({"round": rnd, "expert": ex, "view": view, "tr": str(j.get("tr") or "")[:160], "reason": reason})
        new = []
        if view == "revise" and isinstance(j.get("blocks"), list) and j["blocks"]:
            for row in self.validate(ex, j["blocks"]):
                if row.get("errors") == ["missing block"]:
                    continue
                if row["valid"]:
                    new.append(row["block"])
                else:
                    self.w(f"  {name} revision {row.get('asset')} INVALID ({'; '.join(row['errors'])[:160]}) -> kept old view")
        elif view == "withdraw":
            for a in j.get("assets") or []:
                old = self.cur.get((ex, a))
                if old and old["bias"] != "flat":
                    new.append({"expert": ex, "asof_utc": self.asof, "asset": a, "action": "cancel", "bias": "flat",
                                "timeframe": old["timeframe"], "setup": None, "entry": None, "stop": None, "targets": [],
                                "invalidation": "withdrawn in committee", "confidence": 50, "horizon_h": 4,
                                "rationale": [("committee withdraw: " + reason)[:200]], "data_gaps": []})
        for b in new:
            old = self.cur.get(key(b))
            if old and (old["bias"], old.get("entry"), old.get("stop"), old.get("targets")) == \
                    (b["bias"], b.get("entry"), b.get("stop"), b.get("targets")):
                continue
            self.changes.append({"round": rnd, "expert": ex, "asset": b["asset"], "from": old["bias"] if old else None,
                                 "to": b["bias"], "from_conf": old.get("confidence") if old else None,
                                 "to_conf": b["confidence"], "reason": reason})
            self.cur[key(b)] = b
            self.reused_keys.discard(key(b))
            self.w(f"  CHANGE {name} {short(b['asset'])}: {old['bias'] if old else '-'} -> {vline(b, self.nm)[:260]}")
        self.w(f"  {name}: view={view}; reason: {reason}")

    def speak(self, who, rnd):
        """who: {uzman: [soru]} paralel yanit."""
        sub = f"r{rnd}_yanit"
        res = {}
        with cf.ThreadPoolExecutor(max_workers=max(1, len(who))) as pool:
            futs = {pool.submit(self.call, ex, self.reply_prompt(ex, qs, rnd), self.c["t_reply"], sub): ex
                    for ex, qs in who.items()}
            for f in cf.as_completed(futs):
                res[futs[f]] = f.result()
        self.w(f"\n## Round {rnd} replies")
        for ex in who:   # gundem sirasiyla
            self.apply_reply(ex, res[ex], rnd)

    # ---------- ana ----------
    def run(self):
        c = self.c
        self.dir.mkdir(parents=True, exist_ok=True)
        if not self.directional():
            self.skipped = "all flat, no conflict"
            return self
        why = self.can_change()
        if not why:
            self.skipped = "cannot change outcome (<2 votes near threshold per asset/side, no valid-vote conflict)"
            self.say(f"komite skipped: {self.skipped}")
            return self
        self.say(f"komite held: {why}")
        self._tstart = 0
        self.w(f"# Committee {self.stamp} asof {self.asof} (internal, English)")
        self.w("## Round 1 blind views\n" + self.views_table(self.pre))
        qs = self.agenda()
        self._tstart = len(self.lines)
        self.w("\n## Round 2 agenda (chair Rıza)")
        for q in qs:
            self.w(f"Q{q['q']} -> {self.nm.get(q['to'], q['to'])} [{q.get('asset')}]: {q['text']}")
        who = {}
        for q in qs:
            who.setdefault(q["to"], []).append(q)
        # karsi gorus: soru almamis ama sorulan varlikta zit yonde gorusu olan uzman da konusur
        asked_assets = {q.get("asset") for q in qs}
        for a, d in conflicts(list(self.cur.values())).items():
            if a in asked_assets or not asked_assets:
                for ex in d["long"] + d["short"]:
                    who.setdefault(ex, [])
        who = dict(list(who.items())[:c["max_speakers_r2"]])
        self.rounds = 2
        self.speak(who, 2)
        pre_conf = set(conflicts(list(self.pre.values())))
        new_conf = set(conflicts(list(self.cur.values()))) - pre_conf
        changed_assets = {x["asset"] for x in self.changes}
        if c["max_rounds"] >= 3 and (changed_assets or new_conf):
            if time.time() - self.t0 > c["max_secs"] / 2 or self.cost() > c["max_cost_usd"] * 0.6:
                self.w(f"\n(round 3 skipped: budget secs={round(time.time() - self.t0)} cost={self.cost():.2f})")
            else:
                aff = changed_assets | new_conf
                changers = {x["expert"] for x in self.changes}
                cand = [ex for ex in who if ex not in changers]
                cand += [b["expert"] for b in self.directional() if b["asset"] in aff and b["expert"] not in changers]
                r3, seen = {}, set()
                for ex in cand:
                    if ex in seen:
                        continue
                    seen.add(ex)
                    if any(k[0] == ex and k[1] in aff for k in self.cur):
                        r3[ex] = [{"q": 0, "asset": ",".join(sorted(aff)), "text":
                                   "Round 3. Views changed/new conflict: " + "; ".join(
                                       f"{self.nm.get(x['expert'], x['expert'])} {short(x['asset'])} {x['from']}->{x['to']}"
                                       for x in self.changes) + ". React to the new points: hold or revise, with evidence."}]
                r3 = dict(list(r3.items())[:c["max_speakers_r3"]])
                if r3:
                    self.rounds = 3
                    self.w("\n## Round 3 (no chair call; affected: " + ", ".join(self.nm.get(x, x) for x in r3)
                           + ")\n" + next(iter(r3.values()))[0]["text"])
                    self.speak(r3, 3)
        self.w("\n## Final views (post-debate; EXPERTS for the decision)\n" + self.views_table(self.cur))
        self.w("Changes: " + ("; ".join(f"r{x['round']} {self.nm.get(x['expert'])} {short(x['asset'])} "
                                         f"{x['from']}->{x['to']} ({x['reason'][:120]})" for x in self.changes) or "none"))
        return self

    # ---------- tur.py baglanti noktalari ----------
    @property
    def held(self):
        return self.skipped is None

    def blocks(self):
        """Karar icin toplanti sonrasi bloklar (valid + reused bir arada)."""
        return list(self.cur.values())

    def risk_lines(self):
        if not self.held:
            return []
        return [f"MEETING={self.transcript_f}",
                "Committee was held: EXPERTS = post-meeting views. Apply your rules unchanged to EXPERTS. In `reason` "
                "name the argument(s) that decided it (expert: point) and note dissent; terse English."]

    def summary(self):
        tot = {k: sum((c.get(k) or 0) for c in self.calls) for k in ("tok_in", "tok_cache_w", "tok_cache_r", "tok_out", "cost_usd")}
        return {**tot, "secs": round(time.time() - self.t0), "calls": len(self.calls), "rounds": self.rounds,
                "changes": len(self.changes), "skipped": self.skipped,
                "errors": [f"{c['agent']}/{c['sub']}: {c['error']}" for c in self.calls if c.get("error")]}

    def close(self, decisions, dec_errs, test=False):
        """Karar sonrasi: Turkce tutanak + olcum satiri."""
        TOPLANTI.mkdir(parents=True, exist_ok=True)
        st = self.stamp   # tur damgasi YYYYMMDD_HHMM (UTC)
        f = TOPLANTI / f"{st[:4]}-{st[4:6]}-{st[6:8]}_{st[9:13]}.md"
        s = self.summary()
        if not self.held:
            f.write_text(f"{self.asof} UTC kapanışı: toplantı yapılmadı, bütün uzmanlar beklemede "
                         f"(işlem önerisi yok).{' [deneme]' if test else ''}\n", encoding="utf-8")
        else:
            f.write_text(self.minutes(decisions, dec_errs, s, test), encoding="utf-8")
        row = {"run": self.stamp, "asof_utc": self.asof, "test": test, "held": self.held, "skipped": self.skipped,
               "rounds": self.rounds, "summary": s, "changes": self.changes, "talk": self.talk,
               "pre": {f"{k[0]}|{k[1]}": _brief(b) for k, b in self.pre.items()},
               "post": {f"{k[0]}|{k[1]}": _brief(b) for k, b in self.cur.items()},
               "post_blocks_changed": [self.cur[(x["expert"], x["asset"])] for x in self.changes],
               "decisions": [{k: d.get(k) for k in ("asset", "decision", "side", "reason")} for d in decisions],
               "minutes": str(f)}
        O.append_jsonl(O.DEFTER / ("toplanti_test.jsonl" if test else "toplanti.jsonl"), row)
        self.say(f"komite: {'held' if self.held else 'skipped'} rounds={self.rounds} changes={len(self.changes)} "
                 f"calls={s['calls']} cost={s['cost_usd']:.3f} secs={s['secs']} minutes={f.name}")
        return f

    def minutes(self, decisions, dec_errs, s, test):
        nm = self.nm
        L = [f"# Toplantı — {self.asof} UTC kapanışı{' (deneme, deftere işlenmedi)' if test else ''}"]
        if self.agenda_tr:
            L.append(f"Konu: {self.agenda_tr}")
        by = {d["asset"]: d for d in decisions}
        for a in self.cfg["assets"]:
            d = by.get(a)
            L.append(f"Karar {short(a)}: " + (f"{TR_DEC.get(d['decision'], d['decision'])} — {d['neco_tr']}" if d
                                               else "karar yazılamadı (" + "; ".join(dec_errs)[:120] + ")"))
        spoke = []
        for t in self.talk:
            if t["expert"] in spoke:
                continue
            spoke.append(t["expert"])
        for ex in spoke:
            last = [t for t in self.talk if t["expert"] == ex][-1]
            mine = [x for x in self.changes if x["expert"] == ex]
            if mine:
                tag = ", ".join(f"{short(x['asset'])} {TR_BIAS.get(x['from'], x['from'])} → {TR_BIAS.get(x['to'], x['to'])}"
                                for x in mine) + ", fikrini değiştirdi"
            else:
                tag = ", ".join(f"{short(b['asset'])} {TR_BIAS[b['bias']]}" for k, b in self.cur.items()
                                if k[0] == ex and b["bias"] in DIRS) or "beklemede"
                tag += ", görüşünü korudu"
            L.append(f"- {nm.get(ex, ex)} ({tag}): {last['tr'] or '—'}")
        diss = {}
        for a in self.cfg["assets"]:
            side = (by.get(a) or {}).get("side")
            for b in self.cur.values():
                if b["asset"] == a and b["bias"] in DIRS and b["bias"] != side:
                    diss.setdefault(nm.get(b["expert"], b["expert"]), []).append(f"{short(a)} {TR_BIAS[b['bias']]}")
        L.append("Karara uymayan görüş: " + ("; ".join(f"{k} ({', '.join(v)})" for k, v in diss.items()) or "yok"))
        L.append(f"Toplantı: {self.rounds} tur, {len(spoke)} uzman konuştu, {len(self.changes)} görüş değişikliği; "
                 f"{s['secs']} sn, " + f"{s['cost_usd']:.2f}".replace(".", ",") + " $.")
        return "\n".join(L[:15]) + "\n"

    def shadow(self, D, st, stamp, snap):
        """Degisen gorusler icin ayri golge defter: book 'komite:<uzman>' (kor puan bozulmaz)."""
        bl = []
        for x in self.changes:
            b = dict(self.cur[(x["expert"], x["asset"])])
            b["expert"] = "komite:" + b["expert"]
            bl.append(b)
        if bl:
            D.add_shadow(st, bl, sorted({b["expert"] for b in bl}), stamp, snap)


def _brief(b):
    return {k: b.get(k) for k in ("bias", "action", "confidence", "entry", "stop", "targets", "horizon_h", "setup", "asof_utc")}


def toplanti(cfg, args, snap, stamp, rundir, blocks, reused, views, view_of, run_claude, validate, say):
    """tur.py giris noktasi. Kapaliysa None; aciksa calismis Toplanti (held ya da skipped)."""
    if not (conf(cfg)["enabled"] or getattr(args, "komite", False)) or getattr(args, "no_komite", False):
        return None
    try:
        return Toplanti(cfg, args, snap, stamp, rundir, blocks, reused, views, view_of, run_claude, validate, say).run()
    except Exception:  # noqa: BLE001  komite hatasi turu durdurmaz: kor bloklarla devam
        import traceback
        say("komite CRASH (round continues with blind blocks) " + traceback.format_exc().replace("\n", " | ")[:1500])
        return None


def replay(stamp):
    """Deneme: kayitli bir turun kor bloklariyla yalniz toplanti + Riza kapanisi (uzmanlar yeniden cagrilmaz,
    defter islenmez). python algo/ofis/komite.py --replay <YYYYMMDD_HHMM>"""
    import argparse
    import tur as T
    cfg, src = O.ayar(), O.LOG / stamp
    rows = [r for r in O.read_jsonl(O.DEFTER / "sinyaller.jsonl") if r.get("run") == stamp and r.get("valid")]
    blocks = [r["block"] for r in rows if not r.get("reused")]
    reused = [r["block"] for r in rows if r.get("reused")]
    snap = json.loads(next(O.VERI.glob(f"snap_{blocks[0]['asof_utc'].replace('-', '').replace(' ', '_').replace(':', '')}.json"))
                      .read_text(encoding="utf-8"))
    new = O.now_utc().strftime("%Y%m%d_%H%M")
    rundir = O.LOG / f"{new}_replay_{stamp}"
    rundir.mkdir(parents=True, exist_ok=True)
    views = {r: src / f"view_{r}.json" for r in set(T.VIEW_OF.values())}
    vb = O.validator("expert_block")
    say = lambda m: O.log(T.LOGF, m)  # noqa: E731
    say(f"=== komite replay of {stamp} -> {rundir.name}")
    km = toplanti(cfg, argparse.Namespace(komite=True, no_komite=False), snap, new, rundir, blocks, reused, views,
                  T.VIEW_OF, T.run_claude, lambda ex, p: T.validate_blocks(ex, p, snap, cfg, vb), say)
    decisions = []
    if km and km.held:
        ef = rundir / "experts.json"
        O.write_json(ef, km.blocks())
        lines = [(f"EXPERTS={ef}" if x.startswith("EXPERTS=") else x)
                 for x in (src / "prompt_trader-risk.txt").read_text(encoding="utf-8").splitlines()
                 if not x.startswith(("MEETING=", "Committee was held"))]
        prompt = "\n".join(lines[:-1] + km.risk_lines() + lines[-1:])
        r = T.run_claude("trader-risk", prompt, T.T_RISK, rundir)
        km.calls.append({"agent": "trader-risk", "sub": "close", **{k: r.get(k) for k in ("secs", "cost_usd", "tok_in",
                         "tok_cache_w", "tok_cache_r", "tok_out", "error")}})
        vd = O.validator("decision")
        parsed = O.extract_json(r.get("text")) or []
        decisions = [d for d in parsed if isinstance(d, dict) and not O.schema_errors(vd, d)]
    if km:
        f = km.close(decisions, [] if decisions else ["no valid decision"], test=True)
        print(f.read_text(encoding="utf-8"))


if __name__ == "__main__":
    import os
    import sys
    os.chdir(O.ROOT)
    sys.path.insert(0, str(O.ROOT))
    if len(sys.argv) == 3 and sys.argv[1] == "--replay":
        replay(sys.argv[2])
    else:
        print(__doc__)
