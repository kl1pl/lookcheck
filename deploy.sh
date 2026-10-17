#!/usr/bin/env bash
# Установка бота LookCheck на сервер одной командой (Ubuntu/Debian).
# Запуск:  bash deploy.sh
set -e

echo "=== Установка LookCheck-бота ==="

# 0. Токен
if [ -f .env ] && grep -q "BOT_TOKEN=." .env; then
  echo "[ok] Токен уже есть в .env"
else
  read -r -p "Вставьте токен бота (от @BotFather): " TOKEN
  if [ -z "$TOKEN" ]; then
    echo "Токен не введён — выход."; exit 1
  fi
  cat > .env <<EOF
BOT_TOKEN=$TOKEN
PROVIDER_MODE=demo
DATABASE_URL=sqlite+aiosqlite:///data/bot.db
DAILY_LIMIT_FREE=8
PREMIUM_DAILY_LIMIT=1000
SEARCH_CACHE_TTL=600
PRICE_WATCH_INTERVAL_MIN=30
EOF
  echo "[ok] .env создан"
fi

# 1. Docker
if ! command -v docker >/dev/null 2>&1; then
  echo "[..] Устанавливаю Docker..."
  curl -fsSL https://get.docker.com | sh
  systemctl enable --now docker || true
  echo "[ok] Docker установлен"
else
  echo "[ok] Docker уже есть"
fi

if ! command -v docker compose >/dev/null 2>&1; then
  echo "[..] Ставлю плагин docker compose..."
  apt-get update -qq && apt-get install -y -qq docker-compose-plugin >/dev/null 2>&1 || true
fi

# 2. Сборка и запуск
echo "[..] Собираю и запускаю контейнер..."
docker compose up -d --build

# 3. Проверка
sleep 6
if docker ps --format '{{.Names}}' | grep -q lookcheck-bot; then
  echo ""
  echo "=== ГОТОВО ==="
  echo "Бот запущен. Проверьте в Telegram: /start"
  echo "Логи:  docker logs lookcheck-bot"
else
  echo "Контейнер не поднялся. Смотрите логи:"
  docker logs lookcheck-bot
  exit 1
fi