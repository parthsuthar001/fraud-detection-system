"""
Fraud Rules Engine
==================
Each rule is a pure function: (transaction, context) -> (score_delta, rule_name | None).
Rules are composable and independently testable.
"""
from dataclasses import dataclass, field
from typing import Optional
from datetime import datetime, timezone
import logging

logger = logging.getLogger(__name__)


@dataclass
class TransactionContext:
    """Enriched context pulled from Redis + PostgreSQL before rule evaluation."""
    user_country_history: list[str] = field(default_factory=list)
    transactions_last_60s: int = 0
    transactions_last_10min: int = 0
    last_transaction_country: Optional[str] = None
    last_transaction_ts: Optional[datetime] = None
    account_age_days: int = 365
    is_first_transaction: bool = False


@dataclass
class RuleResult:
    score: int
    triggered_rules: list[str]


HIGH_RISK_COUNTRIES = {"Russia", "Nigeria", "North Korea", "Iran", "Belarus"}
HIGH_RISK_MERCHANTS = {"gambling", "crypto", "adult", "wire_transfer"}


def rule_large_transaction(transaction: dict, ctx: TransactionContext) -> tuple[int, Optional[str]]:
    """Flag unusually large amounts."""
    amount = transaction.get("amount", 0)
    if amount > 50_000:
        return 40, "LARGE_TRANSACTION_50K"
    if amount > 10_000:
        return 20, "LARGE_TRANSACTION_10K"
    return 0, None


def rule_high_risk_country(transaction: dict, ctx: TransactionContext) -> tuple[int, Optional[str]]:
    """Penalise transactions originating from high-risk jurisdictions."""
    if transaction.get("country") in HIGH_RISK_COUNTRIES:
        return 30, "HIGH_RISK_COUNTRY"
    return 0, None


def rule_new_country(transaction: dict, ctx: TransactionContext) -> tuple[int, Optional[str]]:
    """Penalise if the user has never transacted from this country before."""
    country = transaction.get("country")
    if country and ctx.user_country_history and country not in ctx.user_country_history:
        return 20, "NEW_COUNTRY"
    return 0, None


def rule_velocity_60s(transaction: dict, ctx: TransactionContext) -> tuple[int, Optional[str]]:
    """High-velocity micro-transactions — card testing pattern."""
    if ctx.transactions_last_60s >= 5:
        return 35, f"VELOCITY_HIGH_{ctx.transactions_last_60s}_IN_60S"
    if ctx.transactions_last_60s >= 3:
        return 15, f"VELOCITY_MEDIUM_{ctx.transactions_last_60s}_IN_60S"
    return 0, None


def rule_velocity_10min(transaction: dict, ctx: TransactionContext) -> tuple[int, Optional[str]]:
    """Elevated velocity over a 10-minute window."""
    if ctx.transactions_last_10min >= 10:
        return 25, f"VELOCITY_10MIN_{ctx.transactions_last_10min}"
    return 0, None


def rule_impossible_travel(transaction: dict, ctx: TransactionContext) -> tuple[int, Optional[str]]:
    """Impossible travel: same user in two different countries within 20 minutes."""
    if not ctx.last_transaction_ts or not ctx.last_transaction_country:
        return 0, None

    current_country = transaction.get("country")
    if current_country == ctx.last_transaction_country:
        return 0, None

    now = datetime.now(timezone.utc)
    minutes_since_last = (now - ctx.last_transaction_ts).total_seconds() / 60

    if minutes_since_last < 20:
        return 40, f"IMPOSSIBLE_TRAVEL_{ctx.last_transaction_country}_TO_{current_country}"
    return 0, None


def rule_night_activity(transaction: dict, ctx: TransactionContext) -> tuple[int, Optional[str]]:
    """Slight penalty for 1 AM – 5 AM transactions (common fraud window)."""
    hour = datetime.now(timezone.utc).hour
    if 1 <= hour <= 5:
        return 10, "NIGHT_ACTIVITY"
    return 0, None


def rule_new_account(transaction: dict, ctx: TransactionContext) -> tuple[int, Optional[str]]:
    """New accounts making large purchases are higher risk."""
    if ctx.account_age_days < 7 and transaction.get("amount", 0) > 1000:
        return 20, "NEW_ACCOUNT_LARGE_TX"
    return 0, None


def rule_high_risk_merchant(transaction: dict, ctx: TransactionContext) -> tuple[int, Optional[str]]:
    """Flag transactions at historically risky merchant categories."""
    category = (transaction.get("merchant_category") or "").lower()
    if any(risk in category for risk in HIGH_RISK_MERCHANTS):
        return 15, f"HIGH_RISK_MERCHANT_{category.upper()}"
    return 0, None


# Ordered rule pipeline — rules are evaluated in sequence
RULE_PIPELINE = [
    rule_large_transaction,
    rule_high_risk_country,
    rule_new_country,
    rule_velocity_60s,
    rule_velocity_10min,
    rule_impossible_travel,
    rule_night_activity,
    rule_new_account,
    rule_high_risk_merchant,
]


def evaluate(transaction: dict, ctx: TransactionContext) -> RuleResult:
    """Run all rules and return the aggregated fraud score + triggered rule names."""
    total_score = 0
    triggered = []

    for rule_fn in RULE_PIPELINE:
        try:
            delta, rule_name = rule_fn(transaction, ctx)
            if delta > 0 and rule_name:
                total_score += delta
                triggered.append(rule_name)
        except Exception as e:
            logger.error(f"Rule {rule_fn.__name__} failed: {e}")

    # Cap at 100
    total_score = min(total_score, 100)
    return RuleResult(score=total_score, triggered_rules=triggered)


def score_to_level(score: int) -> str:
    if score <= 30:
        return "LOW"
    elif score <= 60:
        return "MEDIUM"
    elif score <= 80:
        return "HIGH"
    return "CRITICAL"


def score_to_action(score: int) -> str:
    if score <= 30:
        return "APPROVE"
    elif score <= 60:
        return "REVIEW"
    return "BLOCK"
