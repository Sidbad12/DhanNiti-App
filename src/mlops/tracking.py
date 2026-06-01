"""
DhanNiti — MLOps Tracking
MLflow experiment tracking with DagsHub as the remote backend.

Architecture decision:
  DagsHub hosts a free, persistent MLflow server tied to your GitHub repo.
  GitHub Actions runners are ephemeral — without a remote URI every daily
  pipeline run would lose its metrics the moment the runner shuts down.
  DagsHub solves this at zero cost for public repos, with no extra infra.

Fallback chain:
  1. DagsHub remote  (if DAGSHUB_TOKEN + DAGSHUB_REPO_OWNER are set)
  2. Local file store (./experiments)  — for local dev without credentials
"""

from __future__ import annotations

import logging
import os
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Generator

import mlflow
import mlflow.xgboost
from mlflow.tracking import MlflowClient

from src.settings import (
    DAGSHUB_REPO_NAME,
    DAGSHUB_REPO_OWNER,
    DAGSHUB_TOKEN,
    MLFLOW_CONFIG,
)

logger = logging.getLogger(__name__)

# ── Module-level state ────────────────────────────────────────────────────────
_tracking_initialised = False


# ════════════════════════════════════════════════════════════
# SETUP
# ════════════════════════════════════════════════════════════

def setup_mlflow_tracking(
    experiment_name: str | None = None,
    force_local: bool = False,
) -> str:
    """
    Initialise MLflow tracking URI and set the active experiment.

    Priority:
      1. DagsHub remote — if DAGSHUB_TOKEN env var is present
      2. Local file store — ./experiments  (CI without credentials, local dev)

    Args:
        experiment_name: Override the experiment name from settings.
        force_local    : Skip DagsHub even if credentials are available.

    Returns:
        The resolved tracking URI string.
    """
    global _tracking_initialised

    exp_name = experiment_name or MLFLOW_CONFIG["experiment_name"]

    # ── 1. Try DagsHub remote ─────────────────────────────────
    token = DAGSHUB_TOKEN or os.getenv("DAGSHUB_TOKEN", "")

    if token and not force_local:
        tracking_uri = (
            f"https://dagshub.com/{DAGSHUB_REPO_OWNER}/{DAGSHUB_REPO_NAME}.mlflow"
        )
        # MLflow uses HTTP Basic Auth — username = dagshub owner, password = token
        os.environ["MLFLOW_TRACKING_USERNAME"] = DAGSHUB_REPO_OWNER
        os.environ["MLFLOW_TRACKING_PASSWORD"] = token

        try:
            mlflow.set_tracking_uri(tracking_uri)
            mlflow.set_experiment(exp_name)
            _tracking_initialised = True
            logger.info(
                f"MLflow → DagsHub remote: "
                f"{DAGSHUB_REPO_OWNER}/{DAGSHUB_REPO_NAME}  "
                f"experiment='{exp_name}'"
            )
            return tracking_uri
        except Exception as e:
            logger.warning(
                f"DagsHub connection failed ({e}). Falling back to local tracking."
            )

    # ── 2. Local file store ───────────────────────────────────
    local_path = Path("experiments")
    local_path.mkdir(exist_ok=True)
    tracking_uri = local_path.resolve().as_uri()   # file:///abs/path/experiments

    mlflow.set_tracking_uri(tracking_uri)
    mlflow.set_experiment(exp_name)
    _tracking_initialised = True
    logger.info(
        f"MLflow → local store: {tracking_uri}  experiment='{exp_name}'"
    )
    return tracking_uri


# ════════════════════════════════════════════════════════════
# CONTEXT MANAGER  (preferred for pipeline runs)
# ════════════════════════════════════════════════════════════

@contextmanager
def mlflow_run(
    run_name: str | None = None,
    tags: dict[str, str] | None = None,
    nested: bool = False,
) -> Generator[mlflow.ActiveRun, None, None]:
    """
    Context manager that wraps a single MLflow run.

    Usage:
        with mlflow_run(run_name="daily_retrain") as run:
            log_classifier_metrics(...)
            log_backtest_results(...)

    Args:
        run_name: Human-readable label for this run.
        tags    : Additional key-value tags merged with MLFLOW_CONFIG defaults.
        nested  : Allow nesting inside an existing active run.

    Yields:
        mlflow.ActiveRun object.
    """
    if not _tracking_initialised:
        setup_mlflow_tracking()

    merged_tags = {**MLFLOW_CONFIG.get("run_tags", {}), **(tags or {})}

    with mlflow.start_run(run_name=run_name, tags=merged_tags, nested=nested) as run:
        logger.info(f"MLflow run started  id={run.info.run_id}  name='{run_name}'")
        try:
            yield run
        except Exception:
            mlflow.set_tag("run_status", "FAILED")
            raise
        else:
            mlflow.set_tag("run_status", "SUCCESS")
        finally:
            logger.info(f"MLflow run ended    id={run.info.run_id}")


# ════════════════════════════════════════════════════════════
# LOGGING HELPERS
# ════════════════════════════════════════════════════════════

def log_classifier_metrics(
    ticker: str,
    eval_results: dict[str, Any],
    step: int | None = None,
) -> None:
    """
    Log XGBoost classifier evaluation metrics to the active MLflow run.

    Logs:
      - test_accuracy, test_f1_macro
      - walk-forward fold accuracies (as step metrics)
      - classification report per class (precision/recall/f1)

    Args:
        ticker      : NSE ticker symbol (used as metric prefix).
        eval_results: Dict from DhanNitiClassifier.eval_results.
        step        : Optional global step (e.g. pipeline day index).
    """
    prefix = ticker.replace(".", "_")

    # Scalar metrics
    flat_metrics = {
        f"{prefix}/test_accuracy" : eval_results.get("test_accuracy", 0.0),
        f"{prefix}/test_f1_macro" : eval_results.get("test_f1_macro", 0.0),
    }
    mlflow.log_metrics(flat_metrics, step=step)

    # Per-fold walk-forward accuracy (step = fold index)
    for label_col, res in eval_results.items():
        if not isinstance(res, dict) or "fold_results" not in res:
            continue
        for fold_i, (acc, f1) in enumerate(res["fold_results"]):
            mlflow.log_metrics(
                {
                    f"{prefix}/{label_col}/fold_accuracy": acc,
                    f"{prefix}/{label_col}/fold_f1"      : f1,
                },
                step=fold_i,
            )

    # Classification report (precision/recall per class)
    report = eval_results.get("classification_report", {})
    for class_label, class_metrics in report.items():
        if not isinstance(class_metrics, dict):
            continue
        for metric_name, value in class_metrics.items():
            safe_key = f"{prefix}/cls_{class_label}/{metric_name}".replace(" ", "_")
            try:
                mlflow.log_metric(safe_key, float(value), step=step)
            except (TypeError, ValueError):
                pass    # skip non-numeric fields like 'support'

    logger.debug(f"Logged classifier metrics for {ticker}")


def log_backtest_results(
    result_summary: dict[str, Any],
    prefix: str = "backtest",
    step: int | None = None,
) -> None:
    """
    Log BacktestResult.summary() dict to the active MLflow run.

    Args:
        result_summary: Output of BacktestResult.summary()
        prefix        : Metric key prefix.
        step          : Optional global step.
    """
    prefixed = {f"{prefix}/{k}": v for k, v in result_summary.items()
                if isinstance(v, (int, float))}
    mlflow.log_metrics(prefixed, step=step)
    logger.debug(f"Logged {len(prefixed)} backtest metrics (prefix='{prefix}')")


def log_feature_importance(
    ticker: str,
    importance: dict[str, float],
    top_n: int = 20,
) -> None:
    """
    Log top-N feature importances as MLflow metrics.

    Args:
        ticker    : NSE ticker symbol.
        importance: {feature_name: importance_score} dict.
        top_n     : Log only the top N most important features.
    """
    prefix    = ticker.replace(".", "_")
    top_feats = sorted(importance.items(), key=lambda x: x[1], reverse=True)[:top_n]

    for feat_name, score in top_feats:
        safe_key = f"{prefix}/importance/{feat_name}"[:250]  # MLflow key length limit
        mlflow.log_metric(safe_key, float(score))

    logger.debug(f"Logged top-{top_n} feature importances for {ticker}")


def log_portfolio_signals(
    signals: dict[str, dict],
    step: int | None = None,
) -> None:
    """
    Log portfolio-level signal summary to the active MLflow run.

    Args:
        signals: {ticker: {action, prob_bullish, prob_bearish, confidence}}
        step   : Optional global step.
    """
    buy_count  = sum(1 for s in signals.values() if s.get("action") == "BUY")
    sell_count = sum(1 for s in signals.values() if s.get("action") == "SELL")
    hold_count = sum(1 for s in signals.values() if s.get("action") == "HOLD")
    avg_conf   = sum(s.get("confidence", 0) for s in signals.values()) / max(len(signals), 1)

    mlflow.log_metrics(
        {
            "signals/buy_count"    : buy_count,
            "signals/sell_count"   : sell_count,
            "signals/hold_count"   : hold_count,
            "signals/avg_confidence": avg_conf,
        },
        step=step,
    )
    logger.debug(f"Logged signals summary: BUY={buy_count} SELL={sell_count} HOLD={hold_count}")


def log_params_from_settings() -> None:
    """
    Log key DhanNiti config parameters from settings to the active run.
    Useful for full reproducibility — associates every run with its config snapshot.
    """
    from src.settings import (
        BACKTEST_CONFIG,
        MINIMUM_ALLOCATION,
        MAXIMUM_ALLOCATION,
        PORTFOLIO_TICKERS,
        RL_CONFIG,
        SIGNAL_CONFIDENCE_THRESHOLD,
        XGBOOST_PARAMS,
    )

    params: dict[str, Any] = {
        # Universe
        "n_tickers"               : len(PORTFOLIO_TICKERS),
        "min_allocation"          : MINIMUM_ALLOCATION,
        "max_allocation"          : MAXIMUM_ALLOCATION,
        # XGBoost
        "xgb_n_estimators"        : XGBOOST_PARAMS.get("n_estimators"),
        "xgb_max_depth"           : XGBOOST_PARAMS.get("max_depth"),
        "xgb_learning_rate"       : XGBOOST_PARAMS.get("learning_rate"),
        "xgb_subsample"           : XGBOOST_PARAMS.get("subsample"),
        # Signal
        "confidence_threshold"    : SIGNAL_CONFIDENCE_THRESHOLD,
        # RL
        "rl_total_timesteps"      : RL_CONFIG.get("total_timesteps"),
        "rl_lookback_window"      : RL_CONFIG.get("lookback_window"),
        "rl_reward_metric"        : RL_CONFIG.get("reward_metric"),
        # Backtest
        "backtest_stt_rate"       : BACKTEST_CONFIG.get("stt_rate"),
        "backtest_brokerage_rate" : BACKTEST_CONFIG.get("brokerage_rate"),
        "backtest_initial_capital": BACKTEST_CONFIG.get("initial_capital"),
    }

    # MLflow param values must be strings or numbers ≤ 250 chars
    mlflow.log_params({k: str(v) for k, v in params.items() if v is not None})
    logger.debug("Logged settings snapshot as MLflow params")


# ════════════════════════════════════════════════════════════
# LEGACY SHIM  (backward compat with old tracking.py calls)
# ════════════════════════════════════════════════════════════

def setup_mlflow_tracking_legacy() -> None:
    """Alias kept for backward compat. Prefer setup_mlflow_tracking()."""
    setup_mlflow_tracking()


def log_run_metrics(
    metrics: dict[str, float],
    params: dict[str, Any],
    tags: dict[str, str] | None = None,
) -> None:
    """Legacy flat-API shim. Prefer mlflow_run() context manager."""
    if not mlflow.active_run():
        mlflow.start_run(tags={**MLFLOW_CONFIG.get("run_tags", {}), **(tags or {})})

    mlflow.log_params({k: str(v) for k, v in params.items()})
    mlflow.log_metrics({k: float(v) for k, v in metrics.items()})
    if tags:
        mlflow.set_tags(tags)
    logger.info("Logged metrics/params via legacy log_run_metrics()")


def end_mlflow_run() -> None:
    """Legacy shim — safely ends any active MLflow run."""
    if mlflow.active_run():
        mlflow.end_run()
        logger.info("MLflow active run ended")
