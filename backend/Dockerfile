FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_NO_CACHE=1 \
    PATH="/app/.venv/bin:$PATH"

RUN set -eux; \
    for source in /etc/apt/sources.list /etc/apt/sources.list.d/*.sources /etc/apt/sources.list.d/*.list; do \
        [ ! -f "$source" ] || sed -i 's|http://|https://|g' "$source"; \
    done; \
    packages="espeak-ng ffmpeg libgl1 libglib2.0-0 libportaudio2 libsndfile1"; \
    attempt=1; \
    while [ "$attempt" -le 5 ]; do \
        if apt-get -o Acquire::Retries=5 -o Acquire::http::Timeout=30 update \
            && apt-get -o Acquire::Retries=5 -o Acquire::http::Timeout=30 \
                install --no-install-recommends -y $packages; then \
            break; \
        fi; \
        if [ "$attempt" -eq 5 ]; then \
            exit 1; \
        fi; \
        apt-get clean; \
        rm -rf /var/lib/apt/lists/*; \
        sleep "$((attempt * 2))"; \
        attempt="$((attempt + 1))"; \
    done; \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY . .

RUN useradd --create-home --uid 10001 studybuddy \
    && mkdir -p /app/data /app/inbox /home/studybuddy/.cache \
    && chown -R studybuddy:studybuddy /app /home/studybuddy

USER studybuddy

EXPOSE 8010

HEALTHCHECK --interval=30s --timeout=5s --start-period=90s --retries=5 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8010/api/health/live', timeout=4)"]

CMD ["python", "-m", "study_buddy"]
