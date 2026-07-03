import os
import asyncio
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.staticfiles import StaticFiles
import socketio
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from slowapi import _rate_limit_exceeded_handler
from app.core.limiter import limiter

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("playrush")

from app.core.database import engine, Base
Base.metadata.create_all(bind=engine)

from app.api.auth import router as auth_router
from app.api.shop import router as shop_router
from app.api.support import router as support_router
from app.api.career import router as career_router

from app.services.cron_jobs import cleanup_abandoned_accounts, cleanup_waiting_rooms, cleanup_anticheat_data, cleanup_collusion_data, release_expired_penalties, cleanup_leaver_data_job, cleanup_closed_tickets_job
from app.services.telegram_bot import telegram_bot_listener, register_telegram_events

from app.sockets.connection import register_connection_events
from app.sockets.lobby import register_lobby_events
from app.sockets.matchmaking import register_matchmaking_events
from app.games.huroof.events import register_huroof_events
# 🔌 تسجيل حروف في إطار BaseGame (المرحلة أ) — الاستيراد يفعّل @GameRegistry.register
from app.games.huroof import game as _huroof_game  # noqa: F401
# ⚽ لعبة مسيرة لاعب (على نفس الإطار)
from app.games.career.events import register_career_events
from app.games.career import game as _career_game  # noqa: F401
from app.sockets.room_events import register_room_events
from app.sockets.store import register_store_events

os.makedirs("uploads/avatars", exist_ok=True)


def _make_supervised_task(coro_factory, name: str, restart_delay: float = 5.0):
    """
    ينشئ background task بـ supervisor داخلي:
    - يُسجّل الاستثناءات بدل ابتلاعها بصمت
    - يعيد التشغيل تلقائياً بعد restart_delay ثانية
    - يتوقف نظيفاً عند CancelledError
    """
    async def _supervisor():
        while True:
            try:
                await coro_factory()
                logger.warning(f"⚠️ [{name}] انتهى بدون استثناء — غير متوقع، إعادة بعد {restart_delay}s")
            except asyncio.CancelledError:
                logger.info(f"🛑 [{name}] ملغي — إيقاف نظيف")
                return
            except Exception as e:
                logger.error(f"🔥 [{name}] crash: {type(e).__name__}: {e} — إعادة بعد {restart_delay}s")
            await asyncio.sleep(restart_delay)

    return asyncio.create_task(_supervisor(), name=name)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("🚀 جاري تشغيل السيرفر...")
    logger.info("🛡️ [moderation] فلتر المحتوى المحلي مُفعّل")

    # ✅ كل task محمية بـ supervisor — لا تموت بصمت
    from app.services.career_importer import career_auto_import_loop
    tasks = [
        _make_supervised_task(cleanup_abandoned_accounts, "cleanup_accounts", restart_delay=60),
        _make_supervised_task(cleanup_waiting_rooms,      "cleanup_rooms",    restart_delay=30),
        _make_supervised_task(cleanup_anticheat_data,     "cleanup_anticheat", restart_delay=60),
        _make_supervised_task(cleanup_collusion_data,     "cleanup_collusion", restart_delay=60),
        _make_supervised_task(release_expired_penalties,  "release_penalties", restart_delay=60),
        _make_supervised_task(cleanup_leaver_data_job,    "cleanup_leavers",  restart_delay=60),
        _make_supervised_task(cleanup_closed_tickets_job, "cleanup_tickets",  restart_delay=60),
        # ⚽ تجديد لاعبي "مسيرة لاعب" تلقائياً (Wikidata، دوري)
        _make_supervised_task(career_auto_import_loop,    "career_importer",  restart_delay=300),
    ]

    yield

    # ✅ Graceful shutdown: أبلغ اللاعبين قبل الإغلاق
    logger.info("🛑 جاري إغلاق السيرفر — إبلاغ اللاعبين المتصلين...")
    try:
        from app.sockets.state import connected_players
        if connected_players:
            logger.info(f"📡 إرسال force_logout لـ {len(connected_players)} لاعب متصل")
            disconnect_tasks = [
                sio.emit('force_logout', {'message': 'السيرفر يعيد التشغيل، سيتم تسجيل دخولك تلقائياً.'}, to=sid)
                for sid in list(connected_players.keys())
            ]
            await asyncio.gather(*disconnect_tasks, return_exceptions=True)
            await asyncio.sleep(0.5)   # فرصة صغيرة لإرسال الرسائل
    except Exception as e:
        logger.warning(f"⚠️ خطأ أثناء إبلاغ اللاعبين عند الإغلاق: {e}")

    # ✅ إلغاء جميع الـ tasks بأمان
    for task in tasks:
        task.cancel()
    await asyncio.gather(*tasks, return_exceptions=True)
    logger.info("✅ إيقاف نظيف اكتمل")


# ==========================================
# 🛡️ Sentry — رصد الأخطاء (المهمة 0.1)
# يُفعّل فقط لو SENTRY_DSN موجود في البيئة (آمن: لا يفعل شيئاً بدونه).
# يصلك كل crash فوراً من اليوم الأول.
# ==========================================
_sentry_dsn = os.environ.get("SENTRY_DSN", "").strip()
if _sentry_dsn:
    try:
        import sentry_sdk
        from sentry_sdk.integrations.fastapi import FastApiIntegration
        from sentry_sdk.integrations.starlette import StarletteIntegration
        sentry_sdk.init(
            dsn=_sentry_dsn,
            environment=os.environ.get("ENV", "development"),
            # نسبة تتبّع الأداء (0.1 = 10% من الطلبات — خفيف على الموارد)
            traces_sample_rate=float(os.environ.get("SENTRY_TRACES_RATE", "0.1")),
            integrations=[StarletteIntegration(), FastApiIntegration()],
            send_default_pii=False,  # لا نرسل بيانات شخصية حساسة
        )
        logging.getLogger("uvicorn").info("✅ Sentry مُفعّل لرصد الأخطاء")
    except Exception as _e:
        logging.getLogger("uvicorn").warning(f"⚠️ تعذّر تفعيل Sentry: {_e}")


app = FastAPI(
    lifespan=lifespan,
    docs_url="/docs" if os.environ.get("ENV") != "production" else None,
    redoc_url=None,
)

# ==========================================
# Rate Limiting
# ==========================================
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(SlowAPIMiddleware)

# ==========================================
# CORS
# ==========================================
raw_origins = os.environ.get("ALLOWED_ORIGINS", "")
ALLOWED_ORIGINS = [o.strip() for o in raw_origins.split(",") if o.strip()] or ["http://127.0.0.1:5500"]

# نسمح أيضاً بعناوين الشبكة المحلية (localhost + IPs محلية بأي منفذ)
# ليعمل الوصول من الجوال عبر WiFi بلا تعديل يدوي. آمن لأنها عناوين شبكة خاصة فقط.
LOCAL_ORIGIN_REGEX = (
    r"^http://("
    r"localhost|127\.0\.0\.1|"
    r"192\.168\.\d{1,3}\.\d{1,3}|"
    r"10\.\d{1,3}\.\d{1,3}\.\d{1,3}|"
    r"172\.(1[6-9]|2\d|3[01])\.\d{1,3}\.\d{1,3}"
    r")(:\d+)?$"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_origin_regex=LOCAL_ORIGIN_REGEX,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["Authorization", "Content-Type"],
)

app.add_middleware(GZipMiddleware, minimum_size=1000)

# ==========================================
# Security Headers
# ==========================================
@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    response = await call_next(request)
    # ============================================================
    # 🛡️ Security Headers — production-grade
    # ============================================================
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=(), payment=()"

    # 🛡️ HSTS — يجبر HTTPS لمدة سنة (production فقط)
    if os.environ.get("ENV") == "production":
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains; preload"

    # 🛡️ CSP — Content Security Policy
    # ⚠️ ملاحظة: هذا CSP لـ API responses فقط (HTML pages تجي من frontend منفصل)
    # لكن لو حدّ يطلب HTML مباشرة من API، نمنع scripts خارجية
    response.headers["Content-Security-Policy"] = (
        "default-src 'none'; "
        "frame-ancestors 'none'; "
        "form-action 'none'; "
        "base-uri 'none';"
    )

    # 🛡️ Cross-Origin policies
    response.headers["Cross-Origin-Opener-Policy"] = "same-origin"
    response.headers["Cross-Origin-Resource-Policy"] = "same-site"

    return response

# ==========================================
# Health Check — يفحص DB + Socket.IO stats
# ==========================================
@app.get("/health", tags=["System"])
async def health_check():
    from app.core.database import SessionLocal
    from app.sockets.state import connected_players, rooms as active_rooms
    from app.games.core_manager import rooms
    from sqlalchemy import text

    db_ok = False
    db_error = None
    try:
        db = SessionLocal()
        try:
            db.execute(text("SELECT 1"))
            db_ok = True
        finally:
            db.close()
    except Exception as e:
        db_error = str(e)[:100]

    overall_status = "ok" if db_ok else "degraded"
    response = {
        "status": overall_status,
        "db": "ok" if db_ok else "down",
        # ✅ إضافة: إحصائيات Socket.IO لمراقبة حية
        "active_connections": len(connected_players),
        "active_rooms": len(rooms),
    }
    if db_error:
        response["db_error"] = db_error

    if not db_ok:
        return JSONResponse(status_code=503, content=response)
    return response


app.mount("/uploads", StaticFiles(directory="uploads"), name="uploads")

# ==========================================
# 📡 API Versioning (المهمة 0.2)
# - المسارات الحالية (/auth, /shop, /support) تبقى للويب — لا يتأثر.
# - نسخة /api/v1/ مكرّرة لتستهدفها Flutter (نفس المعالجات بالضبط).
# هكذا نخدم الويب والموبايل معاً دون كسر أي شيء.
# ==========================================
API_V1 = "/api/v1"

# المسارات الحالية (الويب)
app.include_router(auth_router, prefix="/auth", tags=["Authentication"])
app.include_router(shop_router, prefix="/shop", tags=["Shop"])
app.include_router(support_router, prefix="/support", tags=["Support"])
app.include_router(career_router, prefix="/career", tags=["Career"])

# نسخة v1 (Flutter) — نفس الـ routers بمسار مُصدّر
app.include_router(auth_router, prefix=f"{API_V1}/auth", tags=["Authentication v1"])
app.include_router(shop_router, prefix=f"{API_V1}/shop", tags=["Shop v1"])
app.include_router(support_router, prefix=f"{API_V1}/support", tags=["Support v1"])
app.include_router(career_router, prefix=f"{API_V1}/career", tags=["Career v1"])


# ==========================================
# 🧪 اختبار Sentry (يعمل فقط خارج الإنتاج)
# افتح /sentry-test في المتصفح، ثم راجع لوحة Sentry → Issues.
# احذف هذا المقطع بعد التأكد أن Sentry يعمل.
# ==========================================
if os.environ.get("ENV") != "production":
    @app.get("/sentry-test")
    async def _sentry_test():
        raise Exception("🧪 اختبار Sentry من PlayRush — تجاهل هذا الخطأ")

# ==========================================
# Socket.IO
# ==========================================
# Socket.IO يحتاج إعداد CORS خاصاً به (منفصل عن FastAPI).
# في وضع التطوير المحلي نسمح بكل العناوين (للوصول من الجوال عبر WiFi).
# في الإنتاج: يُستخدم ALLOWED_ORIGINS فقط (دومينك الحقيقي).
def _socket_cors_origins():
    try:
        from app.core.dev_mode import is_dev_mode
        if is_dev_mode():
            return '*'   # وضع تطوير: نسمح بالشبكة المحلية والجوال
    except Exception:
        pass
    return ALLOWED_ORIGINS

sio = socketio.AsyncServer(
    async_mode='asgi',
    cors_allowed_origins=_socket_cors_origins(),
    compression=True,
    ping_timeout=20,
    ping_interval=25,
    max_http_buffer_size=1 * 1024 * 1024,
)
socket_app = socketio.ASGIApp(sio, socketio_path='socket.io')

register_connection_events(sio)
register_lobby_events(sio)
register_matchmaking_events(sio)
register_room_events(sio)
register_store_events(sio)
register_huroof_events(sio)
register_career_events(sio)
register_telegram_events(sio)


async def telegram_bot_supervisor():
    """يحرس البوت ويعيد تشغيله لو فشل."""
    while True:
        try:
            await telegram_bot_listener(sio)
            logger.warning("🤖 [telegram_bot] listener انتهى بدون استثناء — إعادة بعد 5s")
        except asyncio.CancelledError:
            logger.info("🤖 [telegram_bot] supervisor ملغي")
            break
        except Exception as e:
            logger.error(f"🤖 [telegram_bot] crash: {type(e).__name__}: {e} — إعادة بعد 5s")
        await asyncio.sleep(5)


sio.start_background_task(telegram_bot_supervisor)

app.mount('/socket.io', socket_app)
