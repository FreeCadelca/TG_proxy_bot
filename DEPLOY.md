# Развёртывание через Docker Compose

## Что где лежит

| На хосте      | В контейнере    | Назначение                                                        |
|---------------|-----------------|-------------------------------------------------------------------|
| `./.env`      | `/app/.env`     | Настройки бота. Бот сам дописывает туда `MONTHLY_FEE` и `PAYMENT_DAY` |
| `./data/`     | `/app/data/`    | База `bot.db` и файл логов `bot.log` (с ротацией)                 |

`DB_URL` и `LOG_FILE` задаются в `docker-compose.yml` и имеют приоритет над `.env`,
поэтому значение `DB_URL` в `.env` при запуске в Docker не используется.

Часовой пояс по умолчанию — `Europe/Moscow` (от него зависит время ежедневной
проверки в 18:00 и даты списаний). Поменять можно, добавив в `.env` строку `TZ="..."`.

Внутри контейнера бот работает от непривилегированного пользователя `bot` (uid/gid 10001).
При старте контейнер делает владельцем `./data` и `./.env` этого пользователя,
поэтому на хосте у этих файлов будет владелец `10001` — это нормально.

## Первый запуск на новом сервере

```bash
git clone https://github.com/FreeCadelca/TG_proxy_bot.git
cd TG_proxy_bot

cp .env.example .env
nano .env                 # заполнить токены, ADMIN_IDS и т.д.

docker compose up -d --build
docker compose logs -f    # убедиться, что в логах есть "Bot started."
```

## Перенос со старого сервера (systemd)

1. На старом сервере остановить бота, чтобы база не менялась во время копирования:
   ```bash
   sudo systemctl stop <имя-службы>
   sudo systemctl disable <имя-службы>
   ```
2. Скопировать на новый сервер `.env` и `bot.db` из папки проекта:
   ```bash
   scp old-server:/path/to/TG_proxy_bot/.env    ./TG_proxy_bot/.env
   mkdir -p ./TG_proxy_bot/data
   scp old-server:/path/to/TG_proxy_bot/bot.db  ./TG_proxy_bot/data/bot.db
   ```
   Обратите внимание: база кладётся в `data/`, а не в корень проекта.
3. Запустить: `docker compose up -d --build`.

Важно не запускать бота одновременно на двух серверах с одним `BOT_TOKEN`:
Telegram отдаёт обновления только одному polling-клиенту.

## Повседневные команды

```bash
docker compose logs -f --tail 100     # логи
docker compose restart                # перезапуск (например, после правки .env)
docker compose down                   # остановить и удалить контейнер (данные в ./data сохранятся)

# обновление до свежей версии кода
git pull
docker compose up -d --build
```

## Резервная копия

```bash
docker compose stop
cp data/bot.db "bot.db.backup-$(date +%F)"
docker compose start
```
