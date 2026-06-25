"""
Unit tests for the Fraud Rules Engine.
Run with: pytest tests/ -v
"""
import pytest
from app.rules.engine import (
    evaluate,
    score_to_level,
    score_to_action,
    TransactionContext,
    rule_large_transaction,
    rule_high_risk_country,
    rule_velocity_60s,
    rule_impossible_travel,
)
from datetime import datetime, timezone, timedelta


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def base_transaction():
    return {
        "transaction_id": "test-tx-001",
        "user_id": 1001,
        "amount": 100.00,
        "country": "India",
        "merchant": "Amazon",
        "merchant_category": "retail",
    }


@pytest.fixture
def clean_ctx():
    return TransactionContext(
        user_country_history=["India"],
        transactions_last_60s=0,
        transactions_last_10min=0,
    )


# ── Rule: Large Transaction ───────────────────────────────────────────────────

def test_large_transaction_above_50k(base_transaction, clean_ctx):
    base_transaction["amount"] = 55_000
    score, rule = rule_large_transaction(base_transaction, clean_ctx)
    assert score == 40
    assert rule == "LARGE_TRANSACTION_50K"


def test_large_transaction_above_10k(base_transaction, clean_ctx):
    base_transaction["amount"] = 12_000
    score, rule = rule_large_transaction(base_transaction, clean_ctx)
    assert score == 20
    assert rule == "LARGE_TRANSACTION_10K"


def test_large_transaction_normal(base_transaction, clean_ctx):
    base_transaction["amount"] = 500
    score, rule = rule_large_transaction(base_transaction, clean_ctx)
    assert score == 0
    assert rule is None


# ── Rule: High Risk Country ───────────────────────────────────────────────────

def test_high_risk_country_flagged(base_transaction, clean_ctx):
    base_transaction["country"] = "Russia"
    score, rule = rule_high_risk_country(base_transaction, clean_ctx)
    assert score == 30
    assert rule == "HIGH_RISK_COUNTRY"


def test_safe_country_not_flagged(base_transaction, clean_ctx):
    base_transaction["country"] = "Germany"
    score, rule = rule_high_risk_country(base_transaction, clean_ctx)
    assert score == 0


# ── Rule: Velocity ────────────────────────────────────────────────────────────

def test_high_velocity_triggers(base_transaction, clean_ctx):
    clean_ctx.transactions_last_60s = 6
    score, rule = rule_velocity_60s(base_transaction, clean_ctx)
    assert score == 35
    assert "VELOCITY_HIGH" in rule


def test_medium_velocity_triggers(base_transaction, clean_ctx):
    clean_ctx.transactions_last_60s = 3
    score, rule = rule_velocity_60s(base_transaction, clean_ctx)
    assert score == 15


def test_low_velocity_no_flag(base_transaction, clean_ctx):
    clean_ctx.transactions_last_60s = 1
    score, rule = rule_velocity_60s(base_transaction, clean_ctx)
    assert score == 0


# ── Rule: Impossible Travel ───────────────────────────────────────────────────

def test_impossible_travel_detected(base_transaction, clean_ctx):
    """Two different countries within 15 minutes → flag it."""
    clean_ctx.last_transaction_country = "India"
    clean_ctx.last_transaction_ts = datetime.now(timezone.utc) - timedelta(minutes=15)
    base_transaction["country"] = "USA"

    score, rule = rule_impossible_travel(base_transaction, clean_ctx)
    assert score == 40
    assert "IMPOSSIBLE_TRAVEL" in rule


def test_same_country_no_travel_flag(base_transaction, clean_ctx):
    clean_ctx.last_transaction_country = "India"
    clean_ctx.last_transaction_ts = datetime.now(timezone.utc) - timedelta(minutes=5)
    base_transaction["country"] = "India"

    score, rule = rule_impossible_travel(base_transaction, clean_ctx)
    assert score == 0


def test_travel_ok_if_enough_time(base_transaction, clean_ctx):
    clean_ctx.last_transaction_country = "India"
    clean_ctx.last_transaction_ts = datetime.now(timezone.utc) - timedelta(hours=5)
    base_transaction["country"] = "USA"

    score, rule = rule_impossible_travel(base_transaction, clean_ctx)
    assert score == 0


# ── Full Pipeline ────────────────────────────────────────────────────────────

def test_critical_score_multiple_rules(base_transaction, clean_ctx):
    """A Russian transaction, $55k, from a new country should be CRITICAL."""
    base_transaction["amount"] = 55_000
    base_transaction["country"] = "Russia"
    clean_ctx.user_country_history = ["India", "USA"]  # Russia is new

    result = evaluate(base_transaction, clean_ctx)
    assert result.score == 100  # Capped at 100
    assert score_to_level(result.score) == "CRITICAL"
    assert score_to_action(result.score) == "BLOCK"
    assert len(result.triggered_rules) > 1


def test_clean_transaction_low_score(base_transaction, clean_ctx):
    """Normal transaction should have a LOW risk score."""
    result = evaluate(base_transaction, clean_ctx)
    assert result.score <= 30
    assert score_to_level(result.score) == "LOW"
    assert score_to_action(result.score) == "APPROVE"


# ── Score Mapping ─────────────────────────────────────────────────────────────

@pytest.mark.parametrize("score,expected_level,expected_action", [
    (10, "LOW", "APPROVE"),
    (45, "MEDIUM", "REVIEW"),
    (70, "HIGH", "BLOCK"),
    (95, "CRITICAL", "BLOCK"),
])
def test_score_mapping(score, expected_level, expected_action):
    assert score_to_level(score) == expected_level
    assert score_to_action(score) == expected_action
