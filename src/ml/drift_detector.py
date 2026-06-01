"""Concept and data drift detection module for triggering model retraining."""

import logging
import pandas as pd
from scipy.stats import ks_2samp

logger = logging.getLogger(__name__)


class PortfolioDataDriftDetector:
    """Drift detector using the Kolmogorov-Smirnov test to compare feature distributions."""

    def __init__(self, p_value_threshold: float = 0.05, drift_ratio_trigger: float = 0.30) -> None:
        """
        Initialise drift detector.

        Args:
            p_value_threshold: Significance level for KS test (default: 0.05)
            drift_ratio_trigger: Ratio of drifted features to trigger retraining (default: 30%)
        """
        self.p_value_threshold = p_value_threshold
        self.drift_ratio_trigger = drift_ratio_trigger

    def detect_drift(self, baseline_df: pd.DataFrame, current_df: pd.DataFrame, feature_cols: list[str]) -> tuple[bool, dict[str, float]]:
        """
        Detect drift between a baseline dataset (training) and a current dataset (production).

        Uses the Kolmogorov-Smirnov test on numerical features.

        Args:
            baseline_df: Baseline historical feature DataFrame
            current_df: Current production feature DataFrame (recent window)
            feature_cols: List of feature column names to monitor

        Returns:
            Tuple containing:
            - trigger_retraining: bool, True if drift ratio exceeds trigger threshold
            - p_values: dict[str, float] mapping feature name to KS test p-value
        """
        drifted_count = 0
        p_values = {}

        if baseline_df.empty or current_df.empty:
            logger.warning("Empty DataFrame provided to drift detector. Assuming no drift.")
            return False, {}

        # Filter features that are numeric
        numeric_features = [col for col in feature_cols if col in baseline_df.columns and col in current_df.columns]
        
        if not numeric_features:
            logger.warning("No valid features found for drift detection.")
            return False, {}

        for col in numeric_features:
            baseline_sample = baseline_df[col].dropna()
            current_sample = current_df[col].dropna()

            if len(baseline_sample) < 30 or len(current_sample) < 10:
                # Not enough samples for a reliable KS test
                p_values[col] = 1.0
                continue

            # Run Kolmogorov-Smirnov two-sample test
            # H0: The two samples are drawn from the same distribution
            statistic, p_val = ks_2samp(baseline_sample, current_sample)
            p_values[col] = float(p_val)

            # If p-value is below threshold, reject H0 (meaning drift is detected)
            if p_val < self.p_value_threshold:
                drifted_count += 1
                logger.warning(f"Drift detected in feature '{col}': KS p-value = {p_val:.5f}")

        drift_ratio = drifted_count / len(numeric_features)
        trigger_retraining = drift_ratio >= self.drift_ratio_trigger

        logger.info(
            f"Drift Detection Summary: {drifted_count}/{len(numeric_features)} "
            f"features drifted ({drift_ratio:.1%}). "
            f"Retraining triggered: {trigger_retraining}"
        )

        return trigger_retraining, p_values
