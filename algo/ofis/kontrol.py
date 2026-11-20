"""Trader ofisi izleyicisi (LLM yok). Zamanlayici her 5 dakikada calistirir.

Son kontrolden bu yana kapanmis 1m spot mumlarini (data-api.binance.vision) ceker; bekleyen emir dolumu, stop,
hedef, sure dolumu ve fonlamayi ofis + golge defterine isler (kurallar defter.process_candles; ayni mumda stop once).
Acik/bekleyen islem yoksa ag cagrisi yapmaz.
Kullanim: python algo/ofis/kontrol.py [--quiet]
"""
import sys
import time

import requests

import defter as D
import ortak as O

LOGF = "kontrol.log"


def klines_1m(sym, start_ms, end_ms):
    """[start_ms, end_ms) araliginda acilan ve kapanmis 1m mumlar."""
    out, cur = [], start_ms
    while cur < end_ms:
        r = requests.get(O.SPOT_KLINES, params={"symbol": sym, "interval": "1m", "startTime": cur,
                                                 "endTime": end_ms - 1, "limit": 1000}, headers=O.UA, timeout=20)
        r.raise_for_status()
        rows = r.json()
        if not rows:
            break
        for x in rows:
            if x[6] < end_ms:                     # close_time < simdi: kapanmis
                out.append([int(x[0]), float(x[1]), float(x[2]), float(x[3]), float(x[4])])
        nxt = int(rows[-1][0]) + 60000
        if nxt <= cur or len(rows) < 1000:
            break
        cur = nxt
        time.sleep(0.2)
    return out


def run(st, quiet=False):
    """Kilit cagiranda. Donus: (olay sayisi, not)."""
    now = O.ms(O.now_utc())
    active = {t["asset"] for t in st["trades"] if t["status"] in ("pending", "open")}
    events, notes = 0, []
    for sym in sorted(active):
        first = min(t["created_ms"] if t["status"] == "pending" else t["fill_ms"]
                    for t in st["trades"] if t["asset"] == sym and t["status"] in ("pending", "open"))
        start = max(st["last_check_ms"].get(sym, 0), first - first % 60000)
        start = max(start, now - 7 * 24 * 3600 * 1000)          # makine uzun kapali kaldiysa en cok 7 gun geri
        try:
            cs = klines_1m(sym, start, now)
        except Exception as e:  # noqa: BLE001
            notes.append(f"{sym} klines error {type(e).__name__}: {str(e)[:100]}")
            continue
        n = D.process_candles(st, sym, cs)
        events += n
        if cs:
            st["last_check_ms"][sym] = cs[-1][0] + 60000
        notes.append(f"{sym} {len(cs)}x1m ev={n}")
    for sym in set(st["last_check_ms"]) - active:   # islem yokken saat ilerlesin
        st["last_check_ms"][sym] = now - now % 60000
    return events, "; ".join(notes) or "idle"


def main():
    quiet = "--quiet" in sys.argv
    with O.Kilit(wait_s=0) as k:
        if not k.ok:
            O.log(LOGF, "skip: ledger locked (round running)")
            return
        st = D.load_state()
        ev, note = run(st, quiet)
        if ev:
            D.append_equity(st)
            D.write_reports(st)
        D.save_state(st)
        if ev or "error" in note or not quiet or O.now_utc().minute < 5:   # sessizde saatte bir canli satiri
            O.log(LOGF, f"events={ev} {note}")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:  # noqa: BLE001
        import traceback
        O.log(LOGF, "CRASH " + traceback.format_exc().replace("\n", " | ")[:1500])
        raise
