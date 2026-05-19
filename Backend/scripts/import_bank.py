"""
سكربت لاستيراد الأسئلة من new_questions.json إلى قاعدة البيانات الحالية.

طريقة الاستخدام:
    cd Backend
    python -m scripts.import_bank

(يجب التشغيل من مجلد Backend/ ليجد الـ imports)
"""
import json
import os
import sys

# نضيف مجلد Backend للـ Python path عشان نقدر نستورد app.*
BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

# 🔑 تحميل .env عشان DATABASE_URL يصل لـ database.py
from dotenv import load_dotenv
env_path = os.path.join(BACKEND_DIR, ".env")
if os.path.exists(env_path):
    load_dotenv(env_path)
    print(f"✅ تم تحميل: {env_path}")

from sqlalchemy.orm import Session
from app.core.database import engine, Question

def import_questions_from_json(filename="new_questions.json"):
    filepath = os.path.join(os.path.dirname(__file__), filename)

    if not os.path.exists(filepath):
        print(f"❌ الملف {filename} غير موجود!")
        return

    db = Session(bind=engine)

    # ✅ نطبع DB المستخدمة عشان نتأكد
    print(f"📊 DB: {engine.url.render_as_string(hide_password=True)}")

    with open(filepath, 'r', encoding='utf-8') as f:
        data = json.load(f)

    print(f"📖 تم قراءة {len(data)} سؤال من الملف")

    added = 0
    skipped = 0
    for item in data:
        # التحقق من عدم التكرار
        exists = db.query(Question).filter(
            Question.game_mode == item['game_mode'],
            Question.correct_answer == item['answer']
        ).first()

        if not exists:
            new_q = Question(
                game_mode=item['game_mode'],
                question_text=item['question'],
                correct_answer=item['answer'],
                category=item['category'],
                extra_data=json.dumps(item.get('extra_data', {}), ensure_ascii=False)
            )
            db.add(new_q)
            added += 1
        else:
            skipped += 1

    db.commit()
    db.close()

    print(f"🎉 تم استيراد {added} سؤال جديد إلى قاعدة البيانات!")
    if skipped:
        print(f"⏭️  تم تخطي {skipped} سؤال (موجود مسبقاً)")

if __name__ == "__main__":
    import_questions_from_json()