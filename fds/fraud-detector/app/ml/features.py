"""
Feature Engineering
====================
Converts raw transaction + context into a numeric feature vector for XGBoost.

Features are designed to be:
  - Interpretable (you can explain each one in an interview)
  - Fast to compute (all from Redis cache, no slow DB joins)
  - Robust to missing values (sensible defaults everywhere)
"""
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional
import numpy as np


# High-risk country set (same as rules engine for consistency)
HIGH_RISK_COUNTRIES = {"Russia", "Nigeria", "North Korea", "Iran", "Belarus"}
HIGH_RISK_MERCHANTS = {"gambling", "crypto", "adult", "wire_transfer"}


@dataclass
class FeatureVector:
    """All 14 features fed into the XGBoost model."""

    # Amount features
    amount: float
    amount_log: float           # log(amount+1) — reduces skew from large outliers
    is_large_tx: int            # 1 if amount > $10,000

    # Velocity features
    tx_count_60s: int           # Transactions in last 60 seconds
    tx_count_10min: int         # Transactions in last 10 minutes

    # Geographic features
    is_high_risk_country: int   # 1 if country in HIGH_RISK_COUNTRIES
    is_new_country: int         # 1 if country not in user history
    impossible_travel: int      # 1 if different country within 20 min

    # Temporal features
    hour_of_day: int            # 0–23
    is_night: int               # 1 if 1 AM – 5 AM UTC

    # Merchant features
    is_high_risk_merchant: int  # 1 if merchant category is high-risk

    # Account features
    account_age_days: int       # 0 = brand new account
    is_new_account: int         # 1 if account < 7 days

    # Rule engine score (hybrid approach: rules as a feature)
    rule_score: int             # 0–100 score from the rule engine

    def to_array(self) -> np.ndarray:
        """Return features as a 1D numpy array in model-expected order."""
        return np.array([
            self.amount,
            self.amount_log,
            self.is_large_tx,
            self.tx_count_60s,
            self.tx_count_10min,
            self.is_high_risk_country,
            self.is_new_country,
            self.impossible_travel,
            self.hour_of_day,
            self.is_night,
            self.is_high_risk_merchant,
            self.account_age_days,
            self.is_new_account,
            self.rule_score,
        ], dtype=np.float32)

    @staticmethod
    def feature_names() -> list[str]:
        return [
            "amount", "amount_log", "is_large_tx",
            "tx_count_60s", "tx_count_10min",
            "is_high_risk_country", "is_new_country", "impossible_travel",
            "hour_of_day", "is_night",
            "is_high_risk_merchant",
            "account_age_days", "is_new_account",
            "rule_score",
        ]


def build_features(transaction: dict, ctx, rule_score: int) -> FeatureVector:
    """
    Build the feature vector from a transaction dict + TransactionContext.

    Parameters
    ----------
    transaction : dict   — raw transaction payload from Kafka
    ctx         : TransactionContext — enriched context from Redis
    rule_score  : int    — score from the deterministic rules engine
    """
    amount = float(transaction.get("amount", 0))
    country = transaction.get("country", "")
    category = (transaction.get("merchant_category") or "").lower()

    # Impossible travel check
    impossible = 0
    if ctx.last_transaction_ts and ctx.last_transaction_country:
        if ctx.last_transaction_country != country:
            now = datetime.now(timezone.utc)
            minutes_since = (now - ctx.last_transaction_ts).total_seconds() / 60
            if minutes_since < 20:
                impossible = 1

    hour = datetime.now(timezone.utc).hour

    return FeatureVector(
        amount=amount,
        amount_log=float(np.log1p(amount)),
        is_large_tx=1 if amount > 10_000 else 0,
        tx_count_60s=ctx.transactions_last_60s,
        tx_count_10min=ctx.transactions_last_10min,
        is_high_risk_country=1 if country in HIGH_RISK_COUNTRIES else 0,
        is_new_country=1 if (ctx.user_country_history and country not in ctx.user_country_history) else 0,
        impossible_travel=impossible,
        hour_of_day=hour,
        is_night=1 if 1 <= hour <= 5 else 0,
        is_high_risk_merchant=1 if any(r in category for r in HIGH_RISK_MERCHANTS) else 0,
        account_age_days=ctx.account_age_days,
        is_new_account=1 if ctx.account_age_days < 7 else 0,
        rule_score=rule_score,
    )
