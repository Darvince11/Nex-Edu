# syntax=docker/dockerfile:1.10
# Renovate pins these tags to digests (see renovate.json).

FROM ghcr.io/astral-sh/uv:0.13.1 AS uv

FROM python:3.14-slim-trixie AS build
COPY --from=uv /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    UV_PROJECT_ENVIRONMENT=/opt/venv
WORKDIR /src
# Dependencies first for layer caching; --locked fails if uv.lock is stale.
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv uv sync --locked --no-dev --no-install-project
COPY . .
RUN DJANGO_SETTINGS_MODULE=config.settings.dev /opt/venv/bin/python manage.py collectstatic --noinput

FROM python:3.14-slim-trixie AS runtime
# Amazon RDS CA bundle for TLS verification to Aurora.
ADD --chmod=0644 https://truststore.pki.rds.amazonaws.com/global/global-bundle.pem /etc/ssl/certs/rds-global-bundle.pem
RUN groupadd --system --gid 10001 app \
    && useradd --system --uid 10001 --gid app --no-create-home --shell /usr/sbin/nologin app \
    && rm -rf /var/lib/apt/lists/*
ENV PATH=/opt/venv/bin:$PATH \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DJANGO_SETTINGS_MODULE=config.settings.prod
COPY --from=build /opt/venv /opt/venv
COPY --from=build --chown=root:root /src /app
WORKDIR /app
USER 10001:10001
EXPOSE 8000
# ECS runs this with a read-only root filesystem; /tmp is a tmpfs volume.
CMD ["granian", "--interface", "asgi", "--host", "0.0.0.0", "--port", "8000", \
     "--workers", "2", "--runtime-threads", "2", "--respawn-failed-workers", \
     "config.asgi:application"]
