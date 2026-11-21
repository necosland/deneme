"""Trader ofisi ortak yardimcilari: yollar, ayar, sema dogrulama, kilit, gunluk. LLM yok."""
import datetime as dt
import json
import os
import pathlib
import re
import time

ROOT = pathlib.Path(__file__).resolve().parent
REPO = ROOT.parent.parent
VERI, GRAFIK, LOG, DEFTER = ROOT / "veri", ROOT / "grafik", ROOT / "log", ROOT / "defter"
AGENT_BILGI = pathlib.Path(os.path.expanduser("~")) / ".claude" / "agent-bilgi" / "trader-ofis"
PY = pathlib.Path(r"C:\Users\pc\AppData\Local\Programs\Python\Python313\python.exe")
SPOT_KLINES = "https://data-api.binance.vision/api/v3/klines"
FAPI = "https://fapi.binance.com"
UA = {"User-Agent": "Mozilla/5.0 (paper-trading research script)"}


def ayar():
    return json.loads((ROOT / "ofis-ayar.json").read_text(encoding="utf-8"))


def sema():
    return json.loads((ROOT / "sema.json").read_text(encoding="utf-8"))


def now_utc():
    return dt.datetime.now(dt.timezone.utc)


def fmt(t):
    return t.strftime("%Y-%m-%d %H:%M")


def parse_utc(s):
    return dt.datetime.strptime(s, "%Y-%m-%d %H:%M").replace(tzinfo=dt.timezone.utc)


def ms(t):
    return int(t.timestamp() * 1000)


def from_ms(x):
    return dt.datetime.fromtimestamp(x / 1000, tz=dt.timezone.utc)


def log(name, msg):
    LOG.mkdir(parents=True, exist_ok=True)
    line = f"{fmt(now_utc())}Z {msg}"
    with open(LOG / name, "a", encoding="utf-8") as f:
        f.write(line + "\n")
    try:
        print(line, flush=True)
    except Exception:  # noqa: BLE001  (pythonw: stdout yok)
        pass


TESTDIR = None   # --no-ledger kosusunda tur.py bunu kosunun log klasorune cevirir: test satirlari canli defter/ dosyalarina yazilmaz


def ledger_file(name):
    """Yazma/ayni-tur okuma yolu: normalde defter/<name>, --no-ledger'da log/<stamp>/<name>."""
    return (TESTDIR or DEFTER) / name


def append_jsonl(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(obj, ensure_ascii=False) + "\n")


def read_jsonl(path):
    if not path.exists():
        return []
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                pass
    return out


def write_json(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(obj, ensure_ascii=False, indent=1), encoding="utf-8")
    os.replace(tmp, path)


# ---------------- kilit (tur ve kontrol ayni anda defter yazmasin) ----------------
class Kilit:
    def __init__(self, wait_s=0, stale_s=900):
        self.path, self.wait_s, self.stale_s, self.ok = DEFTER / ".kilit", wait_s, stale_s, False

    def __enter__(self):
        DEFTER.mkdir(parents=True, exist_ok=True)
        t0 = time.time()
        while True:
            try:
                fd = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                os.write(fd, str(os.getpid()).encode())
                os.close(fd)
                self.ok = True
                return self
            except FileExistsError:
                try:
                    if time.time() - self.path.stat().st_mtime > self.stale_s:
                        self.path.unlink()
                        continue
                except FileNotFoundError:
                    continue
                if time.time() - t0 >= self.wait_s:
                    return self
                time.sleep(2)

    def __exit__(self, *a):
        if self.ok:
            try:
                self.path.unlink()
            except FileNotFoundError:
                pass


# ---------------- LLM ciktisi ----------------
def extract_json(text):
    """Son ```json blogu; yoksa son [...] dizisi."""
    if not text:
        return None
    blocks = re.findall(r"```(?:json)?\s*(.*?)```", text, flags=re.S)
    for b in reversed(blocks):
        try:
            return json.loads(b)
        except json.JSONDecodeError:
            continue
    i, j = text.rfind("["), text.rfind("]")
    while i != -1:
        try:
            return json.loads(text[i:j + 1])
        except json.JSONDecodeError:
            i = text.rfind("[", 0, i)
    return None


def validator(defname):
    import jsonschema
    s = sema()
    sub = {"$schema": s["$schema"], "$defs": s["$defs"], "$ref": f"#/$defs/{defname}"}
    return jsonschema.Draft202012Validator(sub)


def schema_errors(v, obj):
    return [f"{'/'.join(str(p) for p in e.absolute_path) or '.'}: {e.message[:120]}" for e in v.iter_errors(obj)]


def entry_px(entry, last_close):
    if entry is None:
        return None
    return last_close if entry.get("type") == "market" else entry.get("price")


def geometry_errors(side, entry, stop, targets, last_close, atr4h, lim, check_rr=True):
    """Long'da stop < giris < hedefler, short'ta tersi; R:R, stop mesafesi, giris uzakligi."""
    e = entry_px(entry, last_close)
    errs = []
    if e is None or stop is None or not targets:
        return ["missing entry/stop/targets"]
    sgn = 1 if side == "long" else -1
    if not sgn * (e - stop) > 0:
        errs.append(f"stop {stop} wrong side of entry {e}")
    if any(not sgn * (t - e) > 0 for t in targets):
        errs.append(f"target on wrong side of entry {e}")
    if any(sgn * (b - a) < 0 for a, b in zip(targets, targets[1:])):
        errs.append("targets not ordered near to far")
    # limit giris: T1 son kapanisin islem yonunde otesinde olmali (R17: long limit 75000, T1 77000, son 77029;
    # dolum aninda hedef zaten gecilmis olur). Neco 2026-11-21.
    if (entry or {}).get("type") == "limit" and last_close is not None and not sgn * (targets[0] - last_close) > 0:
        errs.append(f"limit entry: T1 {targets[0]} not beyond last close {last_close} for {side}")
    if errs:
        return errs
    risk = abs(e - stop)
    if check_rr:
        rr, cost_r, rr_net = rr_cost(side, entry, stop, targets[0], last_close, lim)
        if lim.get("rr_cost_aware"):
            if rr_net < lim["min_rr_t1"] - 1e-9:
                errs.append(f"R:R to T1 after costs {rr_net:.2f} (gross {rr:.2f}, cost {cost_r:.2f}R) < {lim['min_rr_t1']}")
        elif rr < lim["min_rr_t1"] - 1e-9:
            errs.append(f"R:R to T1 {rr:.2f} < {lim['min_rr_t1']}")
        if atr4h and risk < lim["min_stop_atr4h"] * atr4h - 1e-9:
            errs.append(f"stop distance {risk:.4g} < {lim['min_stop_atr4h']}xATR4h {atr4h}")
        if lim.get("min_stop_pct") and risk < lim["min_stop_pct"] / 100 * e - 1e-12:
            errs.append(f"stop distance {100 * risk / e:.3f}% < min_stop_pct {lim['min_stop_pct']}%")
        k = lim.get("entry_max_atr4h", 2.0)
        if atr4h and abs(e - last_close) > k * atr4h + 1e-9:
            errs.append(f"entry {e} farther than {k}xATR4h from last close {last_close}")
    return errs


def rr_cost(side, entry, stop, t1, last_close, lim):
    """(brut R:R, maliyet R, net R:R) T1'e. Maliyet: giris ucreti (limit maker, market/stop taker+kayma),
    T1 cikisi maker, stop cikisi taker+kayma. Net R:R = (odul - giris/T1 maliyeti) / (risk + giris/stop maliyeti)."""
    e = entry_px(entry, last_close)
    risk = abs(e - stop)
    if not risk:
        return 0.0, float("inf"), 0.0
    ft, fm, sl = lim.get("fee_taker", 0.0), lim.get("fee_maker", 0.0), lim.get("slippage", 0.0)
    cin = e * (fm if (entry or {}).get("type") == "limit" else ft + sl)
    reward_net = abs(t1 - e) - cin - t1 * fm
    risk_net = risk + cin + stop * (ft + sl)
    cost_r = (cin + t1 * fm) / risk           # T1'e giden islemin maliyeti, R cinsinden
    return abs(t1 - e) / risk, cost_r, reward_net / risk_net


def vote_passes(conf, rr_gross, cost_r, lim):
    """Oy esigi ayardan: vote_rule 'min_conf' (conf >= min_confidence) ya da 'ev'
    (conf/100*RR - (1-conf/100) - cost_R >= min_ev_r). Donus (gecti_mi, aciklama)."""
    if conf is None:
        return False, "no confidence"
    if conf > lim.get("max_confidence", 80):
        return False, f"confidence {conf} > max_confidence {lim.get('max_confidence', 80)}"
    if lim.get("vote_rule", "min_conf") == "ev":
        p = conf / 100
        ev = p * rr_gross - (1 - p) - cost_r
        thr = lim.get("min_ev_r", 0.15)
        return ev >= thr - 1e-9, f"EV {ev:.2f}R vs min_ev_r {thr} (conf {conf}, RR {rr_gross:.2f}, cost {cost_r:.2f}R)"
    thr = lim.get("min_confidence", 55)
    return conf >= thr, f"confidence {conf} vs min_confidence {thr}"


def find_claude():
    """PATH'teki claude; yoksa masaustu uygulamasinin en yeni claude.exe'si."""
    import shutil
    p = shutil.which("claude")
    if p:
        return p
    base = pathlib.Path(os.environ.get("APPDATA", "")) / "Claude" / "claude-code"
    cands = sorted(base.glob("*/*/claude.exe"), key=lambda x: [int(n) if n.isdigit() else n
                                                              for n in re.split(r"[.]", x.parent.parent.name)])
    if cands:
        return str(cands[-1])
    local = pathlib.Path(os.path.expanduser("~")) / ".local" / "bin" / "claude.exe"
    return str(local) if local.exists() else None
