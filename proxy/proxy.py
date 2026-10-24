import itertools
import httpx
import uvicorn
from collections import defaultdict
from fastapi import FastAPI, Request
from fastapi.responses import Response

app = FastAPI()

BACKENDS = ["http://localhost:8080", "http://localhost:8082", "http://localhost:8084"]
_cycle = itertools.cycle(BACKENDS)
request_counts: dict[str, int] = defaultdict(int)

client = httpx.AsyncClient(
    limits=httpx.Limits(max_connections=800),
    timeout=90.0,
)


@app.get("/proxy/status")
async def status():
    return {"request_counts": dict(request_counts)}


@app.get("/proxy/health")
async def health():
    results = {}
    for backend in BACKENDS:
        try:
            r = await client.get(f"{backend}/api/fast", timeout=3.0)
            results[backend] = "up" if r.status_code < 500 else "down"
        except Exception:
            results[backend] = "down"
    return results


@app.api_route("/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"])
async def proxy(path: str, request: Request):
    url_path = path + (f"?{request.url.query}" if request.url.query else "")
    headers = dict(request.headers)
    headers.pop("host", None)
    body = await request.body()

    # Try each backend in round-robin order; skip dead ones
    for _ in range(len(BACKENDS)):
        backend = next(_cycle)
        try:
            r = await client.request(
                method=request.method,
                url=f"{backend}/{url_path}",
                headers=headers,
                content=body,
            )
            request_counts[backend] += 1
            resp_headers = dict(r.headers)
            resp_headers["X-Instance"] = backend.replace("http://", "")
            return Response(
                content=r.content,
                status_code=r.status_code,
                headers=resp_headers,
                media_type=r.headers.get("content-type"),
            )
        except (httpx.ConnectError, httpx.RemoteProtocolError):
            continue  # backend down — try next

    return Response(content=b'{"error":"all backends down"}', status_code=503,
                    media_type="application/json")


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
