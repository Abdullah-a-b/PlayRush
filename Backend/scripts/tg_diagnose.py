"""
تشخيص بوت تليجرام — شغّله من داخل مجلد Backend:  python tg_diagnose.py

يخبرك بالضبط أين المشكلة:
  1) التوكن صالح؟ (getMe)
  2) هل يوجد webhook يمنع getUpdates؟ (getWebhookInfo)
  3) يحذف الـ webhook (deleteWebhook)
  4) هل getUpdates يشتغل أم يرجّع 409 (سيرفر آخر يسحب نفس التوكن)؟

مهم: أوقف السيرفر المنشور وأي نسخة أخرى قبل التشغيل، وإلا سترى 409.
"""
import os
import sys
import requests

try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

TOKEN = os.environ.get("TELEGRAM_TOKEN")
BASE = f"https://api.telegram.org/bot{TOKEN}"


def line():
    print("-" * 60)


def main():
    if not TOKEN:
        print("❌ TELEGRAM_TOKEN غير موجود في البيئة/.env — اضبطه أولاً.")
        sys.exit(1)
    print(f"✅ TELEGRAM_TOKEN محمّل (طول {len(TOKEN)}).")
    line()

    # 1) getMe
    try:
        r = requests.get(f"{BASE}/getMe", timeout=10)
        j = r.json()
        if r.status_code == 200 and j.get("ok"):
            u = j["result"]
            print(f"✅ التوكن صالح. البوت: @{u.get('username')} (id={u.get('id')})")
        else:
            print(f"❌ التوكن غير صالح. الرد: {r.status_code} {j}")
            sys.exit(1)
    except Exception as e:
        print(f"❌ فشل الاتصال بتليجرام (شبكة/جدار ناري؟): {e}")
        sys.exit(1)
    line()

    # 2) getWebhookInfo
    try:
        r = requests.get(f"{BASE}/getWebhookInfo", timeout=10)
        info = r.json().get("result", {})
        url = info.get("url", "")
        pending = info.get("pending_update_count", 0)
        if url:
            print(f"⚠️ يوجد WEBHOOK مضبوط: {url}")
            print("   هذا يمنع getUpdates تماماً — سنحذفه الآن.")
        else:
            print("✅ لا يوجد webhook مضبوط.")
        print(f"   تحديثات معلّقة: {pending}")
        if info.get("last_error_message"):
            print(f"   آخر خطأ webhook: {info.get('last_error_message')}")
    except Exception as e:
        print(f"⚠️ getWebhookInfo فشل: {e}")
    line()

    # 3) deleteWebhook
    try:
        r = requests.get(f"{BASE}/deleteWebhook", timeout=10)
        print(f"🧹 deleteWebhook -> {r.status_code} {r.json()}")
    except Exception as e:
        print(f"⚠️ deleteWebhook فشل: {e}")
    line()

    # 4) getUpdates
    try:
        r = requests.get(f"{BASE}/getUpdates?timeout=1", timeout=10)
        if r.status_code == 200:
            res = r.json().get("result", [])
            print(f"✅ getUpdates يعمل. عدد الرسائل المنتظرة: {len(res)}")
            if res:
                last = res[-1].get("message", {})
                print(f"   آخر رسالة: نص='{last.get('text')}' من chat_id={last.get('chat', {}).get('id')}")
            else:
                print("   لا توجد رسائل جديدة. أرسل /start للبوت ثم أعد تشغيل هذا السكربت لتراها.")
        elif r.status_code == 409:
            print("❌ 409 Conflict: سيرفر آخر يسحب نفس التوكن الآن")
            print("   (غالباً السيرفر المنشور شغّال). أوقفه أو استخدم توكن بوت اختبار منفصل محلياً.")
            print(f"   {r.text[:200]}")
        else:
            print(f"❌ getUpdates رجّع {r.status_code}: {r.text[:200]}")
    except Exception as e:
        print(f"❌ getUpdates فشل: {e}")
    line()
    print("انتهى التشخيص.")


if __name__ == "__main__":
    main()
