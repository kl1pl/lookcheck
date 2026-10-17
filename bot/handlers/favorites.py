"""Хендлеры избранного и трекинга цен."""

from __future__ import annotations

import logging

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message

from .. import models
from ..db import Database, DemoDatabase
from ..services.formatting import _fmt_price, format_favorites_list

log = logging.getLogger(__name__)

router = Router()

_db: Database | DemoDatabase | None = None


def init_router(db: Database | DemoDatabase) -> None:
    global _db
    _db = db


@router.message(Command("fav"))
async def cmd_fav(message: Message) -> None:
    if _db is None:
        await message.answer("⚠️ Бот ещё не готов.")
        return
    items = await _db.list_favorites(message.from_user.id)
    rows = [(f.id, f.title, f.url or "", f.last_price) for f in items]
    await message.answer(format_favorites_list(rows))


@router.callback_query(F.data.startswith("fav:"))
async def on_add_favorite(callback: CallbackQuery) -> None:
    if _db is None:
        await callback.answer("⚠️ Бот ещё не готов.", show_alert=True)
        return
    user_id = callback.from_user.id
    payload = callback.data.removeprefix("fav:")
    market, product_id = (payload.split(":", 1) + [""])[:2]
    if not market or not product_id:
        await callback.answer("Не удалось добавить товар", show_alert=True)
        return

    # Из последнего поиска берём заголовок и цену (упрощённо: сохраняем placeholder)
    title = "Товар"
    url = ""
    price = 0

    await _db.add_favorite(
        models.Favorite(
            user_id=user_id,
            market=market,
            product_id=product_id,
            title=title,
            url=url,
            last_price=price,
        )
    )
    await callback.answer("⭐ Добавлено в избранное! Цены отслеживаются автоматически.")
    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except Exception:  # noqa: BLE001
        pass


@router.callback_query(F.data.startswith("unfav:"))
async def on_remove_favorite(callback: CallbackQuery) -> None:
    if _db is None:
        await callback.answer("⚠️ Бот ещё не готов.", show_alert=True)
        return
    user_id = callback.from_user.id
    fav_id = int(callback.data.removeprefix("unfav:").split(":")[0])
    ok = await _db.delete_favorite(fav_id, user_id)
    await callback.answer("Удалено из избранного" if ok else "Не найдено", show_alert=False)
    items = await _db.list_favorites(user_id)
    rows = [(f.id, f.title, f.url or "", f.last_price) for f in items]
    try:
        await callback.message.edit_text(
            format_favorites_list(rows),
            parse_mode="HTML",
        )
    except Exception:  # noqa: BLE001
        pass


def format_fav_for_list(f: models.Favorite) -> str:
    return f"{f.id}. {f.title} — {_fmt_price(f.last_price)}"