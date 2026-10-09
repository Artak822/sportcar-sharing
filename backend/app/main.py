"""REST API Pitlane. Запуск: uvicorn app.main:app --reload (из папки backend)."""
import secrets
from contextlib import asynccontextmanager
from datetime import timedelta
from pathlib import Path
from typing import Literal

from fastapi import Depends, FastAPI, Query, Request, Response
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field

from . import db as database
from . import services as s
from .services import ServiceError

SESSION_COOKIE = "pitlane_session"
WEB_SESSION_DAYS = 30
AGENT_TOKEN_HOURS = 2
ROOT = Path(__file__).resolve().parents[2]



@asynccontextmanager
async def lifespan(_: FastAPI):
    from .seed import seed
    conn = database.connect()
    database.init(conn)
    seed(conn)
    conn.close()
    yield


app = FastAPI(title="Pitlane API", version="0.1.0", lifespan=lifespan)


@app.exception_handler(ServiceError)
def service_error(_: Request, e: ServiceError) -> JSONResponse:
    return JSONResponse({"error": {"code": e.code, "message": e.message}}, status_code=e.status)


# ——— Зависимости ———

def get_db(request: Request):
    """Одно соединение на запрос. Изменяющие запросы идут в транзакции BEGIN IMMEDIATE,
    поэтому две брони одной машины не подтвердятся одновременно."""
    conn = database.connect()
    try:
        s.housekeeping(conn)
        if request.method != "GET":
            conn.execute("BEGIN IMMEDIATE")
        yield conn
        if conn.in_transaction:
            conn.execute("COMMIT")
    except BaseException:
        if conn.in_transaction:
            conn.execute("ROLLBACK")
        raise
    finally:
        conn.close()


def optional_user(request: Request, db=Depends(get_db)) -> dict | None:
    auth = request.headers.get("authorization", "")
    token = auth[7:] if auth.lower().startswith("bearer ") else request.cookies.get(SESSION_COOKIE)
    if not token:
        return None
    row = db.execute(
        "SELECT u.id, u.name, u.email, ss.scope FROM sessions ss JOIN users u ON u.id = ss.user_id"
        " WHERE ss.token = ? AND ss.expires_at > ?", (token, s.iso(s.now()))).fetchone()
    return dict(row) if row else None


def require_user(user=Depends(optional_user)) -> dict:
    if not user:
        raise ServiceError("unauthorized", "Войдите в аккаунт", 401)
    return user


def require_web(user=Depends(require_user)) -> dict:
    """Подтверждать действия и платить может только сам клиент из браузера, не агент."""
    if user["scope"] != "web":
        raise ServiceError("forbidden_for_agent", "Это действие доступно только клиенту в браузере", 403)
    return user


def create_session(db, user_id: int, scope: str, ttl: timedelta) -> str:
    token = secrets.token_urlsafe(32)
    db.execute("INSERT INTO sessions VALUES (?,?,?,?)", (token, user_id, scope, s.iso(s.now() + ttl)))
    return token


# ——— Модели запросов ———

class Period(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    start: str = Field(alias="from", examples=["2026-10-17T10:00"])
    end: str = Field(alias="to", examples=["2026-10-19T10:00"])


class QuoteIn(Period):
    car_id: str
    extras: list[str] = []


class LoginIn(BaseModel):
    email: str


class ProposeIn(BaseModel):
    tool: Literal["create_booking", "change_booking_dates", "update_booking_extras", "cancel_booking", "request_manager"]
    params: dict = {}


# ——— Каталог: доступен без входа ———

@app.get("/api/cars")
def search_cars(start: str | None = Query(None, alias="from"), end: str | None = Query(None, alias="to"),
                body_type: Literal["coupe", "cabriolet", "sedan"] | None = None,
                max_price_per_day: int | None = None, min_power: int | None = None, seats: int | None = None,
                brand: str | None = None, sort: Literal["price", "power", "accel"] = "price",
                limit: int = Query(6, ge=1, le=50), db=Depends(get_db)):
    return s.search_cars(db, start, end, body_type, max_price_per_day, min_power, seats, brand, sort, limit)


@app.get("/api/cars/{car_id}")
def get_car(car_id: str, db=Depends(get_db)):
    return s.get_car(db, car_id)


@app.get("/api/cars/{car_id}/availability")
def check_availability(car_id: str, start: str = Query(alias="from"), end: str = Query(alias="to"), db=Depends(get_db)):
    return s.check_availability(db, car_id, start, end)


@app.post("/api/quote")
def quote_price(body: QuoteIn, db=Depends(get_db)):
    return s.quote(db, body.car_id, body.start, body.end, body.extras)


@app.get("/api/extras")
def list_extras(db=Depends(get_db)):
    return s.list_extras(db)


@app.get("/api/locations")
def list_locations(db=Depends(get_db)):
    return s.list_locations(db)


@app.get("/api/terms")
def rental_terms(topic: str | None = None):
    return s.get_rental_terms(topic)


# ——— Вход ———

@app.post("/api/auth/login")
def login(body: LoginIn, response: Response, db=Depends(get_db)):
    """Демо-вход по почте без пароля — только для учебного проекта."""
    user = db.execute("SELECT id, name FROM users WHERE lower(email) = lower(?)", (body.email,)).fetchone()
    if not user:
        raise ServiceError("unknown_user", "Нет такого пользователя", 401)
    token = create_session(db, user["id"], "web", timedelta(days=WEB_SESSION_DAYS))
    response.set_cookie(SESSION_COOKIE, token, httponly=True, samesite="lax", max_age=WEB_SESSION_DAYS * 86400)
    return {"id": user["id"], "name": user["name"]}


@app.post("/api/auth/logout")
def logout(request: Request, response: Response, db=Depends(get_db)):
    db.execute("DELETE FROM sessions WHERE token = ?", (request.cookies.get(SESSION_COOKIE),))
    response.delete_cookie(SESSION_COOKIE)
    return {"ok": True}


@app.post("/api/agent/token")
def agent_token(user=Depends(require_web), db=Depends(get_db)):
    """Браузер выдаёт агенту токен того же клиента, но с урезанными правами (scope agent)."""
    token = create_session(db, user["id"], "agent", timedelta(hours=AGENT_TOKEN_HOURS))
    return {"token": token, "expires_in": AGENT_TOKEN_HOURS * 3600}


# ——— Клиент ———

@app.get("/api/me/status")
def my_status(user=Depends(require_user), db=Depends(get_db)):
    return s.profile_status(db, user)


@app.get("/api/bookings")
def my_bookings(status: Literal["upcoming", "active", "past"] | None = None,
                user=Depends(require_user), db=Depends(get_db)):
    return s.list_bookings(db, user, status)


@app.get("/api/bookings/{ref}")
def booking(ref: str, user=Depends(require_user), db=Depends(get_db)):
    return s.get_booking(db, user, ref)


@app.post("/api/bookings/{ref}/pay")
def pay(ref: str, user=Depends(require_web), db=Depends(get_db)):
    return s.pay_booking(db, user, ref)


# ——— Действия агента ———

@app.post("/api/actions", status_code=201)
def propose(body: ProposeIn, user=Depends(require_user), db=Depends(get_db)):
    return s.propose_action(db, user, body.tool, body.params)


@app.get("/api/actions/{action_id}")
def action(action_id: str, user=Depends(require_user), db=Depends(get_db)):
    return s.get_action(db, user, action_id)


@app.post("/api/actions/{action_id}/confirm")
def confirm(action_id: str, user=Depends(require_web), db=Depends(get_db)):
    return s.confirm_action(db, user, action_id)


@app.post("/api/actions/{action_id}/cancel")
def cancel(action_id: str, user=Depends(require_web), db=Depends(get_db)):
    return s.cancel_action(db, user, action_id)


# Фронтенд с того же адреса — чтобы cookie сессии работала без CORS
app.mount("/design-system", StaticFiles(directory=ROOT / "design-system", html=True), name="design-system")
app.mount("/prototype", StaticFiles(directory=ROOT / "prototype", html=True), name="prototype")
