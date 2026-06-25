"""
Model Trainer
=============
Trains an XGBoost classifier on **synthetic** labelled fraud data.

In production you'd replace synthetic_dataset() with real labelled transactions
from your PostgreSQL database. The training pipeline stays identical.

Run once to create the model artifact:
    python -m app.ml.trainer

Output: models/fraud_model.json  (XGBoost native format, ~50 KB)
"""
import json
import logging
import numpy as np
from pathlib import Path

import xgboost as xgb
from sklearn.model_selection import train_test_split
from sklearn.metrics import classification_report, roc_auc_score

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

MODEL_DIR = Path(__file__).parent.parent.parent / "models"
MODEL_PATH = MODEL_DIR / "fraud_model.json"
FEATURE_META_PATH = MODEL_DIR / "feature_meta.json"


def synthetic_dataset(n_samples: int = 50_000) -> tuple[np.ndarray, np.ndarray]:
    """
    Generate a realistic synthetic fraud dataset.

    Fraud rate ≈ 3% (realistic for production payment systems).
    Fraudulent transactions are seeded with higher-risk feature values.
    """
    rng = np.random.default_rng(seed=42)
    n_fraud = int(n_samples * 0.03)
    n_legit = n_samples - n_fraud

    def make_samples(n: int, fraud: bool) -> np.ndarray:
        if fraud:
            return np.column_stack([
                rng.exponential(scale=8000, size=n),          # amount — skewed high
                rng.uniform(5, 10, n),                         # amount_log
                rng.binomial(1, 0.6, n),                       # is_large_tx
                rng.integers(3, 15, n),                        # tx_count_60s — high velocity
                rng.integers(8, 30, n),                        # tx_count_10min
                rng.binomial(1, 0.7, n),                       # is_high_risk_country
                rng.binomial(1, 0.8, n),                       # is_new_country
                rng.binomial(1, 0.5, n),                       # impossible_travel
                rng.integers(1, 5, n),                         # hour_of_day — night
                rng.binomial(1, 0.6, n),                       # is_night
                rng.binomial(1, 0.5, n),                       # is_high_risk_merchant
                rng.integers(0, 30, n),                        # account_age_days — new
                rng.binomial(1, 0.4, n),                       # is_new_account
                rng.integers(55, 100, n),                      # rule_score — high
            ])
        else:
            return np.column_stack([
                rng.exponential(scale=200, size=n),            # amount — typical
                rng.uniform(1, 6, n),                          # amount_log
                rng.binomial(1, 0.05, n),                      # is_large_tx
                rng.integers(0, 2, n),                         # tx_count_60s — normal
                rng.integers(0, 5, n),                         # tx_count_10min
                rng.binomial(1, 0.05, n),                      # is_high_risk_country
                rng.binomial(1, 0.1, n),                       # is_new_country
                rng.binomial(1, 0.01, n),                      # impossible_travel
                rng.integers(6, 23, n),                        # hour_of_day — daytime
                rng.binomial(1, 0.05, n),                      # is_night
                rng.binomial(1, 0.05, n),                      # is_high_risk_merchant
                rng.integers(30, 3650, n),                     # account_age_days — established
                rng.binomial(1, 0.02, n),                      # is_new_account
                rng.integers(0, 35, n),                        # rule_score — low
            ])

    X = np.vstack([make_samples(n_fraud, fraud=True), make_samples(n_legit, fraud=False)])
    y = np.hstack([np.ones(n_fraud), np.zeros(n_legit)])

    # Shuffle
    idx = rng.permutation(len(y))
    return X[idx].astype(np.float32), y[idx].astype(np.float32)


def train():
    logger.info("Generating synthetic training data (50,000 transactions)...")
    X, y = synthetic_dataset()

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=42, stratify=y
    )

    logger.info(f"Train: {len(X_train):,} samples | Test: {len(X_test):,} samples")
    logger.info(f"Fraud rate: {y.mean()*100:.1f}%")

    # ── XGBoost model ────────────────────────────────────────────────────────
    # scale_pos_weight handles class imbalance automatically
    fraud_ratio = (y == 0).sum() / (y == 1).sum()

    model = xgb.XGBClassifier(
        n_estimators=200,
        max_depth=6,
        learning_rate=0.1,
        subsample=0.8,
        colsample_bytree=0.8,
        scale_pos_weight=fraud_ratio,   # Compensate for class imbalance
        use_label_encoder=False,
        eval_metric="auc",
        random_state=42,
        n_jobs=-1,
    )

    logger.info("Training XGBoost model...")
    model.fit(
        X_train, y_train,
        eval_set=[(X_test, y_test)],
        verbose=50,
    )

    # ── Evaluation ───────────────────────────────────────────────────────────
    y_pred = model.predict(X_test)
    y_prob = model.predict_proba(X_test)[:, 1]

    auc = roc_auc_score(y_test, y_prob)
    logger.info(f"\nTest AUC: {auc:.4f}")
    logger.info("\n" + classification_report(y_test, y_pred, target_names=["Legit", "Fraud"]))

    # ── Feature importance ───────────────────────────────────────────────────
    from app.ml.features import FeatureVector
    importances = dict(zip(FeatureVector.feature_names(), model.feature_importances_))
    top_features = sorted(importances.items(), key=lambda x: x[1], reverse=True)
    logger.info("\nTop features by importance:")
    for feat, score in top_features[:8]:
        bar = "█" * int(score * 200)
        logger.info(f"  {feat:<25} {score:.4f}  {bar}")

    # ── Save model + metadata ─────────────────────────────────────────────────
    MODEL_DIR.mkdir(exist_ok=True)
    model.save_model(str(MODEL_PATH))

    meta = {
        "feature_names": FeatureVector.feature_names(),
        "auc": round(auc, 4),
        "n_estimators": 200,
        "fraud_rate_train": round(float(y.mean()), 4),
        "model_path": str(MODEL_PATH),
    }
    with open(FEATURE_META_PATH, "w") as f:
        json.dump(meta, f, indent=2)

    logger.info(f"\n✅ Model saved to {MODEL_PATH}")
    logger.info(f"✅ Metadata saved to {FEATURE_META_PATH}")
    return model, auc


if __name__ == "__main__":
    train()
