FROM python:3.12-slim

# Kontener może działać jako dowolny UID (user: w compose), więc HOME i cache muszą być zapisywalne.
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    OUTPUT_ROOT=/data/output \
    DB_PATH=/data/config/app.db \
    HOME=/tmp \
    XDG_CACHE_HOME=/tmp/.cache \
    DENO_DIR=/tmp/.cache/deno

RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg tzdata \
    && rm -rf /var/lib/apt/lists/*

# yt-dlp potrzebuje runtime'u JS do obsługi YouTube (EJS); domyślnie używa Deno z PATH (min. 2.3.0).
COPY --from=denoland/deno:bin-2.9.7 /deno /usr/local/bin/deno

WORKDIR /srv
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app

RUN useradd --uid 1000 --no-create-home --shell /usr/sbin/nologin app \
    && mkdir -p /data/output /data/config \
    && chown app:app /data/output /data/config
USER app

EXPOSE 5000

# Dokładnie jeden worker gunicorna: wątek pobierający żyje w procesie aplikacji.
CMD ["gunicorn", "-w", "1", "--threads", "4", "-b", "0.0.0.0:5000", "app:create_app()"]
