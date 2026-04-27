# run_dev.py — للتطوير على Windows فقط (worker واحد)
import multiprocessing

import uvicorn

if __name__ == "__main__":
    workers_count = multiprocessing.cpu_count() * 2

    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        workers=workers_count, # 👈 هذا هو السر!
        reload=True,           # ✅ hot reload للتطوير
        loop="asyncio",
        log_level="info",
        backlog=16384,          # زيادة حجم الباك لوج للتعامل مع الذروة
    )