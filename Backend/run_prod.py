import multiprocessing
import asyncio
from hypercorn.config import Config
from hypercorn.asyncio import serve

async def main():
    config = Config()
    config.bind = ["0.0.0.0:8000"]
    config.keep_alive_timeout = 30

    from app.main import app
    await serve(app, config)

if __name__ == "__main__":
    multiprocessing.freeze_support()
    asyncio.run(main())