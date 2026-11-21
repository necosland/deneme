"""Trader ofisi kayitcisi: emir defteri derinligi (LLM yok, anahtar yok). Zamanlayici 5 dakikada bir calistirir
(gorev TraderOfisDerinlik, pythonw: pencere/ses yok).

Her calismada kayit sembolleri (kayit_ortak.kayit_syms: ofis-ayar assets + evren, en cok 12; 2026-11-21 oncesi
yalniz BTC/ETH) icin Binance spot (BTC/ETH 5000, digerleri 1000 kademe) ve USD-M vadeli (1000 kademe) defterini ceker;
satir basina bant likiditesi, en buyuk 5 duvar (~%0.1 kova; once 3) ve +-%5 icindeki ~%0.25'lik fiyat kovalarini
algo/ofis/kayit/derinlik/YYYY-MM-DD.csv.gz dosyasina ekler (UTC gunu). Snapshot bu kayittan 24 saatlik
"derinlik isi haritasi" ozeti (veri_ek.depth_heatmap) ve kalici duvarlar (akis.walls) cikarir.
Kullanim: python algo/ofis/kayit_derinlik.py
"""
import sys
import time

import kayit_ortak as K

SYMS = K.kayit_syms()
SPOT_FULL = ("BTCUSDT", "ETHUSDT")   # 5000 kademe (agirlik 250); digerleri 1000 (agirlik 50)
NWALLS = 5
TIME_LIMIT_S = 140                    # gorev siniri 3 dk: yavas agda kalan semboller bu turda atlanir
HEADER = ["ts_utc", "sym", "mkt", "mid", "reach_bid_pct", "reach_ask_pct",
          "b0.5", "a0.5", "b1", "a1", "b2", "a2", "b5", "a5", "walls_bid", "walls_ask", "heat_step", "heat"]
DIR = K.KAYIT / "derinlik"


def row(t, sym, mkt, book):
    s = K.book_summary(*book, nwalls=NWALLS)
    step, heat = K.heat_buckets(*book)
    bands = [x for b in K.BANDS for x in s["bands_musd"][str(b)]]
    walls = lambda w: "|".join(f"{p}@{u}" for p, u in w)  # noqa: E731
    return ([t, sym, mkt, s["mid"], *s["reach_pct"], *["" if x is None else x for x in bands],
             walls(s["walls_bid"]), walls(s["walls_ask"]), K.rn(step),
             ";".join(f"{K.rn(k)}:{round(v / 1e3)}" for k, v in sorted(heat.items()) if v >= 500)])


def main():
    t0 = K.now_utc()
    t = t0.strftime("%Y-%m-%d %H:%M")
    rows, errs = [], []
    for sym in SYMS:
        if time.time() - t0.timestamp() > TIME_LIMIT_S:
            errs.append(f"time limit: skipped from {sym}")
            break
        for mkt in ("fut", "spot"):
            lim = None if mkt == "fut" or sym in SPOT_FULL else 1000
            book, err = K.fetch_book(mkt, sym, timeout=12, limit=lim)
            if err:
                errs.append(err)
                continue
            try:
                rows.append(row(t, sym, mkt, book))
            except Exception as e:  # noqa: BLE001
                errs.append(f"{mkt} {sym}: {type(e).__name__} {e}")
    if rows:
        K.append_csv_gz(DIR / f"{t0.strftime('%Y-%m-%d')}.csv.gz", HEADER, rows)
    if errs:
        DIR.mkdir(parents=True, exist_ok=True)
        with open(DIR / "hata.log", "a", encoding="utf-8") as f:
            f.write(f"{t}Z rows={len(rows)} " + " | ".join(errs) + "\n")
    try:
        print(f"{t}Z rows={len(rows)} errors={len(errs)}")
    except Exception:  # noqa: BLE001  (pythonw: stdout yok)
        pass
    return 0 if rows else 1


if __name__ == "__main__":
    sys.exit(main())
