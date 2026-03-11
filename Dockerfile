FROM python:3.11-slim

WORKDIR /app

RUN pip install --no-cache-dir uv

COPY pyproject.toml .python-version README.md ./
COPY apps ./apps
COPY packages ./packages
COPY data ./data
COPY docs ./docs

RUN uv sync --all-packages --no-dev

EXPOSE 8000

CMD ["uv", "run", "--package", "webapp", "uvicorn", "webapp.main:app", "--host", "0.0.0.0", "--port", "8000"]
