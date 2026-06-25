"""
ML Scorer
=========
Loads the trained XGBoost model at startup and provides sub-millisecond
fraud probability predictions.

Hybrid scoring strategy:
  - If ML model is available  → use ML probability (0–100 score)
  - If ML model is missing    → graceful fallback to rules engine score
  - Blend mode                → 0.6 * ML + 0.4 * rules (configurable)

This means the system is never "down" even before the model is trained.
"""
import logging
from pathlib import Path
import numpy as np

logger = logging.getLogger(__name__)

MODEL_PATH = Path(__file__).parent.parent.parent / "models" / "fraud_model.json"

# Score blend weights
ML_WEIGHT = 0.65
RULES_WEIGHT = 0.35


class FraudMLScorer:
    """Thread-safe XGBoost inference wrapper."""

    def __init__(self):
        self._model = None
        self._available = False

    def load(self) -> bool:
        """
        Attempt to load the model. Returns True if successful.
        Called at service startup — safe to call even if model doesn't exist yet.
        """
        if not MODEL_PATH.exists():
            logger.warning(
                f"ML model not found at {MODEL_PATH}. "
                "Running in rules-only mode. "
                "Train the model with: python -m app.ml.trainer"
            )
            return False

        try:
            import xgboost as xgb
            self._model = xgb.XGBClassifier()
            self._model.load_model(str(MODEL_PATH))
            self._available = True
            logger.info(f"✅ XGBoost model loaded from {MODEL_PATH}")
            return True
        except Exception as e:
            logger.error(f"Failed to load ML model: {e}")
            return False

    @property
    def is_available(self) -> bool:
        return self._available

    def predict_proba(self, feature_array: np.ndarray) -> float:
        """
        Return fraud probability in [0.0, 1.0].
        Input must be a 1D array of 14 features (see features.py).
        """
        if not self._available or self._model is None:
            raise RuntimeError("Model not available")

        X = feature_array.reshape(1, -1)
        proba = self._model.predict_proba(X)[0][1]   # P(fraud)
        return float(proba)

    def score(self, feature_array: np.ndarray, rule_score: int) -> dict:
        """
        Return a blended fraud score (0–100) + metadata.

        Strategy:
          - If ML available: blend ML prob + rules score
          - If ML unavailable: use rules score directly (graceful degradation)
        """
        if self._available:
            try:
                ml_prob = self.predict_proba(feature_array)
                ml_score = int(ml_prob * 100)
                blended = int(ML_WEIGHT * ml_score + RULES_WEIGHT * rule_score)
                blended = max(0, min(100, blended))

                return {
                    "final_score": blended,
                    "ml_score": ml_score,
                    "ml_probability": round(ml_prob, 4),
                    "rule_score": rule_score,
                    "scoring_mode": "hybrid",
                }
            except Exception as e:
                logger.error(f"ML inference failed, falling back to rules: {e}")

        # Graceful fallback
        return {
            "final_score": rule_score,
            "ml_score": None,
            "ml_probability": None,
            "rule_score": rule_score,
            "scoring_mode": "rules_only",
        }


# Module-level singleton — load once at import time
_scorer = FraudMLScorer()


def get_scorer() -> FraudMLScorer:
    return _scorer
