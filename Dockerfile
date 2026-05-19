FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN groupadd --system bewaarhet \
    && useradd --system --gid bewaarhet --home-dir /app --shell /usr/sbin/nologin bewaarhet

COPY requirements.txt .
RUN python -m pip install --upgrade pip \
    && python -m pip install -r requirements.txt

COPY bewaarhet ./bewaarhet
COPY run_once.py ./run_once.py

RUN mkdir -p /app/data \
    && chown -R bewaarhet:bewaarhet /app

USER bewaarhet

CMD ["python", "-m", "bewaarhet.worker"]

