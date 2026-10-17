"""Конфигурация бота. Все настройки читаются из переменных окружения (.env) с дефолтами."""

from __future__ import annotations

import os
from dataclasses import dataclass, field

from dotenv import load_dotenv

load_dotenv()


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, ""))
    except ValueError:
        return default


def _env_token(name: str) -> str:
    """Токен из окружения с защитой от пробелов/переносов строк."""
    return os.getenv(name, "").strip()


@dataclass(frozen=True)
class Settings:
    token: str = _env_token("BOT_TOKEN")

    # БД: real -> PostgreSQL/SQLite через aiosqlite; demo -> полностью в памяти
    database_url: str = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///data/bot.db")

    # Флаг источника данных о товарах
    provider_mode: str = os.getenv("PROVIDER_MODE", "demo")  # demo | live

    # Ozon Seller API (для live-режима)
    ozon_client_id: str = os.getenv("OZON_CLIENT_ID", "")
    ozon_api_key: str = os.getenv("OZON_API_KEY", "")

    # Wildberries: токен партнёра (для live-режима)
    wb_api_token: str = os.getenv("WB_API_TOKEN", "")

    # Управление частотои запросов (защита от спама)
    daily_limit_free: int = _env_int("DAILY_LIMIT_FREE", 8)
    premium_daily_limit: int = _env_int("PREMIUM_DAILY_LIMIT", 1000)
    request_interval_sec: float = 1.0

    # Таймауты и ретраи к маркетплейсам
    http_timeout_sec: float = 8.0
    http_retries: int = 2

    # Кэш результатов поиска
    search_cache_ttl_sec: int = _env_int("SEARCH_CACHE_TTL", 600)
    search_results_per_market: int = _env_int("SEARCH_RESULTS_PER_MARKET", 5)

    # Расписание фонового трекера цен (каждые N минут)
    price_watch_interval_min: int = _env_int("PRICE_WATCH_INTERVAL_MIN", 30)

    # URL мини-аппа (Telegram WebApp) — кнопка меню в боте
    webapp_url: str = os.getenv("WEBAPP_URL", "https://lookcheck-1.onrender.com/")

    # Поддерживаемые рынки
    supported_markets: tuple[str, ...] = ("wb", "ozon")

    # Админ (для управления) - user_id
    admin_ids: tuple[int, ...] = field(
        default_factory=lambda: tuple(
            int(x) for x in os.getenv("ADMIN_IDS", "").split(",") if x.strip()
        )
    )

    @property
    def is_demo(self) -> bool:
        return self.provider_mode.lower() != "live"


settings = Settings()