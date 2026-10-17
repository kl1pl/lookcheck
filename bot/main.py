"""Точка входа: сборка бота, запуск поллинга и фонового трекера цен."""

from __future__ import annotations

import asyncio
import logging
import os

from aiohttp import web
from aiogram import Bot, Dispatcher

from .config import settings
from .db import create_database
from .handlers import favorites, premium, search
from .providers.factory import build_providers
from .services.search import SearchService
from .services.vision import build_recognizer
from .services.watcher import PriceWatcher

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)
log = logging.getLogger(__name__)


async def _health(_request: web.Request) -> web.Response:
    """Пустышка для healthcheck Render: сервис должен слушать PORT."""
    return web.Response(text="ok")


async def _run_http_server() -> None:
    """HTTP-сервер на порту PORT (Render) или 8080 — иначе платформа убивает процесс."""
    port = int(os.getenv("PORT", "8080"))
    app = web.Application()
    app.router.add_get("/", _health)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    log.info("HTTP healthcheck запущен на порту %s", port)


async def main() -> None:
    if not settings.token:
        log.error("Не задан BOT_TOKEN. Скопируйте .env.example в .env и укажите токен.")
        return

    bot = Bot(token=settings.token, parse_mode="HTML")
    dp = Dispatcher()

    db = await create_database()
    providers = build_providers()
    log.info(
        "Режим источников данных: %s; подключены площадки: %s",
        settings.provider_mode,
        ", ".join(providers.keys()),
    )

    search_service = SearchService(providers, db=db)
    search_service.vision = build_recognizer()
    quota = QueryQuota(db)
    limiter = RateLimiter(
        max_per_window=settings.request_interval_sec and 10 or 5,
        window_sec=60.0,
    )

    search.init_router(search_service, db, quota, limiter)
    favorites.init_router(db)
    premium.init_router(db)
    dp.include_router(search.router)
    dp.include_router(favorites.router)
    dp.include_router(premium.router)

    watcher = PriceWatcher(bot, db, providers)

    try:
        await _run_http_server()
        await watcher.start()
        await bot.delete_webhook(drop_pending_updates=True)
        log.info("Бот запущен. Имя: @%s", (await bot.me()).username)
        await dp.start_polling(bot)
    finally:
        await watcher.stop()
        await db.close()
        await bot.session.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        log.info("Остановка бота.")