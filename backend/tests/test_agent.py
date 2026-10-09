"""Агент и MCP. Модель подменяется сценарием, всё остальное настоящее:
агент ходит в MCP по HTTP с токеном scope=agent, MCP — в ту же базу."""
import json

import pytest

from app import agent
from test_api import WEEKEND, clock, make_client, web  # noqa: F401 — фикстуры


def call(name, **args):
    return {"id": f"call_{name}", "type": "function", "function": {"name": name, "arguments": json.dumps(args)}}


@pytest.fixture
def llm(monkeypatch):
    """Сценарий модели: список ответов по порядку. Запоминает, что модель получила."""
    state = {"script": [], "seen": []}

    async def fake(messages, tools):
        state["seen"].append({"messages": list(messages), "tools": [t["function"]["name"] for t in tools]})
        step = state["script"].pop(0)
        return {"role": "assistant", "content": step} if isinstance(step, str) else \
            {"role": "assistant", "content": None, "tool_calls": step}

    monkeypatch.setattr(agent, "complete", fake)
    return state


def test_agent_searches_shows_cars_and_proposes_booking(web, llm):
    llm["script"] = [
        [call("search_cars", body_type="cabriolet", date_from=WEEKEND["from"], date_to=WEEKEND["to"])],
        [call("show_cars", car_ids=["mustang", "boxster"]), call("suggest_replies", options=["Чем они отличаются?"])],
        "Свободны два кабриолета.",
    ]
    items = web.post("/api/chat", json={"message": "Кабриолет на выходные"}).json()["items"]
    assert [i["type"] for i in items] == ["user", "cars", "replies", "text"]
    assert {c["id"]: c["status"] for c in items[1]["cars"]} == {"mustang": "available", "boxster": "booked"}
    assert items[1]["cars"][0]["deposit"]  # полная карточка из get_car

    # результат search_cars дошёл до модели через MCP
    tool_msg = llm["seen"][1]["messages"][-1]
    assert tool_msg["role"] == "tool" and '"boxster"' in tool_msg["content"] and '"booked"' in tool_msg["content"]

    llm["script"] = [
        [call("create_booking", car_id="bmw-z4", date_from=WEEKEND["from"], date_to=WEEKEND["to"], location_id="city")],
        "Проверьте карточку и подтвердите.",
    ]
    items = web.post("/api/chat", json={"message": "Беру BMW, заберу в City"}).json()["items"]
    action = items[1]["action"]
    assert action["status"] == "proposed" and action["summary"]["title"] == "Забронировать BMW Z4 M40i"
    assert web.get("/api/bookings").json() == []  # агент только предложил

    # история целиком уходит в модель на следующем ходе
    assert [m["role"] for m in llm["seen"][-1]["messages"]][:3] == ["system", "user", "assistant"]

    assert web.post(f"/api/actions/{action['action_id']}/confirm").json()["status"] == "done"
    history = web.get("/api/chat").json()["items"]
    assert history[-2]["action"]["status"] == "done"  # карточка в истории — с актуальным статусом

    llm["script"] = ["Бронь оформлена."]
    web.post("/api/chat", json={"message": "Готово?"})
    assert f"{action['action_id']}: Забронировать BMW Z4 M40i — done" in llm["seen"][-1]["messages"][0]["content"]


def test_agent_has_no_confirm_tool(web, llm):
    llm["script"] = ["Здравствуйте!"]
    web.post("/api/chat", json={"message": "Привет"})
    tools = llm["seen"][0]["tools"]
    assert "create_booking" in tools and "search_cars" in tools
    assert not [t for t in tools if "confirm" in t or "pay" in t]


def test_tool_error_goes_back_to_model(web, llm):
    llm["script"] = [
        [call("create_booking", car_id="boxster", date_from=WEEKEND["from"], date_to=WEEKEND["to"], location_id="city")],
        "Boxster занят, могу предложить другой.",
    ]
    items = web.post("/api/chat", json={"message": "Boxster на выходные"}).json()["items"]
    assert [i["type"] for i in items] == ["user", "text"]
    assert llm["seen"][1]["messages"][-1]["content"].startswith("Ошибка:")


def test_chat_requires_web_session(make_client, web, llm):
    assert make_client().post("/api/chat", json={"message": "Привет"}).status_code == 401
    token = web.post("/api/agent/token").json()["token"]
    agent_client = make_client()
    agent_client.headers["Authorization"] = f"Bearer {token}"
    assert agent_client.post("/api/chat", json={"message": "Привет"}).status_code == 403


def test_model_unavailable(web, monkeypatch):
    async def down(messages, tools):
        raise agent.AgentUnavailable("503")
    monkeypatch.setattr(agent, "complete", down)
    r = web.post("/api/chat", json={"message": "Привет"})
    assert r.status_code == 503 and r.json()["error"]["code"] == "agent_unavailable"
    assert web.get("/api/chat").json()["items"] == []


def test_chat_reset(web, llm):
    llm["script"] = ["Здравствуйте!"]
    web.post("/api/chat", json={"message": "Привет"})
    web.delete("/api/chat")
    assert web.get("/api/chat").json()["items"] == []


def test_schema_cleanup_for_gemini():
    schema = {"type": "object", "title": "X", "properties": {
        "d": {"anyOf": [{"type": "string", "description": "дата"}, {"type": "null"}], "default": None, "title": "D"}}}
    assert agent._clean_schema(schema) == {"type": "object", "properties": {"d": {"type": "string", "description": "дата"}}}
