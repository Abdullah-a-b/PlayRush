# run_dev.py — للتطوير على Windows فقط (worker واحد)
import uvicorn

if __name__ == "__main__":

    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,           # ✅ hot reload للتطوير
        loop="asyncio",
        log_level="info",
    )