"""Чат-агент Pitlane: Gemini + инструменты MCP-сервера.

Агент ходит в MCP как обычный клиент — по Streamable HTTP с токеном scope=agent,
поэтому видит ровно то, что разрешено агенту, и подтвердить ничего не может.
Помимо MCP у него есть инструменты интерфейса (show_cars, suggest_replies):
они ничего не меняют на сервере, а превращаются в карточки в чате.
"""
import asyncio
import json
import os
from datetime import timedelta
from pathlib import Path

import httpx2
from mcp import Client
from mcp.client.streamable_http import streamable_http_client
from openai import APIConnectionError, APIStatusError, AsyncOpenAI

from . import services as s

ROOT = Path(__file__).resolve().parents[2]
GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/openai/"
MAX_STEPS = 8          # сколько раз подряд модель может вызвать инструменты за один ответ
RETRYABLE = {429, 500, 502, 503, 504}

UI_TOOLS = [
    {"type": "function", "function": {
        "name": "show_cars",
        "description": "Показать клиенту карточки машин. Вызывай после search_cars вместо перечисления машин текстом.",
        "parameters": {"type": "object", "properties": {
            "car_ids": {"type": "array", "items": {"type": "string"}, "description": "id машин, до 4"}},
            "required": ["car_ids"]}}},
    {"type": "function", "function": {
        "name": "suggest_replies",
        "description": "Показать 2–3 кнопки с быстрыми ответами клиента, например «Чем они отличаются?».",
        "parameters": {"type": "object", "properties": {
            "options": {"type": "array", "items": {"type": "string"}}}, "required": ["options"]}}},
]


class AgentUnavailable(Exception):
    """Модель не ответила — ни основная, ни запасная."""


def load_env() -> None:
    """Читает корневой .env (ключ Gemini). Уже заданные переменные окружения не трогает."""
    path = ROOT / ".env"
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        key, sep, value = line.strip().partition("=")
        if sep and not key.startswith("#"):
            os.environ.setdefault(key.strip(), value.strip().strip('"\''))


def models() -> list[str]:
    return [os.environ.get("GEMINI_MODEL", "gemini-3.5-flash-lite"),
            os.environ.get("GEMINI_FALLBACK_MODEL", "gemini-2.5-flash-lite")]


# ——— Подсказка ———

def system_prompt(user_name: str, actions: list[dict], page: str | None = None) -> str:
    t = s.now()
    sat = (t + timedelta(days=(5 - t.weekday()) % 7)).replace(hour=10, minute=0)
    if sat <= t:
        sat += timedelta(days=7)
    weekend = s.human_period(s.iso(sat), s.iso(sat + timedelta(days=2)))
    lines = [
        "Ты — консьерж Pitlane, сервиса аренды спорткаров в Москве. Отвечаешь клиенту в чате на сайте.",
        f"Клиента зовут {user_name}. Сейчас {s.WEEKDAYS[t.weekday()]} {s.human_dt(s.iso(t))} по Москве.",
        f"«Эти выходные» = {weekend} (с субботы 10:00 до понедельника 10:00). "
        "Если даты или время неясны — переспроси, не выдумывай.",
        "",
        "Правила:",
        "- Обращайся на «вы», пиши коротко и по делу, без эмодзи. Цены — в рублях.",
        "- Цены, наличие и условия бери только из инструментов, никогда не придумывай.",
        "- Найденные машины показывай через show_cars, а не списком в тексте; в тексте — одна-две фразы. "
        "Занятые на эти даты машины (status booked) не показывай, если клиент не просил.",
        "- Ты не можешь ничего забронировать, изменить или отменить сам. Инструменты create_booking, "
        "change_booking_dates, update_booking_extras, cancel_booking, request_manager только создают черновик: "
        "клиент увидит карточку и подтвердит её кнопкой. После такого вызова не пиши, что дело сделано, — "
        "попроси проверить карточку и подтвердить.",
        "- Перед бронированием уточни точку выдачи (list_locations), если клиент её не назвал.",
        "- Оплата — только на странице оплаты после подтверждения, данные карты в чате не спрашивай.",
        "- ДТП, штрафы, споры и всё, что ты не можешь решить, — предложи передать менеджеру (request_manager).",
        "- Не отвечай на вопросы, не связанные с арендой машин Pitlane; вежливо верни разговор к аренде.",
    ]
    if page:
        lines += ["", f"Клиент сейчас на сайте, на странице: {page}. «Эта машина», «эти даты» — отсюда."]
    if actions:
        lines += ["", "Черновики в этом чате и их текущий статус:"]
        for a in actions:
            result = (a.get("result") or {}).get("note") or a.get("error") or ""
            lines.append(f"- {a['action_id']}: {a['summary']['title']} — {a['status']} {result}".rstrip())
    return "\n".join(lines)


# ——— Схемы инструментов ———

def _clean_schema(node):
    """Gemini принимает урезанный JSON Schema: убираем title/default и разворачиваем anyOf[X, null]."""
    if isinstance(node, list):
        return [_clean_schema(n) for n in node]
    if not isinstance(node, dict):
        return node
    node = dict(node)
    variants = node.get("anyOf")
    if variants:
        real = [v for v in variants if v.get("type") != "null"]
        if len(real) == 1:
            node.pop("anyOf")
            node = {**real[0], **node}
    out = {}
    for k, v in node.items():
        if k in ("title", "default", "additionalProperties", "$schema"):
            continue
        out[k] = {pk: _clean_schema(pv) for pk, pv in v.items()} if k == "properties" else _clean_schema(v)
    return out


def openai_tools(mcp_tools) -> list[dict]:
    return [{"type": "function", "function": {
        "name": t.name, "description": t.description or "",
        "parameters": _clean_schema(t.input_schema)}} for t in mcp_tools] + UI_TOOLS


# ——— Модель ———

async def complete(messages: list[dict], tools: list[dict]) -> dict:
    """Один ответ модели. 429/5xx — повтор, потом запасная модель. Возвращает сообщение как dict."""
    load_env()
    key = os.environ.get("GEMINI_API_KEY")
    if not key:
        raise AgentUnavailable("Не задан GEMINI_API_KEY в .env")
    client = AsyncOpenAI(api_key=key, base_url=GEMINI_URL, timeout=40, max_retries=0)
    last = None
    for model in models():
        for attempt in range(2):
            try:
                r = await client.chat.completions.create(model=model, messages=messages, tools=tools)
                # model_dump сохраняет extra_content с thought_signature — Gemini 3 требует вернуть его обратно
                return r.choices[0].message.model_dump(exclude_none=True)
            except APIStatusError as e:
                last = f"{model}: HTTP {e.status_code}"
                if e.status_code not in RETRYABLE:
                    break
            except APIConnectionError:
                last = f"{model}: нет соединения"
            await asyncio.sleep(1 + attempt)
    raise AgentUnavailable(last)


# ——— Цикл агента ———

def _tool_payload(result) -> object:
    if result.structured_content is not None:
        sc = result.structured_content
        return sc.get("result", sc) if isinstance(sc, dict) and set(sc) == {"result"} else sc
    text = "\n".join(getattr(c, "text", "") for c in result.content)
    try:
        return json.loads(text)  # dict без схемы MCP отдаёт текстом с JSON
    except json.JSONDecodeError:
        return text


async def run(app, token: str, history: list[dict], user_name: str, actions: list[dict],
              page: str | None = None) -> list[dict]:
    """Прогоняет один ход диалога. history — сообщения для модели (без system).
    Возвращает новые записи: {"llm": сообщение для истории} и/или {"ui": элемент чата}."""
    try:
        return await _run(app, token, history, user_name, actions, page)
    except BaseExceptionGroup as eg:  # клиент MCP заворачивает ошибки в группу задач — достаём нашу
        unavailable, _ = eg.split(AgentUnavailable)
        if unavailable:
            raise AgentUnavailable(str(unavailable.exceptions[0])) from eg
        raise


async def _run(app, token, history, user_name, actions, page) -> list[dict]:
    out: list[dict] = []
    statuses: dict[str, str] = {}  # статус машин на даты из последнего search_cars — get_car его не знает
    http = httpx2.AsyncClient(transport=httpx2.ASGITransport(app=app), base_url="http://localhost:8000",
                              headers={"Authorization": f"Bearer {token}"}, timeout=30)
    async with http, Client(streamable_http_client("http://localhost:8000/mcp", http_client=http)) as mcp:
        tools = openai_tools((await mcp.list_tools()).tools)
        messages = [{"role": "system", "content": system_prompt(user_name, actions, page)}, *history]
        for _ in range(MAX_STEPS):
            msg = await complete(messages, tools)
            msg.pop("refusal", None)
            messages.append(msg)
            calls = msg.get("tool_calls") or []
            text = (msg.get("content") or "").strip()
            out.append({"llm": msg, "ui": {"type": "text", "text": text} if text else None})
            if not calls:
                return out
            for call in calls:
                name = call["function"]["name"]
                try:
                    args = json.loads(call["function"].get("arguments") or "{}")
                except json.JSONDecodeError:
                    args = {}
                content, ui = await _call(mcp, name, args, statuses)
                tool_msg = {"role": "tool", "tool_call_id": call["id"], "content": content}
                messages.append(tool_msg)
                out.append({"llm": tool_msg, "ui": ui})
        out.append({"llm": None, "ui": {"type": "text", "text": "Не получилось ответить — попробуйте переформулировать вопрос."}})
        return out


async def _call(mcp, name: str, args: dict, statuses: dict[str, str]) -> tuple[str, dict | None]:
    """Выполняет инструмент. Возвращает (ответ для модели, элемент чата или None)."""
    if name == "suggest_replies":
        options = [str(o) for o in args.get("options", [])][:3]
        return "Показано", {"type": "replies", "options": options}
    if name == "show_cars":
        cars = []
        for car_id in args.get("car_ids", [])[:4]:
            r = await mcp.call_tool("get_car", {"car_id": car_id})
            if not r.is_error:
                car = _tool_payload(r)
                cars.append({**car, "status": statuses.get(car_id, car["status"])})
        return (f"Показано машин: {len(cars)}" if cars else "Таких машин нет, проверь id"), (
            {"type": "cars", "cars": cars} if cars else None)
    r = await mcp.call_tool(name, args)
    payload = _tool_payload(r)
    if r.is_error:
        return f"Ошибка: {payload}", None
    if name == "search_cars" and args.get("date_from") and isinstance(payload, list):
        statuses.update({c["id"]: c["status"] for c in payload})
    ui = None
    if isinstance(payload, dict) and payload.get("status") == "proposed" and "action_id" in payload:
        ui = {"type": "action", "action_id": payload["action_id"]}
        payload = {k: payload[k] for k in ("action_id", "status", "summary")}
        payload["summary"] = {k: v for k, v in payload["summary"].items() if k != "quote"} | {
            "total": (payload["summary"].get("quote") or {}).get("total")}
        payload["next"] = "Клиент видит карточку и сам подтвердит или отменит её."
    return json.dumps(payload, ensure_ascii=False), ui
