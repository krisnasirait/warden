FROM python:3.13-slim

WORKDIR /app

COPY pyproject.toml README.md ./
COPY bot ./bot
COPY migrations ./migrations

RUN pip install --no-cache-dir .

CMD ["python", "-m", "bot.main"]
