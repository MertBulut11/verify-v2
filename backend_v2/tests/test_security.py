"""Offline HTTP and executor regression tests; no provider initialization."""
import asyncio
import logging
import sys
import threading
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app import main
from app.resources import TrackingExecutor, memory_mb
from app.security import Guard, SecurityMiddleware
from app.pipeline import PipelineError


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    # Fail closed if any test accidentally attempts real socket access.
    import socket
    original_connect = socket.socket.connect
    def blocked(sock, address):
        # Windows asyncio creates an internal loopback socketpair.
        if isinstance(address, tuple) and address[0] in ("127.0.0.1", "::1"):
            return original_connect(sock, address)
        raise AssertionError("Network forbidden in tests")
    monkeypatch.setattr(socket.socket, "connect", blocked)
    monkeypatch.setattr(socket.socket, "connect_ex", lambda *args: (_ for _ in ()).throw(AssertionError("Network forbidden")))
    monkeypatch.setattr(main, "guard", Guard())
    main.app.middleware_stack = None
    for middleware in main.app.user_middleware:
        if middleware.cls is SecurityMiddleware:
            monkeypatch.setitem(middleware.kwargs, "guard", main.guard)
    monkeypatch.setitem(main.state, "init_error", None)
    monkeypatch.setattr("app.security.memory_mb", lambda: (50, 70))
    async def fake(text, emit=None):
        if emit:
            await emit({"type": "claims", "claims": []})
        return {"results": [], "partial": False, "timings": {}}
    monkeypatch.setattr(main, "_run", fake)


def run(coro):
    return asyncio.run(coro)


async def request(path="/verify", **kwargs):
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=main.app), base_url="http://test") as client:
        return await client.post(path, **({"json": {"text": "example"}} | kwargs))


def test_normal_stream_ids_and_cors(caplog):
    caplog.set_level(logging.INFO)
    first = run(request(headers={"Origin": "https://verify-test-swart.vercel.app", "X-Request-ID": "forged"}))
    assert first.status_code == 200
    rid = first.headers["x-request-id"]
    assert len(rid) == 32 and rid != "forged"
    assert rid in caplog.text and "example" not in caplog.text
    assert "X-Request-ID" in first.headers["access-control-expose-headers"]
    stream = run(request("/verify/stream"))
    assert stream.status_code == 200
    assert "event: claims" in stream.text and "event: done" in stream.text
    assert stream.headers["x-request-id"] != rid
    assert main.guard.active == 0


@pytest.mark.parametrize("path", ["/verify", "/verify/stream"])
def test_config_error_never_leaks(path, monkeypatch):
    monkeypatch.setitem(main.state, "init_error", "SECRET traceback api_key=hidden")
    response = run(request(path))
    assert response.status_code == 503
    assert response.json()["error"] == "CONFIG_ERROR"
    assert "SECRET" not in response.text and "detail" not in response.text
    assert "x-request-id" in response.headers


@pytest.mark.parametrize("path", ["/verify", "/verify/stream"])
@pytest.mark.parametrize("failure", [RuntimeError("SECRET"), PipelineError("EXTRACTION_TIMEOUT", "SECRET", "SECRET", 504)])
def test_errors_and_timeouts(path, failure, monkeypatch):
    async def fail(*args, **kwargs):
        raise failure
    monkeypatch.setattr(main, "_run", fail)
    response = run(request(path))
    assert "SECRET" not in response.text
    assert "error" in response.text
    assert main.guard.active == 0
    if path == "/verify":
        assert response.status_code == (504 if isinstance(failure, PipelineError) else 500)


def test_busy_concurrent_and_release(monkeypatch):
    async def scenario():
        entered, finish = asyncio.Event(), asyncio.Event()
        async def slow(*args, **kwargs):
            entered.set()
            await finish.wait()
            return {"partial": False, "timings": {}}
        monkeypatch.setattr(main, "_run", slow)
        main.guard.maximum = 1
        task = asyncio.create_task(request())
        await entered.wait()
        response = await request("/verify/stream")
        assert response.status_code == 429 and response.json()["error"] == "BUSY"
        assert response.headers["retry-after"] == "1"
        finish.set()
        await task
        assert main.guard.active == 0
    run(scenario())


@pytest.mark.parametrize("index", [0, 1, 2])
def test_shared_rate_and_quotas(index):
    seconds, _ = main.guard.limits[index]
    main.guard.limits[index] = (seconds, 1)
    assert run(request()).status_code == 200
    response = run(request("/verify/stream"))
    assert response.status_code == 429
    assert int(response.headers["retry-after"]) > 0
    assert main.guard.active == 0


def test_body_validation_low_memory(monkeypatch):
    response = run(request(content=b"x" * 65537))
    assert response.status_code == 413
    assert run(request(json={"text": " "})).status_code == 400
    assert run(request(json={"text": ""})).status_code == 422
    monkeypatch.setattr("app.security.memory_mb", lambda: (999, 999))
    response = run(request())
    assert response.status_code == 503 and response.json()["error"] == "LOW_MEMORY"
    assert "retry-after" in response.headers


def test_trusted_proxy_and_spoofing(monkeypatch):
    scope = {"client": ("192.0.2.1", 1), "headers": [(b"x-forwarded-for", b"1.2.3.4")]}
    assert Guard().client_ip(scope) == "192.0.2.1"
    monkeypatch.setenv("TRUSTED_PROXY_CIDRS", "192.0.2.0/24")
    guard = Guard()
    assert guard.client_ip(scope) == "1.2.3.4"
    scope["headers"] = [(b"x-forwarded-for", b"forged, 8.8.8.8, 192.0.2.2")]
    assert guard.client_ip(scope) == "8.8.8.8"
    scope["headers"] = [(b"x-forwarded-for", b"invalid")]
    assert guard.client_ip(scope) == "192.0.2.1"


def test_production_privacy_health(monkeypatch):
    monkeypatch.setitem(main.state, "init_error", "SECRET")
    async def scenario():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=main.app), base_url="http://test") as client:
            for path in ("/docs", "/redoc", "/openapi.json", "/health/deep", "/missing"):
                response = await client.get(path)
                assert response.status_code == 404
                assert response.json()["status"] == "error"
                assert "x-request-id" in response.headers
            health = await client.get("/health")
            assert health.status_code == 200 and "SECRET" not in health.text
            assert "init_error" not in health.text
    run(scenario())


@pytest.mark.parametrize("disconnect", [False, True])
def test_abandoned_thread_holds_capacity(monkeypatch, disconnect):
    async def scenario():
        loop = asyncio.get_running_loop()
        loop.set_default_executor(TrackingExecutor(max_workers=2))
        entered, finish = threading.Event(), threading.Event()
        def blocking():
            entered.set()
            finish.wait(5)
        async def worker(*args, **kwargs):
            if disconnect:
                await asyncio.to_thread(blocking)
            else:
                try:
                    await asyncio.wait_for(asyncio.to_thread(blocking), .03)
                except asyncio.TimeoutError:
                    raise PipelineError("EXTRACTION_TIMEOUT", "timeout", http_status=504)
        monkeypatch.setattr(main, "_run", worker)
        main.guard.maximum = 1
        task = asyncio.create_task(request("/verify/stream" if disconnect else "/verify"))
        try:
            while not entered.is_set():
                await asyncio.sleep(.001)
            if disconnect:
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)
            else:
                assert (await task).status_code == 504
            assert main.guard.active == 1
            assert (await request()).json()["error"] == "BUSY"
        finally:
            finish.set()
            for _ in range(100):
                if main.guard.active == 0:
                    break
                await asyncio.sleep(.01)
        assert main.guard.active == 0
    run(scenario())


def test_memory_measurement():
    rss, peak = memory_mb()
    assert 0 < rss <= peak


def test_startup_exception_safe(monkeypatch, caplog):
    monkeypatch.setattr(main.settings.__class__, "missing", lambda self: [])
    class Broken:
        def __init__(self, settings):
            raise RuntimeError("SECRET startup")
    monkeypatch.setitem(sys.modules, "app.llm", SimpleNamespace(LLM=Broken))
    async def scenario():
        async with main.lifespan(main.app):
            response = await request()
            assert response.status_code == 503
            assert "SECRET" not in response.text
    run(scenario())
    assert "SECRET" not in caplog.text


def test_preflight_has_request_id():
    async def scenario():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=main.app), base_url="http://test") as client:
            response = await client.options("/verify", headers={
                "Origin": "https://verify-test-swart.vercel.app",
                "Access-Control-Request-Method": "POST",
            })
            assert response.status_code == 200
            assert len(response.headers["x-request-id"]) == 32
            rejected = await client.options("/verify", headers={
                "Origin": "https://untrusted.example", "Access-Control-Request-Method": "POST",
            })
            assert rejected.status_code == 400
            assert rejected.json()["status"] == "error"
            assert "x-request-id" in rejected.headers
    run(scenario())


def test_global_quota_table_bound_and_window_reset(monkeypatch):
    now = [100000.0]
    monkeypatch.setattr("app.security.time.time", lambda: now[0])
    guard = Guard()
    guard.global_daily = 1
    assert guard.quota("one") == 0
    assert guard.quota("two") > 0
    now[0] += 86400
    assert guard.quota("two") == 0
    assert "one" not in guard.clients
    guard.global_daily = 100
    guard.client_limit = 1
    assert guard.quota("three") == 60
    assert len(guard.clients) == 1


def test_chunked_body_limit_without_content_length():
    async def chunks():
        yield b"a" * 40000
        yield b"b" * 25537
    response = run(request(content=chunks()))
    assert response.status_code == 413
    assert response.json()["error"] == "BODY_TOO_LARGE"


def test_adapter_exception_logging_redacted(caplog):
    caplog.set_level(logging.INFO)
    for name in ("verify.llm", "verify.retrieval", "verify.pipeline"):
        try:
            raise RuntimeError("SECRET raw-user-text")
        except RuntimeError:
            logging.getLogger(name).exception("SECRET raw-user-text %s", "api-key")
    assert "SECRET" not in caplog.text
    assert "Traceback" not in caplog.text and "api-key" not in caplog.text


def test_component_log_request_id(monkeypatch, caplog):
    caplog.set_level(logging.INFO)
    async def fake(*args, **kwargs):
        logging.getLogger("verify.llm").warning("SECRET")
        return {"results": [], "partial": False, "timings": {}}
    monkeypatch.setattr(main, "_run", fake)
    response = run(request())
    records = [record for record in caplog.records if record.name == "verify.llm"]
    assert records and response.headers["x-request-id"] in records[0].getMessage()
    assert "SECRET" not in caplog.text


def test_memory_probe_failure_fails_closed(monkeypatch):
    def fail():
        raise OSError("SECRET")
    monkeypatch.setattr("app.security.memory_mb", fail)
    response = run(request())
    assert response.status_code == 503
    assert response.json()["error"] == "LOW_MEMORY"
    assert "SECRET" not in response.text


def test_actual_asgi_stream_disconnect(monkeypatch):
    async def scenario():
        disconnected = asyncio.Event()
        async def slow(text, emit):
            await emit({"type": "claims", "claims": []})
            await asyncio.sleep(10)
        monkeypatch.setattr(main, "_run", slow)
        first = True
        async def receive():
            nonlocal first
            if first:
                first = False
                return {"type": "http.request", "body": b'{"text":"x"}', "more_body": False}
            await disconnected.wait()
            return {"type": "http.disconnect"}
        async def send(message):
            if message["type"] == "http.response.body" and message.get("body"):
                disconnected.set()
        scope = {
            "type": "http", "asgi": {"version": "3.0", "spec_version": "2.0"},
            "http_version": "1.1", "method": "POST", "scheme": "http",
            "path": "/verify/stream", "raw_path": b"/verify/stream", "query_string": b"",
            "headers": [(b"content-type", b"application/json")],
            "client": ("127.0.0.1", 1), "server": ("test", 80), "root_path": "",
        }
        await asyncio.wait_for(main.app(scope, receive, send), 1)
        assert disconnected.is_set()
        assert main.guard.active == 0
    run(scenario())
