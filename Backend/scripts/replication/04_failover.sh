#!/bin/bash
# ==========================================
# 04_failover.sh — تحويل الـ Standby لـ Primary (طوارئ!)
# ==========================================
# يُستخدم فقط إذا الـ Primary سقط ولن يعود قريباً.
#
# ⚠️ خطر: بعد تشغيل هذا، الـ standby يصبح primary جديد.
# الـ primary القديم لا يقدر يرجع للـ replication بدون reset كامل.
#
# الاستخدام (على VPS 2):
#   chmod +x 04_failover.sh
#   sudo ./04_failover.sh

set -e

if [ "$EUID" -ne 0 ]; then
    echo "❌ لازم sudo"
    exit 1
fi

PG_VERSION="${PG_VERSION:-15}"

echo "⚠️ ⚠️ ⚠️  FAILOVER ⚠️ ⚠️ ⚠️"
echo ""
echo "هذا سيرفع الـ Standby ليكون Primary جديد."
echo "الـ Primary القديم لن يقدر يرجع للـ replication بدون reset."
echo ""
read -p "اكتب 'PROMOTE' للمتابعة: " CONFIRM
if [ "$CONFIRM" != "PROMOTE" ]; then
    echo "🛑 ألغيت العملية"
    exit 0
fi

# ==========================================
# 1. التحقق إن السيرفر فعلاً standby
# ==========================================
IS_REPLICA=$(sudo -u postgres psql -t -c "SELECT pg_is_in_recovery();" | tr -d ' ')
if [ "$IS_REPLICA" != "t" ]; then
    echo "❌ هذا السيرفر ليس standby (pg_is_in_recovery() = $IS_REPLICA)"
    echo "ربما تم promotion من قبل، أو هذا السيرفر primary أصلاً"
    exit 1
fi

# ==========================================
# 2. Promote
# ==========================================
echo "🔄 جاري الترقية..."
sudo -u postgres psql -c "SELECT pg_promote();"

# ==========================================
# 3. انتظر حتى يكتمل
# ==========================================
echo "⏳ انتظار اكتمال الـ promotion..."
for i in {1..30}; do
    IS_REPLICA=$(sudo -u postgres psql -t -c "SELECT pg_is_in_recovery();" 2>/dev/null | tr -d ' ' || echo "error")
    if [ "$IS_REPLICA" = "f" ]; then
        echo "✅ تم! السيرفر الآن Primary"
        break
    fi
    sleep 1
done

if [ "$IS_REPLICA" != "f" ]; then
    echo "❌ فشل الـ promotion (لا زال recovery=true بعد 30 ثانية)"
    exit 1
fi

# ==========================================
# 4. تحديث pg_hba.conf للسماح للـ replication الجديد
# ==========================================
echo ""
echo "📝 خطوات تالية يدوية:"
echo ""
echo "1️⃣  حدّث الـ app config ليستخدم هذا السيرفر كـ primary:"
echo "    DATABASE_URL=postgresql://playrush_app:PASS@$(hostname -I | awk '{print $1}'):5432/playrush_db"
echo ""
echo "2️⃣  لما الـ primary القديم يرجع، يجب re-init كـ standby جديد:"
echo "    rm -rf /var/lib/postgresql/${PG_VERSION}/main/*"
echo "    pg_basebackup -h $(hostname -I | awk '{print $1}') -U replicator -D /var/lib/postgresql/${PG_VERSION}/main -X stream -P -R -C -S 'standby_slot_old'"
echo ""
echo "3️⃣  تأكد من الـ DNS / Load Balancer أن يشير للـ IP الجديد"
