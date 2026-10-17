"""Сервис лимитов запросов (защита от спама, квоты пользователей)."""

from __future__ import annotations

import time
from collections import defaultdict, deque

from ..config import settings
from ..db import Database, DemoDatabase


class RateLimiter:
    """Скользящее окно: не более N запросов от одного пользователя за интервал."""

    def __init__(self, max_per_window: int = 5, window_sec: float = 60.0) -> None:
        self.max = max_per_window
        self.window = window_sec
        self._hits: defaultdict[int, deque[float]] = defaultdict(deque)

    def allow(self, user_id: int) -> bool:
        now = time.monotonic()
        q = self._hits[user_id]
        while q and now - q[0] > self.window:
            q.popleft()
        if len(q) >= self.max:
            return False
        q.append(now)
        return True


class QueryQuota:
    """Дневной лимит запросов: бесплатно N, премиум — почти безлимит."""

    def __init__(self, db: Database | DemoDatabase) -> None:
        self.db = db

    async def can_search(self, user_id: int, is_premium: bool) -> tuple[bool, int]:
        """Возвращает (разрешено, осталось_сегодня)."""
        user = await self.db.get_user(user_id)
        used = user.daily_queries_used if user else 0
        limit = settings.premium_daily_limit if is_premium else settings.daily_limit_free
        return used < limit, max(0, limit - used)

    async def consume(self, user_id: int) -> None:
        await self.db.inc_queries(user_id)