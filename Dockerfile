FROM python:3.13-slim-bookworm

ARG TECTONIC_VERSION=0.17.0
ARG TECTONIC_SHA256=8533d07f9ccbd7a65824b9e0459041bca34af1eb33daba48f59215593753a3b7

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    TECTONIC_BIN=/usr/local/bin/tectonic \
    TECTONIC_CACHE_DIR=/var/cache/tectonic \
    BROWSER_PATH=/usr/bin/chromium

RUN apt-get update \
    && apt-get install --yes --no-install-recommends \
        ca-certificates \
        chromium \
        curl \
        fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*

RUN curl --fail --location --silent --show-error \
        --proto '=https' --proto-redir '=https' \
        "https://github.com/tectonic-typesetting/tectonic/releases/download/tectonic%40${TECTONIC_VERSION}/tectonic-${TECTONIC_VERSION}-x86_64-unknown-linux-musl.tar.gz" \
        --output /tmp/tectonic.tar.gz \
    && printf '%s  %s\n' "${TECTONIC_SHA256}" /tmp/tectonic.tar.gz | sha256sum --check --strict \
    && tar --extract --gzip --file /tmp/tectonic.tar.gz --directory /usr/local/bin tectonic \
    && chmod 0755 /usr/local/bin/tectonic \
    && rm /tmp/tectonic.tar.gz \
    && tectonic --version

ENV HOME=/tmp/app-home

RUN mkdir --parents /var/cache/tectonic /tmp/app-home \
    && chmod 0777 /var/cache/tectonic /tmp/app-home

WORKDIR /app

COPY pyproject.toml README.md ./
COPY finance_analysis/ finance_analysis/
COPY scripts/ scripts/
COPY config/ config/

RUN python3 -m pip install --no-cache-dir .

RUN chmod --recursive a+rX /app/config /app/finance_analysis /app/scripts

CMD ["python3", "scripts/run_pipeline.py"]
