FROM python:3.12-bookworm

ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONUNBUFFERED=1
ENV PORT=8000
ENV PLAYWRIGHT_BROWSERS_PATH=/ms-playwright

# Install runtime deps used by Playwright (bookworm packages)
RUN apt-get update \
  && apt-get install -y --no-install-recommends \
    ca-certificates curl wget gnupg libnss3 libatk1.0-0 libcups2 \
    libx11-6 libxcomposite1 libxdamage1 libxrandr2 libasound2 \
    libpango-1.0-0 libxkbcommon0 libgbm1 libxshmfence1 libgtk-3-0 \
    libgdk-pixbuf-xlib-2.0-0 fonts-liberation libnspr4 libxcb1 \
    libx11-xcb1 libxss1 libxtst6 ffmpeg build-essential \
  && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install python deps and playwright & browsers into /ms-playwright
COPY requirements.txt /app/requirements.txt
RUN python -m pip install --upgrade pip setuptools wheel \
 && pip install -r /app/requirements.txt \
 && python -m pip install playwright \
 && python -m playwright install --with-deps chromium \
 && mkdir -p /ms-playwright \
 && chown -R root:root /ms-playwright \
 && chmod -R a+rX /ms-playwright

# Copy app
COPY . /app

# Create non-root user and fix permissions
RUN useradd --create-home appuser || true
RUN chown -R appuser:appuser /app
USER appuser

EXPOSE 8000

# Start server — adjust import path if needed (src.app:app)
CMD ["sh", "-c", "gunicorn -w 1 -b 0.0.0.0:$PORT \"src.app:app\" --timeout 300 --log-level info"]
