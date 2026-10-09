# Pitlane API

FastAPI + SQLite. Бизнес-логика в `app/services.py`: её вызывают REST API, MCP-сервер агента (`app/mcp_server.py`, `/mcp`) и чат (`app/agent.py`, Gemini).

## Запуск

```bash
cd backend
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/uvicorn app.main:app --reload --port 8000
```

- Ключ Gemini — в корневом `.env`: `GEMINI_API_KEY=…`; модели можно сменить через `GEMINI_MODEL` и `GEMINI_FALLBACK_MODEL`
- Документация API: http://localhost:8000/docs
- Сайт в режиме разработки — `frontend/` (см. корневой README); если собран `frontend/dist`, API раздаёт его сам
- Прототип чата: http://localhost:8000/prototype/chat.html
- База — файл `backend/pitlane.db`, создаётся и заполняется при первом запуске. Сбросить: `.venv/bin/python -m app.seed --reset`
- Тесты: `.venv/bin/pytest`

Тестовые пользователи (вход по почте без пароля, только для учебного проекта):

| Почта | Что за клиент |
|---|---|
| demo@pitlane.test | Документы проверены, можно бронировать |
| new@pitlane.test | Права не загружены — бронь не подтвердится |
| other@pitlane.test | Держит Porsche Boxster на ближайшие выходные |

## Сессии и права

| scope | Кто | Что может |
|---|---|---|
| `web` | Браузер клиента (cookie `pitlane_session`) | Всё, включая подтверждение действий и оплату |
| `agent` | Чат-агент (`Authorization: Bearer …`, выдаёт `POST /api/agent/token`, живёт 2 часа) | Читать и **предлагать** действия. Подтверждать, отменять черновики и платить — 403 |

Чужие брони и действия возвращают 404, как несуществующие.

## Эндпоинты и MCP-инструменты

| MCP-инструмент | Эндпоинт | Вход |
|---|---|---|
| `search_cars` | `GET /api/cars?from&to&body_type&max_price_per_day&min_power&seats&brand&sort&limit` | — |
| `get_car` | `GET /api/cars/{car_id}` | — |
| `check_availability` | `GET /api/cars/{car_id}/availability?from&to` | — |
| `quote_price` | `POST /api/quote` `{car_id, from, to, extras}` | — |
| `list_extras` | `GET /api/extras` | — |
| `list_locations` | `GET /api/locations` | — |
| `get_rental_terms` | `GET /api/terms?topic` | — |
| `get_my_profile_status` | `GET /api/me/status` | нужен |
| `list_my_bookings` | `GET /api/bookings?status=upcoming\|active\|past` | нужен |
| `get_booking` | `GET /api/bookings/{id или PL-номер}` | нужен |
| `create_booking`, `change_booking_dates`, `update_booking_extras`, `cancel_booking`, `request_manager` | `POST /api/actions` `{tool, params}` → черновик `proposed` | нужен |
| — (только кнопка в чате) | `POST /api/actions/{id}/confirm`, `/cancel` | только `web` |
| — (страница оплаты) | `POST /api/bookings/{id}/pay` — заглушка, сразу помечает оплаченной | только `web` |

Чат: `GET /api/chat` — история, `POST /api/chat` `{message, page?}` — ход агента (503 `agent_unavailable`, если модель не ответила), `DELETE /api/chat` — новый разговор. Только `web`.

`summary` черновика — это готовые пропсы для `AgentAction`: `title`, `details`, `note`.

## Правила, которые держит сервер

- Цену считает только сервер, при подтверждении — заново.
- Черновик живёт 15 минут, неоплаченная бронь держит машину 30 минут — потом `expired`.
- Подтверждение идёт в транзакции `BEGIN IMMEDIATE`: два черновика на одни даты не превратятся в две брони, второй получит `failed`.
- Ошибка при выполнении — не исключение, а статус `failed` с текстом в `error`.
- Оплаченную бронь бесплатно отменить можно не позже чем за 24 часа.
- Время — локальное московское, формат `2026-10-17T10:00`. Неполные сутки округляются вверх.
