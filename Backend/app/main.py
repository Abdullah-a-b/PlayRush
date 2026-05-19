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

from app.services.cron_jobs import cleanup_abandoned_accounts, cleanup_waiting_rooms, cleanup_anticheat_data
from app.services.telegram_bot import telegram_bot_listener, register_telegram_events

from app.sockets.connection import register_connection_events
from app.sockets.lobby import register_lobby_events
from app.sockets.matchmaking import register_matchmaking_events
from app.games.huroof.events import register_huroof_events
from app.sockets.room_events import register_room_events

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

    # ✅ كل task محمية بـ supervisor — لا تموت بصمت
    tasks = [
        _make_supervised_task(cleanup_abandoned_accounts, "cleanup_accounts", restart_delay=60),
        _make_supervised_task(cleanup_waiting_rooms,      "cleanup_rooms",    restart_delay=30),
        _make_supervised_task(cleanup_anticheat_data,     "cleanup_anticheat", restart_delay=60),
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

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
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
app.include_router(auth_router, prefix="/auth", tags=["Authentication"])
app.include_router(shop_router, prefix="/shop", tags=["Shop"])

# ==========================================
# Socket.IO
# ==========================================
sio = socketio.AsyncServer(
    async_mode='asgi',
    cors_allowed_origins=ALLOWED_ORIGINS,
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
register_huroof_events(sio)
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
