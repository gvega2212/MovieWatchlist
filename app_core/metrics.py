from time import perf_counter
from flask import Blueprint, g, request, Response
from prometheus_client import Counter, Histogram, generate_latest, CONTENT_TYPE_LATEST

metrics_bp = Blueprint("metrics", __name__)

# Prometheus metrics
REQUEST_LATENCY = Histogram(
    "mw_http_request_latency_seconds",
    "Latency of HTTP requests",
    ["method", "path", "status"],
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2, 5),
)
REQUEST_COUNT = Counter(
    "mw_http_requests_total",
    "Total HTTP requests",
    ["method", "path", "status"],
)
ERROR_COUNT = Counter(
    "mw_http_errors_total",
    "Total HTTP 5xx responses",
    ["method", "path", "status"],
)

@metrics_bp.before_app_request
def _metrics_before():
    g._t_start = perf_counter()

@metrics_bp.after_app_request
def _metrics_after(resp):
    try:
        start = getattr(g, "_t_start", None)
        if start is None:
            return resp
        dur = perf_counter() - start
        method = request.method
        # stabilize label cardinality: use the rule pattern when available
        path = request.url_rule.rule if request.url_rule else request.path
        status = str(resp.status_code)

        REQUEST_LATENCY.labels(method, path, status).observe(dur)
        REQUEST_COUNT.labels(method, path, status).inc()
        if resp.status_code >= 500:
            ERROR_COUNT.labels(method, path, status).inc()
    finally:
        return resp

@metrics_bp.get("/metrics")
def metrics():
    data = generate_latest()
    return Response(data, mimetype=CONTENT_TYPE_LATEST)
