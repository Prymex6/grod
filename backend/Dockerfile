# syntax=docker/dockerfile:1

# Dependencies are installed in their own stage so that changing the source
# does not reinstall them.
FROM python:3.14-slim AS builder

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never

RUN pip install --no-cache-dir uv

WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --locked --no-dev --no-install-project

COPY src ./src
COPY migrations ./migrations
COPY alembic.ini ./
RUN uv sync --locked --no-dev


FROM python:3.14-slim

# git is not a convenience here: the repository module shells out to it for
# every clone, push and diff.
RUN apt-get update \
    && apt-get install --no-install-recommends --yes git \
    && rm -rf /var/lib/apt/lists/*

# Nothing needs root, so nothing runs as root.
RUN useradd --create-home --uid 10001 grod

WORKDIR /app
COPY --from=builder --chown=grod:grod /app /app

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1

USER grod
EXPOSE 8000

# Repositories, packages, images, bucket files and published sites.
VOLUME ["/app/var"]

CMD ["uvicorn", "grod.main:app", "--host", "0.0.0.0", "--port", "8000"]
