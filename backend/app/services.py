"""Бизнес-логика Pitlane. Её вызывают REST API и MCP-сервер агента.

Пользователь всегда приходит из сессии (аргумент `user`), а не из параметров запроса.
"""
import json
import math
import secrets
import sqlite3
from datetime import datetime, timedelta

HOLD_MINUTES = 30          # сколько бронь ждёт оплаты
ACTION_TTL_MINUTES = 15    # сколько живёт черновик действия агента
FREE_CANCEL_HOURS = 24     # бесплатная отмена — не позже чем за сутки
BLOCKING = ("pending_payment", "paid", "active")  # брони, которые занимают машину

NBSP = " "
WEEKDAYS = ["пн", "вт", "ср", "чт", "пт", "сб", "вс"]
MONTHS = ["янв", "фев", "мар", "апр", "мая", "июн", "июл", "авг", "сен", "окт", "ноя", "дек"]

TERMS = {
    "deposit": "Депозит зависит от машины: от 80 000 до 200 000 ₽. Его блокируем на карте при выдаче "
               "и снимаем блокировку в течение 3 рабочих дней после сдачи, если нет штрафов и повреждений.",
    "mileage": "В сутки включено 300 км. Каждый километр сверх лимита — 50 ₽.",
    "fines": "Штрафы за нарушения ПДД во время аренды оплачивает клиент. Мы пересылаем их в течение "
             "5 дней после получения и удерживаем сумму из депозита, если клиент не оплатил сам.",
    "age": "Минимальный возраст — 23 года, стаж — от 3 лет. Для машин дороже 40 000 ₽ в сутки — от 25 лет.",
    "cancellation": "Неоплаченную бронь можно отменить в любой момент. Оплаченную — бесплатно не позже "
                    "чем за 24 часа до начала аренды, позже отмена через менеджера.",
}


class ServiceError(Exception):
    def __init__(self, code: str, message: str, status: int = 400):
        super().__init__(message)
        self.code, self.message, self.status = code, message, status


# ——— Время, деньги, форматирование ———

def now() -> datetime:
    return datetime.now().replace(second=0, microsecond=0)


def iso(dt: datetime) -> str:
    return dt.isoformat(timespec="minutes")


def parse_dt(value: str, field: str = "дата") -> datetime:
    try:
        return datetime.fromisoformat(value).replace(second=0, microsecond=0, tzinfo=None)
    except (TypeError, ValueError):
        raise ServiceError("bad_date", f"Не понял {field}: {value!r}. Нужен формат 2026-10-17T10:00")


def rub(n: int) -> str:
    return f"{n:,}".replace(",", NBSP) + NBSP + "₽"


def human_dt(value: str) -> str:
    d = datetime.fromisoformat(value)
    return f"{WEEKDAYS[d.weekday()]}, {d.day} {MONTHS[d.month - 1]}, {d:%H:%M}"


def human_period(start: str, end: str) -> str:
    return f"{human_dt(start)} — {human_dt(end)}"


def booking_number(booking_id: int) -> str:
    return f"PL-{2400 + booking_id}"


def housekeeping(db: sqlite3.Connection) -> None:
    """Просроченные неоплаченные брони и черновики действий помечаем истёкшими."""
    t = iso(now())
    db.execute("UPDATE bookings SET status = 'expired' WHERE status = 'pending_payment' AND hold_until <= ?", (t,))
    db.execute("UPDATE actions SET status = 'expired' WHERE status = 'proposed' AND expires_at <= ?", (t,))


# ——— Каталог ———

def _car_row(db, car_id: str) -> sqlite3.Row:
    row = db.execute("SELECT * FROM cars WHERE id = ?", (car_id,)).fetchone()
    if not row:
        raise ServiceError("car_not_found", f"Машины {car_id!r} нет в каталоге", 404)
    return row


def _period(start: str, end: str) -> tuple[str, str, int]:
    s, e = parse_dt(start, "дату выдачи"), parse_dt(end, "дату возврата")
    if e <= s:
        raise ServiceError("bad_period", "Дата возврата должна быть позже даты выдачи")
    if s < now():
        raise ServiceError("bad_period", "Дата выдачи уже прошла")
    return iso(s), iso(e), math.ceil((e - s) / timedelta(days=1))


def _conflicts(db, car_id: str, start: str, end: str, exclude_booking: int | None = None) -> list[sqlite3.Row]:
    q = (f"SELECT id, start_at, end_at FROM bookings WHERE car_id = ? AND status IN ({','.join('?' * len(BLOCKING))})"
         " AND start_at < ? AND end_at > ?")
    args = [car_id, *BLOCKING, end, start]
    if exclude_booking is not None:
        q += " AND id != ?"
        args.append(exclude_booking)
    return db.execute(q + " ORDER BY start_at", args).fetchall()


def _car_summary(row: sqlite3.Row, status: str | None = None) -> dict:
    return {
        "id": row["id"], "name": row["name"], "brand": row["brand"], "body_type": row["body_type"],
        "price_per_day": row["price_per_day"], "power": row["power"], "accel": row["accel"],
        "seats": row["seats"], "status": status or row["status"], "image_url": row["image_url"],
    }


def search_cars(db, start=None, end=None, body_type=None, max_price_per_day=None, min_power=None,
                seats=None, brand=None, sort="price", limit=6) -> list[dict]:
    where, args = [], []
    for cond, val in (("body_type = ?", body_type), ("price_per_day <= ?", max_price_per_day),
                      ("power >= ?", min_power), ("seats >= ?", seats), ("lower(brand) = lower(?)", brand)):
        if val is not None:
            where.append(cond)
            args.append(val)
    order = {"price": "price_per_day", "power": "power DESC", "accel": "accel"}.get(sort)
    if not order:
        raise ServiceError("bad_sort", "sort: price, power или accel")
    rows = db.execute(
        "SELECT * FROM cars" + (" WHERE " + " AND ".join(where) if where else "") + f" ORDER BY {order} LIMIT ?",
        [*args, max(1, min(int(limit), 50))],
    ).fetchall()
    period = _period(start, end) if start and end else None
    result = []
    for r in rows:
        status = r["status"]
        if status == "available" and period and _conflicts(db, r["id"], period[0], period[1]):
            status = "booked"
        result.append(_car_summary(r, status))
    return result


def get_car(db, car_id: str) -> dict:
    r = _car_row(db, car_id)
    return {
        **_car_summary(r), "deposit": r["deposit"], "mileage_limit_km": r["mileage_limit_km"],
        "min_age": r["min_age"], "min_experience": r["min_experience"],
    }


def check_availability(db, car_id: str, start: str, end: str, exclude_booking: int | None = None) -> dict:
    car = _car_row(db, car_id)
    s, e, _ = _period(start, end)
    if car["status"] == "service":
        return {"car_id": car_id, "available": False, "reason": "service", "busy": [], "next_available_from": None}
    busy = _conflicts(db, car_id, s, e, exclude_booking)
    return {
        "car_id": car_id, "available": not busy, "reason": "booked" if busy else None,
        "busy": [{"from": b["start_at"], "to": b["end_at"]} for b in busy],
        "next_available_from": busy[-1]["end_at"] if busy else None,
    }


def list_extras(db) -> list[dict]:
    return [dict(r) for r in db.execute("SELECT code, name, price, per FROM extras ORDER BY price DESC")]


def list_locations(db) -> list[dict]:
    return [dict(r) for r in db.execute("SELECT * FROM locations ORDER BY id")]


def get_rental_terms(topic: str | None = None) -> dict:
    if topic is None:
        return TERMS
    if topic not in TERMS:
        raise ServiceError("bad_topic", "topic: " + ", ".join(TERMS))
    return {topic: TERMS[topic]}


def quote(db, car_id: str, start: str, end: str, extras: list[str] | None = None) -> dict:
    car = _car_row(db, car_id)
    s, e, days = _period(start, end)
    codes = sorted(set(extras or []))
    known = {r["code"]: r for r in db.execute("SELECT * FROM extras")}
    unknown = [c for c in codes if c not in known]
    if unknown:
        raise ServiceError("bad_extra", "Нет таких услуг: " + ", ".join(unknown) + ". Есть: " + ", ".join(known))
    lines = [{"code": c, "label": known[c]["name"],
              "price": known[c]["price"] * (days if known[c]["per"] == "day" else 1)} for c in codes]
    base = car["price_per_day"] * days
    extras_total = sum(l["price"] for l in lines)
    return {
        "car_id": car_id, "car_name": car["name"], "from": s, "to": e, "days": days,
        "price_per_day": car["price_per_day"], "base": base, "extras": lines,
        "extras_total": extras_total, "total": base + extras_total, "deposit": car["deposit"],
    }


# ——— Клиент и его брони ———

def profile_status(db, user: dict) -> dict:
    u = db.execute("SELECT * FROM users WHERE id = ?", (user["id"],)).fetchone()
    missing = [name for name, ok in (("documents", u["documents_verified"]), ("phone", u["phone_verified"])) if not ok]
    return {"name": u["name"], "documents_verified": bool(u["documents_verified"]),
            "phone_verified": bool(u["phone_verified"]), "missing": missing}


def _booking_row(db, user: dict, ref) -> sqlite3.Row:
    ref = str(ref)
    col = "number" if ref.upper().startswith("PL-") else "id"
    row = db.execute(f"SELECT * FROM bookings WHERE {col} = ? AND user_id = ?",
                     (ref.upper() if col == "number" else ref, user["id"])).fetchone()
    if not row:  # чужая бронь выглядит так же, как несуществующая
        raise ServiceError("booking_not_found", f"Бронь {ref} не найдена", 404)
    return row


def _can_cancel_free(b: sqlite3.Row) -> bool:
    if b["status"] == "pending_payment":
        return True
    return b["status"] == "paid" and parse_dt(b["start_at"]) - now() >= timedelta(hours=FREE_CANCEL_HOURS)


def booking_view(db, b: sqlite3.Row) -> dict:
    car = db.execute("SELECT name FROM cars WHERE id = ?", (b["car_id"],)).fetchone()
    loc = db.execute("SELECT address FROM locations WHERE id = ?", (b["location_id"],)).fetchone()
    extras = db.execute(
        "SELECT be.code, e.name AS label, be.price FROM booking_extras be JOIN extras e USING (code)"
        " WHERE booking_id = ? ORDER BY be.code", (b["id"],)).fetchall()
    return {
        "id": b["id"], "number": b["number"], "car_id": b["car_id"], "car_name": car["name"],
        "location_id": b["location_id"], "location": loc["address"], "from": b["start_at"], "to": b["end_at"],
        "days": b["days"], "price_per_day": b["price_per_day"], "base": b["base"],
        "extras": [dict(e) for e in extras], "total": b["total"], "deposit": b["deposit"],
        "status": b["status"], "hold_until": b["hold_until"], "can_cancel_free": _can_cancel_free(b),
    }


def list_bookings(db, user: dict, status: str | None = None) -> list[dict]:
    t = iso(now())
    filters = {
        None: ("1", ()),
        "upcoming": ("status IN ('pending_payment', 'paid') AND start_at > ?", (t,)),
        "active": ("(status = 'active' OR (status = 'paid' AND start_at <= ? AND end_at > ?))", (t, t)),
        "past": ("(status IN ('completed', 'cancelled', 'expired') OR end_at <= ?)", (t,)),
    }
    if status not in filters:
        raise ServiceError("bad_status", "status: upcoming, active или past")
    cond, args = filters[status]
    rows = db.execute(f"SELECT * FROM bookings WHERE user_id = ? AND {cond} ORDER BY start_at DESC",
                      (user["id"], *args)).fetchall()
    return [booking_view(db, r) for r in rows]


def get_booking(db, user: dict, ref) -> dict:
    return booking_view(db, _booking_row(db, user, ref))


def pay_booking(db, user: dict, ref) -> dict:
    """Заглушка оплаты для учебного проекта: сразу помечает бронь оплаченной."""
    b = _booking_row(db, user, ref)
    if b["status"] != "pending_payment":
        raise ServiceError("not_payable", "Эту бронь нельзя оплатить: статус " + b["status"], 409)
    db.execute("UPDATE bookings SET status = 'paid', hold_until = NULL WHERE id = ?", (b["id"],))
    return get_booking(db, user, b["id"])


# ——— Действия агента: propose → confirm ———
# Каждый инструмент — пара функций: prepare (проверить и собрать карточку) и execute (выполнить после подтверждения).

def _require_free(db, car_id, start, end, exclude_booking=None):
    a = check_availability(db, car_id, start, end, exclude_booking)
    if not a["available"]:
        if a["reason"] == "service":
            raise ServiceError("car_unavailable", "Машина на обслуживании", 409)
        raise ServiceError("car_unavailable", f"Машина занята, свободна с {human_dt(a['next_available_from'])}", 409)


def _price_details(q: dict) -> list[dict]:
    d = [{"label": "Аренда", "value": f"{rub(q['price_per_day'])} × {q['days']}{NBSP}сут. = {rub(q['base'])}"}]
    d += [{"label": e["label"], "value": rub(e["price"])} for e in q["extras"]]
    d += [{"label": "Итого", "value": rub(q["total"])},
          {"label": "Депозит", "value": rub(q["deposit"]) + ", вернём после сдачи"}]
    return d


def _location(db, location_id: str) -> sqlite3.Row:
    loc = db.execute("SELECT * FROM locations WHERE id = ?", (location_id,)).fetchone()
    if not loc:
        ids = ", ".join(r["id"] for r in db.execute("SELECT id FROM locations"))
        raise ServiceError("location_not_found", f"Нет точки {location_id!r}. Есть: {ids}", 404)
    return loc


def _update_booking_price(db, booking_id: int, q: dict) -> None:
    db.execute("UPDATE bookings SET start_at = ?, end_at = ?, days = ?, price_per_day = ?, base = ?,"
               " extras_total = ?, total = ?, deposit = ? WHERE id = ?",
               (q["from"], q["to"], q["days"], q["price_per_day"], q["base"], q["extras_total"],
                q["total"], q["deposit"], booking_id))
    db.execute("DELETE FROM booking_extras WHERE booking_id = ?", (booking_id,))
    db.executemany("INSERT INTO booking_extras VALUES (?,?,?)", [(booking_id, e["code"], e["price"]) for e in q["extras"]])


def _modifiable(b: sqlite3.Row) -> None:
    if b["status"] not in ("pending_payment", "paid"):
        raise ServiceError("booking_locked", f"Бронь {b['number']} уже нельзя менять: статус {b['status']}", 409)


def _booking_extras(db, booking_id: int) -> list[str]:
    return [r["code"] for r in db.execute("SELECT code FROM booking_extras WHERE booking_id = ?", (booking_id,))]


# create_booking

def _prep_create_booking(db, user, p):
    q = quote(db, p["car_id"], p["from"], p["to"], p.get("extras"))
    _require_free(db, q["car_id"], q["from"], q["to"])
    loc = _location(db, p["location_id"])
    params = {"car_id": q["car_id"], "from": q["from"], "to": q["to"], "location_id": loc["id"],
              "extras": [e["code"] for e in q["extras"]]}
    note = f"После подтверждения машина держится за вами {HOLD_MINUTES} минут до оплаты."
    if not profile_status(db, user)["documents_verified"]:
        note += " Перед подтверждением загрузите права в профиле — без них бронь не оформить."
    return params, {
        "title": f"Забронировать {q['car_name']}",
        "details": [{"label": "Машина", "value": q["car_name"]},
                    {"label": "Даты", "value": human_period(q["from"], q["to"])},
                    {"label": "Выдача", "value": loc["address"]}] + _price_details(q),
        "note": note, "quote": q,
    }


def _exec_create_booking(db, user, p):
    if not profile_status(db, user)["documents_verified"]:
        raise ServiceError("documents_required", "Сначала загрузите права в профиле")
    _require_free(db, p["car_id"], p["from"], p["to"])
    q = quote(db, p["car_id"], p["from"], p["to"], p["extras"])  # цену пересчитываем на момент подтверждения
    t = now()
    cur = db.execute(
        "INSERT INTO bookings (user_id, car_id, location_id, start_at, end_at, days, price_per_day, base,"
        " extras_total, total, deposit, status, hold_until, created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?, 'pending_payment', ?, ?)",
        (user["id"], q["car_id"], p["location_id"], q["from"], q["to"], q["days"], q["price_per_day"], q["base"],
         q["extras_total"], q["total"], q["deposit"], iso(t + timedelta(minutes=HOLD_MINUTES)), iso(t)))
    bid, number = cur.lastrowid, booking_number(cur.lastrowid)
    db.execute("UPDATE bookings SET number = ? WHERE id = ?", (number, bid))
    db.executemany("INSERT INTO booking_extras VALUES (?,?,?)", [(bid, e["code"], e["price"]) for e in q["extras"]])
    hold = iso(t + timedelta(minutes=HOLD_MINUTES))
    return {"booking_id": bid, "number": number, "total": q["total"], "hold_until": hold,
            "payment_url": f"/checkout/{number}",
            "note": f"Бронь {number} создана и ждёт оплаты до {hold[11:]}."}


# change_booking_dates

def _prep_change_dates(db, user, p):
    b = _booking_row(db, user, p["booking_id"])
    _modifiable(b)
    q = quote(db, b["car_id"], p["from"], p["to"], _booking_extras(db, b["id"]))
    _require_free(db, b["car_id"], q["from"], q["to"], exclude_booking=b["id"])
    diff = q["total"] - b["total"]
    return {"booking_id": b["id"], "from": q["from"], "to": q["to"]}, {
        "title": f"Перенести бронь {b['number']}",
        "details": [{"label": "Машина", "value": q["car_name"]},
                    {"label": "Было", "value": human_period(b["start_at"], b["end_at"])},
                    {"label": "Станет", "value": human_period(q["from"], q["to"])},
                    {"label": "Итого", "value": f"{rub(b['total'])} → {rub(q['total'])}"}],
        "note": (f"Доплата {rub(diff)} по ссылке после подтверждения." if diff > 0 and b["status"] == "paid"
                 else f"Вернём {rub(-diff)} на карту." if diff < 0 and b["status"] == "paid" else None),
        "quote": q,
    }


def _exec_change_dates(db, user, p):
    b = _booking_row(db, user, p["booking_id"])
    _modifiable(b)
    _require_free(db, b["car_id"], p["from"], p["to"], exclude_booking=b["id"])
    q = quote(db, b["car_id"], p["from"], p["to"], _booking_extras(db, b["id"]))
    _update_booking_price(db, b["id"], q)
    diff = q["total"] - b["total"]
    return {"booking_id": b["id"], "number": b["number"], "total": q["total"], "difference": diff,
            "note": f"Бронь {b['number']} перенесена на {human_period(q['from'], q['to'])}."}


# update_booking_extras

def _prep_update_extras(db, user, p):
    b = _booking_row(db, user, p["booking_id"])
    _modifiable(b)
    current = set(_booking_extras(db, b["id"]))
    codes = sorted((current | set(p.get("add") or [])) - set(p.get("remove") or []))
    if set(codes) == current:
        raise ServiceError("nothing_to_change", "Набор услуг не меняется")
    q = quote(db, b["car_id"], b["start_at"], b["end_at"], codes)
    return {"booking_id": b["id"], "extras": codes}, {
        "title": f"Изменить услуги в брони {b['number']}",
        "details": [{"label": "Услуги", "value": ", ".join(e["label"] for e in q["extras"]) or "без услуг"},
                    {"label": "Итого", "value": f"{rub(b['total'])} → {rub(q['total'])}"}],
        "note": None, "quote": q,
    }


def _exec_update_extras(db, user, p):
    b = _booking_row(db, user, p["booking_id"])
    _modifiable(b)
    q = quote(db, b["car_id"], b["start_at"], b["end_at"], p["extras"])
    _update_booking_price(db, b["id"], q)
    return {"booking_id": b["id"], "number": b["number"], "total": q["total"],
            "difference": q["total"] - b["total"], "note": f"Услуги в брони {b['number']} обновлены."}


# cancel_booking

def _prep_cancel(db, user, p):
    b = _booking_row(db, user, p["booking_id"])
    _modifiable(b)
    free = _can_cancel_free(b)
    car = db.execute("SELECT name FROM cars WHERE id = ?", (b["car_id"],)).fetchone()
    return {"booking_id": b["id"], "reason": p.get("reason")}, {
        "title": f"Отменить бронь {b['number']}",
        "details": [{"label": "Машина", "value": car["name"]},
                    {"label": "Даты", "value": human_period(b["start_at"], b["end_at"])},
                    {"label": "Сумма", "value": rub(b["total"])}],
        "note": ("Отмена бесплатная." if free else
                 f"До начала аренды меньше {FREE_CANCEL_HOURS} часов — бесплатно отменить не получится, нужен менеджер."),
    }


def _exec_cancel(db, user, p):
    b = _booking_row(db, user, p["booking_id"])
    _modifiable(b)
    if not _can_cancel_free(b):
        raise ServiceError("cancel_not_free", f"До начала аренды меньше {FREE_CANCEL_HOURS} часов, отмена через менеджера", 409)
    db.execute("UPDATE bookings SET status = 'cancelled', hold_until = NULL WHERE id = ?", (b["id"],))
    refund = b["total"] if b["status"] == "paid" else 0
    return {"booking_id": b["id"], "number": b["number"], "refund": refund,
            "note": f"Бронь {b['number']} отменена." + (f" Вернём {rub(refund)} на карту." if refund else "")}


# request_manager

def _prep_manager(db, user, p):
    topic, message = (p.get("topic") or "").strip(), (p.get("message") or "").strip()
    if not topic or not message:
        raise ServiceError("bad_params", "Нужны topic и message")
    return {"topic": topic, "message": message}, {
        "title": "Передать разговор менеджеру",
        "details": [{"label": "Тема", "value": topic}, {"label": "Сообщение", "value": message}],
        "note": "Менеджер увидит эту переписку и ответит в чате или по телефону.",
    }


def _exec_manager(db, user, p):
    cur = db.execute("INSERT INTO manager_requests (user_id, topic, message, created_at) VALUES (?,?,?,?)",
                     (user["id"], p["topic"], p["message"], iso(now())))
    return {"request_id": cur.lastrowid, "note": f"Обращение № {cur.lastrowid} передано менеджеру."}


ACTION_TOOLS = {
    "create_booking": (("car_id", "from", "to", "location_id"), _prep_create_booking, _exec_create_booking),
    "change_booking_dates": (("booking_id", "from", "to"), _prep_change_dates, _exec_change_dates),
    "update_booking_extras": (("booking_id",), _prep_update_extras, _exec_update_extras),
    "cancel_booking": (("booking_id",), _prep_cancel, _exec_cancel),
    "request_manager": (("topic", "message"), _prep_manager, _exec_manager),
}


def action_view(row: sqlite3.Row) -> dict:
    return {
        "action_id": row["id"], "tool": row["tool"], "status": row["status"],
        "summary": json.loads(row["summary"]), "result": json.loads(row["result"]) if row["result"] else None,
        "error": row["error"], "created_at": row["created_at"], "expires_at": row["expires_at"],
    }


def _action_row(db, user: dict, action_id: str) -> sqlite3.Row:
    row = db.execute("SELECT * FROM actions WHERE id = ? AND user_id = ?", (action_id, user["id"])).fetchone()
    if not row:
        raise ServiceError("action_not_found", "Действие не найдено", 404)
    return row


def propose_action(db, user: dict, tool: str, params: dict) -> dict:
    """Создаёт черновик. Ничего не меняет, пока клиент не подтвердит."""
    if tool not in ACTION_TOOLS:
        raise ServiceError("unknown_tool", "Инструменты: " + ", ".join(ACTION_TOOLS))
    required, prepare, _ = ACTION_TOOLS[tool]
    missing = [k for k in required if params.get(k) in (None, "")]
    if missing:
        raise ServiceError("bad_params", "Не хватает параметров: " + ", ".join(missing))
    norm, summary = prepare(db, user, params)
    t = now()
    action_id = "act_" + secrets.token_hex(6)
    db.execute("INSERT INTO actions (id, user_id, tool, params, summary, status, created_at, expires_at)"
               " VALUES (?,?,?,?,?, 'proposed', ?, ?)",
               (action_id, user["id"], tool, json.dumps(norm, ensure_ascii=False),
                json.dumps(summary, ensure_ascii=False), iso(t), iso(t + timedelta(minutes=ACTION_TTL_MINUTES))))
    return action_view(_action_row(db, user, action_id))


def get_action(db, user: dict, action_id: str) -> dict:
    return action_view(_action_row(db, user, action_id))


def _require_proposed(row: sqlite3.Row) -> None:
    if row["status"] == "expired":
        raise ServiceError("action_expired", "Предложение устарело, попросите агента подготовить его заново", 409)
    if row["status"] != "proposed":
        raise ServiceError("action_closed", f"Действие уже в статусе {row['status']}", 409)


def confirm_action(db, user: dict, action_id: str) -> dict:
    """Вызывается только из браузера клиента (scope web). Ошибка выполнения → статус failed, а не исключение."""
    row = _action_row(db, user, action_id)
    _require_proposed(row)
    db.execute("UPDATE actions SET status = 'running' WHERE id = ?", (action_id,))
    _, _, execute = ACTION_TOOLS[row["tool"]]
    db.execute("SAVEPOINT exec")
    try:
        result = execute(db, user, json.loads(row["params"]))
    except ServiceError as e:
        db.execute("ROLLBACK TO exec")
        db.execute("UPDATE actions SET status = 'failed', error = ? WHERE id = ?", (e.message, action_id))
    else:
        db.execute("UPDATE actions SET status = 'done', result = ? WHERE id = ?",
                   (json.dumps(result, ensure_ascii=False), action_id))
    db.execute("RELEASE exec")
    return get_action(db, user, action_id)


def cancel_action(db, user: dict, action_id: str) -> dict:
    row = _action_row(db, user, action_id)
    _require_proposed(row)
    db.execute("UPDATE actions SET status = 'cancelled' WHERE id = ?", (action_id,))
    return get_action(db, user, action_id)
