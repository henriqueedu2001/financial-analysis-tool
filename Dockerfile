FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    STREAMLIT_BROWSER_GATHER_USAGE_STATS=false

WORKDIR /app

COPY pyproject.toml README.md app.py ./
COPY finance ./finance
COPY pages ./pages
COPY config ./config
COPY examples ./examples

RUN python -m pip install --no-cache-dir . \
    && useradd --create-home --uid 1000 appuser \
    && mkdir -p /app/data/inbox /app/data/raw /app/data/processed /app/data/rejected \
    && chown -R appuser:appuser /app/data

USER appuser

EXPOSE 8501

HEALTHCHECK --interval=10s --timeout=3s --start-period=15s --retries=3 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8501/_stcore/health', timeout=2)"]

CMD ["streamlit", "run", "app.py", "--server.address=0.0.0.0", "--server.port=8501", "--server.headless=true"]
