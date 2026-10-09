# Pitlane

Учебный сайт аренды спорткаров с ИИ-консьержем. Сайт — каталог, страница машины, бронь, оплата (демо) и «Мои брони». Консьерж — чат в углу любой страницы: подбирает машину, считает цену и готовит черновики действий. Принцип: **агент предлагает, клиент подтверждает** — кнопкой в карточке, мимо агента.

| Папка | Что там |
|---|---|
| `frontend/` | Сайт: React + Vite, компоненты из дизайн-системы |
| `backend/` | FastAPI + SQLite: REST API, MCP-сервер (`/mcp`), чат-агент на Gemini — см. [backend/README.md](backend/README.md) |
| `design-system/` | Дизайн-система: токены и компоненты (`CarCard`, `BookingSummary`, `AgentAction`…) |
| `docs/mcp-tools.md` | Инструменты агента и правила подтверждения |

## Запуск в Docker

Нужен `.env` в корне с ключом Gemini:

```
GEMINI_API_KEY=…
```

```bash
docker compose up --build
```

Сайт: http://localhost:8000. База лежит в томе `pitlane-data` и переживает пересборку. Вход — тестовые клиенты без пароля (список в [backend/README.md](backend/README.md)).

## Разработка

```bash
cd backend && python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/uvicorn app.main:app --reload --port 8000
```

```bash
cd frontend && npm install && npm run dev
```

Сайт с горячей перезагрузкой — http://localhost:5173 (запросы `/api` проксируются на :8000). Тесты бэкенда: `cd backend && .venv/bin/pytest`.
