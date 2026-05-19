# 🛡️ دليل الإعداد الشامل: PostgreSQL Replication + Backups

> **هدف:** حماية مزدوجة لـ DB (streaming replica + scheduled backups)
> **بيئة:** 2 VPSs على Linux Ubuntu 22.04+
> **Replication:** Async (RPO ≈ ثوانٍ)

---

## 📊 البنية النهائية

```
┌─────────────────────────────────┐         ┌─────────────────────────────────┐
│  VPS 1 (App + Primary)          │         │  VPS 2 (Standby + Backups)      │
│                                  │         │                                  │
│  • FastAPI app (port 8000)       │ Stream  │  • PostgreSQL Standby           │
│  • PostgreSQL Primary            │ ─WAL──▶ │    (READ ONLY)                  │
│    (READ + WRITE)                │         │                                  │
│  • Telegram bot                  │         │  • pg_dump كل ساعة             │
│  • Cron jobs                     │         │  • Sync لـ S3/B2 يومياً        │
└─────────────────────────────────┘         └─────────────────────────────────┘
                                                         │
                                                         ▼
                                              ┌─────────────────────┐
                                              │  Offsite Storage    │
                                              │  (S3 / Backblaze)   │
                                              └─────────────────────┘
```

---

## 📋 المرحلة 1: تثبيت PostgreSQL على الـ VPSs الاثنين

على **كل** VPS:

```bash
# Ubuntu 22.04
sudo apt update
sudo apt install -y postgresql-15 postgresql-client-15 postgresql-contrib-15

# تأكد إنه شغّال
sudo systemctl status postgresql
```

**اختبار:**
```bash
sudo -u postgres psql -c "SELECT version();"
```

---

## 📋 المرحلة 2: إعداد Primary (VPS 1)

### 2.1. إنشاء DB والمستخدمين

```bash
sudo -u postgres psql <<EOF
-- DB
CREATE DATABASE playrush_db;

-- مستخدم الـ app (قراءة + كتابة)
CREATE USER playrush_app WITH PASSWORD 'CHANGE_ME_STRONG_PASS_1';
GRANT ALL PRIVILEGES ON DATABASE playrush_db TO playrush_app;

-- مستخدم الـ replication (للـ standby فقط)
CREATE USER replicator WITH REPLICATION ENCRYPTED PASSWORD 'CHANGE_ME_STRONG_PASS_2';

-- مستخدم backup (read only)
CREATE USER backup_user WITH PASSWORD 'CHANGE_ME_STRONG_PASS_3';
GRANT CONNECT ON DATABASE playrush_db TO backup_user;

-- اعطاء صلاحيات للـ schema بعد الإنشاء
\c playrush_db
GRANT USAGE ON SCHEMA public TO playrush_app;
GRANT ALL ON SCHEMA public TO playrush_app;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO playrush_app;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON SEQUENCES TO playrush_app;

-- صلاحيات backup_user
GRANT USAGE ON SCHEMA public TO backup_user;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO backup_user;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO backup_user;
EOF
```

⚠️ **استبدل `CHANGE_ME_STRONG_PASS_X` بـ passwords قوية حقيقية.** استخدم:
```bash
openssl rand -base64 32  # ينتج password عشوائي قوي
```

### 2.2. تطبيق `postgresql.conf`

انسخ المحتوى من `01_primary_postgresql.conf` إلى:
```bash
sudo nano /etc/postgresql/15/main/postgresql.conf
```

**القيم المهمة (الباقي يبقى default):**
- `listen_addresses = '*'`
- `wal_level = replica`
- `max_wal_senders = 5`
- `max_replication_slots = 5`
- `wal_keep_size = 1GB`
- `archive_mode = on`

### 2.3. إنشاء مجلد archive

```bash
sudo mkdir -p /var/lib/postgresql/wal_archive
sudo chown postgres:postgres /var/lib/postgresql/wal_archive
sudo chmod 700 /var/lib/postgresql/wal_archive
```

### 2.4. تطبيق `pg_hba.conf`

```bash
sudo nano /etc/postgresql/15/main/pg_hba.conf
```

أضف (استبدل `<STANDBY_IP>` بـ IP الحقيقي للـ VPS 2):

```
host    playrush_db     playrush_app    127.0.0.1/32       scram-sha-256
host    replication     replicator      <STANDBY_IP>/32    scram-sha-256
```

### 2.5. إعادة تشغيل PostgreSQL

```bash
sudo systemctl restart postgresql
sudo systemctl status postgresql  # تأكد من نجاح التشغيل
```

### 2.6. ضبط Firewall (UFW)

```bash
# اسمح بـ standby فقط
sudo ufw allow from <STANDBY_IP> to any port 5432

# لو الـ app على VPS منفصل
sudo ufw allow from <APP_VPS_IP> to any port 5432

# تأكد ما تفتح 5432 للعالم
sudo ufw status
```

---

## 📋 المرحلة 3: إعداد Standby (VPS 2)

### 3.1. انسخ سكريبت الإعداد

```bash
scp 03_setup_standby.sh root@<STANDBY_IP>:/root/
ssh root@<STANDBY_IP>
chmod +x /root/03_setup_standby.sh
```

### 3.2. شغّل السكريبت

```bash
sudo ./03_setup_standby.sh <PRIMARY_IP> 'CHANGE_ME_STRONG_PASS_2'
# مثال:
# sudo ./03_setup_standby.sh 1.2.3.4 'mY$ecurePassword123'
```

السكريبت يقوم بـ:
1. إيقاف PostgreSQL
2. مسح data directory الفارغة
3. `pg_basebackup` من الـ primary (نسخة كاملة + replication slot)
4. تفعيل `hot_standby` في postgresql.conf
5. إعادة تشغيل PostgreSQL

### 3.3. تأكد من نجاح الـ replication

**على Primary:**
```bash
sudo -u postgres psql -c "SELECT * FROM pg_stat_replication;"
```
يجب أن ترى صف بـ:
- `client_addr` = IP الـ standby
- `state` = `streaming`
- `sync_state` = `async`

**على Standby:**
```bash
sudo -u postgres psql -c "SELECT pg_is_in_recovery();"
# يطبع: t (true)
```

### 3.4. اختبار حقيقي

**على Primary:**
```bash
sudo -u postgres psql -d playrush_db -c "
CREATE TABLE IF NOT EXISTS _test (id SERIAL, val TEXT);
INSERT INTO _test (val) VALUES ('hello from primary');
"
```

**على Standby (بعد ثانية):**
```bash
sudo -u postgres psql -d playrush_db -c "SELECT * FROM _test;"
# يجب أن ترى الصف الجديد
```

✅ **لو ظهر = الـ replication يعمل!**

---

## 📋 المرحلة 4: ربط الـ App بالـ Primary + Replica

### 4.1. عدّل `.env` على VPS 1 (حيث الـ app)

```env
# Primary (للكتابة + القراءات الحرجة)
DATABASE_URL=postgresql://playrush_app:CHANGE_ME_STRONG_PASS_1@localhost:5432/playrush_db

# Replica (للقراءات الثقيلة فقط)
DATABASE_URL_REPLICA=postgresql://playrush_app:CHANGE_ME_STRONG_PASS_1@<STANDBY_IP>:5432/playrush_db
```

### 4.2. تأكد إن الـ app يستخدم الـ replica في endpoints محددة

افتح `app/api/auth.py` (مثلاً) وعدّل الـ endpoints الثقيلة:

```python
# قبل
@router.get("/me")
async def get_my_profile(current_user: User = Depends(get_current_user),
                         db: Session = Depends(get_db)):
    ...

# بعد (استخدم replica)
from app.core.database import get_db_replica

@router.get("/me")
async def get_my_profile(current_user: User = Depends(get_current_user),
                         db: Session = Depends(get_db_replica)):  # ← replica
    ...
```

⚠️ **انتبه:** لا تستخدم replica في endpoints تكتب (login, register, إلخ). فقط القراءات.

---

## 📋 المرحلة 5: إعداد Backups المجدولة (على VPS 2)

### 5.1. اختبار يدوي أولاً

```bash
cd /home/playrush/PlayRush/Backend
source venv/bin/activate
python -m scripts.backup_db --tag manual
ls -la backups/
```

### 5.2. تثبيت Systemd Timers

```bash
cd Backend/scripts/replication

# تأكد من المسارات في الملفات
sudo nano playrush-backup-hourly.service  # عدّل WorkingDirectory و ExecStart
sudo nano playrush-backup-daily.service

# انسخ
sudo cp playrush-backup-hourly.service /etc/systemd/system/
sudo cp playrush-backup-hourly.timer /etc/systemd/system/
sudo cp playrush-backup-daily.service /etc/systemd/system/

# الـ timer للـ daily (المحتوى داخل ملف playrush-backup-daily.service بعد التعليق)
# انسخه لملف منفصل /etc/systemd/system/playrush-backup-daily.timer

sudo systemctl daemon-reload
sudo systemctl enable --now playrush-backup-hourly.timer
sudo systemctl enable --now playrush-backup-daily.timer

# تحقق
sudo systemctl list-timers playrush-backup-*
```

### 5.3. بديل بسيط: cron

لو ما تبي systemd:

```bash
crontab -e
# أضف:
0 * * * * cd /home/playrush/PlayRush/Backend && /home/playrush/venv/bin/python -m scripts.backup_db --tag hourly >> /var/log/playrush_backup.log 2>&1
0 3 * * * cd /home/playrush/PlayRush/Backend && /home/playrush/venv/bin/python -m scripts.backup_db --tag daily >> /var/log/playrush_backup.log 2>&1
```

---

## 📋 المرحلة 6: Offsite Backups (يومياً)

### 6.1. ثبّت rclone (الأكثر مرونة)

```bash
curl https://rclone.org/install.sh | sudo bash
rclone config  # تابع الخطوات لإضافة Google Drive / S3 / B2
```

### 6.2. أضف لـ cron

```bash
crontab -e
# يومياً 4 صباحاً (بعد ساعة من الـ daily backup المحلي)
0 4 * * * cd /home/playrush/PlayRush/Backend/scripts/replication && OFFSITE_PROVIDER=rclone RCLONE_REMOTE='gdrive:playrush-backups' ./upload_to_offsite.sh >> /var/log/offsite_backup.log 2>&1
```

---

## 📋 المرحلة 7: Monitoring + Alerts

### 7.1. اختبار replication دوري

```bash
# على VPS 2 (لأن عنده الـ app)
crontab -e
# كل 5 دقائق
*/5 * * * * DB_PASSWORD='CHANGE_ME_STRONG_PASS_1' /home/playrush/PlayRush/Backend/scripts/replication/test_replication.sh <PRIMARY_IP> <STANDBY_IP> >> /var/log/replication_check.log 2>&1
```

### 7.2. تنبيه لو فشل

أضف في الـ cron line آخره:
```bash
... || curl -X POST 'https://api.telegram.org/bot<TOKEN>/sendMessage' -d 'chat_id=<CHAT>&text=⚠️ Replication broken!'
```

---

## 🆘 سيناريوهات الكوارث

### السيناريو 1: Primary سقط (corruption / hardware failure)

1. **أكّد أنه فعلاً down ولن يعود قريباً:**
   ```bash
   pg_isready -h <PRIMARY_IP> -p 5432
   ```

2. **رقّي Standby ليكون Primary:**
   ```bash
   ssh root@<STANDBY_IP>
   cd /home/playrush/PlayRush/Backend/scripts/replication
   sudo ./04_failover.sh
   ```

3. **حدّث `.env` على VPS 1 (لو رجع):**
   ```env
   DATABASE_URL=postgresql://playrush_app:PASS@<NEW_PRIMARY_IP>:5432/playrush_db
   # احذف DATABASE_URL_REPLICA حالياً
   ```

4. **أعد تشغيل الـ app:**
   ```bash
   sudo systemctl restart playrush
   ```

5. **لاحقاً: حول الـ primary القديم لـ standby جديد** (re-init كامل)

### السيناريو 2: DB مخربة (logical corruption)

1. **استورد من backup حديث:**
   ```bash
   python -m scripts.restore_db --list  # شوف المتاح
   python -m scripts.restore_db --file backups/playrush_hourly_<recent>.sql.gz
   ```

2. **لو الـ replica مخربة معها** (مثلاً DELETE خاطئ بُث للـ replica):
   - استورد على standby أولاً:
     ```bash
     python -m scripts.restore_db --file ... --to-db postgresql://...@<STANDBY>/playrush_db
     ```
   - استورد على primary ثانياً
   - قد تحتاج re-init الـ replication

### السيناريو 3: VPS 1 سقط كلياً

1. على VPS 2: شغّل failover
2. ثبّت الـ app على VPS 2 مؤقتاً
3. وجّه DNS لـ VPS 2

---

## 🔬 اختبار شامل

قبل الإنتاج، **اختبر كل سيناريوهات الكوارث**:

- [ ] إنشاء row على primary، يظهر في standby خلال ثانية
- [ ] backup يومي يُنشأ تلقائياً وقابل للقراءة
- [ ] restore على DB تجريبية يعمل
- [ ] failover من primary لـ standby خلال دقيقة
- [ ] الـ app يتصل بـ replica للـ /me
- [ ] Offsite backup يصل لـ S3/Drive
- [ ] firewall يرفض اتصالات من IPs غريبة

---

## 📚 موارد إضافية

- PostgreSQL Streaming Replication: https://www.postgresql.org/docs/15/warm-standby.html
- pg_basebackup docs: https://www.postgresql.org/docs/15/app-pgbasebackup.html
- pgBouncer (لاحقاً للـ connection pooling): https://www.pgbouncer.org/

---

## ⚠️ ملاحظات أمنية

1. **passwords قوية وعشوائية** — استخدم `openssl rand -base64 32`
2. **firewall محكم** — افتح 5432 فقط للـ IPs المعروفة
3. **`.env` محمي** — `chmod 600 .env`
4. **SSH key only** — عطّل password login
5. **Updates تلقائية** — `sudo apt install unattended-upgrades`
6. **Backups مشفرة** — اشتغل لاحقاً مع `gpg --encrypt`
7. **اختبر استعادة backup شهرياً** — backup غير مُختبر = backup غير موجود

---

## 🎯 ترتيب الأولويات

لو وقتك محدود، الأهم بالترتيب:

1. ✅ **Primary + Backups محلية** (60 دقيقة) — حماية أساسية
2. ✅ **Offsite backups** (30 دقيقة) — حماية من سقوط VPS
3. ⚠️ **Standby + replication** (90 دقيقة) — failover سريع
4. 📊 **Monitoring** (30 دقيقة) — اكتشاف المشاكل قبل تفاقمها

التطبيق الكامل: ~3-4 ساعات لمهندس متمرس.
