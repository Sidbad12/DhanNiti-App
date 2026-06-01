"""SHAP explainability wrapper for model interpretation."""

import logging
import pandas as pd
import numpy as np
import shap
from xgboost import XGBClassifier

logger = logging.getLogger(__name__)


class XGBoostModelExplainer:
    """Wrapper class for generating SHAP interpretations of XGBoost portfolio models."""

    def __init__(self) -> None:
        """Initialise explainer."""
        pass

    def get_feature_contributions(self, model: XGBClassifier, X_data: pd.DataFrame) -> pd.DataFrame:
        """
        Calculate global feature importances based on average absolute SHAP values.

        Args:
            model: Trained XGBClassifier model
            X_data: Feature DataFrame used for calculating SHAP values

        Returns:
            DataFrame with columns ['Feature', 'SHAP_Importance'] sorted descending
        """
        try:
            # Initialize tree explainer
            explainer = shap.TreeExplainer(model)
            shap_values = explainer.shap_values(X_data)

            # Support both binary classification output shapes
            if isinstance(shap_values, list):
                # For older SHAP versions
                shap_values = shap_values[1] if len(shap_values) > 1 else shap_values[0]
            elif len(shap_values.shape) == 3:
                # For newer SHAP versions (samples, features, classes)
                shap_values = shap_values[:, :, 1]

            # Calculate absolute mean shap values
            mean_abs_shap = np.mean(np.abs(shap_values), axis=0)

            # Build importance DataFrame
            df_importance = pd.DataFrame({
                "Feature": X_data.columns,
                "SHAP_Importance": mean_abs_shap
            })

            # Normalise so they sum to 1.0 (easier to read as percentages)
            total_imp = df_importance["SHAP_Importance"].sum()
            if total_imp > 0:
                df_importance["SHAP_Importance_Pct"] = df_importance["SHAP_Importance"] / total_imp
            else:
                df_importance["SHAP_Importance_Pct"] = 0.0

            return df_importance.sort_values(by="SHAP_Importance", ascending=False)

        except Exception as e:
            logger.error(f"Error calculating global SHAP values: {e}")
            # Fallback to model's default feature importances
            df_importance = pd.DataFrame({
                "Feature": X_data.columns,
                "SHAP_Importance": model.feature_importances_
            })
            total_imp = df_importance["SHAP_Importance"].sum()
            df_importance["SHAP_Importance_Pct"] = df_importance["SHAP_Importance"] / (total_imp if total_imp > 0 else 1.0)
            return df_importance.sort_values(by="SHAP_Importance", ascending=False)

    def explain_latest_prediction(self, model: XGBClassifier, latest_row: pd.DataFrame) -> dict[str, float]:
        """
        Generate local explanation (SHAP values) for the latest single prediction.

        Args:
            model: Trained XGBClassifier model
            latest_row: Single-row DataFrame containing the current day's features

        Returns:
            Dictionary mapping feature name to its contribution score (positive means pushed prediction UP, negative pushed DOWN)
        """
        try:
            explainer = shap.TreeExplainer(model)
            shap_values = explainer.shap_values(latest_row)

            # Align SHAP output shapes
            if isinstance(shap_values, list):
                shap_values = shap_values[1] if len(shap_values) > 1 else shap_values[0]
            elif len(shap_values.shape) == 3:
                shap_values = shap_values[:, :, 1]
            elif len(shap_values.shape) == 2 and shap_values.shape[0] == 1:
                # For single sample shape (1, features)
                pass

            # Extract the first (and only) sample's SHAP values
            contributions = shap_values[0]

            # Map features to contributions
            explanation = {
                feature: float(contrib)
                for feature, contrib in zip(latest_row.columns, contributions)
            }

            # Sort by absolute magnitude of contribution
            sorted_explanation = dict(
                sorted(explanation.items(), key=lambda item: abs(item[1]), reverse=True)
            )

            return sorted_explanation

        except Exception as e:
            logger.error(f"Error explaining latest prediction: {e}")
            return {}
