# Payments Domain

نطاق محجوز للمدفوعات. لا توجد وظيفة بطولات في المشروع الحالي،
لذلك الحزمة فارغة عمداً — لم يُكتب أي كود وهمي.

عند التنفيذ، اتبع نفس نمط بقية النطاقات:

    payments/
      models.py       جداول SQLAlchemy
      repository.py   الوصول الوحيد لقاعدة البيانات
      service.py      منطق الأعمال
      router.py       HTTP Controllers (بلا وصول مباشر للقاعدة)
      sockets.py      أحداث WebSocket إن لزم

ثم سجّل الـ router في app/main.py والنماذج في
app/infrastructure/database.py داخل register_models().
