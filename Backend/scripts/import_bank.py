import json
import os
import sys
from sqlalchemy.orm import Session
# هذا السطر السحري يخبر بايثون أن يقرأ المجلد الرئيسي (Backend) تلقائياً
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# الآن ضع استيراداتك هنا
from app.core.database import engine
from app.models.user import Question # (تأكد من مسار واسم الكلاس لديك)

def import_questions_from_json(filename="new_questions.json"):
    filepath = os.path.join(os.path.dirname(__file__), filename)
    
    if not os.path.exists(filepath):
        print(f"❌ الملف {filename} غير موجود!")
        return

    db = Session(bind=engine)
    
    with open(filepath, 'r', encoding='utf-8') as f:
        data = json.load(f)
        
    added = 0
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
            
    db.commit()
    db.close()
    
    print(f"🎉 تم استيراد {added} أسئلة جديدة إلى قاعدة البيانات في لمح البصر!")

if __name__ == "__main__":
    import_questions_from_json()