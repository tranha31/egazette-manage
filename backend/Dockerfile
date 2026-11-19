# syntax=docker/dockerfile:1
# Backend Egazette: Flask API + worker crawl (Playwright/Chromium) + tách PDF. Build từ thư mục backend/ (xem docker-compose.yml).
ARG PYTHON_VERSION=3.14
FROM python:${PYTHON_VERSION}-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright \
    HOST=0.0.0.0 \
    PDF_FONT_DIR=/fonts

WORKDIR /app

# Thư viện Python (bỏ pytest: image chạy thật không cần). Chromium của Playwright + các gói hệ thống nó cần,
# và Xvfb để chạy Chromium có giao diện trong container (ổn định hơn headless với reCAPTCHA).
# libatomic1: driver Node của Playwright cần nó để chạy (Debian slim không có sẵn, nên phải cài trước `playwright install`)
RUN apt-get update \
 && apt-get install -y --no-install-recommends libatomic1 xvfb xauth \
 && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN grep -v -i '^pytest' requirements.txt > /tmp/req.txt \
 && pip install -r /tmp/req.txt \
 && playwright install --with-deps chromium \
 && rm -rf /var/lib/apt/lists/* /tmp/req.txt

RUN useradd --create-home --uid 10001 app
COPY app ./app
COPY run.py docker-entrypoint.sh ./
RUN chmod 0755 docker-entrypoint.sh && chown -R app:app /app
USER app

EXPOSE 8000
HEALTHCHECK --interval=15s --timeout=5s --start-period=40s --retries=5 \
  CMD python -c "import socket; socket.create_connection(('127.0.0.1', 8000), 3).close()"
ENTRYPOINT ["./docker-entrypoint.sh"]
CMD ["python", "run.py"]
