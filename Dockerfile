FROM python:3.12-slim
COPY --from=ghcr.io/astral-sh/uv:0.11.32 /uv /usr/local/bin/uv
WORKDIR /app
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --no-dev --no-install-project
COPY promptsmith ./promptsmith
RUN uv sync --frozen --no-dev
ENV HOST=0.0.0.0 PORT=8000 PROMPTSMITH_DB=/data/promptsmith.db
RUN mkdir -p /data
EXPOSE 8000
CMD ["uv", "run", "--no-dev", "promptsmith"]
