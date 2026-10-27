"""
Verify backend v2.

Endpoints
  GET  /              liveness
  GET  /health        lightweight liveness and safe readiness summary
  GET  /health/deep   disabled (404); never makes paid provider calls
  POST /verify        same request/response shape as the old backend, plus
                      per-claim `status`, `timings`, and `partial`.
                      Always answers within TOTAL_TIMEOUT seconds.
  POST /verify/stream Server-Sent Events: claims arrive first, then each
                      verdict as soon as it is ready, then `done`.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field
from starlette.exceptions import HTTPException

load_dotenv()

from .config import Settings  # noqa: E402
from .pipeline import PipelineError, TTLCache, run_pipeline  # noqa: E402
from .security import Guard, SecurityMiddleware, RequestIDMiddleware, error
from .resources import TrackingExecutor, positive_env
from .safe_logging import install_safe_logging

install_safe_logging()

logging.basicConfig(
    level={"DEBUG": logging.DEBUG, "INFO": logging.INFO, "WARNING": logging.WARNING,
           "ERROR": logging.ERROR}.get(os.getenv("LOG_LEVEL", "INFO").upper(), logging.INFO),
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
install_safe_logging()
log = logging.getLogger("verify.api")

settings = Settings.from_env()
production = os.getenv("APP_ENV", "production").strip().lower() not in {"development", "test"}
guard = Guard()
state: dict = {"llm": None, "retriever": None, "cache": None, "init_error": None}


@asynccontextmanager
async def lifespan(app: FastAPI):
    asyncio.get_running_loop().set_default_executor(
        TrackingExecutor(max_workers=positive_env("MAX_BACKGROUND_THREADS", 8))
    )
    state.update(llm=None, retriever=None, cache=None, init_error=None)
    # A missing key must NOT crash the server: it should start and say what is wrong.
    missing = settings.missing()
    if missing:
        state["init_error"] = "Eksik ortam değişkenleri: " + ", ".join(missing)
        log.error("startup configuration unavailable")
    else:
        try:
            from .llm import LLM
            from .retrieval import build_retriever

            state["llm"] = LLM(settings)
            state["retriever"] = build_retriever(settings)
            state["cache"] = TTLCache(ttl=settings.cache_ttl)
            log.info("startup ready")
        except Exception:
            state["init_error"] = "initialization failed"
            log.error("startup initialization failed")
    yield


app = FastAPI(
    title="Verify Backend", version="2.0.0", lifespan=lifespan,
    docs_url=None if production else "/docs",
    redoc_url=None if production else "/redoc",
    openapi_url=None if production else "/openapi.json",
)

allowed_origins = [
    "https://verify-test-swart.vercel.app",
    "http://localhost:3000",
    "http://localhost:5173",
]
if settings.frontend_origin and settings.frontend_origin not in allowed_origins:
    allowed_origins.append(settings.frontend_origin)
if os.getenv("CORS_ORIGINS"):
    allowed_origins = [value.strip() for value in os.environ["CORS_ORIGINS"].split(",") if value.strip()]
if production:
    allowed_origins = [value for value in allowed_origins if value.startswith("https://") and "*" not in value]

app.add_middleware(SecurityMiddleware, guard=guard)

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Request-ID", "Retry-After"],
)
app.add_middleware(RequestIDMiddleware)


@app.exception_handler(HTTPException)
async def http_exception_handler(request, exc):
    return error("HTTP_ERROR", exc.status_code)


class VerifyRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=10000)


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request, exc):
    return JSONResponse(
        status_code=422,
        content={
            "status": "error",
            "error": "VALIDATION_ERROR",
            "message": "Gönderilen veri geçersiz.",
        },
    )


def _not_ready():
    return JSONResponse(
        status_code=503,
        content={
            "status": "error",
            "error": "CONFIG_ERROR",
            "message": "Sunucu yapılandırması eksik.",
        },
    )


def _error_response(e: PipelineError):
    content = {"status": "error", "error": e.code, "message": "Doğrulama tamamlanamadı."}
    return JSONResponse(status_code=e.http_status, content=content)


async def _run(text: str, emit=None):
    return await run_pipeline(
        text,
        extract=state["llm"].extract,
        retrieve=state["retriever"],
        verify=state["llm"].verify,
        cfg=settings.pipeline,
        cache=state["cache"],
        emit=emit,
    )


@app.get("/")
def root():
    return {"status": "ok", "message": "Backend çalışıyor!"}


@app.get("/health")
def health():
    return {
        "status": "ok" if state["init_error"] is None else "degraded",
        "service": "verify-backend",
        "version": "2.0.0",
        "config": {
            "model": settings.model_name,
            "reasoning_effort": settings.reasoning_effort or None,
            "retriever": settings.retriever,
            "tavily_depth": settings.tavily_depth,
            "groq_key_set": bool(settings.groq_api_key),
            "tavily_key_set": bool(settings.tavily_api_key),
            "max_claims": settings.pipeline.max_claims,
            "claim_concurrency": settings.pipeline.claim_concurrency,
            "total_timeout_s": settings.pipeline.total_timeout,
            "cache_entries": len(state["cache"]) if state["cache"] is not None else 0,
        },
    }


@app.get("/health/deep", include_in_schema=False)
async def health_deep():
    return error("HTTP_ERROR", 404)


@app.post("/verify")
async def verify(request: VerifyRequest):
    if state["init_error"]:
        return _not_ready()

    text = request.text.strip()
    if not text:
        return JSONResponse(
            status_code=400,
            content={
                "status": "error",
                "error": "EMPTY_TEXT",
                "message": "Doğrulanacak metin boş olamaz.",
            },
        )

    try:
        return await _run(text)
    except PipelineError as e:
        return _error_response(e)
    except Exception:
        log.error("verification failed")
        return JSONResponse(
            status_code=500,
            content={
                "status": "error",
                "error": "VERIFY_FAILED",
                "message": "Doğrulama işlemi sırasında bir hata oluştu.",
            },
        )


@app.post("/verify/stream")
async def verify_stream(request: VerifyRequest):
    if state["init_error"]:
        return _not_ready()

    text = request.text.strip()
    if not text:
        return error("EMPTY_TEXT", 400)
    queue: asyncio.Queue = asyncio.Queue(maxsize=64)

    async def emit(event: dict):
        await queue.put(event)

    async def runner():
        try:
            res = await _run(text, emit=emit)
            await queue.put({"type": "done", "partial": res["partial"], "timings": res["timings"]})
        except PipelineError as e:
            await queue.put({"type": "error", "error": e.code, "message": "Doğrulama tamamlanamadı."})
        except Exception:
            log.error("stream verification failed")
            await queue.put(
                {"type": "error", "error": "VERIFY_FAILED", "message": "Doğrulama işlemi sırasında bir hata oluştu.",
                 }
            )
        finally:
            if not asyncio.current_task().cancelling():
                await queue.put(None)

    task = asyncio.create_task(runner())

    async def gen():
        try:
            while True:
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=15)
                except asyncio.TimeoutError:
                    yield ": keep-alive\n\n"  # stops proxies from closing an idle connection
                    continue
                if event is None:
                    break
                yield f"event: {event['type']}\ndata: {json.dumps(event, ensure_ascii=False)}\n\n"
        finally:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
