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

from app.services.cron_jobs import cleanup_abandoned_accounts
from app.services.telegram_bot import telegram_bot_listener, register_telegram_events

from app.sockets.connection import register_connection_events
from app.sockets.lobby import register_lobby_events
from app.sockets.matchmaking import register_matchmaking_events
from app.games.huroof.events import register_huroof_events
from app.sockets.room_events import register_room_events

os.makedirs("uploads/avatars", exist_ok=True)

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("🚀 جاري تشغيل السيرفر...")

    # ✅ إصلاح Bug الأشباح: مسح بيانات الاتصالات القديمة من Redis عند كل تشغيل
    # لأن SIDs من الجلسة السابقة ميتة وتسبب دوبل في قائمة اللاعبين
    from app.core.redis_client import redis_db
    try:
        keys_to_clear = [
            "global:connected_players",  # اللاعبون المتصلون (SIDs ميتة)
            "queue:huroof",              # طابور الماتش ميكنج
            "queue:wordle",
            "queue:trivia",
        ]
        # مسح لوبيات الألعاب
        lobby_keys = await redis_db.keys("lobby:*")
        for key in lobby_keys:
            keys_to_clear.append(key)

        if keys_to_clear:
            await redis_db.delete(*keys_to_clear)
            logger.info(f"🧹 تم مسح {len(keys_to_clear)} مفتاح قديم من Redis (أشباح الجلسة السابقة)")
    except Exception as e:
        logger.warning(f"⚠️ تعذّر مسح Redis عند بدء التشغيل: {e}")

    cleanup_task = asyncio.create_task(cleanup_abandoned_accounts())
    yield
    logger.info("🛑 جاري إيقاف السيرفر بأمان...")
    cleanup_task.cancel()

app = FastAPI(
    lifespan=lifespan,
    # ✅ إخفاء docs في الإنتاج
    docs_url="/docs" if os.environ.get("ENV") != "production" else None,
    redoc_url=None,
)

# ==========================================
# ✅ تفعيل Rate Limiting (SlowAPI)
# ==========================================
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(SlowAPIMiddleware)

# ==========================================
# ✅ CORS محكم — يقرأ من .env
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

# ✅ ضغط الردود
app.add_middleware(GZipMiddleware, minimum_size=1000)

# ==========================================
# ✅ Security Headers Middleware
# ==========================================
@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    return response

# ==========================================
# ✅ Health Check
# ==========================================
@app.get("/health", tags=["System"])
async def health_check():
    return {"status": "ok"}

# الملفات الثابتة
app.mount("/uploads", StaticFiles(directory="uploads"), name="uploads")

app.include_router(auth_router, prefix="/auth", tags=["Authentication"])
app.include_router(shop_router, prefix="/shop", tags=["Shop"])

# 1. إنشاء مدير الاتصالات الذي يربط السيرفرات ببعضها عبر Redis
# (نستخدم localhost:6379 لأن Redis سيعمل على جهازك)
REDIS_URL = os.environ.get("REDIS_URL", "redis://127.0.0.1:6379/0")
redis_mgr = socketio.AsyncRedisManager(REDIS_URL)

# ==========================================
# Socket.IO
# ==========================================
sio = socketio.AsyncServer(
    async_mode='asgi',
    cors_allowed_origins=[],
    compression=True,
    ping_timeout=20,
    ping_interval=25,
    max_http_buffer_size=1 * 1024 * 1024,
    client_manager=redis_mgr,
)
socket_app = socketio.ASGIApp(sio, socketio_path='socket.io')

register_connection_events(sio)
register_lobby_events(sio)
register_matchmaking_events(sio)
register_room_events(sio)
register_huroof_events(sio)
register_telegram_events(sio)

async def _start_telegram():
    await telegram_bot_listener(sio)

sio.start_background_task(_start_telegram)

app.mount('/socket.io', socket_app)