"""Фоновый трекер цен избранных товаров с уведомлениями о снижении."""

from __future__ import annotations

import asyncio
import logging

from aiogram import Bot

from .. import models
from ..config import settings
from ..db import Database, DemoDatabase
from ..providers.base import BaseProvider
from ..services.formatting import _fmt_price

log = logging.getLogger(__name__)


class PriceWatcher:
    """Циклически опрашивает цены избранных товаров и шлёт алерты."""

    def __init__(
        self,
        bot: Bot,
        db: Database | DemoDatabase,
        providers: dict[str, BaseProvider],
        interval_min: int | None = None,
    ) -> None:
        self.bot = bot
        self.db = db
        self.providers = providers
        self.interval = interval_min or settings.price_watch_interval_min
        self._task: asyncio.Task | None = None

    async def start(self) -> None:
        self._task = asyncio.create_task(self._loop())
        log.info("Ценовой трекер запущен, интервал %s мин", self.interval)

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    async def _loop(self) -> None:
        while True:
            try:
                await self.check_all()
            except Exception as exc:  # noqa: BLE001
                log.exception("Ошибка прохода трекера цен: %s", exc)
            await asyncio.sleep(self.interval * 60)

    async def check_all(self) -> None:
        favorites = await self.db.all_favorites()
        if not favorites:
            return

        # Группируем запросы по провайдеру? Пока вызываем последовательно простым образом.
        for fav in favorites:
            try:
                await self._check_one(fav)
            except Exception as exc:  # noqa: BLE001
                log.warning("Ошибка проверки избранного #%s: %s", fav.id, exc)
            await asyncio.sleep(1)  # мягкий шаг, чтобы не словить блокировку

    async def _check_one(self, fav: models.Favorite) -> None:
        provider = self.providers.get(fav.market)
        if not provider:
            return
        price = await provider.get_price(fav.product_id)
        if price is None:
            return
        if fav.last_price and price < fav.last_price:
            drop_pct = round((1 - price / fav.last_price) * 100)
            if drop_pct >= 1:
                text = (
                    f"📉 <b>Цена снизилась!</b>\n"
                    f"{fav.title}\n"
                    f"{_fmt_price(fav.last_price)} → <b>{_fmt_price(price)}</b> (−{drop_pct}%)\n"
                    f"{fav.url}"
                )
                try:
                    await self.bot.send_message(fav.user_id, text, parse_mode="HTML")
                except Exception as exc:  # noqa: BLE001
                    log.warning("Не удалось уведомить пользователя %s: %s", fav.user_id, exc)
        await self.db.update_favorite_price(fav.id, price)