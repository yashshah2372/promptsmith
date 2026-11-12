"""Tests run without a real Claude API key: FakeClaude stands in for AsyncAnthropic."""
from __future__ import annotations

import asyncio
import socket
import threading
import time
from types import SimpleNamespace

import httpx2
import pytest
import uvicorn
from mcp import Client
from mcp.client.streamable_http import streamable_http_client
from starlette.testclient import TestClient

from promptsmith import library
from promptsmith.enhancer import Enhancer
from promptsmith.server import create_app
from promptsmith.store import PLAN_LIMITS, Store


class FakeClaude:
    """Records each call and echoes back a canned prompt."""

    def __init__(self):
        self.calls = []
        self.messages = SimpleNamespace(create=self._create)

    async def _create(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(content=[SimpleNamespace(type="text", text="You are a LinkedIn ghostwriter...")])


@pytest.fixture
def fake():
    return FakeClaude()


@pytest.fixture
def client(tmp_path, fake):
    app = create_app(Store(str(tmp_path / "t.db")), Enhancer(fake), "http://testserver", host="0.0.0.0")
    with TestClient(app) as c:
        yield c


def new_key(client) -> dict:
    r = client.post("/v1/keys")
    assert r.status_code == 201
    return {"Authorization": f"Bearer {r.json()['api_key']}"}


# ---- library -------------------------------------------------------------------------------

def test_match_picks_template_by_keyword():
    assert library.match("LinkedIn post about my launch, keep it short").id == "linkedin_post"
    assert library.match("cold email to a podcast host").id == "cold_email"
    assert library.match("help me name my cat").id == "general"


# ---- REST API ------------------------------------------------------------------------------

def test_rest_requires_api_key(client):
    assert client.post("/v1/enhance", json={"request": "x"}).status_code == 401
    assert client.post("/v1/enhance", json={"request": "x"}, headers={"Authorization": "Bearer nope"}).status_code == 401


def test_profile_round_trip_drops_unknown_fields(client):
    h = new_key(client)
    r = client.put("/v1/profile", headers=h, json={"business": "Yoga studio", "voice": "warm", "password": "x"})
    assert r.json()["profile"] == {"business": "Yoga studio", "voice": "warm"}
    assert client.get("/v1/profile", headers=h).json()["profile"] == {"business": "Yoga studio", "voice": "warm"}


def test_enhance_uses_profile_template_and_haiku(client, fake):
    h = new_key(client)
    client.put("/v1/profile", headers=h, json={"business": "Yoga studio for new mums", "audience": "new mothers"})
    r = client.post("/v1/enhance", headers=h, json={"request": "LinkedIn post about my launch, keep it short"})

    assert r.status_code == 200
    body = r.json()
    assert body["prompt"].startswith("You are")
    assert body["template"] == "linkedin_post"
    assert body["remaining_today"] == PLAN_LIMITS["free"] - 1

    sent = fake.calls[0]
    assert sent["model"] == "claude-haiku-5-5"
    user_msg = sent["messages"][0]["content"]
    assert "Yoga studio for new mums" in user_msg
    assert "LinkedIn post" in user_msg and "keep it short" in user_msg


def test_profiles_are_isolated_between_users(client, fake):
    a, b = new_key(client), new_key(client)
    client.put("/v1/profile", headers=a, json={"business": "Bakery A"})
    client.post("/v1/enhance", headers=b, json={"request": "blog post"})
    assert "Bakery A" not in fake.calls[0]["messages"][0]["content"]


def test_free_plan_daily_limit(client, monkeypatch):
    monkeypatch.setitem(PLAN_LIMITS, "free", 2)
    h = new_key(client)
    codes = [client.post("/v1/enhance", headers=h, json={"request": "email"}).status_code for _ in range(3)]
    assert codes == [200, 200, 429]


def test_rejects_empty_and_oversized_requests(client):
    h = new_key(client)
    assert client.post("/v1/enhance", headers=h, json={"request": "   "}).status_code == 400
    assert client.post("/v1/enhance", headers=h, json={"request": "x" * 2001}).status_code == 400


def test_upgrading_plan_raises_limit(tmp_path):
    store = Store(str(tmp_path / "p.db"))
    user, _ = store.create_user()
    store.set_plan(user.id, "pro")
    user.plan = "pro"
    assert store.consume(user) == PLAN_LIMITS["pro"] - 1


# ---- MCP over real HTTP ----------------------------------------------------------------------

def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture
def live_server(tmp_path, fake):
    port = _free_port()
    url = f"http://127.0.0.1:{port}"
    store = Store(str(tmp_path / "live.db"))
    app = create_app(store, Enhancer(fake), url)
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    while not server.started:
        time.sleep(0.05)
    _, key = store.create_user()
    yield url, key
    server.should_exit = True
    thread.join(timeout=5)


def _mcp(url: str, key: str | None) -> Client:
    headers = {"Authorization": f"Bearer {key}"} if key else {}
    return Client(streamable_http_client(f"{url}/mcp", http_client=httpx2.AsyncClient(headers=headers)))


def test_mcp_rejects_missing_token(live_server):
    url, _ = live_server
    r = httpx2.post(f"{url}/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
    assert r.status_code == 401
    assert "oauth-protected-resource" in r.headers.get("www-authenticate", "")


def test_mcp_tools_end_to_end(live_server, fake):
    url, key = live_server

    async def run():
        async with _mcp(url, key) as c:
            names = {t.name for t in (await c.list_tools()).tools}
            assert names == {"enhance_prompt", "save_profile", "get_profile", "list_templates"}

            await c.call_tool("save_profile", {"business": "Career coaching", "voice": "direct"})
            got = await c.call_tool("get_profile", {})
            assert got.structured_content["profile"]["business"] == "Career coaching"

            res = await c.call_tool("enhance_prompt", {"request": "cold email to a recruiter"})
            assert not res.is_error
            assert res.structured_content["template"] == "cold_email"

    asyncio.run(run())
    assert "Career coaching" in fake.calls[0]["messages"][0]["content"]
