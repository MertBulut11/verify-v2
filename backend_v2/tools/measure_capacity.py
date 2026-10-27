"""Offline synthetic admission/RSS benchmark, not a real provider load test."""
import asyncio
import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
# This is an isolated benchmark process; no persistent configuration changes.
for key in ("RATE_LIMIT_PER_MINUTE", "HOURLY_QUOTA", "DAILY_QUOTA", "GLOBAL_DAILY_QUOTA"):
    os.environ[key] = "10000"

import httpx
from app import main
from app.resources import memory_mb


async def benchmark():
    async def fake(text, emit=None):
        await asyncio.sleep(.02)
        return {"results": [], "partial": False, "timings": {}}

    main._run = fake
    main.state["init_error"] = None
    before = memory_mb()
    started = time.perf_counter()
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=main.app), base_url="http://offline") as client:
        responses = await asyncio.gather(*[
            client.post("/verify", json={"text": "synthetic"}) for _ in range(20)
        ])
    after = memory_mb()
    print(json.dumps({
        "mode": "offline synthetic; no provider calls or lifespan initialization",
        "python": sys.version.split()[0],
        "requests": len(responses),
        "http_200": sum(r.status_code == 200 for r in responses),
        "http_429": sum(r.status_code == 429 for r in responses),
        "elapsed_seconds": round(time.perf_counter() - started, 4),
        "rss_before_mb": round(before[0], 2),
        "rss_after_mb": round(after[0], 2),
        "process_peak_mb": round(after[1], 2),
        "active_after": main.guard.active,
    }, indent=2))


if __name__ == "__main__":
    asyncio.run(benchmark())
