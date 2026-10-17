"""Хендлеры команд и текстовых запросов."""

from __future__ import annotations

import logging

from aiogram import F, Router
from aiogram.filters import Command, CommandStart
from aiogram.types import Message

from ..config import settings
from ..db import Database, DemoDatabase
from ..services.formatting import format_promos, format_savings, format_search_result
from ..services.limits import QueryQuota, RateLimiter
from ..services.search import SearchService

log = logging.getLogger(__name__)

router = Router()

# Сервисы подключаются в main (модуль не создаёт их сам, чтобы избежать циклов)
_search: SearchService | None = None
_db: Database | DemoDatabase | None = None
_quota: QueryQuota | None = None
_limiter: RateLimiter | None = None


def init_router(
    search: SearchService,
    db: Database | DemoDatabase,
    quota: QueryQuota,
    limiter: RateLimiter,
) -> None:
    global _search, _db, _quota, _limiter
    _search, _db, _quota, _limiter = search, db, quota, limiter


@router.message(CommandStart())
async def cmd_start(message: Message) -> None:
    assert _db is not None
    await _db.touch_user(
        message.from_user.id,
        message.from_user.username or "",
        message.from_user.first_name or "",
    )
    await message.answer(
        "🛒 <b>LookCheck</b> — поиск и сравнение цен\n\n"
        "Ищу товары на маркетплейсах, сравниваю цены и слежу за скидками.\n\n"
        "Просто напишите, что хотите найти — например:\n"
        "• «беспроводные наушники»\n"
        "• «смартфон 128 гб»\n"
        "• «кроссовки»\n"
        "• 🖼 или отправьте <b>фото</b> товара\n\n"
        "Команды:\n"
        "/search &lt;запрос&gt; — поиск с ценами\n"
        "/fav — избранное (трекер цен)\n"
        "/stats — сколько вы сэкономили\n"
        "/history — история запросов\n"
        "/promo — актуальные промокоды\n"
        "/premium — премиум-подписка\n"
        "/help — помощь",
        parse_mode="HTML",
    )


@router.message(Command("help"))
async def cmd_help(message: Message) -> None:
    await message.answer(
        "ℹ️ <b>Как пользоваться:</b>\n\n"
        "🔍 <b>Поиск</b> — отправьте боту текст: «наушники», «кроссовки» и т.п.\n"
        "Бот сравнит цены на площадках, покажет выгодное предложение, проверит\n"
        "продавца и отзывы на накрутку.\n\n"
        "⭐ <b>Избранное</b> — /fav. Цены проверяются автоматически,\n"
        "при снижении приходит уведомление.\n\n"
        "💰 <b>Экономия</b> — /stats: сколько вы сэкономили с ботом.\n"
        "🏷 <b>Промокоды</b> — /promo [wb|ozon|lamoda|...].\n"
        "🕘 <b>История</b> — /history, очистка /clear_history.\n"
        "👑 <b>Премиум</b> — /premium (безлимитные запросы).\n\n"
        "🖼 <b>Поиск по фото</b> — отправьте боту фото товара: он распознает\n"
        "объект и найдёт его на маркетплейсах.\n\n"
        "Лимит: {limit} поисковых запросов в день бесплатно."
        "".format(limit=settings.daily_limit_free),
        parse_mode="HTML",
    )


@router.message(Command("search"))
async def cmd_search(message: Message) -> None:
    query = (message.text or "").removeprefix("/search").strip()
    if not query:
        await message.answer("Укажите запрос после команды, например: /search наушники")
        return
    await _do_search(message, query)


async def _deny(message: Message) -> None:
    await message.answer(
        "⏳ Слишком много запросов подряд. Подождите немного и попробуйте снова."
    )


async def _do_search(message: Message, query: str) -> None:
    if _search is None or _db is None or _quota is None or _limiter is None:
        await message.answer("⚠️ Бот ещё не готов к работе, попробуйте позже.")
        return

    user_id = message.from_user.id
    if not _limiter.allow(user_id):
        await _deny(message)
        return

    user = await _db.get_user(user_id) or await _db.create_user(user_id)
    allowed, remaining = await _quota.can_search(user_id, user.is_premium)
    if not allowed:
        await message.answer(
            "🚫 Дневной лимит запросов исчерпан.\n"
            "Завтра лимит обновится, либо оформите премиум-подписку."
        )
        return

    status = await message.answer(f"🔎 Ищу «{query}» на маркетплейсах…")
    try:
        result = await _search.search(query)
        text = format_search_result(result, query)
        await status.edit_text(text)
        await _quota.consume(user_id)
        # Статистика экономии: фиксируем выгоды из выдачи
        if _search.savings is not None:
            offers = [o for p in result.products for o in p.offers]
            await _search.savings.record_search_savings(user_id, offers)
        # История поиска
        await _db.add_search(user_id, query, len(result.products))
        if remaining - 1 <= 3:
            await message.answer(f"ℹ️ Осталось запросов сегодня: {remaining - 1}")
    except Exception as exc:  # noqa: BLE001
        log.exception("Ошибка поиска: %s", exc)
        await status.edit_text("😔 Не удалось выполнить поиск. Попробуйте чуть позже.")


# Любой текст без команды трактуем как поисковый запрос
@router.message(F.text & ~F.text.startswith("/"))
async def text_search(message: Message) -> None:
    await _do_search(message, (message.text or "").strip())


# Поиск по фото: распознаём объект и ищем на маркетплейсах
@router.message(F.photo)
async def photo_search(message: Message) -> None:
    if _search is None or _db is None or _quota is None or _limiter is None:
        await message.answer("⚠️ Бот ещё не готов к работе, попробуйте позже.")
        return

    user_id = message.from_user.id
    if not _limiter.allow(user_id):
        await _deny(message)
        return

    user = await _db.get_user(user_id) or await _db.create_user(user_id)
    allowed, remaining = await _quota.can_search(user_id, user.is_premium)
    if not allowed:
        await message.answer(
            "🚫 Дневной лимит запросов исчерпан.\n"
            "Завтра лимит обновится, либо оформите премиум-подписку."
        )
        return

    # Берём самое большое фото из присланного набора
    photo = message.photo[-1]
    status = await message.answer("🖼 Распознаю товар на фото…")
    try:
        file = await message.bot.get_file(photo.file_id)
        image_bytes = await message.bot.download_file(file.file_path)
        query, result = await _search.search_by_image(await image_bytes.read())
        text = (
            f"🖼 <b>Распознанный запрос:</b> {query}\n\n"
            + format_search_result(result, query)
        )
        await status.edit_text(text)
        await _quota.consume(user_id)
        if _search.savings is not None:
            offers = [o for p in result.products for o in p.offers]
            await _search.savings.record_search_savings(user_id, offers)
        await _db.add_search(user_id, f"[фото] {query}", len(result.products))
    except Exception as exc:  # noqa: BLE001
        log.exception("Ошибка поиска по фото: %s", exc)
        await status.edit_text("😔 Не удалось распознать фото. Попробуйте другое изображение.")


@router.message(Command("promo"))
async def cmd_promo(message: Message) -> None:
    """Показать актуальные промокоды площадки: /promo или /promo wb|ozon|..."""
    if _search is None:
        await message.answer("⚠️ Бот ещё не готов к работе, попробуйте позже.")
        return

    arg = (message.text or "").removeprefix("/promo").strip().lower()
    valid = {"wb", "ozon", "yandex", "megamarket", "lamoda", "aliexpress"}
    market = arg if arg in valid else "wb"

    codes = _search.promo.find_for_market(market)
    await message.answer(format_promos(market, codes))


@router.message(Command("stats"))
async def cmd_stats(message: Message) -> None:
    """Статистика экономии пользователя."""
    if _search is None or _db is None:
        await message.answer("⚠️ Бот ещё не готов к работе, попробуйте позже.")
        return
    user_id = message.from_user.id
    if _search.savings is None:
        await message.answer("⚠️ Статистика экономии недоступна.")
        return
    summary = await _search.savings.summary(user_id)
    recent = await _search.savings.recent(user_id, limit=5)
    text = format_savings(summary, recent)
    await message.answer(text)


@router.message(Command("history"))
async def cmd_history(message: Message) -> None:
    """История поисковых запросов."""
    if _db is None:
        await message.answer("⚠️ Бот ещё не готов к работе, попробуйте позже.")
        return
    entries = await _db.list_searches(message.from_user.id, limit=10)
    if not entries:
        await message.answer("🕘 История поиска пуста. Введите запрос, чтобы начать.")
        return
    lines = ["🕘 <b>Ваши последние запросы:</b>\n"]
    for e in entries:
        found = f" — {e.results_count} находок" if e.results_count else ""
        lines.append(f"• {e.query}{found}")
    lines.append("\n/clear_history — очистить историю")
    await message.answer("\n".join(lines))


@router.message(Command("clear_history"))
async def cmd_clear_history(message: Message) -> None:
    """Очистить историю поиска."""
    if _db is None:
        await message.answer("⚠️ Бот ещё не готов к работе, попробуйте позже.")
        return
    await _db.clear_searches(message.from_user.id)
    await message.answer("🗑 История поиска очищена.")