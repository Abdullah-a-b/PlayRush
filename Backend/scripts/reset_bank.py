from sqlalchemy.orm import Session
from Backend.app.core.database import engine, Question

def wipe_questions_table():
    print("⚠️ تحذير: جاري مسح جميع الأسئلة القديمة من قاعدة البيانات...")
    
    db = Session(bind=engine)
    try:
        # حذف جميع الصفوف في جدول الأسئلة
        deleted_count = db.query(Question).delete()
        db.commit()
        
        print(f"✅ تم التطهير بنجاح! تم مسح ({deleted_count}) سؤال معطوب.")
        print("🚀 قاعدة البيانات الآن نظيفة وجاهزة لاستقبال الأسئلة الجديدة.")
        
    except Exception as e:
        db.rollback()
        print(f"❌ حدث خطأ أثناء المسح: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    # طلب تأكيد من المطور لكي لا يمسح البيانات بالخطأ
    confirm = input("هل أنت متأكد أنك تريد مسح بنك الأسئلة بالكامل؟ (y/n): ")
    if confirm.lower() == 'y':
        wipe_questions_table()
    else:
        print("تم الإلغاء.")