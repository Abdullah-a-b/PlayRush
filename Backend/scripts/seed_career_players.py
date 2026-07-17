"""
 بذور بيانات 'مسيرة لاعب' — لاعبون تجريبيون للاختبار.

التشغيل: python scripts/seed_career_players.py
يملأ جدول career_players ببيانات أولية. لاحقاً تُوسّع عبر Wikidata.

ملاحظة: الشعارات (logo) أسماء ملفات في FrontEnd/assets/clubs/.
لو الشعار غير موجود، الواجهة تعرض اسم النادي فقط (fallback آمن).
"""
import os
import sys
import json

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.infrastructure.database import SessionLocal
from app.domains.games.models import CareerPlayer


# بيانات تجريبية — لاعبون مشهورون (سهل تخمينهم للاختبار)
PLAYERS = [
    {
        "name": "كريستيانو رونالدو", "status": "current", "difficulty": "easy",
        "nationality": "البرتغال",
        "clubs": [
            {"name": "سبورتنغ لشبونة", "logo": "sporting.png"},
            {"name": "مانشستر يونايتد", "logo": "manutd.png"},
            {"name": "ريال مدريد", "logo": "realmadrid.png"},
            {"name": "يوفنتوس", "logo": "juventus.png"},
            {"name": "مانشستر يونايتد", "logo": "manutd.png"},
            {"name": "النصر", "logo": "alnassr.png"},
        ],
        "accepted_answers": ["كريستيانو", "رونالدو", "كريستيانو رونالدو", "cristiano", "ronaldo", "cr7"],
    },
    {
        "name": "ليونيل ميسي", "status": "current", "difficulty": "easy",
        "nationality": "الأرجنتين",
        "clubs": [
            {"name": "برشلونة", "logo": "barcelona.png"},
            {"name": "باريس سان جيرمان", "logo": "psg.png"},
            {"name": "إنتر ميامي", "logo": "intermiami.png"},
        ],
        "accepted_answers": ["ميسي", "ليونيل ميسي", "messi", "leo messi", "ليو ميسي"],
    },
    {
        "name": "محمد صلاح", "status": "current", "difficulty": "easy",
        "nationality": "مصر",
        "clubs": [
            {"name": "المقاولون العرب", "logo": "arabcontractors.png"},
            {"name": "بازل", "logo": "basel.png"},
            {"name": "تشيلسي", "logo": "chelsea.png"},
            {"name": "فيورنتينا", "logo": "fiorentina.png"},
            {"name": "روما", "logo": "roma.png"},
            {"name": "ليفربول", "logo": "liverpool.png"},
        ],
        "accepted_answers": ["صلاح", "محمد صلاح", "mo salah", "salah", "mohamed salah"],
    },
    {
        "name": "زين الدين زيدان", "status": "retired", "difficulty": "medium",
        "nationality": "فرنسا",
        "clubs": [
            {"name": "كان", "logo": "cannes.png"},
            {"name": "بوردو", "logo": "bordeaux.png"},
            {"name": "يوفنتوس", "logo": "juventus.png"},
            {"name": "ريال مدريد", "logo": "realmadrid.png"},
        ],
        "accepted_answers": ["زيدان", "زين الدين زيدان", "zidane", "zizou"],
    },
    {
        "name": "رونالدينيو", "status": "retired", "difficulty": "medium",
        "nationality": "البرازيل",
        "clubs": [
            {"name": "غريميو", "logo": "gremio.png"},
            {"name": "باريس سان جيرمان", "logo": "psg.png"},
            {"name": "برشلونة", "logo": "barcelona.png"},
            {"name": "ميلان", "logo": "milan.png"},
        ],
        "accepted_answers": ["رونالدينيو", "ronaldinho", "رونالدينهو"],
    },
    {
        "name": "فرانشيسكو توتي", "status": "retired", "difficulty": "hard",
        "nationality": "إيطاليا",
        "clubs": [
            {"name": "روما", "logo": "roma.png"},
        ],
        "accepted_answers": ["توتي", "فرانشيسكو توتي", "totti"],
    },
]


def main():
    db = SessionLocal()
    try:
        added = skipped = 0
        for p in PLAYERS:
            existing = db.query(CareerPlayer).filter(CareerPlayer.name == p["name"]).first()
            if existing:
                skipped += 1
                continue
            cp = CareerPlayer(
                name=p["name"],
                status=p["status"],
                difficulty=p.get("difficulty", "medium"),
                nationality=p.get("nationality"),
                clubs=json.dumps(p["clubs"], ensure_ascii=False),
                accepted_answers=json.dumps(p["accepted_answers"], ensure_ascii=False),
                active=True,
            )
            db.add(cp)
            added += 1
        db.commit()
        print(f" أُضيف {added} لاعب | ⏭ متخطّى {skipped} (موجود مسبقاً)")
        total = db.query(CareerPlayer).count()
        print(f" إجمالي اللاعبين في القاعدة: {total}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
