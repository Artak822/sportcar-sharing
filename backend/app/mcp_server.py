"""MCP-сервер Pitlane: инструменты, через которые агент работает с сайтом.

Подключение: http://localhost:8000/mcp, заголовок `Authorization: Bearer <токен>`.
Токен агента выдаёт `POST /api/agent/token`. Агент читает и предлагает действия —
инструмента «подтвердить» здесь нет: подтверждает только клиент кнопкой в чате.
"""
from contextlib import contextmanager
from typing import Annotated, Literal

from mcp.server.mcpserver import Context, MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import ToolAnnotations
from pydantic import Field

from . import db as database
from . import services as s

mcp = MCPServer(
    "pitlane",
    title="Pitlane — аренда спорткаров",
    instructions="Каталог, цены и брони Pitlane. Изменяющие инструменты создают черновик, "
                 "который клиент подтверждает сам. Время — московское, формат 2026-10-17T10:00.",
)

READ = ToolAnnotations(readOnlyHint=True, openWorldHint=False)
PROPOSE = ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=False, openWorldHint=False)

DateTime = Annotated[str, Field(description="Локальное время, формат 2026-10-17T10:00")]
BookingRef = Annotated[str, Field(description="Номер брони вида PL-2401")]
ExtraCodes = Annotated[list[str], Field(description="Коды услуг из list_extras")]


@contextmanager
def _db(write: bool = False):
    """Как get_db в REST API: изменения — в транзакции BEGIN IMMEDIATE, ошибки сервиса — в текст для модели."""
    conn = database.connect()
    try:
        s.housekeeping(conn)
        if write:
            conn.execute("BEGIN IMMEDIATE")
        yield conn
        if conn.in_transaction:
            conn.execute("COMMIT")
    except s.ServiceError as e:
        if conn.in_transaction:
            conn.execute("ROLLBACK")
        raise ToolError(e.message) from e
    except BaseException:
        if conn.in_transaction:
            conn.execute("ROLLBACK")
        raise
    finally:
        conn.close()


def _user(db, ctx: Context) -> dict:
    auth = (ctx.headers or {}).get("authorization", "")
    token = auth[7:] if auth.lower().startswith("bearer ") else None
    row = token and db.execute(
        "SELECT u.id, u.name, ss.scope FROM sessions ss JOIN users u ON u.id = ss.user_id"
        " WHERE ss.token = ? AND ss.expires_at > ?", (token, s.iso(s.now()))).fetchone()
    if not row:
        raise ToolError("Клиент не вошёл в аккаунт — попросите его войти на сайте")
    return dict(row)


def _propose(ctx: Context, tool: str, params: dict) -> dict:
    with _db(write=True) as db:
        return s.propose_action(db, _user(db, ctx), tool, params)


# ——— Каталог ———

@mcp.tool(annotations=READ)
def search_cars(
    date_from: DateTime | None = None, date_to: DateTime | None = None,
    body_type: Literal["coupe", "cabriolet", "sedan"] | None = None,
    max_price_per_day: int | None = None, min_power: Annotated[int | None, Field(description="л. с.")] = None,
    seats: int | None = None, brand: str | None = None,
    sort: Literal["price", "power", "accel"] = "price", limit: int = 6,
) -> list[dict]:
    """Найти машины по фильтрам. Если переданы даты, у занятых машин status = booked."""
    with _db() as db:
        return s.search_cars(db, date_from, date_to, body_type, max_price_per_day, min_power, seats, brand, sort, limit)


@mcp.tool(annotations=READ)
def get_car(car_id: str) -> dict:
    """Карточка машины: характеристики, депозит, лимит пробега, требования к водителю."""
    with _db() as db:
        return s.get_car(db, car_id)


@mcp.tool(annotations=READ)
def check_availability(car_id: str, date_from: DateTime, date_to: DateTime) -> dict:
    """Свободна ли машина на даты; если нет — когда освободится."""
    with _db() as db:
        return s.check_availability(db, car_id, date_from, date_to)


@mcp.tool(annotations=READ)
def quote_price(car_id: str, date_from: DateTime, date_to: DateTime, extras: ExtraCodes | None = None) -> dict:
    """Посчитать стоимость аренды. Неполные сутки округляются вверх."""
    with _db() as db:
        return s.quote(db, car_id, date_from, date_to, extras)


@mcp.tool(annotations=READ)
def list_extras() -> list[dict]:
    """Доп. услуги: страховка, второй водитель, детское кресло, доставка."""
    with _db() as db:
        return s.list_extras(db)


@mcp.tool(annotations=READ)
def list_locations() -> list[dict]:
    """Точки выдачи машин."""
    with _db() as db:
        return s.list_locations(db)


@mcp.tool(annotations=READ)
def get_rental_terms(topic: Literal["deposit", "mileage", "fines", "age", "cancellation"] | None = None) -> dict:
    """Условия аренды: депозит, пробег, штрафы, возраст и стаж, отмена."""
    with _db():
        return s.get_rental_terms(topic)


# ——— Клиент ———

@mcp.tool(annotations=READ)
def get_my_profile_status(ctx: Context) -> dict:
    """Проверены ли документы и телефон клиента — без этого бронь не подтвердить."""
    with _db() as db:
        return s.profile_status(db, _user(db, ctx))


@mcp.tool(annotations=READ)
def list_my_bookings(ctx: Context, status: Literal["upcoming", "active", "past"] | None = None) -> list[dict]:
    """Брони клиента."""
    with _db() as db:
        return s.list_bookings(db, _user(db, ctx), status)


@mcp.tool(annotations=READ)
def get_booking(ctx: Context, booking_id: BookingRef) -> dict:
    """Одна бронь клиента по номеру."""
    with _db() as db:
        return s.get_booking(db, _user(db, ctx), booking_id)


@mcp.tool(annotations=READ)
def get_action(ctx: Context, action_id: str) -> dict:
    """Статус черновика: proposed, done, failed, cancelled или expired."""
    with _db() as db:
        return s.get_action(db, _user(db, ctx), action_id)


# ——— Действия: только черновики ———

@mcp.tool(annotations=PROPOSE)
def create_booking(ctx: Context, car_id: str, date_from: DateTime, date_to: DateTime,
                   location_id: Annotated[str, Field(description="id из list_locations")],
                   extras: ExtraCodes | None = None) -> dict:
    """Предложить бронь. Создаёт черновик — клиент увидит карточку и подтвердит сам."""
    return _propose(ctx, "create_booking", {"car_id": car_id, "from": date_from, "to": date_to,
                                            "location_id": location_id, "extras": extras or []})


@mcp.tool(annotations=PROPOSE)
def change_booking_dates(ctx: Context, booking_id: BookingRef, date_from: DateTime, date_to: DateTime) -> dict:
    """Предложить перенос брони на другие даты. Создаёт черновик."""
    return _propose(ctx, "change_booking_dates", {"booking_id": booking_id, "from": date_from, "to": date_to})


@mcp.tool(annotations=PROPOSE)
def update_booking_extras(ctx: Context, booking_id: BookingRef,
                          add: ExtraCodes | None = None, remove: ExtraCodes | None = None) -> dict:
    """Предложить добавить или убрать услуги в брони. Создаёт черновик."""
    return _propose(ctx, "update_booking_extras", {"booking_id": booking_id, "add": add or [], "remove": remove or []})


@mcp.tool(annotations=PROPOSE)
def cancel_booking(ctx: Context, booking_id: BookingRef, reason: str | None = None) -> dict:
    """Предложить отмену брони. Создаёт черновик."""
    return _propose(ctx, "cancel_booking", {"booking_id": booking_id, "reason": reason})


@mcp.tool(annotations=PROPOSE)
def request_manager(ctx: Context, topic: str, message: Annotated[str, Field(description="Суть вопроса для менеджера")]) -> dict:
    """Предложить передать вопрос живому менеджеру: ДТП, споры, то, что агент не может решить. Создаёт черновик."""
    return _propose(ctx, "request_manager", {"topic": topic, "message": message})
