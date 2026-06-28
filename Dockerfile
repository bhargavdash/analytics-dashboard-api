FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app

# Install dependencies — layer cached until pyproject.toml/uv.lock change
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

# Copy application source
COPY app/ ./app/

# Generate the pre-seeded demo warehouse during the build.
# start.sh copies this to DATA_DIR on first boot (if the volume is empty).
RUN uv run python -m app.db.seed

COPY start.sh ./start.sh
RUN chmod +x ./start.sh

ENV PATH="/app/.venv/bin:$PATH"

EXPOSE 8000

CMD ["./start.sh"]
