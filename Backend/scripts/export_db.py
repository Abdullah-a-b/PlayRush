import sqlite3
import json
import os

def export_all_data():
    # 1. تحديد مسار قاعدة البيانات بدقة
    db_path = os.path.join(os.path.dirname(__file__), 'users.db')
    
    if not os.path.exists(db_path):
        print("❌ قاعدة البيانات users.db غير موجودة في مجلد Backend!")
        return

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    print("🔍 جاري استخراج جميع الأسئلة...")
    
    try:
        # 2. جلب كل الأسئلة
        cursor.execute("SELECT id, game_mode, question_text, correct_answer, category, extra_data FROM questions")
        rows = cursor.fetchall()
        
        # 3. تجميع الأسئلة بشكل ذكي (كل طور في قائمة منفصلة)
        questions_by_mode = {}
        
        for row in rows:
            q_id, mode, text, answer, category, extra = row
            
            # إذا كان الطور غير موجود في القاموس، قم بإنشائه
            if mode not in questions_by_mode:
                questions_by_mode[mode] = []
                
            # تحويل البيانات الإضافية (Extra Data) إلى صيغة مقروءة
            parsed_extra = {}
            if extra:
                try:
                    parsed_extra = json.loads(extra)
                except json.JSONDecodeError:
                    parsed_extra = {"raw_text": extra}

            # إضافة السؤال للقائمة
            questions_by_mode[mode].append({
                "id": q_id,
                "category": category,
                "question": text,
                "answer": answer,
                "extra_data": parsed_extra
            })
            
        # 4. حفظ النتيجة في ملف JSON أنيق يسهل قراءته وتعديله
        output_file = os.path.join(os.path.dirname(__file__), 'all_questions_exported.json')
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(questions_by_mode, f, ensure_ascii=False, indent=4)
            
        # 5. طباعة تقرير نهائي جميل في التيرمينال
        total_questions = sum(len(q) for q in questions_by_mode.values())
        print(f"\n✅ اكتملت المهمة! تم استخراج ({total_questions}) سؤال بالكامل:")
        for mode, qs in questions_by_mode.items():
            print(f"   🎯 طور [{mode}]: {len(qs)} سؤال")
            
        print(f"\n📂 تجد جميع الأسئلة مرتبة بدقة في ملف:\n{output_file}\n")
        
    except sqlite3.Error as e:
        print(f"❌ حدث خطأ أثناء قراءة قاعدة البيانات: {e}")
    finally:
        conn.close()

if __name__ == "__main__":
    export_all_data()