"""Trader ofisi kayitcilari ve snapshot icin ortak, hafif yardimcilar (pandas yok, LLM yok, anahtar yok).

- Emir defteri ozeti (Binance spot data-api + USD-M vadeli, herkese acik REST): +-%0.5/1/2/5 bant likiditesi, en buyuk
  duvarlar, kayit icin fiyat kovalari. Vadeli REST en cok 1000 kademe verir: BTC'de ~+-%0.3, ETH'de ~+-%0.8 kapsar;
  kapsanmayan bant null olur (reach_pct ne kadar uzaga gorulebildigini soyler).
- kayit/ dosyalari: gzip'e ek (her ek ayri gzip uyesi; gzip/pandas okur), yarim yazilmis son uye okumada atlanir.
- Tek ornek kilidi (Windows msvcrt), arka plan surecleri icin.
"""
import csv
import datetime as dt
import gzip
import io
import math
import os
import pathlib

import requests

ROOT = pathlib.Path(__file__).resolve().parent
KAYIT = ROOT / "kayit"
UA = {"User-Agent": "Mozilla/5.0 (paper-trading research script)"}
BOOK = {"spot": ("https://data-api.binance.vision/api/v3/depth", 5000),
        "fut": ("https://fapi.binance.com/fapi/v1/depth", 1000)}
BANDS = (0.5, 1, 2, 5)
WALL_PCT = 0.1        # duvar kovasi = fiyatin ~%0.1'i (yuvarlak adim)
HEAT_PCT = 0.25       # kayit kovasi = fiyatin ~%0.25'i, +-%5 icinde
HEAT_SPAN = 5.0


def now_utc():
    return dt.datetime.now(dt.timezone.utc)


def rn(x, sig=5):
    """sig anlamli basamak; NaN/inf/None -> None."""
    try:
        x = float(x)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(x):
        return None
    if x == 0:
        return 0.0
    d = max(0, sig - int(math.floor(math.log10(abs(x)))) - 1)
    return round(x, d)


def nice(x):
    """x'e en yakin yuvarlak adim (1, 2, 2.5, 5 x 10^k)."""
    e = 10 ** math.floor(math.log10(x))
    return min((m * e for m in (1, 2, 2.5, 5, 10)), key=lambda s: abs(s - x))


def fetch_book(mkt, sym, timeout=20):
    """(bids, asks) [(fiyat, miktar)] en iyiden kotuye; hata -> (None, mesaj)."""
    url, lim = BOOK[mkt]
    try:
        r = requests.get(url, params={"symbol": sym, "limit": lim}, headers=UA, timeout=timeout)
        if r.status_code in (403, 451):
            return None, f"{mkt} depth {sym}: HTTP {r.status_code} (blocked)"
        r.raise_for_status()
        j = r.json()
        bids = [(float(p), float(q)) for p, q in j["bids"]]
        asks = [(float(p), float(q)) for p, q in j["asks"]]
        if not bids or not asks:
            return None, f"{mkt} depth {sym}: empty book"
        return (bids, asks), None
    except Exception as e:  # noqa: BLE001
        return None, f"{mkt} depth {sym}: {type(e).__name__} {str(e)[:100]}"


def _buckets(levels, step, lo, hi):
    out = {}
    for p, q in levels:
        if lo <= p <= hi:
            k = round(p / step) * step
            out[k] = out.get(k, 0.0) + p * q
    return out


def book_summary(bids, asks, nwalls=3):
    """Snapshot icin kompakt ozet. bands_musd: {"0.5": [bid_usd_m, ask_usd_m], ...}; kapsanmayan bant null.
    walls: fiyatin ~%0.1'i genislikte kovalarda en buyuk nominal, [kova_fiyati, usd_m], +-%5 (ya da gorulen) icinde."""
    bb, ba = bids[0][0], asks[0][0]
    mid = (bb + ba) / 2
    rb, ra = (mid - bids[-1][0]) / mid * 100, (asks[-1][0] - mid) / mid * 100
    bands = {}
    for b in BANDS:
        lo, hi = mid * (1 - b / 100), mid * (1 + b / 100)
        bv = sum(p * q for p, q in bids if p >= lo) if rb >= b else None
        av = sum(p * q for p, q in asks if p <= hi) if ra >= b else None
        bands[str(b)] = [None if bv is None else rn(bv / 1e6, 4), None if av is None else rn(av / 1e6, 4)]
    step = nice(mid * WALL_PCT / 100)
    span = mid * HEAT_SPAN / 100
    wb = _buckets(bids, step, mid - span, mid)
    wa = _buckets(asks, step, mid, mid + span)
    top = lambda d: [[rn(k), rn(v / 1e6, 3)] for k, v in sorted(d.items(), key=lambda kv: -kv[1])[:nwalls]]  # noqa: E731
    return {"mid": rn(mid), "spread_bp": rn((ba - bb) / mid * 1e4, 3), "reach_pct": [rn(rb, 3), rn(ra, 3)],
            "bands_musd": bands, "walls_bid": top(wb), "walls_ask": top(wa), "wall_bucket": rn(step)}


def heat_buckets(bids, asks):
    """Kayit icin: +-%5 (gorulen kadar) icinde ~%0.25'lik kovalarda nominal. -> (adim, {kova: usd})."""
    mid = (bids[0][0] + asks[0][0]) / 2
    step = nice(mid * HEAT_PCT / 100)
    span = mid * HEAT_SPAN / 100
    d = _buckets(bids, step, mid - span, mid)
    for k, v in _buckets(asks, step, mid, mid + span).items():
        d[k] = d.get(k, 0.0) + v
    return step, d


# ---------------- dosya ----------------
def append_csv_gz(path, header, rows):
    """Satirlari gzip dosyasina yeni bir uye olarak ekler; dosya yoksa basliga yazar."""
    path.parent.mkdir(parents=True, exist_ok=True)
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    if not path.exists():
        w.writerow(header)
    w.writerows(rows)
    with open(path, "ab") as f, gzip.GzipFile(fileobj=f, mode="wb") as g:
        g.write(buf.getvalue().encode("utf-8"))


def read_csv_any(path):
    """csv ya da csv.gz -> dict satirlari. Yazilmakta olan yarim son satir/uye sessizce atlanir."""
    lines = []
    try:
        if str(path).endswith(".gz"):
            with gzip.open(path, "rt", encoding="utf-8", newline="") as f:
                try:
                    for ln in f:
                        lines.append(ln)
                except (EOFError, OSError, gzip.BadGzipFile):
                    pass
        else:
            with open(path, encoding="utf-8", newline="") as f:
                lines = f.readlines()
    except OSError:
        return []
    if lines and not lines[-1].endswith("\n"):
        lines = lines[:-1]
    return list(csv.DictReader(lines))


def day_files(folder, days, suffix, end=None):
    end = end or now_utc()
    out = []
    for k in range(days, -1, -1):
        f = folder / f"{(end - dt.timedelta(days=k)).strftime('%Y-%m-%d')}{suffix}"
        if f.exists():
            out.append(f)
    return out


class TekOrnek:
    """Tek ornek kilidi: dosyayi acik tutar ve ilk baytini kilitler (surec olunce isletim sistemi birakir)."""

    def __init__(self, path):
        self.path, self.f = pathlib.Path(path), None

    def __enter__(self):
        import msvcrt
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.f = open(self.path, "a+b")
        try:
            self.f.seek(0)
            msvcrt.locking(self.f.fileno(), msvcrt.LK_NBLCK, 1)
            self.ok = True
            self.path.with_suffix(".pid").write_text(str(os.getpid()), encoding="ascii")
        except OSError:
            self.ok = False
        return self

    def __exit__(self, *a):
        try:
            self.f.close()
        except Exception:  # noqa: BLE001
            pass
