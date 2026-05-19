# run_dev.py — للتطوير على Windows
# يحل مشكلة Ctrl+C العالقة بسبب WebSockets
import uvicorn

if __name__ == "__main__":
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        reload_dirs=["app"],                           # ✅ يراقب فقط app/ مش scripts/
        reload_excludes=["*.db", "*.db-journal", "*.pyc", "logs/*"],
        loop="asyncio",
        log_level="info",
        access_log=False,
        # ✅ هذي الإعدادات تخلي Ctrl+C يعمل:
        timeout_graceful_shutdown=3,                   # 3 ثواني فقط ثم force quit
        ws_ping_interval=20.0,
        ws_ping_timeout=10.0,
    )
