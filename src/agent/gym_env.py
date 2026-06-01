"""Gymnasium Environment for Indian Stock Portfolio Allocation."""

import logging
from collections import deque
import numpy as np
import pandas as pd
import gymnasium as gym
from gymnasium import spaces

from src.settings import PORTFOLIO_TICKERS, MINIMUM_ALLOCATION, MAXIMUM_ALLOCATION, RISK_AVERSION

logger = logging.getLogger(__name__)


class NSEPortfolioGymEnv(gym.Env):
    """Custom Gymnasium environment representing the NSE stock portfolio."""
    
    metadata = {"render_modes": ["human"]}

    def __init__(
        self,
        features_dict: dict[str, pd.DataFrame],
        lookback_window: int | None = None,
        risk_aversion: float = RISK_AVERSION,
        transaction_cost_pct: float = 0.0020  # ~0.20% explicit penalty for V2 optimization
    ) -> None:
        """
        Initialise environment.

        Args:
            features_dict: Dict mapping ticker to its feature DataFrame
            lookback_window: Number of historical days included in observation
            risk_aversion: Risk penalty coefficient
            transaction_cost_pct: Transaction cost percentage
        """
        super().__init__()
        self.features_dict = features_dict
        self.risk_aversion = risk_aversion
        self.transaction_cost_pct = transaction_cost_pct
        
        self.tickers = sorted(list(features_dict.keys()))
        self.num_assets = len(self.tickers)

        if not features_dict:
            raise ValueError(
                "Gymnasium environment received an empty 'features_dict'."
            )

        # Find common dates across all tickers
        date_sets = [set(df.index) for df in features_dict.values()]
        self.all_dates = sorted(list(set.intersection(*date_sets)))
        self.dates = self.all_dates.copy()
        
        from src.features.technical import get_feature_columns
        from src.settings import RL_CONFIG
        
        # Pull lookback window from settings if not passed
        self.lookback_window = lookback_window or RL_CONFIG.get("lookback_window", 30)
        
        # Automatically determine feature columns from the first dataframe
        first_df = list(features_dict.values())[0]
        self.feature_cols = get_feature_columns(first_df)
        
        # num_features includes all technical indicator columns + 1 column for current portfolio weights
        self.num_features = len(self.feature_cols) + 1

        # Action Space: Raw weights proposal (will be softmaxed/normalized to bounds)
        self.action_space = spaces.Box(
            low=-1.0, high=1.0, shape=(self.num_assets,), dtype=np.float32
        )

        # Observation Space: (num_assets * lookback_window * num_features)
        obs_shape = self.num_assets * self.lookback_window * self.num_features
        self.observation_space = spaces.Box(
            low=-np.inf, high=np.inf, shape=(obs_shape,), dtype=np.float32
        )

        # RL Phase 1 state
        self.episode_count = 0
        self.current_step = self.lookback_window
        self.current_weights = np.array([1.0 / self.num_assets] * self.num_assets, dtype=np.float32)
        
        # Buffers for advanced risk metrics
        self.return_history = deque(maxlen=30)
        self.portfolio_value_history = []
        self.current_portfolio_value = 1.0
        self.peak_value = 1.0

    def _get_observation(self) -> np.ndarray:
        """
        Construct a permutation-invariant observation matrix and flatten it.
        Shape: (num_assets, lookback_window, num_features)
        Where the last column of the features is the current weight of the stock.
        """
        obs_elements = []
        end_idx = self.current_step
        start_idx = end_idx - self.lookback_window

        # Extract features for each stock over the lookback window
        for idx, ticker in enumerate(self.tickers):
            df = self.features_dict[ticker]
            # Select historical window of dates
            window_df = df.loc[self.dates[start_idx:end_idx]]
            
            ticker_obs = []
            for col in self.feature_cols:
                vals = window_df[col].values if col in window_df.columns else np.zeros(self.lookback_window)
                # Replace infs/nans
                vals = np.nan_to_num(vals, nan=0.0, posinf=0.0, neginf=0.0)
                ticker_obs.append(vals)
                
            # Append current weight of this asset as a constant column across the window
            weight_col = np.full(self.lookback_window, self.current_weights[idx], dtype=np.float32)
            ticker_obs.append(weight_col)
            
            # Stack into a (lookback_window, num_features) matrix
            ticker_matrix = np.column_stack(ticker_obs)
            obs_elements.append(ticker_matrix)

        # Stack into (num_assets, lookback_window, num_features)
        obs_array = np.stack(obs_elements)
        
        # Flatten to shape (num_assets * lookback_window * num_features,) for SB3 compatibility
        return obs_array.flatten().astype(np.float32)

    def _normalize_weights(self, raw_actions: np.ndarray) -> np.ndarray:
        """
        Softmax and bound-adjust raw actions into valid portfolio weights.
        Ensures w_i in [MINIMUM_ALLOCATION, MAXIMUM_ALLOCATION] and sum(w_i) == 1.0.
        """
        exp_actions = np.exp(np.clip(raw_actions, -10, 10))
        weights = exp_actions / np.sum(exp_actions)

        min_w = MINIMUM_ALLOCATION
        max_w = MAXIMUM_ALLOCATION
        
        for _ in range(5):
            weights = np.clip(weights, min_w, max_w)
            weights = weights / np.sum(weights)

        return weights

    def _set_curriculum_dates(self) -> None:
        """
        Progressively expose the agent to harder market regimes (Curriculum Learning).
        Starts with a low-volatility period, expands to rate-hike crashes, then full history.
        """
        total_dates = len(self.all_dates)
        if total_dates == 0:
            return
            
        if self.episode_count < 50:
            # Stage 1: Easy mode. Last ~20% of data (usually recent steady market)
            start_idx = int(total_dates * 0.8)
            self.dates = self.all_dates[start_idx:]
        elif self.episode_count < 150:
            # Stage 2: Medium mode. Add rate-hike volatility (last 50% of data)
            start_idx = int(total_dates * 0.5)
            self.dates = self.all_dates[start_idx:]
        else:
            # Stage 3: Hard mode. Full history including COVID crash (if available in dates)
            self.dates = self.all_dates.copy()
            
        # Fallback if too short
        if len(self.dates) <= self.lookback_window:
            self.dates = self.all_dates.copy()

    def reset(self, seed=None, options=None) -> tuple[np.ndarray, dict]:
        """Reset environment to initial state."""
        super().reset(seed=seed)
        
        self.episode_count += 1
        self._set_curriculum_dates()
        
        self.current_step = self.lookback_window
        self.current_weights = np.array([1.0 / self.num_assets] * self.num_assets, dtype=np.float32)
        
        self.return_history.clear()
        self.portfolio_value_history = [1.0]
        self.current_portfolio_value = 1.0
        self.peak_value = 1.0
        
        obs = self._get_observation()
        info = {"date": self.dates[self.current_step]}
        
        return obs, info

    def step(self, action: np.ndarray) -> tuple[np.ndarray, float, bool, bool, dict]:
        """
        Perform a portfolio rebalance step with rolling Sharpe and drawdown/turnover penalties.
        """
        target_weights = self._normalize_weights(action)
        curr_date = self.dates[self.current_step]

        # 1. Fetch price returns of the assets for this step
        returns = []
        for ticker in self.tickers:
            df = self.features_dict[ticker]
            ret = df.loc[curr_date, "Returns"] if "Returns" in df.columns else 0.0
            returns.append(ret)
        returns = np.array(returns)
        
        # 2. Portfolio return and value update
        portfolio_return = np.dot(self.current_weights, returns)
        self.current_portfolio_value *= (1 + portfolio_return)
        self.portfolio_value_history.append(self.current_portfolio_value)
        self.return_history.append(portfolio_return)

        # 3. Transaction cost penalty
        weight_diffs = target_weights - self.current_weights
        txn_cost = np.sum(np.abs(weight_diffs)) * self.transaction_cost_pct
        
        # 4. Drawdown penalty from peak value
        self.peak_value = max(self.peak_value, self.current_portfolio_value)
        current_dd = (self.current_portfolio_value - self.peak_value) / self.peak_value if self.peak_value > 0 else 0.0
        dd_penalty = 0.5 * abs(min(current_dd, 0.0))
        
        # 5. Base: rolling Sharpe (last 30 steps)
        if len(self.return_history) >= 10:
            hist_returns = np.array(list(self.return_history))
            mean_ret = np.mean(hist_returns)
            std_ret = np.std(hist_returns) + 1e-9
            sharpe = (mean_ret / std_ret) * np.sqrt(252)
        else:
            sharpe = portfolio_return * np.sqrt(252)  # annualized return early on
            
        # 6. Combined Reward
        reward = float(sharpe - txn_cost - dd_penalty)
        
        # State updates
        self.current_weights = target_weights
        self.current_step += 1
        
        terminated = self.current_step >= len(self.dates) - 1
        truncated = False

        obs = self._get_observation() if not terminated else np.zeros(self.observation_space.shape, dtype=np.float32)
        info = {
            "date": curr_date,
            "portfolio_return": portfolio_return,
            "transaction_cost": txn_cost,
            "drawdown": current_dd,
            "portfolio_value": self.current_portfolio_value,
            "weights": {ticker: float(w) for ticker, w in zip(self.tickers, target_weights)}
        }

        return obs, reward, terminated, truncated, info
