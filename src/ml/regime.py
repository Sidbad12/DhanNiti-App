"""
DhanNiti — Regime Detector
Uses Gaussian Hidden Markov Models (HMM) to classify market states into
discrete regimes (bull, bear, high_volatility, range_bound) based on Nifty 50 data.
"""

import logging
import os
import joblib
import numpy as np
import pandas as pd
from datetime import datetime
from typing import Any

logger = logging.getLogger(__name__)

try:
    from hmmlearn.hmm import GaussianHMM
    _HMM_AVAILABLE = True
except ImportError:
    _HMM_AVAILABLE = False
    logger.warning("hmmlearn not installed. Regime detection will use fallback.")

from src.settings import REGIME_CONFIG

class RegimeDetector:
    """
    Detects market regimes using a Gaussian HMM trained on Nifty 50 proxy features.
    States are heuristically mapped to:
    - bull_trending
    - bear_trending
    - high_volatility
    - range_bound
    """

    def __init__(self, model_path: str = "models/hmm_regime.pkl"):
        self.model_path = model_path
        self.model = None
        self.n_components = REGIME_CONFIG.get("n_components", 4)
        
        # State mapping populated after training/loading based on state characteristics
        self.state_labels = {}
        
        if os.path.exists(self.model_path):
            self.load_model()

    def _prepare_features(self, df: pd.DataFrame) -> tuple[np.ndarray, pd.Index]:
        """
        Extract features for HMM: rolling returns, rolling volatility, rolling volume change.
        Expects a DataFrame with 'Close' and 'Volume' columns.
        """
        data = df.copy()
        
        # 1. 5-day rolling return
        data['ret_5d'] = data['Close'].pct_change(5)
        
        # 2. 20-day rolling volatility (annualized)
        data['vol_20d'] = data['Close'].pct_change().rolling(20).std() * np.sqrt(252)
        
        # 3. 5-day volume change relative to 20-day average
        # Handle cases where Volume might be missing or zero
        if 'Volume' in data.columns and not (data['Volume'] == 0).all():
            data['vol_ma20'] = data['Volume'].rolling(20).mean()
            # Replace 0 with tiny float to avoid div zero
            data['vol_ma20'] = data['vol_ma20'].replace(0, 1e-6)
            data['volume_surge'] = data['Volume'] / data['vol_ma20']
        else:
            data['volume_surge'] = 1.0
            
        # Drop NaNs
        data = data.dropna(subset=['ret_5d', 'vol_20d', 'volume_surge'])
        
        features = data[['ret_5d', 'vol_20d', 'volume_surge']].values
        return features, data.index

    def _assign_state_labels(self) -> None:
        """
        Heuristically assign human-readable labels to the HMM hidden states
        based on their learned Gaussian means.
        Means matrix shape: (n_components, n_features) -> (4, 3)
        Features: [ret_5d, vol_20d, volume_surge]
        """
        if self.model is None or not _HMM_AVAILABLE:
            return
            
        means = self.model.means_
        
        # Extract individual feature means across all states
        ret_means = means[:, 0]
        vol_means = means[:, 1]
        
        # Identify highest volatility state
        high_vol_state = int(np.argmax(vol_means))
        
        # Among the rest, identify highest return and lowest return
        remaining_states = [i for i in range(self.n_components) if i != high_vol_state]
        
        bull_state = int(max(remaining_states, key=lambda i: ret_means[i]))
        bear_state = int(min(remaining_states, key=lambda i: ret_means[i]))
        
        # The leftover state is range-bound
        range_bound_state = [i for i in remaining_states if i not in (bull_state, bear_state)][0]
        
        self.state_labels = {
            bull_state: "bull_trending",
            bear_state: "bear_trending",
            high_vol_state: "high_volatility",
            range_bound_state: "range_bound"
        }
        
        logger.info(f"HMM State Mapping: {self.state_labels}")

    def fit(self, df: pd.DataFrame) -> None:
        """
        Train the Gaussian HMM on historical Nifty 50 data.
        df should contain at least 4 years of data for robust states.
        """
        if not _HMM_AVAILABLE:
            logger.error("Cannot fit model. hmmlearn is not installed.")
            return
            
        logger.info("Extracting features for HMM regime training...")
        features, _ = self._prepare_features(df)
        
        if len(features) < 252:
            logger.warning("Less than 1 year of data provided for regime training. Results may be poor.")
            
        self.model = GaussianHMM(
            n_components=self.n_components,
            covariance_type=REGIME_CONFIG.get("covariance_type", "full"),
            n_iter=REGIME_CONFIG.get("n_iter", 100),
            random_state=REGIME_CONFIG.get("random_state", 42),
            init_params="kmeans"
        )
        
        logger.info("Fitting GaussianHMM...")
        self.model.fit(features)
        
        if self.model.monitor_.converged:
            logger.info("HMM converged successfully.")
        else:
            logger.warning("HMM did NOT converge. Consider increasing n_iter.")
            
        self._assign_state_labels()
        self.save_model()

    def predict_current_regime(self, df: pd.DataFrame) -> dict[str, Any]:
        """
        Predict the regime for the latest date in the provided dataframe.
        Returns the label and the probability distribution across all states.
        """
        if self.model is None or not _HMM_AVAILABLE:
            return {"regime": "unknown", "probabilities": {}}
            
        features, index = self._prepare_features(df)
        if len(features) == 0:
            return {"regime": "unknown", "probabilities": {}}
            
        # We need the sequence to infer the latest state
        probas = self.model.predict_proba(features)
        
        # Take the probabilities for the very last step
        latest_probs = probas[-1]
        
        best_state = int(np.argmax(latest_probs))
        label = self.state_labels.get(best_state, "unknown")
        
        prob_dict = {self.state_labels.get(i, f"state_{i}"): float(p) for i, p in enumerate(latest_probs)}
        
        return {
            "regime": label,
            "probabilities": prob_dict,
            "date": str(index[-1].date() if hasattr(index[-1], 'date') else index[-1])
        }

    def get_regime_history(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Returns a time series DataFrame of regime labels for visualization.
        """
        if self.model is None or not _HMM_AVAILABLE:
            return pd.DataFrame()
            
        features, index = self._prepare_features(df)
        states = self.model.predict(features)
        labels = [self.state_labels.get(s, "unknown") for s in states]
        
        res = pd.DataFrame(index=index)
        res['regime'] = labels
        res['state_id'] = states
        
        return res

    def save_model(self) -> None:
        """Persist HMM model to disk."""
        if self.model:
            os.makedirs(os.path.dirname(self.model_path), exist_ok=True)
            joblib.dump({"model": self.model, "labels": self.state_labels}, self.model_path)
            logger.info(f"Regime model saved to {self.model_path}")

    def load_model(self) -> None:
        """Load HMM model from disk."""
        try:
            data = joblib.load(self.model_path)
            self.model = data["model"]
            self.state_labels = data["labels"]
            logger.info(f"Regime model loaded from {self.model_path}")
        except Exception as e:
            logger.error(f"Failed to load regime model: {e}")
