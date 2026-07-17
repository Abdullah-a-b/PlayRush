import os
import re
from fastapi import HTTPException

# SVG ممنوع لأنه XML قابل للتنفيذ (قد يحتوي JS)، وGIF ممنوع بسبب
# هجمات polyglot (GIFAR) وقنابل فك الضغط. المسموح صيغ raster ثنائية فقط.
ALLOWED_EXTENSIONS = {"jpg", "jpeg", "png", "webp"}

# التواقيع الثنائية (Magic Bytes) للصيغ المسموحة — يجب أن تطابق المحتوى
IMAGE_SIGNATURES = {
    b"\xff\xd8\xff": "jpg",
    b"\x89PNG\r\n\x1a\n": "png",
}

MAX_FILE_SIZE_BYTES = 2 * 1024 * 1024   # 2 MB
MAX_IMAGE_DIMENSIONS = 4096             # يمنع decompression bomb

UPLOAD_DIR = "uploads/avatars"
os.makedirs(UPLOAD_DIR, exist_ok=True)

# الأفاتارات الافتراضية فقط: assets/avatars/avatar_<N>.svg بدون أي رموز خاصة
DEFAULT_AVATAR_PATTERN = re.compile(r'^(?:\.\./)?assets/avatars/avatar_\d{1,3}\.svg$')
DEFAULT_AVATAR_NORMALIZED = re.compile(r'^assets/avatars/avatar_\d{1,3}\.svg$')


def validate_default_avatar_url(avatar_url: str) -> str:
    """يتحقق أن الرابط أفاتار افتراضي من قائمة المنصة ويرجع المسار المُطبَّع.

    يغلق ثغرات path traversal وXSS وSSRF في avatar_url.
    """
    if not DEFAULT_AVATAR_PATTERN.match(avatar_url):
        raise HTTPException(
            status_code=400,
            detail="رابط الأفاتار غير صالح. يجب أن يكون أفاتار افتراضي من قائمة المنصة."
        )
    normalized = avatar_url.replace("../", "")
    if not DEFAULT_AVATAR_NORMALIZED.match(normalized):
        raise HTTPException(status_code=400, detail="رابط الأفاتار غير صالح بعد التطبيع.")
    return normalized


def remove_old_avatar(path: str):
    """يمسح الأفاتار القديم بأمان ضد path traversal.

    يستخدم realpath للتأكد أن الملف فعلاً داخل uploads/avatars بعد حل
    كل الروابط الرمزية ومقاطع '..'.
    """
    if not path or not path.startswith("/uploads/"):
        return
    try:
        p = path.lstrip("/")
        abs_target = os.path.realpath(p)
        abs_uploads = os.path.realpath(UPLOAD_DIR)
        if not abs_target.startswith(abs_uploads + os.sep):
            print(f"[SECURITY] محاولة حذف ملف خارج uploads/avatars: {abs_target}")
            return
        if os.path.exists(abs_target) and os.path.isfile(abs_target):
            os.remove(abs_target)
    except Exception as e:
        print(f"cleanup error: {e}")


def validate_image_file(file_bytes: bytes, original_filename: str) -> tuple[str, bytes]:
    """التحقق الأمني الكامل من الصورة مع إعادة ترميزها.

    الفحوصات بالترتيب:
    1. حجم الملف (حد أقصى 2 MB)
    2. الامتداد ضمن القائمة البيضاء (jpg/png/webp)
    3. تطابق Magic Bytes مع المحتوى الفعلي
    4. الصورة قابلة للفتح عبر Pillow (يكشف الملفات التالفة أو الخبيثة)
    5. الأبعاد ضمن الحد (يمنع decompression bombs)
    6. إعادة الترميز من بيانات البكسل فقط — يمسح أي metadata أو حمولة
       مدفونة (EXIF خبيث، polyglot، سكربتات مضمنة)

    يرجع: (الامتداد الآمن، بايتات الصورة النظيفة)
    """
    if len(file_bytes) > MAX_FILE_SIZE_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"حجم الصورة يتجاوز الحد المسموح ({MAX_FILE_SIZE_BYTES // 1024 // 1024} MB)"
        )
    if len(file_bytes) < 8:
        raise HTTPException(status_code=400, detail="الملف تالف أو فارغ")

    ext = original_filename.rsplit(".", 1)[-1].lower() if "." in original_filename else ""
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"نوع الملف غير مسموح. الأنواع المقبولة: {', '.join(sorted(ALLOWED_EXTENSIONS))}"
        )

    detected_type = None
    for signature, img_type in IMAGE_SIGNATURES.items():
        if file_bytes[:len(signature)] == signature:
            detected_type = img_type
            break
    # لـ WebP توقيع خاص: RIFF ثم WEBP
    if detected_type is None and file_bytes[:4] == b"RIFF" and file_bytes[8:12] == b"WEBP":
        detected_type = "webp"
    if detected_type is None:
        raise HTTPException(
            status_code=400,
            detail="محتوى الملف لا يطابق أي صيغة صورة معروفة. رُفض."
        )

    normalized_ext = "jpg" if ext == "jpeg" else ext
    if normalized_ext != detected_type:
        raise HTTPException(
            status_code=400,
            detail=f"الامتداد ({ext}) لا يتطابق مع المحتوى الحقيقي ({detected_type}). رُفض."
        )

    try:
        from PIL import Image
        import io
    except ImportError:
        # بدون Pillow تحمينا المراحل 1-3 فقط
        print("[SECURITY] Pillow غير مثبت — لن نتمكن من فحص الأبعاد أو إعادة الترميز")
        return detected_type, file_bytes

    try:
        img = Image.open(io.BytesIO(file_bytes))
        img.verify()
    except Exception:
        raise HTTPException(status_code=400, detail="الصورة تالفة أو خبيثة. رُفضت.")

    # نفتحها ثانية لأن verify() يقفل كائن الصورة
    try:
        img = Image.open(io.BytesIO(file_bytes))
        width, height = img.size
    except Exception:
        raise HTTPException(status_code=400, detail="فشل قراءة أبعاد الصورة.")

    if width > MAX_IMAGE_DIMENSIONS or height > MAX_IMAGE_DIMENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"أبعاد الصورة كبيرة جداً (الحد {MAX_IMAGE_DIMENSIONS}×{MAX_IMAGE_DIMENSIONS}). رُفضت."
        )
    if width < 16 or height < 16:
        raise HTTPException(status_code=400, detail="أبعاد الصورة صغيرة جداً.")

    output = io.BytesIO()
    save_format_map = {"jpg": "JPEG", "png": "PNG", "webp": "WEBP"}
    save_format = save_format_map[detected_type]

    if detected_type == "jpg" and img.mode in ("RGBA", "LA", "P"):
        background = Image.new("RGB", img.size, (255, 255, 255))
        if img.mode == "P":
            img = img.convert("RGBA")
        background.paste(img, mask=img.split()[-1] if img.mode in ("RGBA", "LA") else None)
        img = background
    elif detected_type == "jpg" and img.mode != "RGB":
        img = img.convert("RGB")

    save_kwargs = {}
    if save_format == "JPEG":
        save_kwargs = {"quality": 85, "optimize": True}
    elif save_format == "PNG":
        save_kwargs = {"optimize": True}
    elif save_format == "WEBP":
        save_kwargs = {"quality": 85, "method": 4}

    try:
        img.save(output, format=save_format, **save_kwargs)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"فشل معالجة الصورة: {e}")

    return detected_type, output.getvalue()
