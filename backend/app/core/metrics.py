"""
Prometheus Metrics Registry & Collectors for SHG Credit Manager (Phase 7)
Monitors:
  - Request latency histogram (http_request_duration_seconds)
  - Ledger postings per second (ledger_posts_total)
  - Outbox queue lag / depth (outbox_pending_events)
  - Scheduled job duration (job_duration_seconds)
  - Total HTTP requests (http_requests_total)
"""

from prometheus_client import (
    CONTENT_TYPE_LATEST,
    Counter,
    Gauge,
    Histogram,
    generate_latest,
)

# 1. HTTP Request Latency Histogram
HTTP_REQUEST_DURATION_SECONDS = Histogram(
    "http_request_duration_seconds",
    "HTTP request latency in seconds",
    ["method", "endpoint", "status_code"],
    buckets=[0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0],
)

# 2. Total HTTP Requests Counter
HTTP_REQUESTS_TOTAL = Counter(
    "http_requests_total",
    "Total HTTP requests received",
    ["method", "endpoint", "status_code"],
)

# 3. Double-Entry Ledger Postings Counter
LEDGER_POSTS_TOTAL = Counter(
    "ledger_posts_total",
    "Total double-entry journal entries posted",
    ["source_type", "shg_id"],
)

# 4. Outbox Queue Lag / Pending Events Gauge
OUTBOX_PENDING_EVENTS = Gauge(
    "outbox_pending_events",
    "Current number of pending / unconsumed transactional outbox events",
)

# 5. Scheduled & Background Job Duration
JOB_DURATION_SECONDS = Histogram(
    "job_duration_seconds",
    "Duration of batch / background jobs in seconds",
    ["job_name"],
    buckets=[0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 15.0, 30.0, 60.0],
)


def get_metrics_content() -> tuple[bytes, str]:
    """Generates Prometheus latest metrics format with correct content-type."""
    return generate_latest(), CONTENT_TYPE_LATEST
