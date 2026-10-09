# Pitlane: один контейнер — FastAPI раздаёт API, MCP (/mcp) и собранный сайт.

# 1. Сборка сайта. Нужна дизайн-система: сайт импортирует её из ../design-system
FROM node:26-slim AS site
WORKDIR /app
COPY design-system ./design-system
COPY frontend/package.json frontend/package-lock.json ./frontend/
RUN npm --prefix frontend ci
COPY frontend ./frontend
RUN npm --prefix frontend run build

# 2. Бэкенд
FROM python:3.14-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PITLANE_DB=/data/pitlane.db
WORKDIR /app
COPY backend/requirements.txt ./backend/
RUN pip install --no-cache-dir -r backend/requirements.txt
COPY backend ./backend
COPY design-system ./design-system
COPY prototype ./prototype
COPY --from=site /app/frontend/dist ./frontend/dist
RUN useradd --create-home pitlane && mkdir /data && chown pitlane /data
USER pitlane
VOLUME /data
EXPOSE 8000
WORKDIR /app/backend
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
