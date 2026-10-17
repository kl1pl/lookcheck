"""Точка входа: сборка бота, запуск поллинга и фонового трекера цен."""

from __future__ import annotations

import asyncio
import logging
import os

from aiohttp import web
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.types import MenuButtonWebApp, WebAppInfo

from .config import settings
from .db import create_database
from .handlers import favorites, premium, search
from .providers.factory import build_providers
from .services.limits import QueryQuota, RateLimiter
from .services.search import SearchService
from .services.vision import build_recognizer
from .services.watcher import PriceWatcher

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)
log = logging.getLogger(__name__)


WEBAPP_HTML = None


def _load_webapp_html() -> str:
    """Читает мини-апп (webapp/index.html) из файла рядом с проектом."""
    global WEBAPP_HTML
    if WEBAPP_HTML is not None:
        return WEBAPP_HTML
    here = os.path.dirname(os.path.abspath(__file__))
    path = os.path.join(os.path.dirname(here), "webapp", "index.html")
    if not os.path.exists(path):
        path = os.path.join(here, "webapp", "index.html")
    try:
        with open(path, "r", encoding="utf-8") as f:
            WEBAPP_HTML = f.read()
    except OSError as exc:
        log.warning("Не найден мини-апп (%s): %s", path, exc)
        WEBAPP_HTML = "<h1>LookCheck mini-app</h1>"
    return WEBAPP_HTML


async def _root(_request: web.Request) -> web.Response:
    """Главная страница — мини-апп (Telegram WebApp)."""
    html = _load_webapp_html()
    return web.Response(text=html, content_type="text/html", charset="utf-8")


async def _health(_request: web.Request) -> web.Response:
    """Healthcheck для Render."""
    return web.Response(text="ok")


async def _probe(_request: web.Request) -> web.Response:
    """Временная диагностика: доступны ли API WB/Ozon с сервера Render."""
    import aiohttp

    out = {}
    UA = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0 Safari/537.36",
    }
    async with aiohttp.ClientSession() as s:
        try:
            async with s.get(
                "https://search.wb.ru/exactmatch/ru/common/v9/search",
                params={
                    "query": "наушники", "page": 1, "appType": 1, "curr": "rub",
                    "lang": "ru", "dest": -1257786, "resultset": "catalog",
                },
                headers=UA, timeout=aiohttp.ClientTimeout(total=15),
            ) as r:
                body = await r.text()
                ok = r.status == 200 and "products" in body
                out["wb_search"] = {"status": r.status, "products_found": ok}
        except Exception as exc:  # noqa: BLE001
            out["wb_search"] = {"error": str(exc)[:160]}

        try:
            async with s.get(
                "https://card.wb.ru/cards/v2/detail",
                params={"nm": "153011213", "appType": 1, "curr": "rub", "dest": -1257786, "spp": 30},
                headers=UA, timeout=aiohttp.ClientTimeout(total=15),
            ) as r:
                out["wb_card"] = {"status": r.status}
        except Exception as exc:  # noqa: BLE001
            out["wb_card"] = {"error": str(exc)[:160]}

        try:
            async with s.get("https://api-seller.ozon.ru/v1/product/list",
                             headers={"Client-Id": "0", "Api-Key": "0"},
                             timeout=aiohttp.ClientTimeout(total=15)) as r:
                out["ozon_seller"] = {"status": r.status}
        except Exception as exc:  # noqa: BLE001
            out["ozon_seller"] = {"error": str(exc)[:160]}

    import json

    return web.Response(text=json.dumps(out, ensure_ascii=False), content_type="application/json")


async def _run_http_server() -> None:
    """HTTP-сервер на порту PORT (Render) или 8080 — иначе платформа убивает процесс."""
    port = int(os.getenv("PORT", "8080"))
    app = web.Application()
    app.router.add_get("/", _root)
    app.router.add_get("/healthz", _health)
    app.router.add_get("/probe", _probe)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    log.info("HTTP healthcheck запущен на порту %s", port)


async def main() -> None:
    if not settings.token:
        log.error("Не задан BOT_TOKEN. Скопируйте .env.example в .env и укажите токен.")
        return

    bot = Bot(token=settings.token, default=DefaultBotProperties(parse_mode="HTML"))
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
        # Кнопка меню «Мини-апп» под полем ввода
        try:
            await bot.set_chat_menu_button(
                menu_button=MenuButtonWebApp(
                    text="🎛 Мини-апп",
                    web_app=WebAppInfo(url=settings.webapp_url),
                )
            )
            log.info("Кнопка мини-аппа установлена на %s", settings.webapp_url)
        except Exception as exc:  # noqa: BLE001
            log.warning("Не удалось установить кнопку мини-аппа: %s", exc)
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