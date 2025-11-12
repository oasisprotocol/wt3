FROM python:3.11.11-slim

WORKDIR /app

COPY --from=ghcr.io/astral-sh/uv:0.9.8 /uv /uvx /bin/

COPY pyproject.toml uv.lock* README.md ./

RUN uv sync --frozen --no-cache

COPY . .

ENV PYTHONPATH="/app"

CMD ["uv", "run", "python", "-m", "src.wt3"]
