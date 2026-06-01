"""
DhanNiti V2 — stock-Level Gymnasium Environment
Represents a single-stock trading task for training ticker-agnostic agents.
"""

import logging
from collections import deque
import numpy as np
import pandas as pd
import gymnasium as gym
from gymnasium import spaces

from src.data.feature_builder import build_v2_features, V2_STRICT_STATIC_COLUMNS

logger = logging.getLogger(__name__)

# Curriculum categories as defined in V2 architecture
LARGE_CAP_TICKERS = [
    "HDFCBANK.NS", "ICICIBANK.NS", "SBIN.NS", "KOTAKBANK.NS", "AXISBANK.NS",
    "BAJFINANCE.NS", "HDFCLIFE.NS", "SBILIFE.NS", "TCS.NS", "INFY.NS",
    "WIPRO.NS", "HCLTECH.NS", "TECHM.NS", "LTIM.NS", "RELIANCE.NS",
    "ONGC.NS", "NTPC.NS", "POWERGRID.NS", "LT.NS", "COALINDIA.NS",
    "BPCL.NS", "HINDUNILVR.NS", "ITC.NS", "NESTLEIND.NS", "BRITANNIA.NS",
    "DABUR.NS", "BHARTIARTL.NS", "TATAMOTORS.NS", "MARUTI.NS", "BAJAJ-AUTO.NS",
    "HEROMOTOCO.NS", "EICHERMOT.NS", "TATASTEEL.NS", "JSWSTEEL.NS", "HINDALCO.NS",
    "SUNPHARMA.NS", "DRREDDY.NS", "CIPLA.NS", "DIVISLAB.NS", "ADANIENT.NS",
    "ADANIPORTS.NS", "ULTRACEMCO.NS", "TITAN.NS", "ASIANPAINT.NS", "APOLLOHOSP.NS",
    "BAJAJFINSV.NS", "GRASIM.NS", "INDUSINDBK.NS", "M&M.NS", "TATACONSUM.NS"
]

MID_CAP_TICKERS = [
    "BANDHANBNK.NS", "FEDERALBNK.NS", "IDFCFIRSTB.NS", "MUTHOOTFIN.NS", "PNB.NS",
    "CHOLAFIN.NS", "PERSISTENT.NS", "COFORGE.NS", "MPHASIS.NS", "LTTS.NS",
    "MARICO.NS", "GODREJCP.NS", "COLPAL.NS", "EMAMILTD.NS", "BALKRISIND.NS",
    "MOTHERSON.NS", "BOSCHLTD.NS", "CUMMINSIND.NS", "AUROPHARMA.NS", "TORNTPHARM.NS",
    "ALKEM.NS", "IPCALAB.NS", "SIEMENS.NS", "ABB.NS", "HAVELLS.NS",
    "VOLTAS.NS", "POLYCAB.NS", "DLF.NS", "GODREJPROP.NS", "OBEROIRLTY.NS",
    "PIDILITIND.NS", "BERGEPAINT.NS", "SRF.NS", "ATUL.NS"
]

SMALL_CAP_TICKERS = [
    "RBLBANK.NS", "UJJIVANSFB.NS", "MASTEK.NS", "KPITTECH.NS", "TATAELXSI.NS",
    "ZYDUSWELL.NS", "JYOTHYLAB.NS", "GRINDWELL.NS", "KAYNES.NS", "APLAPOLLO.NS",
    "GRANULES.NS", "SUVEN.NS"
]


class NSEStockGymEnv(gym.Env):
    """
    Custom single-stock Gymnasium environment.
    Enables training ticker-agnostic agents on arbitrary NSE stocks.
    """
    
    metadata = {"render_modes": ["human"]}

    def __init__(
        self,
        ticker: str | list[str] | None = None,
        features_dict: dict[str, pd.DataFrame] | None = None,
        risk_aversion: float = 1.0,
        random_start: bool = True
    ) -> None:
        """
        Args:
            ticker: Specific ticker string (e.g. 'HDFCBANK.NS') to lock training,
                    or a list of tickers, or None to use full curriculum universe.
            features_dict: Preloaded dict mapping ticker to its V2 feature DataFrame.
                           If None, download/calculate features on the fly.
            risk_aversion: Risk aversion parameter.
            random_start: Whether to randomize the start day of each episode.
        """
        super().__init__()
        self.locked_ticker = ticker if isinstance(ticker, str) else None
        self.ticker_pool = ticker if isinstance(ticker, list) else None
        self.features_dict = features_dict or {}
        self.risk_aversion = risk_aversion
        self.random_start = random_start
        
        self.episode_count = 0
        self.current_ticker = None
        self.df = None
        self.current_step = 0
        
        # Action Space: target position size w in [0.0, 1.0]
        self.action_space = spaces.Box(
            low=0.0, high=1.0, shape=(1,), dtype=np.float32
        )
        
        # Observation Space: 78 static features (incl. 8 news) + 3 position context = 81 total
        self.observation_space = spaces.Box(
            low=-np.inf, high=np.inf, shape=(81,), dtype=np.float32
        )
        
        # Simulation state variables
        self.current_position = 0.0
        self.days_in_position = 0
        self.unrealised_pnl = 0.0
        self.entry_price = 0.0
        self.portfolio_value = 1.0
        self.peak_value = 1.0
        
        self.return_history = deque(maxlen=30)

    def _get_curriculum_stage(self) -> dict:
        """Get the active curriculum stage parameters based on episode count."""
        if self.episode_count < 200:
            return {
                "tickers": LARGE_CAP_TICKERS,
                "data_window": "last_2y",
                "description": "Large cap only, recent stable regime"
            }
        elif self.episode_count < 600:
            return {
                "tickers": LARGE_CAP_TICKERS + MID_CAP_TICKERS,
                "data_window": "last_3y",
                "description": "Large + mid cap, includes rate hike volatility"
            }
        else:
            return {
                "tickers": LARGE_CAP_TICKERS + MID_CAP_TICKERS + SMALL_CAP_TICKERS,
                "data_window": "full_5y",
                "description": "Full universe, all regimes including COVID crash"
            }

    def _load_ticker_data(self, ticker: str, data_window: str) -> pd.DataFrame:
        """Load features for a ticker and slice to the curriculum window."""
        if ticker not in self.features_dict:
            # Build on the fly
            logger.info(f"Features for {ticker} not preloaded. Generating on the fly...")
            self.features_dict[ticker] = build_v2_features(ticker)
            
        df = self.features_dict[ticker].copy()
        
        # Apply window slicing
        total_rows = len(df)
        if data_window == "last_2y":
            df = df.iloc[-min(total_rows, 504):]
        elif data_window == "last_3y":
            df = df.iloc[-min(total_rows, 756):]
            
        return df

    def reset(self, seed=None, options=None) -> tuple[np.ndarray, dict]:
        """Reset environment to start of an episode."""
        super().reset(seed=seed)
        
        self.episode_count += 1
        
        # 1. Choose Ticker and Window based on curriculum / locks
        if self.locked_ticker:
            self.current_ticker = self.locked_ticker
            # Default locked ticker to full history
            self.df = self._load_ticker_data(self.current_ticker, "full_5y")
        else:
            stage = self._get_curriculum_stage()
            allowed_tickers = stage["tickers"]
            
            # Restrict to preloaded tickers to avoid on-the-fly downloads/lags during training
            if self.features_dict:
                allowed_tickers = [t for t in allowed_tickers if t in self.features_dict]
                if not allowed_tickers:
                    allowed_tickers = list(self.features_dict.keys())
                    
            if self.ticker_pool:
                # Intersect allowed tickers with custom ticker pool
                allowed_tickers = [t for t in allowed_tickers if t in self.ticker_pool]
                if not allowed_tickers:
                    allowed_tickers = self.ticker_pool
            
            self.current_ticker = np.random.choice(allowed_tickers)
            self.df = self._load_ticker_data(self.current_ticker, stage["data_window"])

        # 2. Reset episode tracking variables
        # Use options to override default random_start behavior if provided
        use_random = options.get("random_start", self.random_start) if options else self.random_start
        
        max_start = len(self.df) - 252 - 1
        if use_random and max_start > 0:
            self.current_step = int(np.random.randint(0, max_start))
        else:
            self.current_step = 0
            
        self.current_position = 0.0
        self.days_in_position = 0
        self.unrealised_pnl = 0.0
        self.entry_price = 0.0
        self.portfolio_value = 1.0
        self.peak_value = 1.0
        self.return_history.clear()

        # Construct initial observation
        obs = self._get_observation()
        info = {
            "ticker": self.current_ticker,
            "date": str(self.df.index[self.current_step])
        }
        
        return obs, info

    def _get_observation(self) -> np.ndarray:
        """Construct the 81-feature observation vector."""
        # Extract the 78 static features for current step
        static_features = self.df.iloc[self.current_step][V2_STRICT_STATIC_COLUMNS].values.astype(np.float32)
        
        # Handle potential NaNs or infs from indicator calculations
        static_features = np.nan_to_num(static_features, nan=0.0, posinf=1.0, neginf=-1.0)
        
        # Calculate the 3 dynamic features
        # Normalize days in position to [0.0, 1.0] range (capped at 20 days)
        norm_days = float(min(self.days_in_position, 20) / 20.0)
        norm_pnl = float(np.clip(self.unrealised_pnl, -1.0, 1.0))
        
        dynamic_features = np.array([self.current_position, norm_days, norm_pnl], dtype=np.float32)
        
        # Combine
        obs = np.concatenate([static_features, dynamic_features])
        return obs

    def step(self, action: np.ndarray) -> tuple[np.ndarray, float, bool, bool, dict]:
        """Execute one simulation step."""
        target_position = float(np.clip(action[0], 0.0, 1.0))
        
        # Get market pricing for current step
        curr_row = self.df.iloc[self.current_step]
        stock_price = float(curr_row["Close"])
        stock_return = float(curr_row["Returns"])
        
        # 1. Update Portfolio return and value
        portfolio_return = self.current_position * stock_return
        self.portfolio_value *= (1.0 + portfolio_return)
        self.peak_value = max(self.peak_value, self.portfolio_value)
        
        # 2. Drawdown
        drawdown = (self.portfolio_value - self.peak_value) / (self.peak_value + 1e-9)

        # 3. Position context updates
        if target_position >= 0.2:  # Active position (BUY / REDUCE / HOLD)
            if self.current_position < 0.2:  # New position opened
                self.entry_price = stock_price
                self.days_in_position = 0
            else:
                self.days_in_position += 1
            self.unrealised_pnl = (stock_price - self.entry_price) / (self.entry_price + 1e-9)
        else:  # EXIT / FLAT
            self.entry_price = 0.0
            self.days_in_position = 0
            self.unrealised_pnl = 0.0

        # 4. Compute turnover for transaction cost calculation
        turnover = abs(target_position - self.current_position)

        # 5. Compute rolling Sharpe
        self.return_history.append(portfolio_return)
        if len(self.return_history) >= 10:
            hist_returns = np.array(list(self.return_history))
            mean_ret = np.mean(hist_returns)
            std_ret = np.std(hist_returns) + 1e-9
            sharpe_contrib = (mean_ret / std_ret) * np.sqrt(252)
        else:
            sharpe_contrib = portfolio_return * np.sqrt(252)

        # 6. Calculate continuous Bernoulli entropy proxy of target position
        a = np.clip(target_position, 1e-5, 1.0 - 1e-5)
        entropy = - (a * np.log(a) + (1.0 - a) * np.log(1.0 - a))

        # 7. Aggregate reward components
        # Transaction cost penalty
        tx_penalty = 0.004 * turnover * (1.0 + 0.5 * max(0.0, turnover - 0.10))
        # Drawdown penalty
        dd_penalty = 0.5 * abs(min(drawdown, 0.0))
        # Churn penalty (discourage holding beyond 20 days)
        churn_penalty = 0.001 * max(0, self.days_in_position - 20)
        # Entropy bonus
        entropy_bonus = 0.01 * entropy

        raw_reward = sharpe_contrib - tx_penalty - dd_penalty + entropy_bonus - churn_penalty
        
        # Bounded to [-1.0, 1.0] for stable training
        reward = float(np.clip(raw_reward, -1.0, 1.0))

        # Transition state
        self.current_position = target_position
        self.current_step += 1
        
        terminated = self.current_step >= len(self.df) - 1
        truncated = False
        
        obs = self._get_observation() if not terminated else np.zeros(self.observation_space.shape, dtype=np.float32)
        
        info = {
            "ticker": self.current_ticker,
            "date": str(self.df.index[min(self.current_step, len(self.df) - 1)]),
            "portfolio_value": self.portfolio_value,
            "drawdown": drawdown,
            "unrealised_pnl": self.unrealised_pnl,
            "days_held": self.days_in_position,
            "reward": reward
        }
        
        return obs, reward, terminated, truncated, info
