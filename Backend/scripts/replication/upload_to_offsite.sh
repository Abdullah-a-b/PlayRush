#!/bin/bash
# ==========================================
# upload_to_offsite.sh — رفع backups للحماية من سقوط VPSs
# ==========================================
# يدعم: AWS S3, Backblaze B2, rclone (يدعم 40+ provider)
#
# الاستخدام:
#   1. اختر مزود
#   2. ضع credentials في environment أو ملف منفصل
#   3. شغّل: ./upload_to_offsite.sh
#
# 💡 منصوح به: rclone — يدعم Google Drive, OneDrive, Dropbox, S3, إلخ

set -e

BACKEND_DIR="${BACKEND_DIR:-/home/playrush/PlayRush/Backend}"
LOCAL_DIR="$BACKEND_DIR/backups"
RETENTION_DAYS="${RETENTION_DAYS:-30}"  # احتفظ بـ 30 يوم في offsite

# ==========================================
# الخيار A: AWS S3 (اللاعب الأكبر)
# ==========================================
upload_s3() {
    if ! command -v aws &> /dev/null; then
        echo "❌ aws cli غير مثبت. تثبيت:"
        echo "   curl 'https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip' -o awscli.zip"
        echo "   unzip awscli.zip && sudo ./aws/install"
        return 1
    fi

    # Credentials من ~/.aws/credentials أو env vars
    BUCKET="${S3_BUCKET:-playrush-backups}"
    PREFIX="db-backups"

    echo "📤 رفع لـ s3://$BUCKET/$PREFIX/"
    aws s3 sync "$LOCAL_DIR" "s3://$BUCKET/$PREFIX/" \
        --exclude "*" --include "*.sql.gz" \
        --storage-class STANDARD_IA  # cheaper than STANDARD

    # حذف القديم في S3 (يحتاج lifecycle policy في S3 — أسهل من سكريبت)
    echo "💡 تذكير: ضع S3 Lifecycle Policy لحذف files أقدم من $RETENTION_DAYS يوم"
}

# ==========================================
# الخيار B: Backblaze B2 (أرخص بكثير من S3)
# ==========================================
upload_b2() {
    if ! command -v b2 &> /dev/null; then
        echo "❌ b2 cli غير مثبت. تثبيت:"
        echo "   pip install b2"
        return 1
    fi

    BUCKET="${B2_BUCKET:-playrush-backups}"

    echo "📤 رفع لـ b2://$BUCKET/"
    b2 sync --exclude "*" --include "*.sql.gz" "$LOCAL_DIR" "b2://$BUCKET/"
}

# ==========================================
# الخيار C: rclone (الأكثر مرونة)
# ==========================================
upload_rclone() {
    if ! command -v rclone &> /dev/null; then
        echo "❌ rclone غير مثبت. تثبيت:"
        echo "   curl https://rclone.org/install.sh | sudo bash"
        echo "   ثم: rclone config (لإعداد المزود)"
        return 1
    fi

    REMOTE="${RCLONE_REMOTE:-gdrive:playrush-backups}"

    echo "📤 رفع لـ $REMOTE"
    rclone sync "$LOCAL_DIR" "$REMOTE" \
        --include "*.sql.gz" \
        --transfers 2 \
        --checksum

    # rclone يدعم retention تلقائياً
    rclone delete "$REMOTE" --min-age "${RETENTION_DAYS}d" --include "*.sql.gz"
}

# ==========================================
# اختر المزود
# ==========================================
PROVIDER="${OFFSITE_PROVIDER:-rclone}"

case "$PROVIDER" in
    s3)      upload_s3 ;;
    b2)      upload_b2 ;;
    rclone)  upload_rclone ;;
    *)
        echo "❌ مزود غير معروف: $PROVIDER"
        echo "   اضبط OFFSITE_PROVIDER=s3|b2|rclone"
        exit 1
        ;;
esac

echo "✅ Offsite backup مكتمل"
