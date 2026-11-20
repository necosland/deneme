"""Trader ofisi gundem toplayici (LLM yok): kaynaklar.json'daki kaynaklardan son calismadan beri yayimlanan
icerigi indirir, duz metne cevirir, ham/<kaynak>/ altina yazar ve ham/kalemler.jsonl'e kaydeder.

Kaynak tipleri:
  rss       : RSS tam metin (content:encoded), link_contains filtresi (Glassnode The Week On-chain)
  youtube   : kanal RSS'i ile liste + yt-dlp otomatik altyazi (video indirilmez, ses calinmaz)
  x         : api.fxtwitter.com/2/profile/<handle>/statuses (oturumsuz ayna); yeni gonderiler tek kaleme toplanir
  okx_rapor : tr.okx.com haftalik arastirma raporu sayfasi (numara artarak)
Durum: durum.json (son calisma, gorulen kalemler, altyazisi gelmemis bekleyenler). ham/ ve durum.json gitignore'da.

Kullanim: python algo/ofis/gundem/topla.py [--gun 7] [--only id1,id2]
"""
import argparse
import datetime as dt
import email.utils
import html
import json
import pathlib
import re
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

G = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(G.parent))
import ortak as O  # noqa: E402

HAM, DURUM, KAYNAK = G / "ham", G / "durum.json", G / "kaynaklar.json"
KALEMLER = HAM / "kalemler.jsonl"
YTDLP = r"C:\Users\pc\.local\bin\yt-dlp.exe"
UA = {"User-Agent": "Mozilla/5.0"}   # glassnode uzun/ozel UA dizesine 403 veriyor
NOWIN = getattr(subprocess, "CREATE_NO_WINDOW", 0)
MAX_CHARS = 120_000          # ~35k token; uzun yayinlarda kirpilir (kirpma kaydedilir)
PENDING_GIVEUP_H = 72        # altyazi 3 gunde gelmezse birak
LOGF = "gundem.log"
UTC = dt.timezone.utc
TR_AY = {"Oca": 1, "Şub": 2, "Mar": 3, "Nis": 4, "May": 5, "Haz": 6, "Tem": 7, "Ağu": 8, "Eyl": 9, "Eki": 10,
         "Kas": 11, "Ara": 12}


def say(m):
    O.log(LOGF, "topla: " + m)


def iso(t):
    return t.astimezone(UTC).strftime("%Y-%m-%dT%H:%MZ")


def from_iso(s):
    return dt.datetime.strptime(s, "%Y-%m-%dT%H:%MZ").replace(tzinfo=UTC)


def get(url, timeout=30, tries=3):
    last = None
    for i in range(tries):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=timeout) as r:
                return r.read()
        except urllib.error.HTTPError as e:
            if e.code == 404:
                raise
            last = e
        except Exception as e:  # noqa: BLE001
            last = e
        time.sleep(5 * (i + 1))
    raise last


def html_to_text(s):
    s = re.sub(r"(?is)<(script|style|noscript|svg)[^>]*>.*?</\1>", " ", s)
    s = re.sub(r"(?i)<br\s*/?>", "\n", s)
    s = re.sub(r"(?i)</(p|h[1-6]|li|tr|div|blockquote|figcaption)>", "\n", s)
    s = re.sub(r"(?i)<li[^>]*>", "- ", s)
    s = html.unescape(re.sub(r"<[^>]+>", " ", s))
    s = re.sub(r"[ \t\r\f\v]+", " ", s)
    s = re.sub(r"\n\s*\n+", "\n", s)
    return s.strip()


def safe(s):
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", s)[:80]


# ---------------- durum + kayit ----------------
def load_state():
    if DURUM.exists():
        return json.loads(DURUM.read_text(encoding="utf-8"))
    return {"last_run_utc": None, "seen": [], "pending": {}, "okx_next": {}}


def save_state(st):
    st["seen"] = st["seen"][-3000:]
    O.write_json(DURUM, st)


def write_item(src, item_id, published, title, url, kind, text, extra=None):
    trunc = len(text) > MAX_CHARS
    if trunc:
        text = text[:MAX_CHARS] + "\n[...TRUNCATED by topla.py]"
    d = HAM / src["id"]
    d.mkdir(parents=True, exist_ok=True)
    path = d / f"{published.strftime('%Y-%m-%d')}_{safe(item_id.split(':', 1)[1])}.txt"
    head = [f"SOURCE: {src['name']}", f"TITLE: {title}", f"URL: {url}", f"PUBLISHED_UTC: {iso(published)}",
            f"KIND: {kind}", "---"]
    path.write_text("\n".join(head) + "\n" + text + "\n", encoding="utf-8")
    rec = {"id": item_id, "source": src["id"], "source_name": src["name"], "published_utc": iso(published),
           "title": title, "url": url, "kind": kind, "path": str(path), "chars": len(text), "truncated": trunc,
           "collected_utc": iso(O.now_utc()), **(extra or {})}
    O.append_jsonl(KALEMLER, rec)
    return rec


# ---------------- rss ----------------
def do_rss(src, since, st):
    root = ET.fromstring(get(src["url"]))
    ns = {"content": "http://purl.org/rss/1.0/modules/content/"}
    cands = []
    for it in root.iter("item"):
        link = (it.findtext("link") or "").strip()
        if src.get("link_contains") and not any(k in link for k in src["link_contains"]):
            continue
        pub = email.utils.parsedate_to_datetime(it.findtext("pubDate")).astimezone(UTC)
        iid = f"{src['id']}:{link.rstrip('/').rsplit('/', 1)[-1]}"
        if pub < since or iid in st["seen"]:
            continue
        body = it.findtext("content:encoded", namespaces=ns) or it.findtext("description") or ""
        cands.append((pub, iid, (it.findtext("title") or "").strip(), link, body))
    out = []
    for pub, iid, title, link, body in sorted(cands, reverse=True)[:src.get("max_items", 3)]:
        out.append(write_item(src, iid, pub, title, link, "article", html_to_text(body)))
        st["seen"].append(iid)
    return out


# ---------------- youtube ----------------
def vtt_to_text(vtt):
    """YouTube otomatik altyazisi kayan satirlar halinde gelir: etiketsiz satirlar ardisik tekrarsiz alinir,
    ~3 dakikada bir [ss:dd:sn] isareti konur."""
    out, last, mark, t = [], None, -999, 0
    tagged_tail = None
    for line in vtt.splitlines():
        m = re.match(r"(\d+):(\d\d):(\d\d)\.\d+ -->", line)
        if m:
            t = int(m[1]) * 3600 + int(m[2]) * 60 + int(m[3])
            continue
        if not line.strip() or line.startswith(("WEBVTT", "Kind:", "Language:", "NOTE")):
            continue
        if "<" in line:
            tagged_tail = re.sub(r"<[^>]+>", "", line).strip()
            continue
        s = html.unescape(line.strip())
        if s and s != last:
            if t - mark >= 180:
                out.append(f"\n[{t // 3600:02d}:{t % 3600 // 60:02d}:{t % 60:02d}]")
                mark = t
            out.append(s)
            last = s
    if tagged_tail and tagged_tail != last:
        out.append(tagged_tail)
    return re.sub(r"[ ]+", " ", " ".join(out)).strip()


def yt_subs(vid, lang):
    """(live_status, duration, text|None). Video/ses indirilmez."""
    with tempfile.TemporaryDirectory() as td:
        for langs in (f"{lang}-orig,{lang}", "en-orig,en"):
            cmd = [YTDLP, "--js-runtimes", "node", "--no-simulate", "--skip-download", "--write-auto-subs",
                   "--write-subs", "--sub-langs", langs, "--sub-format", "vtt", "--no-warnings",
                   "--print", "%(live_status)s|%(duration)s", "-o", str(pathlib.Path(td) / "%(id)s.%(ext)s"),
                   f"https://www.youtube.com/watch?v={vid}"]
            p = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=240,
                               creationflags=NOWIN)
            first = (p.stdout.strip().splitlines() or ["|"])[0].split("|")
            live, dur = first[0], (int(float(first[1])) if len(first) > 1 and first[1] not in ("", "NA") else None)
            if live in ("is_live", "is_upcoming", "post_live"):
                return live, dur, None
            files = sorted(pathlib.Path(td).glob(f"{vid}*.vtt"), key=lambda f: ("-orig" not in f.name, f.name))
            if files:
                return live, dur, vtt_to_text(files[0].read_text(encoding="utf-8", errors="replace"))
            if p.returncode != 0:
                say(f"yt-dlp {vid} rc={p.returncode} {p.stderr.strip()[-300:]}")
        return live, dur, None


def do_youtube(src, since, st):
    root = ET.fromstring(get(f"https://www.youtube.com/feeds/videos.xml?channel_id={src['channel_id']}"))
    ns = {"a": "http://www.w3.org/2005/Atom", "yt": "http://www.youtube.com/xml/schemas/2015"}
    cands = []
    for e in root.findall("a:entry", ns):
        vid, title = e.findtext("yt:videoId", namespaces=ns), (e.findtext("a:title", namespaces=ns) or "").strip()
        pub = dt.datetime.fromisoformat(e.findtext("a:published", namespaces=ns)).astimezone(UTC)
        iid = f"{src['id']}:{vid}"
        if iid in st["seen"] or (pub < since and iid not in st["pending"]):
            continue
        if src.get("title_include") and not any(k.lower() in title.lower() for k in src["title_include"]):
            continue
        cands.append((pub, iid, vid, title))
    out = []
    for pub, iid, vid, title in sorted(cands, reverse=True):
        if len(out) >= src.get("max_items", 3):
            break
        live, dur, text = yt_subs(vid, src.get("lang", "tr"))
        if dur is not None and dur < src.get("min_duration_s", 0):
            st["seen"].append(iid)
            st["pending"].pop(iid, None)
            say(f"{iid} skipped: short ({dur}s) {title[:60]}")
            continue
        if not text:
            pend = st["pending"].setdefault(iid, {"first_utc": iso(O.now_utc()), "tries": 0})
            pend["tries"] += 1
            age_h = (O.now_utc() - from_iso(pend["first_utc"])).total_seconds() / 3600
            if age_h > PENDING_GIVEUP_H:
                st["seen"].append(iid)
                st["pending"].pop(iid)
                say(f"{iid} GAVE UP: no subtitles after {round(age_h)}h ({live}) {title[:60]}")
            else:
                say(f"{iid} pending: no subtitles yet ({live}, try {pend['tries']}) {title[:60]}")
            continue
        out.append(write_item(src, iid, pub, title, f"https://www.youtube.com/watch?v={vid}", "youtube_transcript",
                              text, {"duration_s": dur}))
        st["seen"].append(iid)
        st["pending"].pop(iid, None)
    return out


# ---------------- x (fxtwitter aynasi) ----------------
def x_time(r):
    if r.get("created_timestamp"):
        return dt.datetime.fromtimestamp(r["created_timestamp"], tz=UTC)
    return email.utils.parsedate_to_datetime(r["created_at"]).astimezone(UTC)


def do_x(src, since, st):
    h = src["handle"]
    base = f"https://api.fxtwitter.com/2/profile/{h}/statuses"
    posts, cursor = {}, None
    for _page in range(6):
        url = base + (f"?cursor={urllib.parse.quote(cursor)}" if cursor else "")
        j = json.loads(get(url).decode("utf-8"))
        res = j.get("results") or []
        for r in res:
            if (r.get("author") or {}).get("screen_name", "").lower() != h.lower():
                continue                                   # baskasinin gonderisi (retweet)
            rep = r.get("replying_to")
            if rep and str(rep.get("screen_name") if isinstance(rep, dict) else rep).lower() != h.lower():
                continue                                   # baskasina yanit: sohbet, gurultu
            t = x_time(r)
            if t >= since and f"x:{r['id']}" not in st["seen"]:
                posts[r["id"]] = (t, r)
        cursor = (j.get("cursor") or {}).get("bottom")
        if not res or not cursor or min(x_time(r) for r in res) < since:
            break
        time.sleep(2)
    if not posts:
        return []
    rows = sorted(posts.values(), key=lambda x: x[0])
    imgdir = HAM / src["id"] / "img"
    photos_left, lines, imgs = src.get("max_photos", 3), [], []
    for t, r in rows:
        txt = (r.get("text") or "").strip()
        q = r.get("quote")
        if q:
            txt += f"\n  QUOTE @{(q.get('author') or {}).get('screen_name')}: {(q.get('text') or '').strip()[:600]}"
        media = r.get("media") or {}
        ph = media.get("photos") or []
        vids = [m for m in (media.get("all") or []) if m.get("type") in ("video", "gif")]
        for i, p in enumerate(ph):
            if photos_left <= 0:
                txt += "\n  [image not downloaded: photo cap]"
                break
            try:
                imgdir.mkdir(parents=True, exist_ok=True)
                f = imgdir / f"{r['id']}_{i}.jpg"
                f.write_bytes(get(p["url"].replace("name=orig", "name=small")))
                imgs.append(str(f))
                photos_left -= 1
                txt += f"\n  [image: {f}]"
            except Exception as e:  # noqa: BLE001
                txt += f"\n  [image fetch failed: {e}]"
        if vids:
            txt += "\n  [video attached: not transcribed]"
        lines.append(f"[{iso(t)}] (views {r.get('views')}, likes {r.get('likes')}) {r.get('url')}\n{txt}\n")
        st["seen"].append(f"x:{r['id']}")
    newest = rows[-1][0]
    iid = f"{src['id']}:{newest.strftime('%Y%m%d%H%M')}_{rows[-1][1]['id']}"
    return [write_item(src, iid, newest, f"@{h} posts {iso(rows[0][0])} .. {iso(newest)} ({len(rows)})",
                       f"https://x.com/{h}", "tweets", "\n".join(lines), {"posts": len(rows), "images": imgs})]


# ---------------- okx tr raporu ----------------
def do_okx(src, since, st):
    n = st["okx_next"].get(src["id"], src["start_no"])
    out, misses = [], 0
    while misses < 2 and len(out) < src.get("max_items", 1) + 2:
        url = src["url_pattern"].format(n=n)
        try:
            page = get(url, tries=2).decode("utf-8", "replace")
        except urllib.error.HTTPError:
            page = ""
        if f"#{n}" not in (re.search(r"<title>(.*?)</title>", page, re.S) or [None, ""])[1]:
            misses += 1
            n += 1
            continue
        text = html_to_text(page)
        m = re.search(r"Yayımlama Zamanı:\s*(\d{1,2}) (\w{3}) (\d{4})", text)
        pub = dt.datetime(int(m[3]), TR_AY.get(m[2], 1), int(m[1]), 12, tzinfo=UTC) if m else O.now_utc()
        i = text.find("Okuma Süresi")
        j = min([k for k in (text.find("İlgili Makaleler", i), text.find("Daha Fazlasını Görüntüle", i)) if k > 0]
                or [len(text)])
        body = text[i:j] if i > 0 else text
        iid = f"{src['id']}:{n}"
        if iid not in st["seen"] and pub >= since - dt.timedelta(days=1):
            out.append(write_item(src, iid, pub, f"OKX TR Haftalik Arastirma Raporu #{n}", url, "report", body))
        st["seen"].append(iid)
        n += 1
        misses = 0
        st["okx_next"][src["id"]] = n
    return out


HANDLERS = {"rss": do_rss, "youtube": do_youtube, "x": do_x, "okx_rapor": do_okx}


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--gun", type=float, help="son N gun (varsayilan: son calismadan beri; ilk calismada ayardaki)")
    ap.add_argument("--only", help="yalniz bu kaynak id'leri (virgulle)")
    a = ap.parse_args(argv)
    cfg = json.loads(KAYNAK.read_text(encoding="utf-8"))
    st = load_state()
    now = O.now_utc()
    if a.gun:
        since = now - dt.timedelta(days=a.gun)
    elif st["last_run_utc"]:
        since = from_iso(st["last_run_utc"]) - dt.timedelta(hours=6)   # cakisma payi; tekrar 'seen' ile elenir
    else:
        since = now - dt.timedelta(days=cfg.get("lookback_days_first_run", 7))
    say(f"start since={iso(since)}")
    new, report = [], {}
    for src in cfg["sources"]:
        if not src.get("enabled", True) or (a.only and src["id"] not in a.only.split(",")):
            continue
        try:
            got = HANDLERS[src["type"]](src, since, st)
            new += got
            report[src["id"]] = f"ok {len(got)}"
        except Exception as e:  # noqa: BLE001
            report[src["id"]] = f"ERROR {type(e).__name__}: {str(e)[:160]}"
        say(f"{src['id']}: {report[src['id']]}")
        save_state(st)
    if not a.only:
        st["last_run_utc"] = iso(now)
    save_state(st)
    say(f"done new={len(new)} " + json.dumps(report, ensure_ascii=False))
    return new, report


if __name__ == "__main__":
    new, rep = main()
    try:
        print(json.dumps({"new": [r["id"] for r in new], "sources": rep}, ensure_ascii=False, indent=1))
    except Exception:  # noqa: BLE001
        pass
