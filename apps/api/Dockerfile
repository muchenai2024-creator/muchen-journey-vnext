FROM python:3.14.6-slim@sha256:cea0e6040540fb2b965b6e7fb5ffa00871e632eef63719f0ea54bca189ce14a6

ARG VCS_REF=local
LABEL org.opencontainers.image.source="https://github.com/muchenai2024-creator/muchen-journey-vnext" \
      org.opencontainers.image.title="Muchen Journey vNext API" \
      org.opencontainers.image.revision="${VCS_REF}"

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY requirements.lock ./
RUN python -m pip install --upgrade pip==26.1.2 \
    && python -m pip install -r requirements.lock

COPY pyproject.toml ./
COPY apps/api ./apps/api
COPY apps/worker ./apps/worker
COPY migrations ./migrations
COPY alembic.ini ./
COPY contracts ./contracts
RUN chmod 0555 contracts && chmod 0444 contracts/openapi.json
COPY tests ./tests
COPY scripts ./scripts

RUN python -m pip install --no-deps .

RUN useradd --create-home --uid 10001 journey
USER journey

CMD ["uvicorn", "journey_api.main:app", "--host", "0.0.0.0", "--port", "8000"]
