FROM node:22-slim AS chat-web-build

WORKDIR /frontend/apps/chat_web

COPY apps/chat_web/package.json apps/chat_web/package-lock.json ./
RUN npm ci

COPY apps/chat_web ./
RUN npm run build


FROM python:3.11-slim

WORKDIR /app

RUN pip install --no-cache-dir uv

COPY pyproject.toml .python-version README.md ./
COPY apps ./apps
COPY packages ./packages
COPY data ./data
COPY docs ./docs
COPY --from=chat-web-build /frontend/apps/chat_web/out ./apps/chat_web/out

RUN uv sync --all-packages --no-dev

EXPOSE 8000

CMD ["uv", "run", "--package", "webapp", "uvicorn", "webapp.main:app", "--host", "0.0.0.0", "--port", "8000"]
