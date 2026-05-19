#!/bin/bash
# ==========================================
# 03_setup_standby.sh — إعداد VPS 2 كـ Standby
# ==========================================
# يُشغّل على VPS 2 بعد تثبيت PostgreSQL
#
# الاستخدام:
#   chmod +x 03_setup_standby.sh
#   sudo ./03_setup_standby.sh <PRIMARY_IP> <REPLICATOR_PASSWORD>
#
# مثال:
#   sudo ./03_setup_standby.sh 1.2.3.4 'StrongRepPassword123'

set -e  # توقف عند أي خطأ

PRIMARY_IP="${1:-}"
REPL_PASSWORD="${2:-}"
PG_VERSION="${PG_VERSION:-15}"
PG_DATA="/var/lib/postgresql/${PG_VERSION}/main"

if [ -z "$PRIMARY_IP" ] || [ -z "$REPL_PASSWORD" ]; then
    echo "❌ الاستخدام: $0 <PRIMARY_IP> <REPLICATOR_PASSWORD>"
    exit 1
fi

if [ "$EUID" -ne 0 ]; then
    echo "❌ لازم sudo"
    exit 1
fi

echo "🔄 إعداد VPS 2 كـ Standby"
echo "   Primary IP: $PRIMARY_IP"
echo "   PG Version: $PG_VERSION"

# ==========================================
# 1. إيقاف PostgreSQL
# ==========================================
echo ""
echo "📛 إيقاف PostgreSQL..."
systemctl stop postgresql

# ==========================================
# 2. مسح الـ data directory الفارغة
# ==========================================
echo "🗑️  مسح data directory الحالية..."
rm -rf "$PG_DATA"
mkdir -p "$PG_DATA"
chown postgres:postgres "$PG_DATA"
chmod 700 "$PG_DATA"

# ==========================================
# 3. أخذ نسخة كاملة من الـ primary عبر pg_basebackup
# ==========================================
echo ""
echo "📥 جاري نسخ DB من Primary (قد يستغرق دقائق)..."
sudo -u postgres PGPASSWORD="$REPL_PASSWORD" pg_basebackup \
    -h "$PRIMARY_IP" \
    -p 5432 \
    -U replicator \
    -D "$PG_DATA" \
    -X stream \
    -P \
    -R \
    -C \
    -S "standby_slot_$(hostname -s)"

# 🔍 شرح الخيارات:
# -X stream  → ينقل WAL أثناء النسخ (يضمن consistency)
# -P         → progress bar
# -R         → ينشئ standby.signal و postgresql.auto.conf تلقائياً
# -C         → ينشئ replication slot (يحفظ WAL على primary لو standby بطيء)
# -S name    → اسم الـ slot (يجب يكون unique)

# ==========================================
# 4. تعديل postgresql.conf للـ standby
# ==========================================
echo ""
echo "⚙️  تعديل postgresql.conf للـ standby..."
PG_CONF="/etc/postgresql/${PG_VERSION}/main/postgresql.conf"

# نُمكن hot_standby (يسمح بالقراءة من standby)
sed -i "s/^#*hot_standby.*/hot_standby = on/" "$PG_CONF"

# إعدادات إضافية للـ standby
cat >> "$PG_CONF" <<EOF

# ==========================================
# Standby-specific settings
# ==========================================
hot_standby = on                       # يسمح بـ READ queries
hot_standby_feedback = on              # يبلغ primary بحالته (يمنع conflicts)
max_standby_streaming_delay = 30s      # 30 ثانية قبل قتل query على standby
wal_receiver_status_interval = 5s
EOF

# ==========================================
# 5. تشغيل PostgreSQL
# ==========================================
echo ""
echo "🚀 تشغيل PostgreSQL..."
systemctl start postgresql
sleep 3

# ==========================================
# 6. تحقق من الـ replication
# ==========================================
echo ""
echo "🔍 فحص حالة الـ replication..."
sudo -u postgres psql -c "SELECT pg_is_in_recovery();"
# يجب أن يطبع: t (true)

echo ""
echo "✅ Standby جاهز!"
echo ""
echo "📋 خطوات التأكد:"
echo "   على الـ Primary، شغّل:"
echo "     sudo -u postgres psql -c \"SELECT * FROM pg_stat_replication;\""
echo "   يجب أن ترى صف يحوي IP هذا الـ standby"
echo ""
echo "   على الـ Standby، شغّل:"
echo "     sudo -u postgres psql -c \"SELECT pg_is_in_recovery();\""
echo "   يجب أن يطبع: t"
echo ""
echo "🔬 اختبار: على primary أنشئ row جديد، تأكد إنه ظهر في standby خلال ثانيتين"
