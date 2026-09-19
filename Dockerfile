# Private-deployment image for 企业智脑. The layer order below is load-bearing and must
# not be reordered: the dependency layer alone is ~5.8 GB, so any instruction that
# invalidates it costs gigabytes of export and minutes of build on a customer machine.
# Two rules keep that from happening: (1) dependencies install before any application
# source is copied; (2) sources carry their ownership through COPY --chown instead of a
# trailing `chown -R /app`, which used to copy the whole venv into a second 5.78 GB layer.

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
# fonts-wqy-microhei is not decoration: the image had no font at all, so every generated
# chart rendered Chinese as boxes and the PDF exporter had nothing to embed. Its path is the
# one candidate app/tools/export.py looks for on Linux, and its family name is already in the
# app/tools/chart.py preference list, so one package covers both surfaces.
    apt-get install -y --no-install-recommends $opts build-essential git tzdata fonts-wqy-microhei; \
    rm -rf /var/lib/apt/lists/*

# PIP_INDEX_URL is the same switch as APT_MIRROR for a customer intranet: one build
# argument instead of a hand-edited Dockerfile. The cache mount keeps the wheel cache
# across rebuilds, which matters because a private server with a cold cache would
# otherwise re-download gigabytes of torch.
ARG PIP_INDEX_URL=
RUN set -eux; \
    if [ -n "$PIP_INDEX_URL" ]; then \
        pip install --no-cache-dir --index-url "$PIP_INDEX_URL" uv; \
    else \
        pip install --no-cache-dir uv; \
    fi

COPY pyproject.toml uv.lock README.md ./

# Dependencies resolve from the lockfile only, so this layer is keyed by pyproject.toml
# and uv.lock and survives every ordinary code change. It must stay above the COPYs of
# migrations/scripts/deploy/app: with them above it, editing one line of Python
# invalidated this 5.8 GB layer (measured 2026-09-19: a one-file rebuild spent 217 s
# exporting, and the image store carried 18.4 GB for a single tag).
RUN --mount=type=cache,target=/root/.cache/uv \
    set -eux; \
    if [ -n "$PIP_INDEX_URL" ]; then \
        uv sync --frozen --no-dev --default-index "$PIP_INDEX_URL"; \
    else \
        uv sync --frozen --no-dev; \
    fi

# The service account exists before the sources are copied so the COPYs below can carry
# ownership directly (see the note at the top). Recursing over /app afterwards would
# duplicate the venv into a fresh layer.
RUN groupadd --system --gid 10001 brain \
    && useradd --system --uid 10001 --gid 10001 --home-dir /app --shell /usr/sbin/nologin brain \
    && mkdir -p /app/data /app/logs /app/chroma_db /app/documents /app/static/charts /app/static/exports /app/.cache \
    && chown -R 10001:10001 /app/data /app/logs /app/chroma_db /app/documents /app/static /app/.cache

# Customer uploads and generated files are never baked into the image: they live on
# mounted volumes so a rebuild cannot lose or leak them.
# Every path a named volume gets mounted on has to exist here with the application
# owner already set, /app/documents included: Docker initializes a volume from the
# image directory it mounts, ownership included, and a path the image never creates
# becomes a root-owned mount point. This image then runs as uid 10001, so the first
# POST /api/v1/upload on a fresh install failed with EACCES on its temporary file.
COPY --chown=10001:10001 migrations ./migrations
COPY --chown=10001:10001 scripts ./scripts
COPY --chown=10001:10001 deploy ./deploy
COPY --chown=10001:10001 app ./app

# Provenance, declared last on purpose: an ARG or LABEL placed above the layers would
# re-key them on every commit and throw away the caching this file just bought.
# GIT_SHA is the commit the build context came from; the stamp is what P-8 ("is the
# image under test the same source as the tree under test?") reads instead of
# comparing a UTC `Created` timestamp against a committer date. Without it an operator
# who forgets to pass GIT_SHA still gets a truthful "unknown" instead of a wrong hash.
ARG GIT_SHA=unknown
ARG BUILT_AT=unknown
LABEL org.opencontainers.image.revision=${GIT_SHA}
RUN printf 'revision=%s\nbuilt_at=%s\n' "$GIT_SHA" "$BUILT_AT" > /app/BUILD_INFO

USER 10001:10001

VOLUME ["/app/documents", "/app/data", "/app/static", "/app/logs", "/app/chroma_db"]

EXPOSE 8001

HEALTHCHECK --interval=20s --timeout=5s --start-period=45s --retries=5 \
    CMD ["python", "-c", "import sys,urllib.request; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8001/api/v1/health', timeout=4).status == 200 else 1)"]

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8001"]
