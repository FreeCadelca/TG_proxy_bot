#!/bin/sh
set -e

# Контейнер стартует от root только для того, чтобы поправить владельца
# примонтированных с хоста файлов (папка data и .env), после чего
# процесс бота запускается от непривилегированного пользователя bot.
if [ "$(id -u)" = "0" ]; then
    mkdir -p /app/data /app/cached_charts
    chown -R bot:bot /app/data /app/cached_charts
    # .env бот перезаписывает сам (/set_fee, /set_payment_day), поэтому ему нужны права на запись
    if [ -f /app/.env ]; then
        chown bot:bot /app/.env
    fi
    exec setpriv --reuid=bot --regid=bot --init-groups "$@"
fi

exec "$@"
