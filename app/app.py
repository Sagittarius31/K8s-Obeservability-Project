"""
Sample microservice instrumented for Prometheus.

Endpoints:
  GET  /            - simple health/info response
  GET  /work        - simulates variable latency + a configurable error rate
                       (use this to generate interesting graphs and trigger alerts)
  GET  /healthz      - liveness probe
  GET  /readyz       - readiness probe
  GET  /metrics      - Prometheus scrape endpoint
"""

import os
import random
import time

from flask import Flask, Response, jsonify
from prometheus_client import (
    Counter,
    Gauge,
    Histogram,
    generate_latest,
    CONTENT_TYPE_LATEST,
)

app = Flask(__name__)

# ---- Metrics -----------------------------------------------------------
# Counter: total requests, labeled by route + status, so we can compute
# error rate and request rate with PromQL (rate(...)/sum(...)).
REQUEST_COUNT = Counter(
    "app_http_requests_total",
    "Total HTTP requests",
    ["method", "endpoint", "http_status"],
)

# Histogram: request latency, used for p50/p95/p99 dashboards and
# latency-based alerting.
REQUEST_LATENCY = Histogram(
    "app_http_request_duration_seconds",
    "HTTP request duration in seconds",
    ["endpoint"],
    buckets=(0.05, 0.1, 0.25, 0.5, 1, 2, 5),
)

# Gauge: in-flight requests, used to demonstrate gauges + as a custom
# metric the HPA / Prometheus Adapter can scale on.
IN_PROGRESS = Gauge(
    "app_requests_in_progress",
    "Number of requests currently being processed",
)

# Configurable via env vars so you can crank up errors/latency during
# demos without redeploying code.
ERROR_RATE = float(os.environ.get("ERROR_RATE", "0.05"))  # 5% errors by default
MAX_LATENCY_MS = int(os.environ.get("MAX_LATENCY_MS", "400"))


@app.route("/")
def index():
    start = time.time()
    IN_PROGRESS.inc()
    try:
        REQUEST_COUNT.labels(method="GET", endpoint="/", http_status="200").inc()
        return jsonify(status="ok", message="k8s observability demo app")
    finally:
        REQUEST_LATENCY.labels(endpoint="/").observe(time.time() - start)
        IN_PROGRESS.dec()


@app.route("/work")
def work():
    start = time.time()
    IN_PROGRESS.inc()
    try:
        # Simulate realistic, variable latency
        delay = random.uniform(0, MAX_LATENCY_MS) / 1000.0
        time.sleep(delay)

        # Simulate a percentage of failures so you have something to alert on
        if random.random() < ERROR_RATE:
            REQUEST_COUNT.labels(method="GET", endpoint="/work", http_status="500").inc()
            return jsonify(status="error", message="simulated failure"), 500

        REQUEST_COUNT.labels(method="GET", endpoint="/work", http_status="200").inc()
        return jsonify(status="ok", latency_ms=round(delay * 1000, 2))
    finally:
        REQUEST_LATENCY.labels(endpoint="/work").observe(time.time() - start)
        IN_PROGRESS.dec()


@app.route("/healthz")
def healthz():
    return jsonify(status="alive")


@app.route("/readyz")
def readyz():
    return jsonify(status="ready")


@app.route("/metrics")
def metrics():
    return Response(generate_latest(), mimetype=CONTENT_TYPE_LATEST)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
