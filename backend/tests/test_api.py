from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from app import services

NOW = datetime(2026, 10, 9, 10, 0)  # пятница
WEEKEND = {"from": "2026-10-10T10:00", "to": "2026-10-12T10:00"}  # сб–пн, Boxster в сиде занят


@pytest.fixture
def clock(monkeypatch):
    state = {"now": NOW}
    monkeypatch.setattr(services, "now", lambda: state["now"])
    return state


@pytest.fixture
def make_client(tmp_path, monkeypatch, clock):
    monkeypatch.setenv("PITLANE_DB", str(tmp_path / "test.db"))
    from app.main import app
    clients = []

    def make(email=None):
        c = TestClient(app)
        c.__enter__()
        clients.append(c)
        if email:
            assert c.post("/api/auth/login", json={"email": email}).status_code == 200
        return c

    yield make
    for c in clients:
        c.__exit__(None, None, None)


@pytest.fixture
def web(make_client):
    return make_client("demo@pitlane.test")


def agent_for(web, make_client):
    token = web.post("/api/agent/token").json()["token"]
    c = make_client()
    c.headers["Authorization"] = f"Bearer {token}"
    return c


def propose(client, tool, **params):
    r = client.post("/api/actions", json={"tool": tool, "params": params})
    assert r.status_code == 201, r.text
    return r.json()


def book(web, car="bmw-z4", period=WEEKEND, extras=()):
    a = propose(web, "create_booking", car_id=car, location_id="city", extras=list(extras), **period)
    r = web.post(f"/api/actions/{a['action_id']}/confirm").json()
    assert r["status"] == "done", r
    return r["result"]


# ——— Каталог ———

def test_search_marks_booked_car_on_dates(make_client):
    c = make_client()
    cars = c.get("/api/cars", params={"body_type": "cabriolet", "max_price_per_day": 30000, **WEEKEND}).json()
    status = {car["id"]: car["status"] for car in cars}
    assert status == {"mustang": "available", "bmw-z4": "available", "boxster": "booked"}
    assert [car["id"] for car in cars] == ["mustang", "bmw-z4", "boxster"]  # по цене


def test_service_car_is_unavailable(make_client):
    r = make_client().get("/api/cars/supra/availability", params=WEEKEND).json()
    assert r == {"car_id": "supra", "available": False, "reason": "service", "busy": [], "next_available_from": None}


def test_quote_counts_days_and_extras(make_client):
    r = make_client().post("/api/quote", json={"car_id": "bmw-z4", "extras": ["full_insurance", "delivery"], **WEEKEND})
    q = r.json()
    assert q["days"] == 2 and q["base"] == 49800
    assert {e["code"]: e["price"] for e in q["extras"]} == {"delivery": 3000, "full_insurance": 7000}
    assert q["total"] == 59800 and q["deposit"] == 100000


def test_partial_day_rounds_up(make_client):
    q = make_client().post("/api/quote", json={"car_id": "bmw-z4", "from": "2026-10-10T10:00", "to": "2026-10-11T12:00"}).json()
    assert q["days"] == 2


@pytest.mark.parametrize("body,code", [
    ({"from": "2026-10-12T10:00", "to": "2026-10-10T10:00"}, "bad_period"),
    ({"from": "2026-10-01T10:00", "to": "2026-10-02T10:00"}, "bad_period"),
    ({"from": "завтра", "to": "2026-10-12T10:00"}, "bad_date"),
    ({**WEEKEND, "extras": ["jetpack"]}, "bad_extra"),
])
def test_quote_validation(make_client, body, code):
    r = make_client().post("/api/quote", json={"car_id": "bmw-z4", **body})
    assert r.status_code == 400 and r.json()["error"]["code"] == code


# ——— Действия: propose → confirm ———

def test_proposal_changes_nothing_until_confirmed(web):
    a = propose(web, "create_booking", car_id="bmw-z4", location_id="city", extras=["full_insurance"], **WEEKEND)
    assert a["status"] == "proposed"
    assert a["summary"]["title"] == "Забронировать BMW Z4 M40i"
    assert {"label": "Итого", "value": "56 800 ₽"} in a["summary"]["details"]
    assert web.get("/api/bookings").json() == []

    done = web.post(f"/api/actions/{a['action_id']}/confirm").json()
    assert done["status"] == "done"
    assert done["result"]["number"].startswith("PL-") and done["result"]["total"] == 56800
    b = web.get(f"/api/bookings/{done['result']['number']}").json()
    assert b["status"] == "pending_payment" and b["hold_until"] == "2026-10-09T10:30"


def test_agent_token_cannot_confirm_or_pay(web, make_client):
    agent = agent_for(web, make_client)
    a = propose(agent, "create_booking", car_id="bmw-z4", location_id="city", **WEEKEND)  # предлагать агент может
    r = agent.post(f"/api/actions/{a['action_id']}/confirm")
    assert r.status_code == 403 and r.json()["error"]["code"] == "forbidden_for_agent"
    assert agent.post(f"/api/actions/{a['action_id']}/cancel").status_code == 403
    assert web.post(f"/api/actions/{a['action_id']}/confirm").json()["status"] == "done"  # а клиент — да
    number = web.get("/api/bookings").json()[0]["number"]
    assert agent.post(f"/api/bookings/{number}/pay").status_code == 403
    assert agent.post("/api/agent/token").status_code == 403


def test_other_users_data_is_invisible(web, make_client):
    result = book(web)
    other = make_client("other@pitlane.test")
    assert other.get(f"/api/bookings/{result['number']}").status_code == 404
    a = propose(web, "cancel_booking", booking_id=result["number"])
    assert other.get(f"/api/actions/{a['action_id']}").status_code == 404
    assert other.post(f"/api/actions/{a['action_id']}/confirm").status_code == 404
    r = other.post("/api/actions", json={"tool": "cancel_booking", "params": {"booking_id": result["number"]}})
    assert r.status_code == 404


def test_anonymous_cannot_use_actions(make_client):
    r = make_client().post("/api/actions", json={"tool": "create_booking", "params": {}})
    assert r.status_code == 401


def test_cannot_book_taken_car(web):
    r = web.post("/api/actions", json={"tool": "create_booking", "params": {"car_id": "boxster", "location_id": "city", **WEEKEND}})
    assert r.status_code == 409 and r.json()["error"]["code"] == "car_unavailable"


def test_second_confirm_for_same_dates_fails(web):
    a1 = propose(web, "create_booking", car_id="bmw-z4", location_id="city", **WEEKEND)
    a2 = propose(web, "create_booking", car_id="bmw-z4", location_id="city", **WEEKEND)
    assert web.post(f"/api/actions/{a1['action_id']}/confirm").json()["status"] == "done"
    r2 = web.post(f"/api/actions/{a2['action_id']}/confirm").json()
    assert r2["status"] == "failed" and "занята" in r2["error"]
    assert len(web.get("/api/bookings").json()) == 1


def test_action_expires_after_15_minutes(web, clock):
    a = propose(web, "create_booking", car_id="bmw-z4", location_id="city", **WEEKEND)
    clock["now"] += timedelta(minutes=16)
    r = web.post(f"/api/actions/{a['action_id']}/confirm")
    assert r.status_code == 409 and r.json()["error"]["code"] == "action_expired"


def test_action_confirms_only_once(web):
    a = propose(web, "create_booking", car_id="bmw-z4", location_id="city", **WEEKEND)
    web.post(f"/api/actions/{a['action_id']}/cancel")
    r = web.post(f"/api/actions/{a['action_id']}/confirm")
    assert r.status_code == 409 and r.json()["error"]["code"] == "action_closed"


def test_unpaid_booking_expires_and_frees_car(web, clock):
    book(web)
    clock["now"] += timedelta(minutes=31)
    assert web.get("/api/bookings").json()[0]["status"] == "expired"
    assert web.get("/api/cars/bmw-z4/availability", params=WEEKEND).json()["available"]


def test_documents_required(make_client):
    newbie = make_client("new@pitlane.test")
    a = propose(newbie, "create_booking", car_id="bmw-z4", location_id="city", **WEEKEND)
    assert "загрузите права" in a["summary"]["note"]
    r = newbie.post(f"/api/actions/{a['action_id']}/confirm").json()
    assert r["status"] == "failed" and newbie.get("/api/bookings").json() == []


# ——— Изменение и отмена брони ———

def test_change_dates_recalculates(web):
    number = book(web, extras=["full_insurance"])["number"]
    a = propose(web, "change_booking_dates", booking_id=number, **{"from": "2026-10-10T10:00", "to": "2026-10-13T10:00"})
    r = web.post(f"/api/actions/{a['action_id']}/confirm").json()
    assert r["result"]["total"] == 3 * (24900 + 3500) and r["result"]["difference"] == 24900 + 3500


def test_change_dates_ignores_own_booking_but_not_others(web):
    number = book(web, car="boxster", period={"from": "2026-10-13T10:00", "to": "2026-10-15T10:00"})["number"]
    propose(web, "change_booking_dates", booking_id=number, **{"from": "2026-10-14T10:00", "to": "2026-10-16T10:00"})
    r = web.post("/api/actions", json={"tool": "change_booking_dates", "params": {"booking_id": number, **WEEKEND}})
    assert r.status_code == 409


def test_update_extras(web):
    number = book(web)["number"]
    a = propose(web, "update_booking_extras", booking_id=number, add=["child_seat"])
    r = web.post(f"/api/actions/{a['action_id']}/confirm").json()
    assert r["result"]["total"] == 49800 + 1000
    assert [e["code"] for e in web.get(f"/api/bookings/{number}").json()["extras"]] == ["child_seat"]


def test_cancel_paid_booking_within_24h_fails(web):
    number = book(web, period={"from": "2026-10-10T09:00", "to": "2026-10-11T09:00"})["number"]
    assert web.post(f"/api/bookings/{number}/pay").json()["status"] == "paid"
    a = propose(web, "cancel_booking", booking_id=number)
    assert "бесплатно отменить не получится" in a["summary"]["note"]
    r = web.post(f"/api/actions/{a['action_id']}/confirm").json()
    assert r["status"] == "failed"
    assert web.get(f"/api/bookings/{number}").json()["status"] == "paid"


def test_cancel_paid_booking_early_refunds(web):
    number = book(web)["number"]
    web.post(f"/api/bookings/{number}/pay")
    a = propose(web, "cancel_booking", booking_id=number)
    r = web.post(f"/api/actions/{a['action_id']}/confirm").json()
    assert r["status"] == "done" and r["result"]["refund"] == 49800
    assert web.get("/api/cars/bmw-z4/availability", params=WEEKEND).json()["available"]


def test_request_manager(web):
    a = propose(web, "request_manager", topic="ДТП", message="Поцарапал бампер на парковке")
    r = web.post(f"/api/actions/{a['action_id']}/confirm").json()
    assert r["status"] == "done" and "передано менеджеру" in r["result"]["note"]


def test_bookings_filters(web, clock):
    book(web)
    assert len(web.get("/api/bookings", params={"status": "upcoming"}).json()) == 1
    assert web.get("/api/bookings", params={"status": "past"}).json() == []
