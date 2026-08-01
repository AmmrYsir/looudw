FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    HOST=0.0.0.0 \
    PORT=8000

WORKDIR /app

# Install system build tools required by libcurl/curl-cffi
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libffi-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy project definition, static assets, and source code
COPY pyproject.toml README.md AGENTS.md ./
COPY src/ src/
COPY public/ public/

# Upgrade pip and install loouwd package and dependencies
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir .

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/api/v1/sources || exit 1

CMD ["loouwd", "serve", "--host", "0.0.0.0", "--port", "8000"]
