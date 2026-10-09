FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_ROOT_USER_ACTION=ignore \
    TZ=Europe/Moscow

# tzdata нужен, чтобы TZ работал: планировщик (cron в 18:00) и datetime.now()
# опираются на локальное время контейнера, а по умолчанию там UTC
RUN apt-get update \
    && apt-get install -y --no-install-recommends tzdata \
    && rm -rf /var/lib/apt/lists/*

# Непривилегированный пользователь, под которым работает бот.
# UID/GID нарочно высокие, чтобы не совпасть с реальным пользователем на хосте
ARG APP_UID=10001
ARG APP_GID=10001
RUN groupadd --gid "${APP_GID}" bot \
    && useradd --uid "${APP_UID}" --gid bot --no-create-home --home-dir /app --shell /usr/sbin/nologin bot

WORKDIR /app

# Сначала только зависимости — чтобы слой кешировался между пересборками
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .
RUN mkdir -p data cached_charts \
    && chown -R bot:bot data cached_charts \
    && chmod +x docker/entrypoint.sh

ENTRYPOINT ["/app/docker/entrypoint.sh"]
CMD ["python", "main.py"]
