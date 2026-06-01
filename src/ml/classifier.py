"""
DhanNiti — XGBoost Classifier
Walk-forward training, confidence thresholding, SHAP explainability, and Model Registry.
"""

from __future__ import annotations

import logging
import pickle
import glob
import os
from datetime import datetime
from pathlib import Path
from typing import Optional, Any

import numpy as np
import pandas as pd
import shap
from sklearn.metrics import accuracy_score, classification_report, f1_score
from sklearn.model_selection import GridSearchCV, TimeSeriesSplit
from xgboost import XGBClassifier

from src.features.technical import get_feature_columns
from src.settings import (
    LABEL_LOOKAHEADS,
    LABEL_THRESHOLDS,
    SIGNAL_CONFIDENCE_THRESHOLD,
    TIMESERIES_N_SPLITS,
    XGBOOST_PARAMS,
    XGBOOST_TUNING_GRID,
)

logger = logging.getLogger(__name__)

# class labels
LABEL_NEUTRAL  = 0
LABEL_BEARISH  = 1
LABEL_BULLISH  = 2
SIGNAL_MAP     = {LABEL_NEUTRAL: "HOLD", LABEL_BEARISH: "SELL", LABEL_BULLISH: "BUY"}


# ════════════════════════════════════════════════════════════
# WALK-FORWARD EVALUATOR
# ════════════════════════════════════════════════════════════

def walk_forward_evaluate(
    df: pd.DataFrame,
    label_col: str,
    n_splits: int = TIMESERIES_N_SPLITS,
    params: dict | None = None,
) -> dict:
    """
    Walk-forward cross-validation for one label scheme.
    """
    params    = params or XGBOOST_PARAMS.copy()
    params["enable_categorical"] = True  # Required for regime_label
    
    feat_cols = get_feature_columns(df)
    if "regime_label" in df.columns and "regime_label" not in feat_cols:
        feat_cols.append("regime_label")
        df["regime_label"] = df["regime_label"].astype("category")

    df_clean  = df[feat_cols + [label_col]].dropna()

    X = df_clean[feat_cols]
    y = df_clean[label_col].values.astype(int)

    tscv       = TimeSeriesSplit(n_splits=n_splits)
    fold_accs  = []
    fold_f1s   = []

    for fold, (train_idx, test_idx) in enumerate(tscv.split(X)):
        X_train, X_test = X.iloc[train_idx], X.iloc[test_idx]
        y_train, y_test = y[train_idx], y[test_idx]

        model = XGBClassifier(**params)
        model.fit(X_train, y_train, eval_set=[(X_test, y_test)], verbose=False)

        preds = model.predict(X_test)
        acc   = accuracy_score(y_test, preds)
        f1    = f1_score(y_test, preds, average="macro", zero_division=0)

        fold_accs.append(acc)
        fold_f1s.append(f1)

    return {
        "label_col"   : label_col,
        "accuracy"    : float(np.mean(fold_accs)),
        "f1_macro"    : float(np.mean(fold_f1s)),
        "fold_results": list(zip(fold_accs, fold_f1s)),
    }


# ════════════════════════════════════════════════════════════
# LABEL SELECTION
# ════════════════════════════════════════════════════════════

def select_best_label(
    df: pd.DataFrame,
    lookaheads: list = LABEL_LOOKAHEADS,
    thresholds: list = LABEL_THRESHOLDS,
) -> tuple[str, dict]:
    """
    Evaluate all label combinations, return the best by macro-F1.
    """
    label_cols = [
        f"label_la{la}_th{th:.3f}"
        for la in lookaheads
        for th in thresholds
        if f"label_la{la}_th{th:.3f}" in df.columns
    ]

    if not label_cols:
        raise ValueError("No label columns found in df. Run build_features with add_labels=True.")

    results = {}
    logger.info(f"Evaluating {len(label_cols)} label schemes...")

    for lc in label_cols:
        res = walk_forward_evaluate(df, lc)
        results[lc] = res

    best_col = max(results, key=lambda k: results[k]["f1_macro"])
    logger.info(f"Best label: {best_col} (f1={results[best_col]['f1_macro']:.3f})")

    return best_col, results


# ════════════════════════════════════════════════════════════
# TRAINER
# ════════════════════════════════════════════════════════════

class DhanNitiClassifier:
    """
    XGBoost classifier with walk-forward training, hyperparameter tuning,
    confidence thresholding, and SHAP explainability.
    """

    def __init__(
        self,
        params: dict | None = None,
        confidence_threshold: float = SIGNAL_CONFIDENCE_THRESHOLD,
    ) -> None:
        self.params               = params or XGBOOST_PARAMS.copy()
        self.params["enable_categorical"] = True
        self.confidence_threshold = confidence_threshold
        self.model: Optional[XGBClassifier] = None
        self.best_label: Optional[str]      = None
        self.feature_cols: list[str]        = []
        self.eval_results: dict             = {}
        self.shap_summary: dict[str, float] = {}

    # ── Training ─────────────────────────────────────────────

    def fit(
        self,
        df: pd.DataFrame,
        tune: bool = False,
        train_ratio: float = 0.60,
        val_ratio: float   = 0.20,
    ) -> DhanNitiClassifier:
        """
        Full training pipeline with SHAP integration.
        """
        # 1. Feature Prep
        feat_cols = get_feature_columns(df)
        if "regime_label" in df.columns and "regime_label" not in feat_cols:
            feat_cols.append("regime_label")
            df["regime_label"] = df["regime_label"].astype("category")

        self.feature_cols = feat_cols

        # 2. Select best label
        self.best_label, self.eval_results = select_best_label(df)

        # 3. Splits
        df_clean = df[feat_cols + [self.best_label]].dropna()
        n        = len(df_clean)
        n_train  = int(n * train_ratio)
        n_val    = int(n * val_ratio)

        train_df = df_clean.iloc[:n_train]
        val_df   = df_clean.iloc[n_train : n_train + n_val]
        test_df  = df_clean.iloc[n_train + n_val :]

        X_train = train_df[feat_cols]
        y_train = train_df[self.best_label].values.astype(int)
        X_val   = val_df[feat_cols]
        y_val   = val_df[self.best_label].values.astype(int)
        X_test  = test_df[feat_cols]
        y_test  = test_df[self.best_label].values.astype(int)

        # 4. Tune (Optional)
        if tune:
            logger.info("Running GridSearchCV (this may take a while)...")
            self.params = self._tune(X_train, y_train)

        # 5. Train final model
        self.model = XGBClassifier(**self.params)
        self.model.fit(
            X_train, y_train,
            eval_set=[(X_val, y_val)],
            verbose=False,
        )

        # 6. Evaluate
        preds  = self.model.predict(X_test)
        acc    = accuracy_score(y_test, preds)
        f1     = f1_score(y_test, preds, average="macro", zero_division=0)
        report = classification_report(y_test, preds, output_dict=True, zero_division=0)

        self.eval_results["test_accuracy"] = acc
        self.eval_results["test_f1_macro"] = f1
        self.eval_results["classification_report"] = report

        # 7. SHAP Explainer
        try:
            logger.info("Generating SHAP explainability values...")
            explainer = shap.TreeExplainer(self.model)
            shap_values = explainer.shap_values(X_test)
            
            # Extract raw values if it is an Explanation object
            if hasattr(shap_values, "values"):
                shap_arr = shap_values.values
            else:
                shap_arr = shap_values

            if isinstance(shap_arr, list):
                # Older SHAP: list of length num_classes, each element of shape (num_samples, num_features)
                # Stack to shape (num_classes, num_samples, num_features)
                mean_shap = np.abs(np.array(shap_arr)).mean(axis=(0, 1))
            elif isinstance(shap_arr, np.ndarray):
                if shap_arr.ndim == 3:
                    # Shape is (num_samples, num_features, num_classes) or (num_classes, num_samples, num_features)
                    n_feats = len(self.feature_cols)
                    if shap_arr.shape[1] == n_feats:
                        # (num_samples, num_features, num_classes) -> average over axis 0 and 2
                        mean_shap = np.abs(shap_arr).mean(axis=(0, 2))
                    elif shap_arr.shape[2] == n_feats:
                        # (num_classes, num_samples, num_features) -> average over axis 0 and 1
                        mean_shap = np.abs(shap_arr).mean(axis=(0, 1))
                    else:
                        # Default fallback
                        mean_shap = np.abs(shap_arr).mean(axis=(0, 2))
                else:
                    # Shape is (num_samples, num_features)
                    mean_shap = np.abs(shap_arr).mean(axis=0)
            else:
                # General fallback
                shap_arr = np.array(shap_arr)
                if shap_arr.ndim == 3:
                    mean_shap = np.abs(shap_arr).mean(axis=(0, 2))
                else:
                    mean_shap = np.abs(shap_arr).mean(axis=0)
                
            shap_dict = {f: float(v) for f, v in zip(self.feature_cols, mean_shap)}
            
            # Store top 5 features
            self.shap_summary = dict(sorted(shap_dict.items(), key=lambda x: x[1], reverse=True)[:5])
        except Exception as e:
            logger.warning(f"Failed to generate SHAP values: {e}")
            self.shap_summary = {}

        return self

    def _tune(self, X: pd.DataFrame, y: np.ndarray) -> dict:
        base = XGBClassifier(
            objective="multi:softprob",
            num_class=3,
            n_jobs=-1,
            eval_metric="mlogloss",
            seed=42,
            enable_categorical=True
        )
        grid = GridSearchCV(
            estimator=base,
            param_grid=XGBOOST_TUNING_GRID,
            cv=TimeSeriesSplit(n_splits=TIMESERIES_N_SPLITS),
            scoring="f1_macro",
            n_jobs=-1,
        )
        grid.fit(X, y)
        return {**self.params, **grid.best_params_}

    # ── Prediction ───────────────────────────────────────────

    def predict_proba(self, df: pd.DataFrame) -> np.ndarray:
        if self.model is None:
            raise RuntimeError("Model not fitted. Call fit() first.")
            
        if "regime_label" in df.columns:
            df["regime_label"] = df["regime_label"].astype("category")
            
        X = df[self.feature_cols].dropna()
        return self.model.predict_proba(X)

    def predict_signal(self, df: pd.DataFrame) -> pd.DataFrame:
        if self.model is None:
            raise RuntimeError("Model not fitted.")

        if "regime_label" in df.columns:
            df["regime_label"] = df["regime_label"].astype("category")

        clean = df[self.feature_cols].dropna()
        proba = self.model.predict_proba(clean)

        preds = self._threshold_predict(proba)

        result = pd.DataFrame(
            {
                "prob_neutral" : proba[:, LABEL_NEUTRAL],
                "prob_bearish" : proba[:, LABEL_BEARISH],
                "prob_bullish" : proba[:, LABEL_BULLISH],
                "signal"       : preds,
                "confidence"   : proba[np.arange(len(proba)), preds],
                "action"       : [SIGNAL_MAP[s] for s in preds],
            },
            index=clean.index,
        )
        return result

    def _threshold_predict(self, proba: np.ndarray) -> np.ndarray:
        preds = np.full(len(proba), LABEL_NEUTRAL, dtype=int)
        
        bull_mask = (proba[:, LABEL_BULLISH] >= self.confidence_threshold) & (proba[:, LABEL_BULLISH] > proba[:, LABEL_BEARISH])
        preds[bull_mask] = LABEL_BULLISH

        bear_mask = (proba[:, LABEL_BEARISH] >= self.confidence_threshold) & (proba[:, LABEL_BEARISH] > proba[:, LABEL_BULLISH])
        preds[bear_mask] = LABEL_BEARISH

        return preds

    def latest_signal(self, df: pd.DataFrame) -> dict:
        signals = self.predict_signal(df)
        if signals.empty:
            return {"action": "HOLD", "prob_bullish": 0.33, "prob_bearish": 0.33, "prob_neutral": 0.34, "confidence": 0.33}
        last = signals.iloc[-1]
        return {
            "action"       : last["action"],
            "prob_bullish" : float(last["prob_bullish"]),
            "prob_bearish" : float(last["prob_bearish"]),
            "prob_neutral" : float(last["prob_neutral"]),
            "confidence"   : float(last["confidence"]),
        }

    # ── Persistence & Registry ───────────────────────────────

    def save(self, path: str | Path) -> None:
        """Legacy save method."""
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "wb") as f:
            pickle.dump(self, f)

    @classmethod
    def load(cls, path: str | Path) -> "DhanNitiClassifier":
        """Legacy load method."""
        with open(path, "rb") as f:
            return pickle.load(f)

    def save_versioned(self, ticker: str, base_dir: str = "models") -> None:
        """Save model to versioned registry and clean up old versions."""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        model_dir = Path(base_dir) / ticker
        model_dir.mkdir(parents=True, exist_ok=True)
        
        path = model_dir / f"xgb_v{timestamp}.pkl"
        self.save(path)
        
        # Keep only the last 3 versions
        models = sorted(list(model_dir.glob("xgb_v*.pkl")))
        while len(models) > 3:
            oldest = models.pop(0)
            oldest.unlink()
            logger.info(f"Registry cleanup: removed old model {oldest.name}")

    @classmethod
    def load_best_version(cls, ticker: str, base_dir: str = "models") -> Optional["DhanNitiClassifier"]:
        """Load the model with the highest F1 score from the registry."""
        model_dir = Path(base_dir) / ticker
        models = list(model_dir.glob("xgb_v*.pkl"))
        if not models:
            return None
            
        best_model = None
        best_f1 = -1.0
        
        for path in models:
            try:
                obj = cls.load(path)
                f1 = obj.eval_results.get("test_f1_macro", 0.0)
                if f1 > best_f1:
                    best_f1 = f1
                    best_model = obj
            except Exception:
                continue
                
        if best_model:
            logger.info(f"Loaded best registry model for {ticker} (F1: {best_f1:.3f})")
        return best_model

    # ── Properties ───────────────────────────────────────────

    def get_shap_summary(self) -> dict[str, float]:
        """Returns the top SHAP features for UI explainability."""
        return self.shap_summary

    @property
    def is_fitted(self) -> bool:
        return self.model is not None


# ════════════════════════════════════════════════════════════
# PORTFOLIO-LEVEL SIGNAL GENERATION
# ════════════════════════════════════════════════════════════

def generate_portfolio_signals(
    feature_dfs: dict[str, pd.DataFrame],
    models: dict[str, DhanNitiClassifier],
) -> dict[str, dict]:
    signals = {}
    for ticker, df in feature_dfs.items():
        if ticker not in models:
            signals[ticker] = {"action": "HOLD", "confidence": 0.33}
            continue
        try:
            signals[ticker] = models[ticker].latest_signal(df)
        except Exception:
            signals[ticker] = {"action": "HOLD", "confidence": 0.33}
    return signals

def get_portfolio_shap_summaries(models: dict[str, DhanNitiClassifier]) -> dict[str, dict[str, float]]:
    """Get SHAP explainability for all tickers."""
    return {ticker: model.get_shap_summary() for ticker, model in models.items() if model.is_fitted}