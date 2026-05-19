#!/bin/bash
# ==========================================
# test_replication.sh — اختبار شامل للـ replication
# ==========================================
# يُشغّل دورياً (cron كل 5 دقائق) ويُنبه لو في مشكلة
#
# الاستخدام:
#   ./test_replication.sh <PRIMARY_IP> <STANDBY_IP>

set -e

PRIMARY="${1:-localhost}"
STANDBY="${2:-}"

if [ -z "$STANDBY" ]; then
    echo "الاستخدام: $0 <PRIMARY_IP> <STANDBY_IP>"
    exit 1
fi

# ==========================================
# 1. تحقق إن primary يعمل
# ==========================================
echo "🔍 فحص Primary ($PRIMARY)..."
if ! pg_isready -h "$PRIMARY" -p 5432 -q; then
    echo "❌ Primary لا يستجيب!"
    exit 2
fi
echo "✅ Primary يعمل"

# ==========================================
# 2. تحقق إن standby يعمل وفي recovery mode
# ==========================================
echo ""
echo "🔍 فحص Standby ($STANDBY)..."
if ! pg_isready -h "$STANDBY" -p 5432 -q; then
    echo "❌ Standby لا يستجيب!"
    exit 3
fi

IS_RECOVERY=$(PGPASSWORD="$DB_PASSWORD" psql -h "$STANDBY" -U playrush_app -d playrush_db -t -c "SELECT pg_is_in_recovery();" | tr -d ' ')
if [ "$IS_RECOVERY" != "t" ]; then
    echo "❌ Standby ليس في recovery mode!"
    exit 4
fi
echo "✅ Standby في recovery mode"

# ==========================================
# 3. تحقق من lag
# ==========================================
echo ""
echo "🔍 فحص الـ replication lag..."

LAG_BYTES=$(PGPASSWORD="$DB_PASSWORD" psql -h "$PRIMARY" -U playrush_app -d playrush_db -t -c "
SELECT COALESCE(MAX(pg_wal_lsn_diff(sent_lsn, replay_lsn)), 0)
FROM pg_stat_replication;
" | tr -d ' ')

LAG_SECONDS=$(PGPASSWORD="$DB_PASSWORD" psql -h "$STANDBY" -U playrush_app -d playrush_db -t -c "
SELECT EXTRACT(EPOCH FROM (now() - pg_last_xact_replay_timestamp()))::int;
" | tr -d ' ')

echo "   Lag bytes:   $LAG_BYTES"
echo "   Lag seconds: ${LAG_SECONDS}s"

# تنبيه لو lag كبير
THRESHOLD_SEC=60
if [ "$LAG_SECONDS" -gt "$THRESHOLD_SEC" ] 2>/dev/null; then
    echo "⚠️ تحذير: Lag تجاوز $THRESHOLD_SEC ثانية"
    exit 5
fi

# ==========================================
# 4. اختبار write على primary + read من standby
# ==========================================
echo ""
echo "🔬 اختبار write/read..."

TEST_VALUE="repl_test_$(date +%s)"
PGPASSWORD="$DB_PASSWORD" psql -h "$PRIMARY" -U playrush_app -d playrush_db -c "
CREATE TABLE IF NOT EXISTS _replication_test (id SERIAL PRIMARY KEY, val TEXT, ts TIMESTAMP DEFAULT NOW());
INSERT INTO _replication_test (val) VALUES ('$TEST_VALUE');
" > /dev/null

# انتظر 3 ثواني
sleep 3

# اقرأ من standby
FOUND=$(PGPASSWORD="$DB_PASSWORD" psql -h "$STANDBY" -U playrush_app -d playrush_db -t -c "
SELECT COUNT(*) FROM _replication_test WHERE val = '$TEST_VALUE';
" | tr -d ' ')

if [ "$FOUND" != "1" ]; then
    echo "❌ القيمة المكتوبة على primary لم تظهر في standby!"
    exit 6
fi
echo "✅ Write/Read يعمل عبر replication"

# تنظيف
PGPASSWORD="$DB_PASSWORD" psql -h "$PRIMARY" -U playrush_app -d playrush_db -c "
DELETE FROM _replication_test WHERE val = '$TEST_VALUE';
" > /dev/null

echo ""
echo "🎉 Replication صحي 100%"
