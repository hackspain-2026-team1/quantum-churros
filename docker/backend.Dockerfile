FROM ghcr.io/astral-sh/uv:0.8.15-python3.12-bookworm-slim
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
COPY pyproject.toml uv.lock ./
COPY backend ./backend
COPY engine ./engine
COPY params ./params
RUN uv sync --locked --package quantum-churros-api --no-dev
USER nobody
EXPOSE 8000
CMD ["sh", "-c", "uv run --locked --package quantum-churros-api alembic -c backend/alembic.ini upgrade head && uv run --locked --package quantum-churros-api uvicorn app.main:app --host 0.0.0.0 --port 8000"]
