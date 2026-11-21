"""Elliott itki dedektoru (LLM yok, anahtar yok). Kod aday sayimi bulur, uzman (trader-elliott) yargilar.

Amac (sahibin karari): Elliott yalniz NET itkilerde 3. ve 5. dalgayi yakalamak icin. Zigzag/flat/ucgen/yatay/
ust uste binme = islem yok; yalniz iptal seviyesi + hedef.

Yontem
- Cok dereceli zigzag: her zaman diliminde birden cok esik (k x ATR14). Pivot, fiyat asiri noktadan k*ATR
  geri donunce onaylanir (geriye bakmaz; onay mumu 'ci' saklanir -> gecmis testte sizinti yok).
- Sert kurallar: w2 w1 baslangicini asmaz; w3 en kisa olamaz; w4 w1 bolgesine girmez (girerse ayni son dibi paylasan sayima 'alt_diagonal_same_end' bayragi,
  islem yok). Her dalga ucu kendi araliginin en uc noktasi olmali (yanlis capa secimini engeller).
- Rehber puan (0-100): w2 geri cekilme 0.382-0.786, w3 >= 1.618*w1, almasma (w2/w4 derinlik ya da sure),
  RSI tepe w3'te, hacim w3'te, w1 onceki yapiyi kiriyor, temiz w1 bacagi.

Kullanim:  python algo/ofis/elliott_say.py BTCUSDT [ETHUSDT ...]   (canli Binance spot, kapanmis mumlar)
Ice aktarma: elliott_say.analyze(fr)  fr = {"4h": df, "1d": df}  (kolonlar open/high/low/close + qvol|volume)
"""
import json
import math
import sys

import numpy as np
import pandas as pd

TF_K = {"4h": (1.5, 2.5, 4.0), "1d": (2.0, 3.0, 5.0)}   # zaman dilimi -> zigzag esikleri (k x ATR14)
FRESH = 3          # tetik kapanisi son 3 mumdaysa "yeni onaylandi"
MIN_SCORE = 50     # "actionable" icin en dusuk puan (kod_plan.md ile on-kayitli)
KEEP_PIV = 16      # sayimda bakilan son onayli pivot sayisi
FLIP = {"H": "L", "L": "H"}
ORDER = {"w3_setup": 0, "w5_setup": 0, "w3_in_progress": 1, "impulse_done": 2}


# ---------------- yardimcilar ----------------
def r5(x):
    try:
        x = float(x)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(x):
        return None
    if x == 0:
        return 0.0
    return round(x, max(0, 5 - int(math.floor(math.log10(abs(x)))) - 1))


def atr(df, n=14):
    pc = df.close.shift()
    tr = pd.concat([df.high - df.low, (df.high - pc).abs(), (df.low - pc).abs()], axis=1).max(axis=1)
    return tr.ewm(alpha=1 / n, adjust=False).mean()


def rsi(s, n=14):
    d = s.diff()
    up = d.clip(lower=0).ewm(alpha=1 / n, adjust=False).mean()
    dn = (-d.clip(upper=0)).ewm(alpha=1 / n, adjust=False).mean()
    return (100 - 100 / (1 + up / dn)).fillna(50)


def zigzag(h, l, a, k):
    """veri_topla.zigzag ile ayni algoritma; ek olarak onay mumu: [(i, fiyat, 'H'|'L', ci)], suren uc (i, p, t)."""
    n, s = len(h), 14
    if n <= s + 2:
        return [], None
    piv, d, ei, hi_i, lo_i = [], 0, s, s, s
    for i in range(s + 1, n):
        th = k * a[i]
        if d == 0:
            if h[i] > h[hi_i]:
                hi_i = i
            if l[i] < l[lo_i]:
                lo_i = i
            if hi_i < i and h[hi_i] - l[i] > th:
                piv.append((hi_i, h[hi_i], "H", i))
                d, ei = -1, hi_i + 1 + int(np.argmin(l[hi_i + 1:i + 1]))
            elif lo_i < i and h[i] - l[lo_i] > th:
                piv.append((lo_i, l[lo_i], "L", i))
                d, ei = 1, lo_i + 1 + int(np.argmax(h[lo_i + 1:i + 1]))
        elif d == 1:
            if h[i] >= h[ei]:
                ei = i
            elif h[ei] - l[i] > th:
                piv.append((ei, h[ei], "H", i))
                d, ei = -1, ei + 1 + int(np.argmin(l[ei + 1:i + 1]))
        else:
            if l[i] <= l[ei]:
                ei = i
            elif h[i] - l[ei] > th:
                piv.append((ei, l[ei], "L", i))
                d, ei = 1, ei + 1 + int(np.argmax(h[ei + 1:i + 1]))
    prov = None if d == 0 else (ei, h[ei] if d == 1 else l[ei], "H" if d == 1 else "L")
    return piv, prov


def space(df, d):
    """Yon uzayi: d=+1 oldugu gibi, d=-1 fiyat ters cevrilir (dusen itki = yukselen itki mantigi)."""
    o, h, l, c = (df[x].to_numpy(float) for x in ("open", "high", "low", "close"))
    vc = "qvol" if "qvol" in df else ("volume" if "volume" in df else None)
    v = df[vc].to_numpy(float) if vc else None
    r = rsi(df.close).to_numpy()
    a = atr(df).to_numpy()
    if d == 1:
        return {"O": o, "H": h, "L": l, "C": c, "R": r, "V": v, "A": a, "d": 1}
    return {"O": -o, "H": -l, "L": -h, "C": -c, "R": 100 - r, "V": v, "A": a, "d": -1}


def to_space(piv, d):
    return [(i, d * p, t if d == 1 else FLIP[t], ci) for i, p, t, ci in piv]


# ---------------- aday sayimlar ----------------
def _ext(Z, a, b, t):
    v = [Z[x][1] for x in range(a, b + 1) if Z[x][2] == t]
    return (max(v) if t == "H" else min(v)) if v else None


def _back(j, n):
    return [x for x in range(j, j - 2 * n, -2) if x >= 0]


def _in(x, lo, hi):
    return lo <= x <= hi


def _avg(v, a, b):
    if v is None or b <= a:
        return None
    return float(np.nanmean(v[a:b + 1]))


def _trend_start(S, i0, look=120):
    lo = S["L"][max(0, i0 - look):i0 + 1]
    return S["L"][i0] <= lo.min()


def _mk(kind, Z, ix, S):
    I = [Z[a][0] for a in ix]
    P = [Z[a][1] for a in ix]
    R, V, A = S["R"], S["V"], S["A"]
    len1 = P[1] - P[0]
    if len1 <= 0:
        return None
    r2 = (P[1] - P[2]) / len1
    chk, sc = [], 0
    c = {"kind": kind, "I": I, "P": P, "ci": Z[ix[-1]][3], "ratios": {"w2": r2}}
    a0 = ix[0]
    prior_hi = Z[a0 - 1][1] if a0 - 1 >= 0 and Z[a0 - 1][2] == "H" else None
    clean1 = (ix[1] - ix[0]) == 1          # w1 bu derecede tek bacak (ic pivot yok)
    if kind == "w3":
        if _in(r2, 0.382, 0.786):
            sc += 25; chk.append("w2_382_786")
        elif _in(r2, 0.236, 0.9):
            sc += 10
        tr = (I[2] - I[1]) / max(1, I[1] - I[0])
        if _in(tr, 0.3, 3):
            sc += 10; chk.append("w2_time_ok")
        if prior_hi is not None and P[1] > prior_hi:
            sc += 15; chk.append("w1_breaks_prior_high")
        if _trend_start(S, I[0]):
            sc += 10; chk.append("w0_120bar_low")
        if R[I[1]] >= 60:
            sc += 10; chk.append("w1_rsi_thrust")
        v1, v2 = _avg(V, I[0], I[1]), _avg(V, I[1], I[2])
        if v1 is not None and v2 is not None and v1 > v2:
            sc += 10; chk.append("vol_w1_gt_w2")
        m = len1 / max(A[I[1]], 1e-12)
        sc += 10 if m >= 4 else 5 if m >= 2.5 else 0
        if clean1:
            sc += 10; chk.append("w1_clean")
        # T (ic): 1.0 / 1.618 / 2.618 x w1 (durum mantigi 1.0 ve 2.618'i kullanir). Cikti hedefleri: 1.618, 2.618;
        # 1.0 = t_min (kismi/bilgi). 2026-11-21 v2: R:R icin T1 = 1.618 uzanti (test_ekrem/kod_plan.md).
        c.update(trig=P[1], inval=P[2], T=[P[2] + x * len1 for x in (1.0, 1.618, 2.618)], out_T=(1, 2), tmin=0)
        c["ratios"]["w1_atr"] = m
    else:
        len3 = P[3] - P[2]
        c["ratios"]["w3/w1"] = len3 / len1
        if len3 >= 1.618 * len1:
            sc += 20; chk.append("w3_ge_1618")
        elif len3 > len1:
            sc += 10
        if _in(r2, 0.382, 0.786):
            sc += 10; chk.append("w2_382_786")
        if R[I[2]:I[3] + 1].max() > R[I[0]:I[1] + 1].max():
            sc += 15; chk.append("rsi_peak_w3")
        v1, v3 = _avg(V, I[0], I[1]), _avg(V, I[2], I[3])
        if v1 is not None and v3 is not None and v3 > v1:
            sc += 10; chk.append("vol_w3_gt_w1")
        if _trend_start(S, I[0]) or (prior_hi is not None and P[1] > prior_hi):
            sc += 10; chk.append("w1_starts_trend")
        if kind == "w4f":
            if len3 >= len1:
                sc += 15  # w4 henuz bitmedi: almasma/geri cekilme puani yerine
            sc += 15 if clean1 else 0
            c.update(trig=None, inval=P[1], zone=[P[3] - 0.5 * len3, P[3] - 0.236 * len3],
                     T=[P[3] - 0.236 * len3, P[3] - 0.382 * len3])
        else:
            r4 = (P[3] - P[4]) / len3
            c["ratios"]["w4"] = r4
            if _in(r4, 0.236, 0.5):
                sc += 15; chk.append("w4_236_500")
            elif _in(r4, 0.5, 0.618):
                sc += 5
            t2, t4 = I[2] - I[1], I[4] - I[3]
            if (r2 > 0.5) != (r4 > 0.5) or t4 >= 2 * t2 or t2 >= 2 * t4:
                sc += 15; chk.append("alternation")
            if P[4] - P[1] >= 0.1 * len1:
                sc += 5; chk.append("w4_clear_of_w1")
            if kind == "w5":
                internal_b = ix[3] == ix[4] - 3
                trig = Z[ix[4] - 1][1] if internal_b else P[4] + 0.382 * (P[3] - P[4])
                e, f = P[4] + len1, P[4] + 0.618 * (P[3] - P[0])
                T = sorted([e, f])
                if len3 < len1:   # w3 en kisa olamaz -> w5 < w3
                    cap = P[4] + len3
                    T = [min(x, cap) for x in T]
                    chk.append("w5_capped_lt_w3")
                c.update(trig=trig, inval=P[1], stop_tight=P[4], T=T)
            elif kind == "done":
                len5 = P[5] - P[4]
                c["ratios"]["w5/w1"] = len5 / len1
                if _in(len5 / len1, 0.618, 1.618) or _in(len5 / (P[3] - P[0]), 0.5, 0.7):
                    sc += 5; chk.append("w5_fib")
                whole = P[5] - P[0]
                c.update(trig=None, inval=P[5], T=[P[5] - 0.382 * whole, P[4], P[5] - 0.618 * whole])
            else:  # diag
                c.update(trig=None, inval=P[2], T=[])
    c["score"] = int(min(100, sc))
    c["checks"] = chk
    return c


def candidates(Z, S, last_only=True):
    """Z: yon uzayinda onayli pivotlar [(i,u,t,ci)], son eleman en son onayli pivot. Son pivotla biten sayimlar."""
    out, j = [], len(Z) - 1
    if j < 2:
        return out
    E = lambda a, b, t: _ext(Z, a, b, t)  # noqa: E731
    if Z[j][2] == "L":
        p = Z[j][1]
        for a1 in _back(j - 1, 3):                       # w3: 0-1-2, 2 = son dip
            if Z[a1][1] < E(a1, j, "H") or p > E(a1, j, "L"):
                continue
            for a0 in _back(a1 - 1, 3):
                if Z[a0][1] > E(a0, a1, "L") or Z[a1][1] < E(a0, a1, "H") or p <= Z[a0][1]:
                    continue
                c = _mk("w3", Z, [a0, a1, j], S)
                if c:
                    out.append(c)
        for a3 in _back(j - 1, 2):                       # w5: 0-1-2-3-4, 4 = son dip
            if Z[a3][1] < E(a3, j, "H") or p > E(a3, j, "L"):
                continue
            for a2 in _back(a3 - 1, 2):
                if Z[a2][1] > E(a2, a3, "L") or Z[a3][1] < E(a2, j, "H"):
                    continue
                for a1 in _back(a2 - 1, 2):
                    if Z[a1][1] < E(a1, a2, "H") or Z[a2][1] > E(a1, a3, "L"):
                        continue
                    for a0 in _back(a1 - 1, 2):
                        P = [Z[a0][1], Z[a1][1], Z[a2][1], Z[a3][1], p]
                        if P[0] > E(a0, a1, "L") or P[1] < E(a0, a2, "H"):
                            continue
                        if not (P[2] > P[0] and P[3] > P[1] and P[4] > P[2]):
                            continue
                        kind = "w5" if P[4] > P[1] else "diag"
                        c = _mk(kind, Z, [a0, a1, a2, a3, j], S)
                        if c:
                            out.append(c)
    else:
        p = Z[j][1]
        for a2 in _back(j - 1, 3):                       # w4 suruyor: 0-1-2-3, 3 = son tepe
            if Z[a2][1] > E(a2, j, "L") or p < E(a2, j, "H"):
                continue
            for a1 in _back(a2 - 1, 2):
                if Z[a1][1] < E(a1, a2, "H") or Z[a2][1] > E(a1, j, "L"):
                    continue
                for a0 in _back(a1 - 1, 2):
                    P = [Z[a0][1], Z[a1][1], Z[a2][1], p]
                    if P[0] > E(a0, a1, "L") or P[1] < E(a0, a2, "H"):
                        continue
                    if P[2] > P[0] and P[3] > P[1]:
                        c = _mk("w4f", Z, [a0, a1, a2, j], S)
                        if c:
                            out.append(c)
        for a4 in _back(j - 1, 2):                       # bitti: 0-1-2-3-4-5, 5 = son tepe
            if Z[a4][1] > E(a4, j, "L") or p < E(a4, j, "H"):
                continue
            for a3 in _back(a4 - 1, 2):
                if Z[a3][1] < E(a3, a4, "H") or Z[a4][1] > E(a3, j, "L"):
                    continue
                for a2 in _back(a3 - 1, 2):
                    if Z[a2][1] > E(a2, a3, "L") or Z[a3][1] < E(a2, a4, "H"):
                        continue
                    for a1 in _back(a2 - 1, 2):
                        if Z[a1][1] < E(a1, a2, "H") or Z[a2][1] > E(a1, a3, "L"):
                            continue
                        for a0 in _back(a1 - 1, 2):
                            P = [Z[a0][1], Z[a1][1], Z[a2][1], Z[a3][1], Z[a4][1], p]
                            if P[0] > E(a0, a1, "L") or P[1] < E(a0, a2, "H"):
                                continue
                            l1, l3, l5 = P[1] - P[0], P[3] - P[2], P[5] - P[4]
                            if not (P[2] > P[0] and P[3] > P[1] and P[4] > P[1] and P[5] > P[3]):
                                continue
                            if l3 < min(l1, l5):
                                continue
                            c = _mk("done", Z, [a0, a1, a2, a3, a4, j], S)
                            if c:
                                out.append(c)
    return out


def state_at(c, S, t):
    """Sayimin t mumundaki durumu (yalniz t'ye kadar veri). None = sayim bozuldu."""
    k, I, P = c["kind"], c["I"], c["P"]
    s = I[-1] + 1
    if s > t:
        lo, hi = P[-1], P[-1]
    else:
        lo, hi = S["L"][s:t + 1].min(), S["H"][s:t + 1].max()
    C = S["C"]
    if k == "w3":
        if lo < P[2] or hi >= c["T"][2]:
            return None
        b = np.nonzero(C[s:t + 1] > c["trig"])[0] if s <= t else []
        if not len(b):
            return {"state": "w3_setup", "confirmed": False, "fresh": False, "phase": "waiting_break_w1_end"}
        age = t - (s + int(b[0]))
        if age < FRESH and hi < c["T"][0]:
            return {"state": "w3_setup", "confirmed": True, "fresh": True, "phase": "just_broke_w1_end", "age": age}
        return {"state": "w3_in_progress", "confirmed": True, "fresh": False, "phase": "w3_running", "age": age}
    if k == "w4f":
        if lo <= P[1] or hi > P[3]:
            return None
        return {"state": "w3_in_progress", "confirmed": True, "fresh": False, "phase": "w4_forming"}
    if k == "w5":
        if lo < P[4]:
            return None
        if hi >= c["T"][1]:
            return {"state": "impulse_done", "confirmed": True, "fresh": False, "phase": "w5_reached_T2"}
        b = np.nonzero(C[s:t + 1] > c["trig"])[0] if s <= t else []
        if not len(b):
            return {"state": "w5_setup", "confirmed": False, "fresh": False, "phase": "waiting_w4_end_trigger"}
        age = t - (s + int(b[0]))
        fr = age < FRESH and hi < c["T"][0]
        return {"state": "w5_setup", "confirmed": True, "fresh": bool(fr),
                "phase": "just_triggered" if fr else "w5_running", "age": age}
    if k == "done":
        if hi > P[5]:
            return None
        return {"state": "impulse_done", "confirmed": True, "fresh": False, "phase": "correction_expected"}
    if k == "diag":
        if lo < P[2]:
            return None
        return {"state": "corrective_or_unclear", "confirmed": False, "fresh": False, "phase": "w4_overlaps_w1_diagonal?"}
    return None


# ---------------- cikti ----------------
def _ts(t, tf):
    return t.strftime("%Y-%m-%d" if tf == "1d" else "%Y-%m-%d %H:%M")


def _px(u, d):
    return None if u is None else r5(d * u)


def _fmt(c, full=True):
    d, df, tf = c["d"], c["df"], c["tf"]
    lab = {"w3": "012", "w4f": "0123", "w5": "01234", "done": "012345", "diag": "01234"}[c["kind"]]
    o = {"state": c["st"]["state"], "dir": "up" if d == 1 else "down", "tf": tf, "zz_k": c["k"],
         "score": c["score"], "confirmed": c["st"]["confirmed"], "fresh": c["st"]["fresh"], "phase": c["st"]["phase"]}
    if c["st"]["state"] in ("w3_setup", "w5_setup"):
        o["actionable"] = bool(c["st"]["confirmed"] and c["st"]["fresh"] and c["score"] >= MIN_SCORE)
    o["trigger"] = _px(c.get("trig"), d)
    o["invalidation"] = _px(c["inval"], d)
    if c.get("stop_tight") is not None:
        o["stop_tight"] = _px(c["stop_tight"], d)
    if c.get("zone"):
        o["w4_zone"] = [_px(x, d) for x in c["zone"]]
    T = [c["T"][j] for j in c["out_T"]] if c.get("out_T") else c["T"]
    o["targets"] = [p for p in (_px(x, d) for x in T) if p is not None and p > 0]
    if c.get("tmin") is not None:
        o["t_min"] = _px(c["T"][c["tmin"]], d)
    if full and c["st"]["state"] in ("w3_setup", "w5_setup") and T:
        stop = c.get("stop_tight", c["inval"]) if c["kind"] == "w5" else c["inval"]
        e = c["trig"] if not c["st"]["confirmed"] else d * float(df.close.iloc[-1])
        if e is not None and e > stop:
            o["rr_t1"] = round((T[0] - e) / (e - stop), 2)
    if c.get("flags"):
        o["flags"] = c["flags"]
    o["waves"] = [[lab[n], _ts(df.index[i], tf), _px(p, d)] for n, (i, p) in enumerate(zip(c["I"], c["P"]))]
    if full:
        o["ratios"] = {kk: round(v, 3) for kk, v in c["ratios"].items()}
        o["checks"] = c["checks"]
    return o


def scan(fr, tf_k=TF_K, t=None):
    """Tum derecelerdeki gecerli sayimlar (state ile). t: her df icin son mum (None = son)."""
    out, seen = [], set()
    for tf, ks in tf_k.items():
        df = fr.get(tf)
        if df is None or len(df) < 60:
            continue
        n = len(df) - 1 if t is None else t
        Sd = {d: space(df, d) for d in (1, -1)}
        a = Sd[1]["A"]
        for k in ks:
            piv, _ = zigzag(Sd[1]["H"], Sd[1]["L"], a, k)
            piv = [x for x in piv if x[3] <= n]
            for d in (1, -1):
                Z = to_space(piv[-KEEP_PIV:], d)
                for c in candidates(Z, Sd[d]):
                    key = (tf, d, c["kind"], tuple(c["I"]))
                    if key in seen:
                        continue
                    st = state_at(c, Sd[d], n)
                    if st is None:
                        continue
                    seen.add(key)
                    c.update(st=st, d=d, tf=tf, k=k, df=df)
                    out.append(c)
    return out


def _rank(c):
    st = c["st"]["state"]
    bonus = {"w3_setup": 15, "w5_setup": 15, "w3_in_progress": 5, "impulse_done": 0}.get(st, -50)
    if c["st"].get("fresh"):
        bonus += 10
    if c["tf"] == "1d":
        bonus += 3   # buyuk derece hafif oncelikli
    return c["score"] + bonus


def analyze(fr, tf_k=TF_K):
    """Ana cikti (JSON uyumlu, kucuk). state: w3_setup | w3_in_progress | w5_setup | impulse_done | corrective_or_unclear."""
    cs = scan(fr, tf_k)
    good = [c for c in cs if c["st"]["state"] != "corrective_or_unclear" and c["score"] >= 35]
    # bayrak sayim basina (2026-11-21 v2): ayni zaman dilimi+yonde, ayni son dibi 4. dalga sayan ve 1. dalgayla cakisan
    # (diyagonal benzeri) bir okuma da varsa yalniz O sayima 'alt_diagonal_same_end' konur.
    dg = {(c["tf"], c["d"], c["I"][-1]) for c in cs if c["kind"] == "diag"}
    for c in cs:
        if c["kind"] != "diag" and (c["tf"], c["d"], c["I"][-1]) in dg:
            c["flags"] = ["alt_diagonal_same_end"]
    good.sort(key=_rank, reverse=True)
    if not good:
        o = {"state": "corrective_or_unclear", "reason": "no impulse count passes hard rules with score>=35 at any degree"
             " (overlap/sideways/zigzag/triangle-like). No trade; use levels only."}
        df = fr.get("4h")
        if df is not None and len(df) > 60:
            S = space(df, 1)
            piv, _ = zigzag(S["H"], S["L"], S["A"], 2.5)
            o["last_swings_4h"] = [[_ts(df.index[i], "4h"), r5(p), t] for i, p, t, _ in piv[-5:]]
        weak = sorted(cs, key=_rank, reverse=True)[:2]
        if weak:
            o["weak_alts"] = [_fmt(c, False) for c in weak]
    else:
        o = _fmt(good[0])
        alts, used = [], {(good[0]["tf"], good[0]["d"], tuple(good[0]["I"][-2:]))}
        for c in good[1:]:
            key = (c["tf"], c["d"], tuple(c["I"][-2:]))
            if key in used:
                continue
            used.add(key)
            alts.append(_fmt(c, False))
            if len(alts) == 2:
                break
        o["alts"] = alts
    o["rule"] = ("trade only actionable w3/w5 setups; others = invalidation+targets only. Backtest 2020-26 "
                 "(test_ekrem/KOD_SONUC.md): no edge after costs (avg R ~0); a map, not a signal")
    return o


# ---------------- CLI ----------------
def _klines(sym, iv, limit):
    import requests
    r = requests.get("https://data-api.binance.vision/api/v3/klines",
                     params=dict(symbol=sym, interval=iv, limit=limit), timeout=30,
                     headers={"User-Agent": "Mozilla/5.0 (paper-trading research script)"})
    r.raise_for_status()
    df = pd.DataFrame([[x[0], x[1], x[2], x[3], x[4], x[7]] for x in r.json()],
                      columns=["t", "open", "high", "low", "close", "qvol"])
    df.index = pd.to_datetime(df.pop("t"), unit="ms", utc=True)
    df = df.astype(float)
    step = pd.Timedelta(iv.replace("h", "h").replace("d", "D"))
    return df[df.index + step <= pd.Timestamp.now(tz="UTC")]


if __name__ == "__main__":
    syms = [s.upper() for s in sys.argv[1:]] or ["BTCUSDT"]
    for s in syms:
        fr = {"4h": _klines(s, "4h", 500), "1d": _klines(s, "1d", 400)}
        res = analyze(fr)
        txt = json.dumps(res, ensure_ascii=False, separators=(",", ":"))
        print(f"== {s} (~{len(txt) // 4} tokens)")
        print(json.dumps(res, ensure_ascii=False, indent=1))
