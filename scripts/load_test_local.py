from __future__ import annotations

import argparse
import json
import statistics
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed


def hit(url: str, token: str) -> tuple[int, float]:
    headers = {"X-Request-Id": f"load-{time.time_ns()}"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(url, headers=headers)
    started = time.perf_counter()
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            response.read()
            status = response.status
    except urllib.error.HTTPError as exc:
        status = exc.code
    return status, (time.perf_counter() - started) * 1000


def main() -> int:
    parser = argparse.ArgumentParser(description="Smoke/load test local no destructivo.")
    parser.add_argument("--url", default="http://127.0.0.1:8000/readyz/")
    parser.add_argument("--requests", type=int, default=200)
    parser.add_argument("--concurrency", type=int, default=20)
    parser.add_argument("--token", default="")
    args = parser.parse_args()

    results = []
    with ThreadPoolExecutor(max_workers=max(1, args.concurrency)) as pool:
        futures = [pool.submit(hit, args.url, args.token) for _ in range(max(1, args.requests))]
        for future in as_completed(futures):
            results.append(future.result())

    latencies = sorted(latency for _status, latency in results)
    statuses = {}
    for status, _latency in results:
        statuses[str(status)] = statuses.get(str(status), 0) + 1
    percentile_index = min(len(latencies) - 1, int(len(latencies) * 0.95))
    payload = {
        "requests": len(results),
        "concurrency": args.concurrency,
        "statuses": statuses,
        "latency_ms": {
            "mean": round(statistics.mean(latencies), 2),
            "p95": round(latencies[percentile_index], 2),
            "max": round(max(latencies), 2),
        },
    }
    print(json.dumps(payload, indent=2))
    return 0 if all(200 <= status < 400 for status, _latency in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
