"""Trader ofisi kayitcisi: gozlenen tasfiyeler (LLM yok, anahtar yok). Surekli calisir, tek ornek.

Binance USD-M herkese acik websocket `!forceOrder@arr` -> BTCUSDT/ETHUSDT tasfiye emirleri
algo/ofis/kayit/tasfiye/YYYY-MM-DD.csv (UTC gunu): time_utc, sym, side, price, qty, usd.
side = tasfiye EMRININ yonu: SELL = long pozisyon tasfiye edildi, BUY = short tasfiye edildi.
Not (Binance belgesi): akim sembol basina 1000 ms'de en fazla son tasfiyeyi verir; yogun anlarda bazilari kacar.
Yani toplamlar alt sinirdir, kumelenme (hangi fiyatta) yine de gorunur.
Kapsam: baglanti acikken her 5 dakikada kalp.csv'ye bir satir; snapshot kapsami bundan olcer (sessiz piyasa != kayit yok).
Hicbir sembolden 20 dk mesaj yoksa ya da kopma -> artan beklemeyle (en cok 60 sn) yeniden baglanir. Gorev TraderOfisTasfiye: oturum acilisi + saatte bir
(calisiyorsa kilit yuzunden hemen cikar). pythonw: pencere/ses yok.
Kullanim: python algo/ofis/kayit_tasfiye.py [--seconds N]   (N: deneme icin N saniye sonra cik)
"""
import argparse
import asyncio
import json
import sys
import time

import kayit_ortak as K

# 2026-11-21 denendi: eski /ws/ yolu baglaniyor ama veri gondermiyor; Binance USD-M akimlari /market/ altinda.
URLS = ("wss://fstream.binance.com/market/ws/!forceOrder@arr", "wss://fstream.binance.com/ws/!forceOrder@arr")
SYMS = {"BTCUSDT", "ETHUSDT"}
DIR = K.KAYIT / "tasfiye"
HEADER = ["time_utc", "sym", "side", "price", "qty", "usd"]
FLUSH_S, BEAT_S, STALE_S = 30, 300, 1200   # STALE: hicbir sembolden mesaj gelmezse yeniden baglan


class Stale(Exception):
    pass


def log(msg):
    DIR.mkdir(parents=True, exist_ok=True)
    with open(DIR / "tasfiye.log", "a", encoding="utf-8") as f:
        f.write(f"{K.now_utc().strftime('%Y-%m-%d %H:%M:%S')}Z {msg}\n")


def flush(buf):
    if not buf:
        return
    by_day = {}
    for r in buf:
        by_day.setdefault(r[0][:10], []).append(r)
    for day, rows in by_day.items():
        f = DIR / f"{day}.csv"
        new = not f.exists()
        with open(f, "a", encoding="utf-8", newline="") as fh:
            if new:
                fh.write(",".join(HEADER) + "\n")
            fh.write("".join(",".join(str(x) for x in r) + "\n" for r in rows))
    buf.clear()


def beat():
    f = DIR / "kalp.csv"
    new = not f.exists()
    with open(f, "a", encoding="utf-8") as fh:
        if new:
            fh.write("ts_utc\n")
        fh.write(K.now_utc().strftime("%Y-%m-%d %H:%M") + "\n")


async def run(stop_at):
    import websockets
    buf, wait, n, k = [], 1, 0, 0
    while stop_at is None or time.time() < stop_at:
        url = URLS[k % len(URLS)]
        try:
            async with websockets.connect(url, ping_interval=60, ping_timeout=30, open_timeout=20, close_timeout=5,
                                          max_size=2 ** 20) as ws:
                log(f"connected {url}")
                t_conn = last_flush = time.time()
                last_beat, last_msg = 0.0, None
                while stop_at is None or time.time() < stop_at:
                    now = time.time()
                    if last_msg and now - last_msg < BEAT_S and now - last_beat >= BEAT_S:
                        beat()                     # kapsam: yalniz akim gercekten veri gonderirken sayilir
                        last_beat = now
                    if now - (last_msg or t_conn) > STALE_S:
                        raise Stale(f"no message from any symbol for {STALE_S}s")
                    if now - last_flush >= FLUSH_S:
                        flush(buf)
                        last_flush = now
                    try:
                        msg = await asyncio.wait_for(ws.recv(), timeout=5)
                    except asyncio.TimeoutError:
                        continue
                    last_msg, wait = time.time(), 1
                    try:
                        o = json.loads(msg)["o"]
                    except (ValueError, KeyError, TypeError):
                        continue
                    if o.get("s") not in SYMS:
                        continue
                    px, q = float(o.get("ap") or o.get("p")), float(o.get("z") or o.get("q"))
                    t = K.dt.datetime.fromtimestamp(int(o["T"]) / 1000, tz=K.dt.timezone.utc)
                    buf.append([t.strftime("%Y-%m-%d %H:%M:%S"), o["s"], o["S"], K.rn(px, 7), K.rn(q, 6),
                                round(px * q, 2)])
                    n += 1
        except Exception as e:  # noqa: BLE001
            log(f"disconnected: {type(e).__name__} {str(e)[:160]} (records so far {n}); retry in {wait}s")
            if isinstance(e, Stale):
                k += 1                             # veri gelmeyen adresten otekine gec
        flush(buf)
        if stop_at is not None and time.time() >= stop_at:
            break
        await asyncio.sleep(wait)
        wait = min(60, wait * 2)
    flush(buf)
    return n


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seconds", type=float, help="deneme: N saniye sonra cik")
    a = ap.parse_args()
    with K.TekOrnek(DIR / ".kilit") as lock:
        if not lock.ok:
            return 0                       # baska ornek calisiyor
        log("start")
        n = asyncio.run(run(None if a.seconds is None else time.time() + a.seconds))
        log(f"stop records={n}")
        try:
            print(f"records={n}")
        except Exception:  # noqa: BLE001
            pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
