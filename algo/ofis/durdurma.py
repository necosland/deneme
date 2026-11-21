"""Onceden yazilan durdurma kurali (TASARIM.md 5; ofis-ayar.json stop_rule). LLM yok.

Kurulum turu (blok `setup`) basina havuzlanmis kapanan uzman golge islemleri (komite:* ve ofis defteri haric):
her `step_trades` (60) katinda ilk N islemin ortalama R'si ve bootstrap %90 araligi; ust sinir < 0 ise o kurulum
turu kapanir (defter.vote_check oy saymaz: Riza ve gevsek defter). Sonraki katta yeniden bakilir; ust sinir >= 0
olursa yeniden acilir. 60 islem yalniz ~0,3R buyuklugundeki etkiyi ayirt eder (bilerek kabul).
Durum: defter/durdurma.json, gunluk: log/defter.log.
"""
import json

import ortak as O

DEF = {"enabled": True, "step_trades": 60, "ci_pct": 90, "exclude_book_prefix": ["komite:"]}


def scfg(cfg=None):
    s = dict(DEF)
    s.update((cfg or O.ayar()).get("stop_rule") or {})
    return s


def state_f():
    return O.DEFTER / "durdurma.json"


def norm(setup):
    return str(setup or "").strip().lower() or "-"


def load():
    f = state_f()
    if f.exists():
        try:
            return json.loads(f.read_text(encoding="utf-8"))
        except ValueError:
            pass
    return {"setups": {}, "disabled": []}


def disabled(cfg=None):
    """Kapali kurulum turleri (kural kapaliysa bos)."""
    try:
        if not scfg(cfg).get("enabled"):
            return set()
        return set(load().get("disabled") or [])
    except Exception:  # noqa: BLE001
        return set()


def pooled(st, cfg=None):
    """{setup: [r_mult, ...]} kapanis sirasiyla (uzman golge defterleri)."""
    s = scfg(cfg)
    ex = tuple(s.get("exclude_book_prefix") or ())
    tr = [t for t in st["trades"] if t["book"] != "ofis" and not str(t["book"]).startswith(ex)
          and t["status"] == "closed" and t.get("r_mult") is not None]
    tr.sort(key=lambda t: (t.get("exit_ms") or 0, t["id"]))
    out = {}
    for t in tr:
        src = t.get("src") if isinstance(t.get("src"), dict) else {}
        out.setdefault(norm(src.get("setup")), []).append(float(t["r_mult"]))
    return out


def check(st, cfg=None, log=None):
    """Yeni katlari degerlendirir, durumu yazar. Donus: bu cagride yapilan degerlendirmeler listesi."""
    import defter as D
    s = scfg(cfg)
    if not s.get("enabled"):
        return []
    step, q = int(s["step_trades"]), (100 - s["ci_pct"]) / 2
    stt = load()
    new = []
    for setup, rs in pooled(st, cfg).items():
        rec = stt["setups"].setdefault(setup, {"checks": [], "disabled": False})
        done = {c["n"] for c in rec["checks"]}
        for n in range(step, len(rs) - len(rs) % step + 1, step):
            if n in done:
                continue
            x = rs[:n]
            lo, hi = D.bootstrap_ci(x, (q, 100 - q))
            mean = round(sum(x) / n, 3)
            off = hi is not None and hi < 0
            c = {"n": n, "mean_r": mean, "ci": [lo, hi], "utc": O.fmt(O.now_utc()), "disabled": off}
            rec["checks"].append(c)
            rec["disabled"] = off
            new.append({"setup": setup, **c})
            O.log("defter.log", f"stop rule {setup}: n={n} mean_R={mean} ci{s['ci_pct']}={[lo, hi]} -> "
                                f"{'DISABLED' if off else 'enabled'}")
    stt["disabled"] = sorted(k for k, v in stt["setups"].items() if v.get("disabled"))
    stt["step_trades"], stt["ci_pct"] = step, s["ci_pct"]
    O.write_json(state_f(), stt)
    if log and new:
        for c in new:
            log(f"stop rule: {c}")
    return new


def counts(st, cfg=None):
    """{setup: (kapanan, sonraki kontrol n)} rapor icin."""
    step = int(scfg(cfg)["step_trades"])
    return {k: (len(v), (len(v) // step + 1) * step) for k, v in pooled(st, cfg).items()}
