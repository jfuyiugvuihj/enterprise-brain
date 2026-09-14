# The lockfile and pyproject require CPython >=3.11,<3.14, so the interpreter here is
# part of the contract: 3.14 would make `uv sync --frozen` refuse to resolve.
FROM python:3.11-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_PROJECT_ENVIRONMENT=/app/.venv \
    PATH=/app/.venv/bin:/usr/local/bin:/usr/local/sbin:/usr/bin:/usr/sbin:/bin:/sbin

# A dropped connection during the fetch used to abort the whole layer with apt exit 100,
# so retries and an explicit timeout belong to the image build itself. APT_MIRROR stays
# empty by default, which means the upstream archive; a build machine behind a link that
# cannot hold a Fastly connection open passes --build-arg APT_MIRROR=<host> instead.
ARG APT_MIRROR=
RUN set -eux; \
    opts="-o Acquire::Retries=5 -o Acquire::http::Timeout=20 -o Acquire::ForceIPv4=true"; \
    if [ -n "$APT_MIRROR" ]; then \
        for f in /etc/apt/sources.list /etc/apt/sources.list.d/debian.sources; do \
            if [ -f "$f" ]; then sed -i "s|deb.debian.org|$APT_MIRROR|g; s|security.debian.org|$APT_MIRROR|g" "$f"; fi; \
        done; \
    fi; \
    apt-get update $opts; \
    apt-get install -y --no-install-recommends $opts build-essential git tzdata; \
    rm -rf /var/lib/apt/lists/*

# PIP_INDEX_URL is the same switch as APT_MIRROR for a customer intranet: one build
# argument instead of a hand-edited Dockerfile. The cache mount keeps the wheel cache
# across rebuilds, which matters because every code change invalidates COPY layers and
# a private server re-downloads gigabytes of torch otherwise.
ARG PIP_INDEX_URL=
RUN set -eux; \
    if [ -n "$PIP_INDEX_URL" ]; then \
        pip install --no-cache-dir --index-url "$PIP_INDEX_URL" uv; \
    else \
        pip install --no-cache-dir uv; \
    fi

COPY pyproject.toml uv.lock README.md ./
COPY migrations ./migrations
COPY scripts ./scripts
COPY deploy ./deploy
COPY app ./app

RUN --mount=type=cache,target=/root/.cache/uv \
    set -eux; \
    if [ -n "$PIP_INDEX_URL" ]; then \
        uv sync --frozen --no-dev --default-index "$PIP_INDEX_URL"; \
    else \
        uv sync --frozen --no-dev; \
    fi

# Customer uploads and generated files are never baked into the image: they live on
# mounted volumes so a rebuild cannot lose or leak them.
RUN groupadd --system --gid 10001 brain \
    && useradd --system --uid 10001 --gid 10001 --home-dir /app --shell /usr/sbin/nologin brain \
    && mkdir -p /app/data /app/logs /app/chroma_db /app/static/charts /app/static/exports \
    && chown -R 10001:10001 /app
USER 10001:10001

VOLUME ["/app/documents", "/app/data", "/app/static", "/app/logs", "/app/chroma_db"]

EXPOSE 8001

HEALTHCHECK --interval=20s --timeout=5s --start-period=45s --retries=5 \
    CMD ["python", "-c", "import sys,urllib.request; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8001/api/v1/health', timeout=4).status == 200 else 1)"]

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8001"]