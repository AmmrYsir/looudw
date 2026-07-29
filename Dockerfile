FROM python:3.12-slim

WORKDIR /app

# Install dependencies and build package
COPY pyproject.toml README.md /app/
COPY src /app/src

RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir .

EXPOSE 8000

CMD ["loouwd", "serve", "--host", "0.0.0.0", "--port", "8000"]
