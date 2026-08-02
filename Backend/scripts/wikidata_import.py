"""
 استيراد لاعبين من Wikidata — تغذية قاعدة بيانات "مسيرة لاعب"

  1. أشهر لاعبي كرة القدم (SPARQL بترتيب الشهرة + offset للتوسّع التدريجي).
  2. المسيرة بالأندية فقط (فلتر منتخبات مزدوج: بنيوي + نصّي).
  3. شعارات بـ3 مصادر متتالية (رغم عنها):
     Wikidata P154  TheSportsDB  صورة مقالة ويكيبيديا.
  4. Upsert بـwikidata_id  التشغيل الدوري يحدّث بلا تكرار.
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
    print(" pip install requests")
    sys.exit(1)

from sqlalchemy import text as _sql_text
from app.infrastructure.database import SessionLocal, engine
from app.domains.games.models import CareerPlayer

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
            for col in ("wikidata_id VARCHAR", "era VARCHAR", "position VARCHAR"):
                conn.execute(_sql_text(
                    f"ALTER TABLE career_players ADD COLUMN IF NOT EXISTS {col}"))
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


# كاش الكيانات عبر الدورة كاملة (الأندية تتكرر بين اللاعبين — نجلبها مرة واحدة)
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


_YOUTH_AR = ("شباب", "أكاديمية", "تحت", "رديف", "ب)")
_YOUTH_EN = ("youth", "academy", "u17", "u19", "u21", "u23", "under-", " b\u200e",
             " b team", "reserves", "juvenil", "castilla", "ii", " b)")


def is_youth_team(club_ent):
    ar = (_label(club_ent, ("ar",)) or "")
    en = (_label(club_ent, ("en",)) or "").lower()
    if any(w in ar for w in _YOUTH_AR):
        return True
    return any(w in en for w in _YOUTH_EN)


def compute_era(career_entries):
    """فترة المسيرة: "1995-2010" أو "2015-الآن" للحالي."""
    starts = [y for y in (_year_of(e.get("start")) for e in career_entries) if y and y < 9000]
    ends = [y for y in (_year_of(e.get("end")) for e in career_entries) if y]
    if not starts:
        return None
    first = min(starts)
    if any(not e["has_end"] for e in career_entries):
        return f"{first}-الآن"
    return f"{first}-{max(ends)}" if ends else str(first)


def extract_position_qid(player_ent):
    """QID مركز اللاعب (P413) الأول إن وُجد."""
    for st in player_ent.get("claims", {}).get("P413", []):
        try:
            return st["mainsnak"]["datavalue"]["value"]["id"]
        except (KeyError, TypeError):
            continue
    return None


def extract_nationality_qid(player_ent):
    """QID الجنسية (P27) الأولى إن وُجدت."""
    for st in player_ent.get("claims", {}).get("P27", []):
        try:
            return st["mainsnak"]["datavalue"]["value"]["id"]
        except (KeyError, TypeError):
            continue
    return None


def detect_status(player_ent, career_entries):
    """حالي/معتزل بدقة:
    - نادٍ بلا تاريخ نهاية  حالي.
    - P2032 (نهاية المسيرة) أو P570 (وفاة)  معتزل.
    - بين ناديين (آخر نهاية خلال آخر سنتين)  حالي (مثل كاسيميرو).
    - آخر نهاية أقدم من سنتين  معتزل."""
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


def download_logo(club_qid, club_ent, en_name, redo=False):
    """3 مصادر بالأولوية: TheSportsDB (شعارات رسمية حديثة)
    ويكيبيديا (svg/png فقط — نرفض صور jpg)  كومنز P154 (غالباً قديم — آخر ملاذ).

    نُرجع رابط الصورة مباشرة (بدون تحميلها وحفظها في FrontEnd/assets/clubs) —
    الواجهة تعرضها من مصدرها الأصلي مباشرة. السبب: هذا السكربت يشتغل تلقائياً
    كل أسبوع من داخل سيرفر الإنتاج (career_auto_import_loop)، وما كان فيه أي
    طريقة يوصل فيها ملف محلي محفوظ هناك إلى Cloudflare Pages إلا بـ git push
    يدوي — فكانت الأندية الجديدة تظهر بلا شعار (404) لحد ما يصير الرفع اليدوي.
    نتحقق أول إن الرابط فعلاً يرجّع صورة قبل ما نعتمده، لتفادي حفظ روابط ميتة.
    (التوافق مع الشعارات القديمة المحمّلة محلياً قبل هذا التعديل باقٍ كما هو أدناه.)"""
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
                # أسماء مثل "Arsenal" تعيد أندية من دول مختلفة (لندن/بوليفيا/تولا).
                # نطابق الاسم الإنجليزي الأصلي بدقّة، ونرفض المطابقات الضعيفة تماماً.
                orig_low = (en_name or "").lower().strip()
                orig_nofc = re.sub(r"\b(fc|f\.c\.|cf|c\.f\.|afc|sc|club)\b", "",
                                   orig_low).strip()
                def _score(t):
                    tn = (t.get("strTeam") or "").lower().strip()
                    tn_nofc = re.sub(r"\b(fc|f\.c\.|cf|c\.f\.|afc|sc|club)\b", "",
                                     tn).strip()
                    s = -1
                    if tn == orig_low:
                        s = 100                       # مطابقة تامة
                    elif tn_nofc == orig_nofc and orig_nofc:
                        s = 80                        # مطابقة بعد إزالة FC
                    elif tn == name.lower().strip():
                        s = 60                        # مطابقة variant المبحوث
                    else:
                        return -1                     # اسم مختلف  مرفوض
                    if (t.get("strSport") or "").lower() == "soccer":
                        s += 5
                    # إشارات الأندية الكبرى (دوري معروف)
                    lg = (t.get("strLeague") or "").lower()
                    if any(k in lg for k in ("premier", "liga", "serie", "bundesliga",
                                             "ligue 1", "eredivisie", "primeira")):
                        s += 10
                    return s
                scored = [(t, _score(t)) for t in teams]
                scored = [(t, sc) for t, sc in scored if sc >= 0]  # نرفض المختلفة
                if not scored:
                    continue  # لا مطابقة موثوقة  ننتقل للمصدر التالي
                scored.sort(key=lambda x: x[1], reverse=True)
                badge = None
                for t, sc in scored:
                    if (t.get("strSport") or "").lower() not in ("", "soccer"):
                        continue
                    badge = t.get("strBadge") or t.get("strTeamBadge")
                    if badge:
                        break
                if not badge:
                    continue
                logo_url = badge + "/small"
                r2 = _get_with_retry(logo_url, max_tries=2, timeout=30)
                if not (r2.ok and len(r2.content) > 500):
                    logo_url = badge
                    r2 = _get_with_retry(logo_url, max_tries=2, timeout=30)
                if r2.ok and len(r2.content) > 500:
                    return logo_url
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
                    if r2.ok and len(r2.content) > 500:
                        return thumb
    except Exception:
        pass

    # 3) كومنز P154 — آخر ملاذ (النسخ المتاحة غالباً قديمة)
    for st in club_ent.get("claims", {}).get("P154", []):
        try:
            commons_name = st["mainsnak"]["datavalue"]["value"]
            url = COMMONS_FILE.format(name=requests.utils.quote(commons_name))
            r = _get_with_retry(url, max_tries=3, timeout=30)
            if r.ok and len(r.content) > 500:
                return url
        except Exception:
            continue
    # فشلت المصادر: لو كنا نعيد التحميل ويوجد ملف قديم — نُبقيه
    if os.path.exists(fpath) and os.path.getsize(fpath) > 500:
        return fname
    return None


def build_clubs_json(career_list, club_ents, skip_logos=False, redo_logos=False):
    """يبني قائمة أندية لاعب واحد (بالاسم + الشعار) من مسيرته المفروزة
    و كيانات الأندية المجلوبة مسبقاً. مستقلة عن run_import كي يُعاد
    استخدامها من الاستيراد الكامل وبكسل تصحيح الشعارات القديمة معاً."""
    clubs_json = []
    _logo_by_base = {}
    _starts_youth = bool(career_list and career_list[0].get("_youth"))

    for _idx, e in enumerate(career_list):
        club_ent = club_ents.get(e["club"], {})
        if is_national_team(club_ent):
            continue

        is_youth = bool(e.get("_youth"))
        # قاعدة الشباب: نُبقي فقط أكاديمية البداية (لامين يامال)،
        # ونحذف أي فريق شباب آخر (يعقّد اللعبة).
        if is_youth and not (_starts_youth and _idx == 0):
            continue

        en_lbl = (_label(club_ent, ("en",)) or "")
        _base = re.sub(r"\b(youth|academy|u\d+|under[- ]\d+|b|ii|reserves?|juvenil|castilla)\b",
                       "", en_lbl.lower()).strip()

        if is_youth:
            # أكاديمية البداية: نسمّيها "أكاديمية <النادي الأم>"
            parent = _base.title() if _base else en_lbl
            club_label = f"أكاديمية {parent}"
        else:
            club_label = _label(club_ent) or e["club"]

        logo = None
        if not skip_logos:
            logo = download_logo(e["club"], club_ent,
                                 _label(club_ent, ("en",)), redo=redo_logos)
        entry = {"name": club_label}
        if logo:
            entry["logo"] = logo
            if _base:
                _logo_by_base.setdefault(_base, logo)
        entry["_base"] = _base
        entry["_youth"] = is_youth
        clubs_json.append(entry)

    # أكاديمية البداية بلا شعار  ترث شعار النادي الأم (لو ظهر لاحقاً)
    for entry in clubs_json:
        if "logo" not in entry and entry.get("_youth") \
                and entry.get("_base") in _logo_by_base:
            entry["logo"] = _logo_by_base[entry["_base"]]
        entry.pop("_base", None)
        entry.pop("_youth", None)
    return clubs_json


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
            out.add(parts[0])            # الاسم الأول وحده (بيبي، كاكا…)
            out.add(f"{parts[0]} {parts[-1]}")
    return sorted(out)


def difficulty_for(sitelinks):
    # 🩹 حد الاستيراد الأدنى (min_sitelinks=45) مرتفع أصلاً — أي لاعب يتجاوزه
    # معروف عالمياً بشكل معقول، مو عشوائي مغمور. عتبة medium=70 القديمة كانت
    # تحشر كل نطاق 45-69 (لاعبين معروفين فعلاً لعشاق الكرة) في "hard" —
    # فصار 83% من القاعدة المستوردة "hard" رغم إنهم مو مغمورين فعلياً بهذا
    # الحجم. خفّضناها لتنصيف هذا النطاق الواسع بدل تركه كله بخانة واحدة.
    if sitelinks >= 110:
        return "easy"
    if sitelinks >= 55:
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
                for _fx in (extract_position_qid(ents.get(qid, {})),
                            extract_nationality_qid(ents.get(qid, {}))):
                    if _fx:
                        club_qids.add(_fx)
            club_ents = wd_get_entities(list(club_qids)) if club_qids else {}

            for qid in qids:
                ent = ents.get(qid, {})
                # فرز ثانوي: أكاديميات/شباب النادي قبل الفريق الأول
                # (غالباً بلا P580 — نضعها في البداية لا النهاية)
                _career = careers.get(qid, [])
                for e in _career:
                    e["_youth"] = is_youth_team(club_ents.get(e["club"], {}))
                    if e["start"] == "+9999" and e["_youth"]:
                        e["start"] = "+0000"  # شباب بلا تاريخ  البداية
                _career.sort(key=lambda e: (e["start"], 0 if e["_youth"] else 1))
                ar_name = _label(ent, ("ar",))
                en_name = _label(ent, ("en",))
                display = ar_name or en_name
                if not display:
                    failed += 1
                    continue

                clubs_json = build_clubs_json(careers.get(qid, []), club_ents,
                                              skip_logos=skip_logos, redo_logos=redo_logos)

                if not clubs_json:
                    skipped += 1
                    continue

                # حالي/معتزل بدقة (يعالج حالة "بين ناديين" مثل كاسيميرو)
                status = detect_status(ent, careers.get(qid, []))
                era = compute_era(careers.get(qid, []))
                pos_qid = extract_position_qid(ent)
                position = _label(club_ents.get(pos_qid, {})) if pos_qid else None
                nat_qid = extract_nationality_qid(ent)
                nationality = _label(club_ents.get(nat_qid, {})) if nat_qid else None

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
                    era=era, position=position, nationality=nationality,
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


def backfill_difficulty(log=print, on_progress=None):
    """يعيد حساب difficulty لكل اللاعبين المستوردين حالياً بالعتبات
    الحالية في difficulty_for() — يُستخدم مرة واحدة بعد أي تعديل بالعتبات
    كي لا ينتظر اللاعبون القدامى دورة الاستيراد الأسبوعية التالية.
    تُعاد قراءة sitelinks الحقيقية من Wikidata لكل لاعب (غير مخزّنة بالجدول)."""
    db = SessionLocal()
    try:
        rows = db.query(CareerPlayer).filter(CareerPlayer.wikidata_id.isnot(None)).all()
        total = len(rows)
        log(f"🔎 إعادة حساب difficulty لـ{total} لاعب…")
        before = {}
        for r in rows:
            before[r.difficulty] = before.get(r.difficulty, 0) + 1

        changed = 0
        qids = [r.wikidata_id for r in rows]
        BATCH = 50
        for i in range(0, len(qids), BATCH):
            batch_qids = qids[i:i + BATCH]
            ents = wd_get_entities(batch_qids, props="sitelinks")
            for r in rows[i:i + BATCH]:
                ent = ents.get(r.wikidata_id, {})
                sitelinks = len(ent.get("sitelinks", {}))
                new_diff = difficulty_for(sitelinks) if sitelinks else r.difficulty
                if new_diff != r.difficulty:
                    changed += 1
                r.difficulty = new_diff
            db.commit()
            done = min(i + BATCH, total)
            log(f"   ...{done}/{total}")
            if on_progress:
                on_progress(done, total)

        after = {}
        for r in rows:
            after[r.difficulty] = after.get(r.difficulty, 0) + 1
        log(f"✅ تغيّر تصنيف {changed} لاعب | قبل={before} | بعد={after}")
        return {"total": total, "changed": changed, "before": before, "after": after}
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
