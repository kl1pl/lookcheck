"""Премиум-подписка: тарифы, выдача/отзыв доступа (админ)."""

from __future__ import annotations

import logging

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from ..config import settings
from ..db import Database, DemoDatabase

log = logging.getLogger(__name__)

router = Router()

_db: Database | DemoDatabase | None = None

PREMIUM_PRICE = 299  # ₽/месяц (демо-тариф; реальная оплата — в следующей итерации)


def init_router(db: Database | DemoDatabase) -> None:
    global _db
    _db = db


def _is_admin(user_id: int) -> bool:
    return user_id in settings.admin_ids


@router.message(Command("premium"))
async def cmd_premium(message: Message) -> None:
    """Информация о премиуме."""
    if _db is None:
        await message.answer("⚠️ Бот ещё не готов к работе, попробуйте позже.")
        return
    user = await _db.get_user(message.from_user.id)
    is_premium = bool(user and user.is_premium)
    if is_premium:
        await message.answer(
            "👑 <b>У вас активна премиум-подписка!</b>\n\n"
            "✅ Безлимитные запросы\n"
            "✅ Мгновенные алерты о падении цен\n"
            "✅ Расширенная аналитика отзывов\n\n"
            "Спасибо, что поддерживаете бота!"
        )
        return
    await message.answer(
        "👑 <b>Премиум-подписка — {price} ₽/мес</b>\n\n"
        "Бесплатная версия: {limit} запросов в день.\n\n"
        "Ваши преимущества:\n"
        "✅ Безлимитные запросы (вместо {limit}/день)\n"
        "✅ Мгновенные алерты о багах цен\n"
        "✅ Трекер цен без ограничений\n"
        "✅ Расширенная аналитика\n\n"
        "💳 Оплата скоро появится. Пока что доступ выдаёт администратор: "
        "напишите ему ваш Telegram ID (`{uid}`)."
        "".format(price=PREMIUM_PRICE, limit=settings.daily_limit_free, uid=message.from_user.id)
    )


@router.message(Command("grant"))
async def cmd_grant(message: Message) -> None:
    """Админ: выдать премиум. Использование: /grant <user_id>"""
    if _db is None:
        return
    if not _is_admin(message.from_user.id):
        await message.answer("⛔ Только для администратора.")
        return
    arg = (message.text or "").removeprefix("/grant").strip()
    if not arg.isdigit():
        await message.answer("Использование: /grant &lt;user_id&gt;")
        return
    user_id = int(arg)
    await _db.create_user(user_id)
    await _db.set_premium(user_id, True)
    await message.answer(f"👑 Премиум выдан пользователю {user_id}.")


@router.message(Command("revoke"))
async def cmd_revoke(message: Message) -> None:
    """Админ: отозвать премиум. Использование: /revoke <user_id>"""
    if _db is None:
        return
    if not _is_admin(message.from_user.id):
        await message.answer("⛔ Только для администратора.")
        return
    arg = (message.text or "").removeprefix("/revoke").strip()
    if not arg.isdigit():
        await message.answer("Использование: /revoke &lt;user_id&gt;")
        return
    user_id = int(arg)
    await _db.set_premium(user_id, False)
    await message.answer(f"Премиум отозван у пользователя {user_id}.")