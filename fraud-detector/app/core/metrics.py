"""
Prometheus Metrics
==================
Exposes business and technical metrics for Grafana dashboards.

Metrics exposed:
  fraud_transactions_total          — Counter by status (APPROVE/BLOCK/REVIEW)
  fraud_risk_score_histogram         — Distribution of risk scores
  fraud_processing_latency_seconds  — End-to-end processing time
  fraud_ml_probability_histogram    — Distribution of ML fraud probabilities
  fraud_rules_triggered_total       — Counter per rule name (top offenders)
  fraud_scoring_mode_total          — Counter: hybrid vs rules_only
"""
from prometheus_client import Counter, Histogram, Gauge, CollectorRegistry, generate_latest
import logging

logger = logging.getLogger(__name__)

# ── Registry ──────────────────────────────────────────────────────────────────
REGISTRY = CollectorRegistry()

# ── Counters ──────────────────────────────────────────────────────────────────
transactions_total = Counter(
    "fraud_transactions_total",
    "Total transactions processed, by decision status",
    labelnames=["status", "risk_level"],
    registry=REGISTRY,
)

rules_triggered_total = Counter(
    "fraud_rules_triggered_total",
    "Number of times each fraud rule fired",
    labelnames=["rule_name"],
    registry=REGISTRY,
)

scoring_mode_total = Counter(
    "fraud_scoring_mode_total",
    "Scoring mode used: hybrid (ML+rules) vs rules_only",
    labelnames=["mode"],
    registry=REGISTRY,
)

# ── Histograms ────────────────────────────────────────────────────────────────
risk_score_histogram = Histogram(
    "fraud_risk_score",
    "Distribution of final fraud risk scores (0–100)",
    buckets=[10, 20, 30, 40, 50, 60, 70, 80, 90, 100],
    registry=REGISTRY,
)

ml_probability_histogram = Histogram(
    "fraud_ml_probability",
    "Distribution of raw ML fraud probabilities (0.0–1.0)",
    buckets=[0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0],
    registry=REGISTRY,
)

processing_latency = Histogram(
    "fraud_processing_latency_seconds",
    "End-to-end transaction processing time",
    buckets=[0.005, 0.010, 0.025, 0.050, 0.075, 0.100, 0.250, 0.500],
    registry=REGISTRY,
)

# ── Gauges ────────────────────────────────────────────────────────────────────
active_consumers_gauge = Gauge(
    "fraud_active_consumers",
    "Number of active Kafka consumer workers",
    registry=REGISTRY,
)


def record_decision(decision: dict):
    """Call this after each fraud decision is made."""
    try:
        status = decision.get("status", "UNKNOWN")
        risk_level = decision.get("risk_level", "UNKNOWN")
        risk_score = decision.get("risk_score", 0)
        latency_ms = decision.get("processing_time_ms", 0)
        mode = decision.get("scoring_mode", "rules_only")

        transactions_total.labels(status=status, risk_level=risk_level).inc()
        risk_score_histogram.observe(risk_score)
        processing_latency.observe(latency_ms / 1000.0)
        scoring_mode_total.labels(mode=mode).inc()

        if decision.get("ml_probability") is not None:
            ml_probability_histogram.observe(decision["ml_probability"])

        for rule in decision.get("triggered_rules", []):
            rules_triggered_total.labels(rule_name=rule).inc()

    except Exception as e:
        logger.error(f"Failed to record metrics: {e}")


def get_metrics() -> bytes:
    """Return Prometheus text format metrics."""
    return generate_latest(REGISTRY)
