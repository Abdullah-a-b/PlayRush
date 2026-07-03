"""
⚽ استيراد لاعبين من Wikidata — تغذية قاعدة بيانات "مسيرة لاعب"

  1. أشهر لاعبي كرة القدم (SPARQL بترتيب الشهرة + offset للتوسّع التدريجي).
  2. المسيرة بالأندية فقط (فلتر منتخبات مزدوج: بنيوي + نصّي).
  3. شعارات بـ3 مصادر متتالية (رغم عنها):
     Wikidata P154 → TheSportsDB → صورة مقالة ويكيبيديا.
  4. Upsert بـwikidata_id → التشغيل الدوري يحدّث بلا تكرار.
  5. run_import() قابلة للاستدعاء من خلفية المنصة (تجديد تلقائي).

التشغيل اليدوي:
  python scripts/wikidata_import.py --limit 200
  python scripts/wikidata_import.py --limit 200 --offset 200   # الدفعة التالية
  python scripts/wikidata_import.py --dry-run
"""
import os
import sys
import json
import time
import argparse
import re

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    import requests
except ImportError:
    print("❌ pip install requests")
    sys.exit(1)

from sqlalchemy import text as _sql_text
from app.core.database import SessionLocal, CareerPlayer, engine

WDQS_URL = "https://query.wikidata.org/sparql"
WD_API = "https://www.wikidata.org/w/api.php"
COMMONS_FILE = "https://commons.wikimedia.org/wiki/Special:FilePath/{name}?width=128"
SPORTSDB_SEARCH = "https://www.thesportsdb.com/api/v1/json/3/searchteams.php"
WIKI_SUMMARY = "https://en.wikipedia.org/api/rest_v1/page/summary/{title}"
HEADERS = {"User-Agent": "PlayRushImporter/1.1 (game data; contact: dev@playrush)"}

CLUBS_DIR = os.path.abspath(os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..", "..", "FrontEnd", "assets", "clubs"))

# فلتر المنتخبات — بنيوي (P31) + احتياطي نصّي (يلتقط ما يفلت من القائمة)
NATIONAL_TEAM_TYPES = {
    "Q6979593", "Q23904672", "Q21945604", "Q1194951",
    "Q19833118",  # منتخب وطني تحت سن
    "Q1194970",   # منتخب كرة قدم وطني (نساء)
    "Q98988303",  # منتخب رديف
}
_NT_WORDS_AR = ("منتخب",)
_NT_WORDS_EN = ("national team", "national under", "olympic", " u-17", " u-19",
                " u-20", " u-21", " u-23", "national football", "national soccer")


def _ensure_wikidata_column():
    try:
        with engine.connect() as conn:
            conn.execute(_sql_text(
                "ALTER TABLE career_players ADD COLUMN IF NOT EXISTS wikidata_id VARCHAR"))
            conn.commit()
    except Exception:
        pass


def sparql_top_players(limit, min_sitelinks, offset=0):
    query = f"""
    SELECT ?player ?sitelinks WHERE {{
      ?player wdt:P106 wd:Q937857 ;
              wikibase:sitelinks ?sitelinks .
      FILTER(?sitelinks >= {min_sitelinks})
    }} ORDER BY DESC(?sitelinks) LIMIT {limit} OFFSET {offset}
    """
    r = _get_with_retry(WDQS_URL, params={"query": query, "format": "json"},
                        timeout=120)
    rows = r.json()["results"]["bindings"]
    return [(b["player"]["value"].rsplit("/", 1)[-1], int(b["sitelinks"]["value"]))
            for b in rows]


def _get_with_retry(url, params=None, max_tries=5, timeout=60):
    """طلب GET مع إعادة محاولة ذكية عند 429/5xx (يحترم Retry-After)."""
    for attempt in range(max_tries):
        try:
            r = requests.get(url, params=params, headers=HEADERS, timeout=timeout)
            if r.status_code == 429 or r.status_code >= 500:
                wait = r.headers.get("Retry-After")
                delay = float(wait) if (wait and wait.isdigit()) else (2 ** attempt) * 3
                print(f"   ⏳ {r.status_code} — انتظار {delay:.0f} ثانية ثم إعادة…")
                time.sleep(delay)
                continue
            r.raise_for_status()
            return r
        except requests.exceptions.RequestException:
            if attempt == max_tries - 1:
                raise
            time.sleep((2 ** attempt) * 2)
    raise RuntimeError("استنفدت المحاولات")


# 🗃️ كاش الكيانات عبر الدورة كاملة (الأندية تتكرر بين اللاعبين — نجلبها مرة واحدة)
_ENTITY_CACHE = {}


def wd_get_entities(qids, props="claims|labels|sitelinks"):
    out = {}
    missing = []
    for q in qids:
        if q in _ENTITY_CACHE:
            out[q] = _ENTITY_CACHE[q]
        else:
            missing.append(q)
    for i in range(0, len(missing), 50):
        batch = missing[i:i + 50]
        r = _get_with_retry(WD_API, params={
            "action": "wbgetentities", "ids": "|".join(batch),
            "props": props, "languages": "ar|en", "format": "json",
        })
        ents = r.json().get("entities", {})
        for k, v in ents.items():
            _ENTITY_CACHE[k] = v
        out.update(ents)
        time.sleep(1.2)  # وتيرة لطيفة مع Wikidata (تتجنب 429)
    return out


def _label(ent, lang_pref=("ar", "en")):
    labels = ent.get("labels", {})
    for lg in lang_pref:
        if lg in labels:
            return labels[lg]["value"]
    return None


def _qualifier_time(claim, pid):
    q = claim.get("qualifiers", {}).get(pid)
    if not q:
        return None
    dv = q[0].get("datavalue", {}).get("value", {})
    return dv.get("time")


def parse_career(player_ent):
    claims = player_ent.get("claims", {}).get("P54", [])
    entries = []
    for c in claims:
        try:
            club_qid = c["mainsnak"]["datavalue"]["value"]["id"]
        except (KeyError, TypeError):
            continue
        start = _qualifier_time(c, "P580") or "+9999"
        end = _qualifier_time(c, "P582")
        entries.append({"club": club_qid, "start": start,
                        "has_end": end is not None, "end": end})
    entries.sort(key=lambda e: e["start"])
    return entries


def _year_of(wd_time):
    """يستخرج السنة من صيغة وقت Wikidata (+2023-07-01T…)."""
    try:
        return int(str(wd_time).lstrip("+")[:4])
    except (ValueError, TypeError):
        return None


def detect_status(player_ent, career_entries):
    """حالي/معتزل بدقة:
    - نادٍ بلا تاريخ نهاية → حالي.
    - P2032 (نهاية المسيرة) أو P570 (وفاة) → معتزل.
    - بين ناديين (آخر نهاية خلال آخر سنتين) → حالي (مثل كاسيميرو).
    - آخر نهاية أقدم من سنتين → معتزل."""
    import datetime as _dt
    if any(not e["has_end"] for e in career_entries):
        return "current"
    claims = player_ent.get("claims", {})
    if claims.get("P2032") or claims.get("P570"):
        return "retired"
    end_years = [y for y in (_year_of(e.get("end")) for e in career_entries) if y]
    if end_years and (_dt.date.today().year - max(end_years)) <= 2:
        return "current"  # خرج من ناديه مؤخراً ولم يعتزل
    return "retired"


def is_national_team(club_ent):
    """فلتر مزدوج: P31 البنيوي + فحص نصّي للاسم (يلتقط كل المنتخبات)."""
    for st in club_ent.get("claims", {}).get("P31", []):
        try:
            if st["mainsnak"]["datavalue"]["value"]["id"] in NATIONAL_TEAM_TYPES:
                return True
        except (KeyError, TypeError):
            continue
    ar = (_label(club_ent, ("ar",)) or "")
    en = (_label(club_ent, ("en",)) or "").lower()
    if any(w in ar for w in _NT_WORDS_AR):
        return True
    if any(w in en for w in _NT_WORDS_EN):
        return True
    return False


def _save_img(fpath, content):
    if content and len(content) > 500:
        with open(fpath, "wb") as f:
            f.write(content)
        return True
    return False


def download_logo(club_qid, club_ent, en_name, redo=False):
    """3 مصادر بالأولوية: TheSportsDB (شعارات رسمية حديثة) →
    ويكيبيديا (svg/png فقط — نرفض صور jpg) → كومنز P154 (غالباً قديم — آخر ملاذ)."""
    fname = f"club_{club_qid}.png"
    fpath = os.path.join(CLUBS_DIR, fname)
    if not redo and os.path.exists(fpath) and os.path.getsize(fpath) > 500:
        return fname

    # 1) TheSportsDB — الشعار الرسمي الحديث (أفضل جودة)
    if en_name:
        variants = [en_name,
                    re.sub(r"\b(FC|F\.C\.|CF|C\.F\.|AFC|SC)\b", "", en_name).strip()]
        for name in dict.fromkeys(v for v in variants if v):
            try:
                r = _get_with_retry(SPORTSDB_SEARCH, params={"t": name},
                                    max_tries=3, timeout=30)
                teams = (r.json() or {}).get("teams") or []
                if not teams:
                    continue
                badge = teams[0].get("strBadge") or teams[0].get("strTeamBadge")
                if not badge:
                    continue
                r2 = _get_with_retry(badge + "/small", max_tries=2, timeout=30)
                if not (r2.ok and len(r2.content) > 500):
                    r2 = _get_with_retry(badge, max_tries=2, timeout=30)
                if r2.ok and _save_img(fpath, r2.content):
                    return fname
            except Exception:
                continue

    # 2) صورة مقالة ويكيبيديا — svg/png فقط (jpg = صورة فوتوغرافية غالباً)
    try:
        enwiki = (club_ent.get("sitelinks", {}).get("enwiki", {}) or {}).get("title")
        if enwiki:
            r = _get_with_retry(WIKI_SUMMARY.format(title=requests.utils.quote(enwiki)),
                                max_tries=3, timeout=30)
            if r.ok:
                thumb = ((r.json() or {}).get("thumbnail") or {}).get("source") or ""
                low = thumb.lower()
                if thumb and ".jpg" not in low and ".jpeg" not in low:
                    r2 = _get_with_retry(thumb, max_tries=2, timeout=30)
                    if r2.ok and _save_img(fpath, r2.content):
                        return fname
    except Exception:
        pass

    # 3) كومنز P154 — آخر ملاذ (النسخ المتاحة غالباً قديمة)
    for st in club_ent.get("claims", {}).get("P154", []):
        try:
            commons_name = st["mainsnak"]["datavalue"]["value"]
            url = COMMONS_FILE.format(name=requests.utils.quote(commons_name))
            r = _get_with_retry(url, max_tries=3, timeout=30)
            if r.ok and _save_img(fpath, r.content):
                return fname
        except Exception:
            continue
    # فشلت المصادر: لو كنا نعيد التحميل ويوجد ملف قديم — نُبقيه
    if os.path.exists(fpath) and os.path.getsize(fpath) > 500:
        return fname
    return None


def gen_accepted(ar_name, en_name):
    out = set()
    for n in (ar_name, en_name):
        if not n:
            continue
        n = n.strip()
        out.add(n)
        parts = [p for p in re.split(r"\s+", n) if len(p) > 2]
        if len(parts) >= 2:
            out.add(parts[-1])
            out.add(f"{parts[0]} {parts[-1]}")
    return sorted(out)


def difficulty_for(sitelinks):
    if sitelinks >= 110:
        return "easy"
    if sitelinks >= 70:
        return "medium"
    return "hard"


def run_import(limit=200, min_sitelinks=45, offset=0,
               dry_run=False, skip_logos=False, refresh=False,
               redo_logos=False, log=print):
    """الاستيراد الفعلي — قابلة للاستدعاء من خلفية المنصة.
    ترجع dict بالنتائج."""
    os.makedirs(CLUBS_DIR, exist_ok=True)
    _ensure_wikidata_column()

    log(f"🔎 جلب {limit} لاعب (offset={offset})…")
    players = sparql_top_players(limit, min_sitelinks, offset)
    log(f"   وجدت {len(players)}")

    db = SessionLocal()
    added = updated = skipped = failed = 0
    try:
        existing_qids = {q for (q,) in db.query(CareerPlayer.wikidata_id)
                         .filter(CareerPlayer.wikidata_id.isnot(None)).all()}

        for i in range(0, len(players), 25):
            batch = players[i:i + 25]
            qids = [q for q, _ in batch]
            if not refresh:
                qids = [q for q in qids if q not in existing_qids]
                if not qids:
                    skipped += len(batch)
                    continue
            ents = wd_get_entities(qids)

            club_qids = set()
            careers = {}
            for qid in qids:
                career = parse_career(ents.get(qid, {}))
                careers[qid] = career
                club_qids.update(e["club"] for e in career)
            club_ents = wd_get_entities(list(club_qids)) if club_qids else {}

            for qid in qids:
                ent = ents.get(qid, {})
                ar_name = _label(ent, ("ar",))
                en_name = _label(ent, ("en",))
                display = ar_name or en_name
                if not display:
                    failed += 1
                    continue

                clubs_json = []
                for e in careers.get(qid, []):
                    club_ent = club_ents.get(e["club"], {})
                    if is_national_team(club_ent):
                        continue
                    club_label = _label(club_ent) or e["club"]
                    logo = None
                    if not skip_logos:
                        logo = download_logo(e["club"], club_ent,
                                             _label(club_ent, ("en",)),
                                             redo=redo_logos)
                    entry = {"name": club_label}
                    if logo:
                        entry["logo"] = logo
                    clubs_json.append(entry)

                if not clubs_json:
                    skipped += 1
                    continue

                # حالي/معتزل بدقة (يعالج حالة "بين ناديين" مثل كاسيميرو)
                status = detect_status(ent, careers.get(qid, []))

                sitelinks = next((s for q, s in batch if q == qid), 60)
                row = db.query(CareerPlayer).filter(
                    CareerPlayer.wikidata_id == qid).first()
                if row is None:
                    row = db.query(CareerPlayer).filter(
                        CareerPlayer.name == display).first()

                payload = dict(
                    wikidata_id=qid, name=display,
                    status=status,
                    clubs=json.dumps(clubs_json, ensure_ascii=False),
                    accepted_answers=json.dumps(gen_accepted(ar_name, en_name),
                                                ensure_ascii=False),
                    difficulty=difficulty_for(sitelinks), active=True,
                )
                if dry_run:
                    log(f"   [{'تحديث' if row else 'إضافة'}] {display} — "
                        f"{len(clubs_json)} نادٍ ({'حالي' if status == 'current' else 'معتزل'})")
                    continue
                if row:
                    for k, v in payload.items():
                        setattr(row, k, v)
                    updated += 1
                else:
                    db.add(CareerPlayer(**payload))
                    added += 1
            if not dry_run:
                db.commit()
            log(f"   دفعة {i // 25 + 1}: مضاف {added} | محدّث {updated}")
            time.sleep(0.4)

        total = db.query(CareerPlayer).count()
        log(f"✅ مضاف {added} | 🔄 محدّث {updated} | ⏭️ {skipped} | ⚠️ {failed} | "
            f"📊 الإجمالي: {total}")
        return {"added": added, "updated": updated, "skipped": skipped,
                "failed": failed, "total": total, "fetched": len(players)}
    finally:
        db.close()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=200)
    ap.add_argument("--min-sitelinks", type=int, default=45)
    ap.add_argument("--offset", type=int, default=0)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--skip-logos", action="store_true")
    ap.add_argument("--refresh", action="store_true")
    ap.add_argument("--redo-logos", action="store_true",
                    help="إعادة تحميل الشعارات (يستبدل القديمة بأفضل مصدر)")
    a = ap.parse_args()
    run_import(a.limit, a.min_sitelinks, a.offset, a.dry_run, a.skip_logos,
               a.refresh, a.redo_logos)


if __name__ == "__main__":
    main()
