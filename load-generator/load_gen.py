#!/usr/bin/env python3
"""Thread Pool Lab - Load Generator Control API (port 8090)"""

import asyncio, statistics, time, random, subprocess
from typing import Optional
import httpx
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

app = FastAPI(title="Thread Pool Lab – Load Generator")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

_results: list = []
_running = False
_current_task: Optional[asyncio.Task] = None
_summary: dict = {}

SCENARIOS = [
    {
        "id": "cluster-chaos",
        "name": "🌪️ Cluster Chaos + Failover (2 min)",
        "description": "Ramps to 580 concurrent across all 3 instances (maxing 600 threads). At t=40s Instance 2 is killed — watch the proxy reroute. At t=80s Instance 3 is killed — only Instance 1 survives. See p99 spike and the single surviving grid stay full red.",
        "config": {},
        "mode": "failover", "duration": 30, "max_concur": 700
    },
    {
        "id": "production-chaos",
        "name": "🌪️ Production Chaos (5 min)",
        "description": "Simulates real production traffic: random request durations (100ms–8s), mixed endpoints (I/O, DB, CPU, fast), concurrency swings wildly between 5 and 180. Sudden spikes and drops every 5–25s. Watch the grid breathe.",
        "config": {"TOMCAT_MAX_THREADS": "200"},
        "mode": "chaos", "duration": 300, "min_concur": 5, "max_concur": 550
    },
    {
        "id": "spike-storm",
        "name": "⚡ Spike Storm (3 min)",
        "description": "Quiet baseline of ~10 threads, then random violent spikes to 150+ threads every 10–30s. Each spike uses slow requests (2–8s) so the red grid stays full longer. Models traffic after a viral event or retry storm.",
        "config": {"TOMCAT_MAX_THREADS": "200"},
        "mode": "chaos", "duration": 180, "min_concur": 3, "max_concur": 500,
        "spike_bias": 0.4
    },
    {
        "id": "lb-round-robin",
        "name": "⚖️ Load Balancer Distribution",
        "description": "300 concurrent requests via the round-robin proxy. Each instance should handle ~33%. Watch all 3 thread grids fill equally. Shows even distribution across the cluster.",
        "config": {},
        "mode": "burst", "n": 300, "endpoint": "/api/io", "params": {"ms": 4000}
    },
    {
        "id": "instance-overload",
        "name": "🔥 Cluster Overload (600 req)",
        "description": "600 simultaneous requests against a 3×200 thread cluster. All 600 thread slots fill instantly. 0 queuing if all 3 instances healthy. Kill one instance mid-run to watch the other two compensate.",
        "config": {},
        "mode": "burst", "n": 600, "endpoint": "/api/io", "params": {"ms": 5000}
    },
    {
        "id": "burst-showcase",
        "name": "🚀 Burst 300→Pool 200 (Showcase)",
        "description": "300 requests hit a 200-thread pool simultaneously. First 200 execute immediately; 100 queue. Watch the grid fill in one frame, then the queue drain as threads free up. Expected: first 200 complete at ~1s, last 100 at ~2s.",
        "config": {"TOMCAT_MAX_THREADS": "200"},
        "mode": "burst", "n": 300, "endpoint": "/api/io", "params": {"ms": 5000}
    },
    {
        "id": "under-capacity",
        "name": "Under Capacity (50 vs 200 pool)",
        "description": "50 concurrent requests against a 200-thread pool. Grid shows 50/200 squares busy. Latency flat (~3s). Little's Law: L=50, W=3s → λ=17 req/s.",
        "config": {"TOMCAT_MAX_THREADS": "200"},
        "mode": "burst", "n": 50, "endpoint": "/api/io", "params": {"ms": 3000}
    },
    {
        "id": "tiny-pool",
        "name": "Tiny Pool (10 threads, 50 requests)",
        "description": "50 requests, pool=10. Only 10/10 squares lit. 40 requests queue with long orange wait bars. Restart app with TOMCAT_MAX_THREADS=10.",
        "config": {"TOMCAT_MAX_THREADS": "10"},
        "mode": "burst", "n": 50, "endpoint": "/api/io", "params": {"ms": 3000}
    },
    {
        "id": "sustained-overload",
        "name": "Sustained Overload",
        "description": "20 req/s arrival, 500ms processing = 10 always in flight. Pool=10 → queue grows unboundedly. Watch p99 climb over 30s. Restart with TOMCAT_MAX_THREADS=10.",
        "config": {"TOMCAT_MAX_THREADS": "10"},
        "mode": "sustained", "rate": 20, "duration": 30, "endpoint": "/api/io", "params": {"ms": 500}
    },
    {
        "id": "db-bottleneck",
        "name": "DB Pool Bottleneck",
        "description": "50 threads, DB pool=3. Threads pick up work instantly then block waiting for a DB connection. More threads won't help. Restart with DB_POOL_MAX=3.",
        "config": {"TOMCAT_MAX_THREADS": "50", "DB_POOL_MAX": "3"},
        "mode": "burst", "n": 30, "endpoint": "/api/db-sleep", "params": {"ms": 300}
    },
    {
        "id": "cpu-bound",
        "name": "CPU Bound vs I/O Bound",
        "description": "20 CPU-heavy requests. On M3 Pro (12 cores) adding threads beyond 12 causes context-switching overhead. Compare throughput: n=6 vs n=20.",
        "config": {"TOMCAT_MAX_THREADS": "20"},
        "mode": "burst", "n": 20, "endpoint": "/api/cpu", "params": {"iterations": 200000000}
    },
    {
        "id": "slow-starves-fast",
        "name": "Slow Starves Fast (Bulkhead needed)",
        "description": "100 slow requests (3s each) fill a 20-thread pool. Fast requests queue behind them. Fix: separate thread pools per endpoint. Restart with TOMCAT_MAX_THREADS=20.",
        "config": {"TOMCAT_MAX_THREADS": "20"},
        "mode": "burst", "n": 100, "endpoint": "/api/slow", "params": {"ms": 3000}
    },
    {
        "id": "virtual-threads",
        "name": "Virtual Threads (Project Loom)",
        "description": "With VIRTUAL_THREADS=true, Spring uses Project Loom. 500 I/O requests execute concurrently without blocking carrier threads. The thread grid shows carrier threads only. Restart with VIRTUAL_THREADS=true.",
        "config": {"VIRTUAL_THREADS": "true", "TOMCAT_MAX_THREADS": "200"},
        "mode": "burst", "n": 500, "endpoint": "/api/io", "params": {"ms": 500}
    },
    {
        "id": "littles-law",
        "name": "Little's Law Verification",
        "description": "L = λ × W. Sending 10 req/s at 200ms each → L = 2 concurrent. Busy threads should ≈ 2. Sustained 30s run with steady state.",
        "config": {"TOMCAT_MAX_THREADS": "200"},
        "mode": "sustained", "rate": 10, "duration": 30, "endpoint": "/api/io", "params": {"ms": 200}
    },
]

APP_BASE = "http://localhost:8000"   # round-robin proxy


@app.get("/scenarios")
def list_scenarios():
    return SCENARIOS


@app.get("/status")
def status():
    return {"running": _running, "count": len(_results), **_summary}


@app.get("/results")
def get_results():
    if not _results:
        return {"count": 0, "p50": 0.0, "p99": 0.0, "errors": 0, "recent": []}
    done = [r for r in _results if not r.get("error") and r.get("total_ms") is not None]
    errs = sum(1 for r in _results if r.get("error"))
    lats = [r["total_ms"] for r in done]
    p50 = round(statistics.median(lats), 1) if lats else 0
    p99 = round(
        (statistics.quantiles(lats, n=100)[98] if len(lats) >= 2 else (lats[0] if lats else 0)), 1
    )
    inst_counts = {}
    for r in _results:
        inst = r.get("instance", "?")
        inst_counts[inst] = inst_counts.get(inst, 0) + 1
    return {"count": len(_results), "completed": len(done), "errors": errs, "p50": p50, "p99": p99, "instances": inst_counts, "recent": _results[-2000:]}


@app.post("/run/{scenario_id}")
async def run_scenario(scenario_id: str):
    global _running, _results, _current_task, _summary
    s = next((x for x in SCENARIOS if x["id"] == scenario_id), None)
    if not s:
        return {"error": f"unknown scenario: {scenario_id}"}
    if _running:
        return {"error": "already running — POST /stop first"}
    _results = []
    _summary = {}
    _running = True
    _current_task = asyncio.create_task(_do_run(s))
    return {"status": "started", "scenario": s["name"]}


@app.post("/stop")
async def stop():
    global _running, _current_task
    _running = False
    if _current_task:
        _current_task.cancel()
    return {"status": "stopped"}


async def _req(client: httpx.AsyncClient, url: str) -> dict:
    sent = time.time() * 1000
    hdrs = {"X-Sent-At": str(int(sent))}
    try:
        r = await client.get(url, headers=hdrs, timeout=90.0)
        done = time.time() * 1000
        return {
            "sent_at": sent,
            "complete_at": done,
            "total_ms": round(done - sent, 1),
            "wait_ms": int(r.headers.get("X-Wait-Ms", 0)),
            "exec_ms": int(r.headers.get("X-Exec-Ms", 0)),
            "thread": r.headers.get("X-Thread-Name", "?"),
            "instance": r.headers.get("X-Instance", "?"),
            "status": r.status_code,
        }
    except Exception as e:
        done = time.time() * 1000
        return {"sent_at": sent, "complete_at": done, "total_ms": round(done - sent, 1), "error": str(e)}


def _random_chaos_url(s: dict) -> str:
    spike_bias = s.get("spike_bias", 0.0)
    roll = random.random()
    # Spike-storm scenarios use longer sleeps
    ms_lo = 2000 if spike_bias > 0.3 else 100
    ms_hi = 8000 if spike_bias > 0.3 else 6000
    if roll < 0.55:
        ms = random.randint(ms_lo, ms_hi)
        return f"{APP_BASE}/api/io?ms={ms}"
    elif roll < 0.70:
        rows = random.randint(10, 300)
        return f"{APP_BASE}/api/db?rows={rows}"
    elif roll < 0.80:
        return f"{APP_BASE}/api/fast"
    elif roll < 0.90:
        ms = random.randint(500, 4000)
        return f"{APP_BASE}/api/slow?ms={ms}"
    else:
        iters = random.randint(5_000_000, 50_000_000)
        return f"{APP_BASE}/api/cpu?iterations={iters}"


LIMITS = httpx.Limits(max_connections=800, max_keepalive_connections=400)


async def _chaos_run(client: httpx.AsyncClient, s: dict):
    global _running
    duration = s.get("duration", 300)
    min_concur = s.get("min_concur", 5)
    max_concur = s.get("max_concur", 180)
    spike_bias = s.get("spike_bias", 0.0)

    end_time = time.time() + duration
    target = random.randint(min_concur, max(min_concur, max_concur // 4))
    next_change = time.time() + random.uniform(8, 20)
    active: set = set()

    async def spawn_one():
        url = _random_chaos_url(s)
        result = await _req(client, url)
        _results.append(result)

    while time.time() < end_time and _running:
        now = time.time()

        # Periodic concurrency change — sudden spikes/drops
        if now > next_change:
            roll = random.random()
            if roll < (0.30 + spike_bias):          # sudden spike
                target = random.randint(int(max_concur * 0.6), max_concur)
            elif roll < (0.30 + spike_bias + 0.20): # sudden drop
                target = random.randint(min_concur, max(min_concur, max_concur // 6))
            else:                                    # gradual drift
                delta = random.randint(-25, 25)
                target = max(min_concur, min(max_concur, target + delta))
            next_change = now + random.uniform(5, 25)

        # Reap finished tasks
        finished = {t for t in active if t.done()}
        active -= finished

        # Fill up to target concurrency
        while len(active) < target and _running:
            t = asyncio.create_task(spawn_one())
            active.add(t)

        await asyncio.sleep(0.05)

    # Drain remaining in-flight requests
    if active:
        await asyncio.gather(*active, return_exceptions=True)


async def _failover_run(client: httpx.AsyncClient, s: dict):
    """Ramp to max concurrency, then kill Instance 2 at t=40s and Instance 3 at t=80s."""
    global _running
    duration = s.get("duration", 120)
    max_concur = s.get("max_concur", 580)
    start_time = time.time()
    end_time = start_time + duration
    active: set = set()
    killed_2 = False
    killed_3 = False

    JAVA_HOME = subprocess.run(
        ["/usr/libexec/java_home", "-v", "25"], capture_output=True, text=True
    ).stdout.strip() or subprocess.run(
        ["/usr/libexec/java_home"], capture_output=True, text=True
    ).stdout.strip()
    JAR = "/Users/suchith.kumargm/personal/study/study materials/spring boot/my practice codes/spring boot thread pool testing/app/target/thread-pool-lab-1.0.0-SNAPSHOT.jar"

    async def spawn_one():
        url = _random_chaos_url(s)
        result = await _req(client, url)
        _results.append(result)

    while time.time() < end_time and _running:
        elapsed = time.time() - start_time
        # Ramp up to full concurrency in first 15s
        target = min(max_concur, max(20, int(max_concur * elapsed / 15)))

        # t=10s: kill Instance 2
        if elapsed >= 10 and not killed_2:
            subprocess.run(["pkill", "-f", "server.port=8082"], capture_output=True)
            killed_2 = True

        # t=20s: kill Instance 3
        if elapsed >= 20 and not killed_3:
            subprocess.run(["pkill", "-f", "server.port=8084"], capture_output=True)
            killed_3 = True

        finished = {t for t in active if t.done()}
        active -= finished
        while len(active) < target and _running:
            active.add(asyncio.create_task(spawn_one()))

        await asyncio.sleep(0.05)

    if active:
        await asyncio.gather(*active, return_exceptions=True)


async def _do_run(s: dict):
    global _running, _summary
    ep = s.get("endpoint", "/api/io")
    qs = "&".join(f"{k}={v}" for k, v in s.get("params", {}).items())
    url = f"{APP_BASE}{ep}{'?' + qs if qs else ''}"
    try:
        async with httpx.AsyncClient(limits=LIMITS) as client:
            if s["mode"] == "burst":
                rs = await asyncio.gather(*[_req(client, url) for _ in range(s["n"])])
                _results.extend(rs)
            elif s["mode"] == "sustained":
                interval = 1.0 / s["rate"]
                end = time.time() + s["duration"]
                tasks = []
                while time.time() < end and _running:
                    tasks.append(asyncio.create_task(_req(client, url)))
                    await asyncio.sleep(interval)
                _results.extend(await asyncio.gather(*tasks))
            elif s["mode"] == "failover":
                await _failover_run(client, s)
            elif s["mode"] == "chaos":
                await _chaos_run(client, s)
    finally:
        _running = False
        done = [r for r in _results if not r.get("error")]
        lats = [r["total_ms"] for r in done]
        _summary = {
            "total": len(_results),
            "errors": len(_results) - len(done),
            "p50": round(statistics.median(lats), 1) if lats else 0,
            "p99": round(
                (statistics.quantiles(lats, n=100)[98] if len(lats) >= 2 else (lats[0] if lats else 0)), 1
            ),
        }


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8090, log_level="info")
