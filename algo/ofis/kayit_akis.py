"""Trader ofisi kayitcisi: USD-M vadeli islem akisi (Binance fapi aggTrades; LLM yok, anahtar yok). Zamanlayici 5 dakikada
bir calistirir (gorev TraderOfisAkis, pythonw: pencere/ses yok). 2026-11-21, Bora'nin footprint/delta okumasi icin.

Her calismada kayit sembolleri (kayit_ortak.kayit_syms) icin son islenen aggTrade id'sinden bu yana gelen islemleri
ceker (yalniz kapanmis dakikalar), dakika basina toplar ve kayit/akis/YYYY-MM-DD.csv.gz dosyasina ekler (UTC gunu):
  min_utc, sym, id0, id1   dakika ve bu satirin ilk/son aggTrade id'si (ayni dakika iki satira bolunebilir: okuyan toplar,
                            (sym, min_utc, id0) tekrarini atar)
  tick                      fiyat kovasi (~%0.05, yuvarlak adim)
  n                         islem sayisi (aggTrade l-f+1; kline 'trades' ile ayni sayim)
  buy_k, sell_k             taker alis / satis, bin USD (quote)
  cells                     "kova:alis_k:satis_k;..."  (footprint hucreleri)
  big                       dakikanin en buyuk 3 emri "epoch_s:B|S:vwap:usd_k|..." (ayni ms + ayni yon aggTrade'ler
                            tek piyasa emri sayilir)
Durum: kayit/akis/durum.json {sym: {id, t}}. Durum 90 dk'dan eskiyse bosluk kabul edilir, son 5 dk'dan baslanir.
Hiz siniri: fapi aggTrades agirligi 20; X-MBX-USED-WEIGHT-1M 1200'u gecerse dakika sonuna kadar bekler; 429/418'de durur.
Kullanim: python algo/ofis/kayit_akis.py [--backfill-h 8] [--syms BTCUSDT,ETHUSDT]
  --backfill-h: durumu olmayan semboller bu kadar saat geriden, bayat durumlu olanlar kaldigi id'den devam eder;
  sayfa/sure siniri yok (tek seferlik).
  --fill-h: son H saatte satirlarin id araliklari arasindaki bosluklari doldurur (kesinti sonrasi; durum degismez).
"""
import argparse
import json
import sys
import time

import requests

import kayit_ortak as K

URL = "https://fapi.binance.com/fapi/v1/aggTrades"
DIR = K.KAYIT / "akis"
STATE = DIR / "durum.json"
HEADER = ["min_utc", "sym", "id0", "id1", "tick", "n", "buy_k", "sell_k", "cells", "big"]
TICK_PCT = 0.05
MAX_LAG_MIN, START_BACK_MIN = 90, 5
PAGES_SYM, PAGES_RUN, TIME_LIMIT_S = 40, 160, 150   # normal calisma; gorev siniri 4 dk
FLUSH_PAGES = 25
WEIGHT_PAUSE = 1200


def num(x):
    """kisa sayi metni: 57900.0 -> 57900"""
    s = str(K.rn(x))
    return s[:-2] if s.endswith(".0") else s


class Durdur(Exception):
    pass


def page(sym, params):
    for k in range(3):   # gecici ag hatasinda 2 yeniden deneme; yoksa sembol yarida kalir, durum yine tutarli
        try:
            r = requests.get(URL, params={"symbol": sym, "limit": 1000, **params}, headers=K.UA, timeout=15)
            if r.status_code in (418, 429):
                raise Durdur(f"HTTP {r.status_code} rate limit")
            r.raise_for_status()
            break
        except requests.RequestException:
            if k == 2:
                raise
            time.sleep(3 * (k + 1))
    w = int(r.headers.get("X-MBX-USED-WEIGHT-1M") or 0)
    if w > WEIGHT_PAUSE:
        time.sleep(61 - time.time() % 60)
    return r.json()


class Agg:
    def __init__(self, tick):
        self.tick, self.m = tick, {}

    def add(self, t):
        p, u, T, sell = float(t["p"]), float(t["p"]) * float(t["q"]), int(t["T"]), 1 if t["m"] else 0
        d = self.m.get(T // 60000)
        if d is None:
            d = self.m[T // 60000] = {"id0": t["a"], "n": 0, "bs": [0.0, 0.0], "c": {}, "o": {}}
        d["id1"] = t["a"]
        d["n"] += int(t["l"]) - int(t["f"]) + 1
        d["bs"][sell] += u
        c = d["c"].setdefault(round(p / self.tick), [0.0, 0.0])
        c[sell] += u
        o = d["o"].setdefault((T, sell), [0.0, 0.0])
        o[0] += u
        o[1] += float(t["q"])

    def rows(self, sym):
        out = []
        for mk in sorted(self.m):
            d = self.m[mk]
            cells = ";".join(f"{num(k * self.tick)}:{b / 1e3:.1f}:{s / 1e3:.1f}" for k, (b, s) in sorted(d["c"].items()))
            big = sorted(d["o"].items(), key=lambda kv: -kv[1][0])[:3]
            bigs = "|".join(f"{T // 1000}:{'S' if sl else 'B'}:{num(u / q)}:{u / 1e3:.0f}" for (T, sl), (u, q) in big)
            t = time.strftime("%Y-%m-%d %H:%M", time.gmtime(mk * 60))
            out.append([t, sym, d["id0"], d["id1"], num(self.tick), d["n"], f"{d['bs'][0] / 1e3:.1f}",
                        f"{d['bs'][1] / 1e3:.1f}", cells, bigs])
        return out


def flush(agg, sym, state, last):
    rows = agg.rows(sym)
    by_day = {}
    for r in rows:
        by_day.setdefault(r[0][:10], []).append(r)
    for day, rs in by_day.items():
        K.append_csv_gz(DIR / f"{day}.csv.gz", HEADER, rs)
    if last is not None:   # once veri, sonra durum: cokmede en kotu ayni id0'li satir tekrar eder, okuyan atar
        state[sym] = {"id": int(last["a"]), "t": int(last["T"])}
        tmp = STATE.with_suffix(".tmp")
        tmp.write_text(json.dumps(state), encoding="utf-8")
        tmp.replace(STATE)
    agg.m = {}


def run_sym(sym, state, budget, backfill_h, t_start):
    end_ms = int(time.time() // 60 * 60000)           # yalniz kapanmis dakikalar
    st = state.get(sym)
    if st and (backfill_h or end_ms - st["t"] <= MAX_LAG_MIN * 60000):   # geri doldurma bosluga kalinan yerden devam eder
        params, start = {"fromId": st["id"] + 1}, None
    else:
        start = end_ms - int((backfill_h * 60) if backfill_h else START_BACK_MIN) * 60000
        params = {"startTime": start, "endTime": min(start + 3600000 - 1, end_ms - 1)}
    agg, last, pages = None, None, 0
    while True:
        data = page(sym, params)
        pages += 1
        budget[0] -= 1
        if not data and start is not None and params["endTime"] < end_ms - 1:   # bos saat (az islem): ileri kay
            start += 3600000
            params = {"startTime": start, "endTime": min(start + 3600000 - 1, end_ms - 1)}
            continue
        keep = [t for t in data if int(t["T"]) < end_ms]
        if keep:
            if agg is None:
                agg = Agg(K.nice(float(keep[0]["p"]) * TICK_PCT / 100))
            for t in keep:
                agg.add(t)
            last = keep[-1]
        done = len(keep) < len(data) or len(data) < 1000
        if agg is not None and (done or pages % FLUSH_PAGES == 0):
            flush(agg, sym, state, last)
        if done:
            return pages, True
        params = {"fromId": int(data[-1]["a"]) + 1}
        if not backfill_h and (pages >= PAGES_SYM or budget[0] <= 0 or time.time() - t_start > TIME_LIMIT_S):
            if agg is not None:
                flush(agg, sym, state, last)
            return pages, False


def fill_sym(sym, hours):
    """Son `hours` saatteki kayit bosluklarini id araligiyla doldurur (durum degismez, cift sayim yok): satirlarin
    [id0, id1] araliklari arasindaki atlama ve pencere basindan ilk satira kadar olan kisim."""
    end_ms = int(time.time() // 60 * 60000)
    lo_ms = end_ms - int(hours * 3600000)
    lo_s = time.strftime("%Y-%m-%d %H:%M", time.gmtime(lo_ms / 1000))
    rows = [r for f in K.day_files(DIR, int(hours // 24) + 1, ".csv.gz") for r in K.read_csv_any(f)
            if r.get("sym") == sym and r.get("min_utc", "") >= lo_s]
    spans = sorted({(int(r["id0"]), int(r["id1"])) for r in rows})
    if not spans:
        return 0, True
    gaps, hi = [(None, spans[0][0] - 1)], spans[0][1]
    for a0, a1 in spans[1:]:
        if a0 > hi + 1:
            gaps.append((hi + 1, a0 - 1))
        hi = max(hi, a1)
    pages = 0
    for g0, g1 in gaps:
        params = {"fromId": g0} if g0 is not None else {"startTime": lo_ms, "endTime": lo_ms + 3600000 - 1}
        agg = None
        while True:
            data = page(sym, params)
            pages += 1
            keep = [t for t in data if int(t["a"]) <= g1 and int(t["T"]) >= lo_ms]
            for t in keep:
                if agg is None:
                    agg = Agg(K.nice(float(t["p"]) * TICK_PCT / 100))
                agg.add(t)
            if agg is not None and pages % FLUSH_PAGES == 0:
                flush(agg, sym, {}, None)
            if not data or int(data[-1]["a"]) >= g1 or len(data) < 1000:
                break
            params = {"fromId": int(data[-1]["a"]) + 1}
        if agg is not None:
            flush(agg, sym, {}, None)
    return pages, True


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--backfill-h", type=float, default=0)
    ap.add_argument("--fill-h", type=float, default=0, help="son H saatteki id bosluklarini doldur (durum degismez)")
    ap.add_argument("--syms")
    a = ap.parse_args()
    syms = [s.strip().upper() for s in a.syms.split(",")] if a.syms else K.kayit_syms()
    t0 = time.time()
    stamp = K.now_utc().strftime("%Y-%m-%d %H:%M")
    with K.TekOrnek(DIR / ".kilit") as lk:
        if not lk.ok:
            return 0   # onceki calisma / geri doldurma suruyor
        try:
            state = json.loads(STATE.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            state = {}
        budget, errs, info = [PAGES_RUN], [], []
        for sym in syms:
            try:
                n, ok = fill_sym(sym, a.fill_h) if a.fill_h else run_sym(sym, state, budget, a.backfill_h, t0)
                info.append(f"{sym}:{n}{'' if ok else '+'}")
            except Durdur as e:
                errs.append(f"{sym}: {e}")
                break
            except Exception as e:  # noqa: BLE001
                errs.append(f"{sym}: {type(e).__name__} {str(e)[:100]}")
        if time.time() - t0 > 120 and not (a.backfill_h or a.fill_h):   # gorev siniri 240 sn (2026-11-21)
            errs.append(f"slow run {round(time.time() - t0)}s")
        if errs:
            DIR.mkdir(parents=True, exist_ok=True)
            with open(DIR / "hata.log", "a", encoding="utf-8") as f:
                f.write(f"{stamp}Z pages {' '.join(info)} | " + " | ".join(errs) + "\n")
        try:
            print(f"{stamp}Z pages {' '.join(info)} errors={len(errs)} {round(time.time() - t0)}s")
        except Exception:  # noqa: BLE001  (pythonw: stdout yok)
            pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
