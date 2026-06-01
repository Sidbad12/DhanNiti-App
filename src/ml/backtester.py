"""
DhanNiti — NSE Portfolio Backtester
Walk-forward simulation with realistic Indian market transaction costs,
signal-driven rebalancing, and comprehensive performance analytics.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Optional

import numpy as np
import pandas as pd

from src.settings import BACKTEST_CONFIG

logger = logging.getLogger(__name__)

# Risk-free rate: RBI repo rate proxy
RISK_FREE_RATE_ANNUAL = 0.065   # 6.5% p.a.
TRADING_DAYS_PER_YEAR = 252


# ════════════════════════════════════════════════════════════
# TRANSACTION COST MODEL
# ════════════════════════════════════════════════════════════

@dataclass
class NSECostModel:
    """
    Realistic NSE transaction cost model.

    Buy-side  : brokerage + STT (0.1%) + stamp duty (0.015%) + exchange charges
    Sell-side : brokerage + STT (0.1%) + exchange charges  (no stamp duty on sell)
    Impact cost is applied symmetrically on both sides.
    """
    brokerage_rate : float = BACKTEST_CONFIG["brokerage_rate"]   # 0.03%
    stt_rate       : float = BACKTEST_CONFIG["stt_rate"]         # 0.1%
    stamp_duty_rate: float = 0.00015                             # 0.015% buy only
    sebi_turnover  : float = 0.000001                            # ₹1 per ₹1 lakh
    exchange_txn   : float = 0.0000325                           # NSE exchange charges
    gst_rate       : float = 0.18                                # 18% GST on (brokerage + exchange)
    impact_cost    : float = BACKTEST_CONFIG["impact_cost"]      # 0.05% market impact

    @property
    def buy_rate(self) -> float:
        brokerage_eff = self.brokerage_rate * (1 + self.gst_rate)
        exchange_eff  = self.exchange_txn   * (1 + self.gst_rate)
        return (
            brokerage_eff
            + self.stt_rate
            + self.stamp_duty_rate
            + exchange_eff
            + self.sebi_turnover
            + self.impact_cost
        )

    @property
    def sell_rate(self) -> float:
        brokerage_eff = self.brokerage_rate * (1 + self.gst_rate)
        exchange_eff  = self.exchange_txn   * (1 + self.gst_rate)
        return (
            brokerage_eff
            + self.stt_rate          # STT applies on sell too (delivery)
            + exchange_eff
            + self.sebi_turnover
            + self.impact_cost
        )

    def cost_for_trade(self, trade_value: float, is_buy: bool) -> float:
        """Compute absolute INR cost for a single-side trade."""
        rate = self.buy_rate if is_buy else self.sell_rate
        return abs(trade_value) * rate

    def rebalance_cost(
        self,
        old_weights: pd.Series,
        new_weights: pd.Series,
        portfolio_value: float,
    ) -> float:
        """
        Total INR cost of rebalancing from old_weights → new_weights.
        Separately computes buy-side and sell-side costs.
        """
        all_tickers = old_weights.index.union(new_weights.index)
        total_cost  = 0.0

        for ticker in all_tickers:
            w_old = old_weights.get(ticker, 0.0)
            w_new = new_weights.get(ticker, 0.0)
            delta = w_new - w_old
            if abs(delta) < 1e-6:
                continue
            trade_val   = abs(delta) * portfolio_value
            total_cost += self.cost_for_trade(trade_val, is_buy=(delta > 0))

        return total_cost


# ════════════════════════════════════════════════════════════
# PERFORMANCE ANALYTICS
# ════════════════════════════════════════════════════════════

def _annualised_return(daily_returns: pd.Series) -> float:
    mean = daily_returns.mean()
    return float(mean * TRADING_DAYS_PER_YEAR) if not np.isnan(mean) else 0.0


def _annualised_volatility(daily_returns: pd.Series) -> float:
    std = daily_returns.std()
    return float(std * np.sqrt(TRADING_DAYS_PER_YEAR)) if not np.isnan(std) and std > 0 else 1e-8


def _sharpe_ratio(daily_returns: pd.Series, rf: float = RISK_FREE_RATE_ANNUAL) -> float:
    ann_ret = _annualised_return(daily_returns)
    ann_vol = _annualised_volatility(daily_returns)
    return (ann_ret - rf) / ann_vol


def _sortino_ratio(daily_returns: pd.Series, rf: float = RISK_FREE_RATE_ANNUAL) -> float:
    """Downside-deviation Sortino ratio."""
    ann_ret  = _annualised_return(daily_returns)
    downside = daily_returns[daily_returns < 0].std()
    if np.isnan(downside) or downside == 0:
        return 0.0
    ann_downside = downside * np.sqrt(TRADING_DAYS_PER_YEAR)
    return (ann_ret - rf) / ann_downside


def _max_drawdown(portfolio_values: pd.Series) -> float:
    rolling_max = portfolio_values.cummax()
    drawdown    = (portfolio_values - rolling_max) / (rolling_max + 1e-9)
    return float(drawdown.min())


def _calmar_ratio(daily_returns: pd.Series, portfolio_values: pd.Series) -> float:
    ann_ret = _annualised_return(daily_returns)
    mdd     = abs(_max_drawdown(portfolio_values))
    return ann_ret / mdd if mdd > 1e-6 else 0.0


def _win_rate(daily_returns: pd.Series) -> float:
    valid = daily_returns.dropna()
    if len(valid) == 0:
        return 0.0
    return float((valid > 0).sum() / len(valid))


def _value_at_risk(daily_returns: pd.Series, confidence: float = 0.95) -> float:
    """Historical VaR at given confidence level (negative = loss)."""
    return float(np.percentile(daily_returns.dropna(), (1 - confidence) * 100))


def _compute_alpha_beta(
    portfolio_returns: pd.Series,
    benchmark_returns: pd.Series,
) -> tuple[float, float]:
    """
    OLS regression: portfolio ~ alpha + beta * benchmark.
    Returns (alpha_annualised, beta).
    """
    aligned = pd.concat(
        [portfolio_returns.rename("port"), benchmark_returns.rename("bench")],
        axis=1,
    ).dropna()

    if len(aligned) < 10:
        return 0.0, 1.0

    x = aligned["bench"].values
    y = aligned["port"].values

    cov_matrix = np.cov(x, y)
    beta       = cov_matrix[0, 1] / (cov_matrix[0, 0] + 1e-9)
    alpha_daily = y.mean() - beta * x.mean()
    alpha_ann   = alpha_daily * TRADING_DAYS_PER_YEAR

    return float(alpha_ann), float(beta)


# ════════════════════════════════════════════════════════════
# RESULTS CONTAINER
# ════════════════════════════════════════════════════════════

@dataclass
class BacktestResult:
    """Structured container for all backtest outputs."""
    # Equity curve
    equity_curve    : pd.Series   = field(default_factory=pd.Series)
    daily_returns   : pd.Series   = field(default_factory=pd.Series)

    # Core metrics
    initial_capital : float = 0.0
    final_value     : float = 0.0
    total_return    : float = 0.0       # e.g. 0.45 = 45%
    ann_return      : float = 0.0
    ann_volatility  : float = 0.0

    # Risk-adjusted
    sharpe_ratio    : float = 0.0
    sortino_ratio   : float = 0.0
    calmar_ratio    : float = 0.0
    max_drawdown    : float = 0.0       # negative, e.g. -0.12

    # Activity
    win_rate        : float = 0.0
    var_95          : float = 0.0       # 1-day 95% VaR
    total_fees_inr  : float = 0.0
    n_rebalances    : int   = 0

    # Benchmark comparison (optional)
    benchmark_return : float = 0.0
    alpha            : float = 0.0
    beta             : float = 1.0

    def summary(self) -> dict:
        """Return a flat metrics dict for MLflow logging."""
        return {
            "final_value"     : round(self.final_value, 2),
            "total_return_pct": round(self.total_return * 100, 3),
            "ann_return_pct"  : round(self.ann_return   * 100, 3),
            "ann_volatility"  : round(self.ann_volatility, 4),
            "sharpe_ratio"    : round(self.sharpe_ratio,  4),
            "sortino_ratio"   : round(self.sortino_ratio, 4),
            "calmar_ratio"    : round(self.calmar_ratio,  4),
            "max_drawdown_pct": round(self.max_drawdown * 100, 3),
            "win_rate_pct"    : round(self.win_rate * 100, 2),
            "var_95_pct"      : round(self.var_95  * 100, 3),
            "total_fees_inr"  : round(self.total_fees_inr, 2),
            "n_rebalances"    : self.n_rebalances,
            "benchmark_return": round(self.benchmark_return * 100, 3),
            "alpha"           : round(self.alpha, 4),
            "beta"            : round(self.beta, 4),
        }

    def __repr__(self) -> str:
        s = self.summary()
        lines = [
            "═" * 50,
            "  DhanNiti Backtest Results",
            "═" * 50,
            f"  Total Return     : {s['total_return_pct']:>8.2f}%",
            f"  Ann. Return      : {s['ann_return_pct']:>8.2f}%",
            f"  Ann. Volatility  : {s['ann_volatility']:>8.4f}",
            f"  Sharpe Ratio     : {s['sharpe_ratio']:>8.4f}",
            f"  Sortino Ratio    : {s['sortino_ratio']:>8.4f}",
            f"  Calmar Ratio     : {s['calmar_ratio']:>8.4f}",
            f"  Max Drawdown     : {s['max_drawdown_pct']:>8.2f}%",
            f"  Win Rate         : {s['win_rate_pct']:>8.2f}%",
            f"  95% VaR (1-day)  : {s['var_95_pct']:>8.3f}%",
            f"  Total Fees (₹)   : {s['total_fees_inr']:>10.2f}",
            f"  Rebalances       : {s['n_rebalances']:>8d}",
            "─" * 50,
            f"  Benchmark Return : {s['benchmark_return']:>8.2f}%",
            f"  Alpha (ann.)     : {s['alpha']:>8.4f}",
            f"  Beta             : {s['beta']:>8.4f}",
            "═" * 50,
        ]
        return "\n".join(lines)


# ════════════════════════════════════════════════════════════
# BACKTESTER
# ════════════════════════════════════════════════════════════

class DhanNitiBacktester:
    """
    Walk-forward portfolio backtester for NSE equities.

    Supports:
    - Signal-driven rebalancing (from DhanNitiClassifier outputs)
    - Static weight rebalancing (Markowitz / equal-weight baselines)
    - Full NSE transaction cost model
    - Benchmark comparison (Nifty 50 or custom series)
    """

    def __init__(
        self,
        initial_capital : float           = BACKTEST_CONFIG["initial_capital"],
        cost_model      : Optional[NSECostModel] = None,
        rebalance_freq  : str             = "W",       # pandas offset alias: 'D', 'W', 'M'
        min_weight      : float           = 0.05,
        max_weight      : float           = 0.30,
    ) -> None:
        self.initial_capital = initial_capital
        self.cost_model      = cost_model or NSECostModel()
        self.rebalance_freq  = rebalance_freq
        self.min_weight      = min_weight
        self.max_weight      = max_weight

    # ── Weight helpers ───────────────────────────────────────

    def _clip_and_renormalise(self, weights: pd.Series) -> pd.Series:
        """
        Iteratively clip weights to [min, max] and renormalise until convergence.
        A single-pass clip + renorm can push redistributed weights back over max;
        iterating until no weight violates bounds guarantees feasibility.
        """
        w = weights.copy().clip(lower=0.0)
        for _ in range(50):  # max 50 iterations — always converges
            total = w.sum()
            if total <= 0:
                break
            w = w / total           # normalise to sum=1
            clipped = w.clip(lower=self.min_weight, upper=self.max_weight)
            if (clipped - w).abs().max() < 1e-9:
                break               # converged
            w = clipped
        # Final normalise
        total = w.sum()
        return (w / total) if total > 0 else w

    def _equal_weights(self, tickers: list[str]) -> pd.Series:
        n = len(tickers)
        raw = pd.Series(1.0 / n, index=tickers)
        return self._clip_and_renormalise(raw)

    # ── Signal → weight conversion ──────────────────────────

    def signals_to_weights(
        self,
        signals: dict[str, dict],
        base_weights: Optional[pd.Series] = None,
    ) -> pd.Series:
        """
        Convert DhanNitiClassifier signals to portfolio weights.

        Strategy:
          - BUY  signal → scale up by (1 + confidence × 0.5)
          - SELL signal → scale down by (1 - confidence × 0.5)
          - HOLD        → keep base weight unchanged
        Then clip to [min_weight, max_weight] and renormalise.

        Args:
            signals     : {ticker: {action, confidence, ...}}
            base_weights: Starting weights (equal-weight if None)

        Returns:
            Normalised weight Series
        """
        tickers = list(signals.keys())
        if base_weights is None:
            base_weights = self._equal_weights(tickers)

        adjusted = base_weights.copy().reindex(tickers).fillna(1.0 / len(tickers))

        for ticker, sig in signals.items():
            action     = sig.get("action", "HOLD")
            confidence = float(sig.get("confidence", 0.5))

            if action == "BUY":
                adjusted[ticker] *= (1.0 + confidence * 0.5)
            elif action == "SELL":
                adjusted[ticker] *= (1.0 - confidence * 0.5)
            # HOLD: no change

        return self._clip_and_renormalise(adjusted)

    # ── Core backtest ────────────────────────────────────────

    def run(
        self,
        prices          : pd.DataFrame,
        weights_history : Optional[pd.DataFrame] = None,
        signals_history : Optional[dict[str, dict[str, dict]]] = None,
        benchmark_prices: Optional[pd.Series] = None,
    ) -> BacktestResult:
        """
        Run the walk-forward backtest.

        Args:
            prices          : DataFrame [Date × Ticker] of Close prices.
            weights_history : DataFrame [Date × Ticker] of pre-computed weights.
                              If None, signal_history is used; falls back to equal-weight.
            signals_history : {date_str: {ticker: signal_dict}} from classifier.
                              Used when weights_history is None.
            benchmark_prices: Series [Date] of Nifty 50 (or benchmark) close prices.
                              If None, benchmark metrics are set to NaN.

        Returns:
            BacktestResult with full analytics.
        """
        # Align index types to standard pd.Timestamp and strip timezones for seamless alignment
        def strip_tz(idx):
            dt_idx = pd.to_datetime(idx)
            if dt_idx.tz is not None:
                try:
                    return dt_idx.tz_convert(None).tz_localize(None)
                except Exception:
                    try:
                        return dt_idx.tz_localize(None)
                    except Exception:
                        pass
            return dt_idx

        prices = prices.copy()
        prices.index = strip_tz(prices.index)
        
        if weights_history is not None:
            weights_history = weights_history.copy()
            weights_history.index = strip_tz(weights_history.index)
            
        if benchmark_prices is not None:
            benchmark_prices = benchmark_prices.copy()
            benchmark_prices.index = strip_tz(benchmark_prices.index)

        prices = prices.sort_index()
        dates  = prices.index.tolist()

        if len(dates) < 2:
            raise ValueError("Need at least 2 dates of price data to run backtest.")

        # Determine rebalance dates based on actual last trading day of each resample interval
        rebal_dates = set(
            pd.Series(prices.index, index=prices.index)
            .resample(self.rebalance_freq)
            .last()
        )

        # ── Initialise state ─────────────────────────────────
        tickers        = prices.columns.tolist()
        equity_curve   = []
        portfolio_val  = self.initial_capital
        total_fees     = 0.0
        n_rebalances   = 0
        current_weights = self._equal_weights(tickers)

        equity_curve.append((dates[0], portfolio_val))

        # ── Main loop ─────────────────────────────────────────
        for i in range(1, len(dates)):
            prev_date = dates[i - 1]
            curr_date = dates[i]

            # 1. Apply daily price returns
            prev_prices = prices.loc[prev_date]
            curr_prices = prices.loc[curr_date]
            daily_rets  = (curr_prices - prev_prices) / (prev_prices.replace(0, np.nan) + 1e-9)
            daily_rets  = daily_rets.fillna(0.0)

            port_ret    = float((current_weights * daily_rets).sum())
            portfolio_val *= (1.0 + port_ret)

            # 2. Rebalance if on a rebalance date
            if curr_date in rebal_dates:
                new_weights = self._resolve_target_weights(
                    curr_date, tickers, weights_history, signals_history, current_weights
                )

                # Check if weights actually changed (avoid tiny-cost phantom trades)
                weight_diff = (new_weights - current_weights).abs().sum()
                if weight_diff > 0.005:
                    fees = self.cost_model.rebalance_cost(
                        current_weights, new_weights, portfolio_val
                    )
                    portfolio_val  -= fees
                    total_fees     += fees
                    n_rebalances   += 1
                    current_weights = new_weights
                    logger.debug(
                        f"{curr_date.date()}: rebalanced | fees=₹{fees:.2f} | "
                        f"portfolio=₹{portfolio_val:,.2f}"
                    )

            equity_curve.append((curr_date, portfolio_val))

        # ── Build equity Series ───────────────────────────────
        eq_dates, eq_vals = zip(*equity_curve)
        equity_series     = pd.Series(eq_vals, index=eq_dates, name="Portfolio_Value")
        daily_ret_series  = equity_series.pct_change().dropna()

        # ── Benchmark analytics ───────────────────────────────
        bench_total_return = 0.0
        alpha, beta        = 0.0, 1.0

        if benchmark_prices is not None:
            bench_aligned   = benchmark_prices.reindex(equity_series.index).ffill()
            bench_rets      = bench_aligned.pct_change().dropna()
            bench_total_return = float(
                (bench_aligned.iloc[-1] / bench_aligned.iloc[0]) - 1
            )
            alpha, beta = _compute_alpha_beta(daily_ret_series, bench_rets)

        # ── Assemble result ────────────────────────────────────
        total_return = (portfolio_val - self.initial_capital) / self.initial_capital

        result = BacktestResult(
            equity_curve    = equity_series,
            daily_returns   = daily_ret_series,
            initial_capital = self.initial_capital,
            final_value     = portfolio_val,
            total_return    = total_return,
            ann_return      = _annualised_return(daily_ret_series),
            ann_volatility  = _annualised_volatility(daily_ret_series),
            sharpe_ratio    = _sharpe_ratio(daily_ret_series),
            sortino_ratio   = _sortino_ratio(daily_ret_series),
            calmar_ratio    = _calmar_ratio(daily_ret_series, equity_series),
            max_drawdown    = _max_drawdown(equity_series),
            win_rate        = _win_rate(daily_ret_series),
            var_95          = _value_at_risk(daily_ret_series),
            total_fees_inr  = total_fees,
            n_rebalances    = n_rebalances,
            benchmark_return= bench_total_return,
            alpha           = alpha,
            beta            = beta,
        )

        logger.info(result)
        return result

    def _resolve_target_weights(
        self,
        date          : pd.Timestamp,
        tickers       : list[str],
        weights_history : Optional[pd.DataFrame],
        signals_history : Optional[dict],
        current_weights : pd.Series,
    ) -> pd.Series:
        """
        Determine the target weights for a given rebalance date.
        Priority: weights_history > signals_history > hold current weights.
        """
        # 1. Explicit weight table (Markowitz / RL output)
        if weights_history is not None:
            # Check if exact date exists
            if date in weights_history.index:
                raw = weights_history.loc[date].reindex(tickers).fillna(0.0)
                return self._clip_and_renormalise(raw)
            else:
                # Find nearest prior date in the weights history index
                prior_dates = weights_history.index[weights_history.index <= date]
                if not prior_dates.empty:
                    nearest_date = prior_dates[-1]
                    raw = weights_history.loc[nearest_date].reindex(tickers).fillna(0.0)
                    return self._clip_and_renormalise(raw)

        # 2. Classifier signals
        if signals_history is not None:
            date_key = str(date.date())
            if date_key in signals_history:
                return self.signals_to_weights(
                    signals_history[date_key],
                    base_weights=current_weights,
                )

        # 3. Hold current (no rebalance)
        return current_weights

    # ── Convenience: run on signal dict directly ─────────────

    def run_from_signals(
        self,
        prices          : pd.DataFrame,
        signals_history : dict[str, dict[str, dict]],
        benchmark_prices: Optional[pd.Series] = None,
    ) -> BacktestResult:
        """
        Shorthand for signal-driven backtests.

        Args:
            prices          : Close price DataFrame [Date × Ticker]
            signals_history : {date_str: {ticker: signal_dict}}
            benchmark_prices: Optional benchmark price Series
        """
        return self.run(
            prices          = prices,
            weights_history = None,
            signals_history = signals_history,
            benchmark_prices= benchmark_prices,
        )

    def run_from_weights(
        self,
        prices          : pd.DataFrame,
        weights_history : pd.DataFrame,
        benchmark_prices: Optional[pd.Series] = None,
    ) -> BacktestResult:
        """
        Shorthand for weight-table driven backtests.

        Args:
            prices          : Close price DataFrame [Date × Ticker]
            weights_history : DataFrame [Date × Ticker] of target weights
            benchmark_prices: Optional benchmark price Series
        """
        return self.run(
            prices          = prices,
            weights_history = weights_history,
            signals_history = None,
            benchmark_prices= benchmark_prices,
        )

    # ── Phase 5: RL Feedback Loop & Regime Split ─────────────

    def compute_rl_feedback(self, result: BacktestResult) -> dict:
        """
        Generate structured feedback for the RL Curriculum agent based on backtest performance.
        Returns metrics used to dynamically adjust episode difficulty.
        """
        daily_returns = result.daily_returns
        equity = result.equity_curve
        
        # Calculate rolling 30-day cumulative returns
        if len(daily_returns) >= 30:
            roll_30 = daily_returns.rolling(30).apply(lambda x: (1 + x).prod() - 1).dropna()
            if not roll_30.empty:
                best_30d_date = str(roll_30.idxmax().date() if hasattr(roll_30.idxmax(), 'date') else roll_30.idxmax())
                worst_30d_date = str(roll_30.idxmin().date() if hasattr(roll_30.idxmin(), 'date') else roll_30.idxmin())
            else:
                best_30d_date = None
                worst_30d_date = None
        else:
            best_30d_date = None
            worst_30d_date = None
            
        # Identify crisis dates (running drawdown > 15%)
        rolling_max = equity.cummax()
        drawdowns = (equity - rolling_max) / (rolling_max + 1e-9)
        crisis_mask = drawdowns < -0.15
        crisis_dates = [str(d.date() if hasattr(d, 'date') else d) for d in drawdowns[crisis_mask].index]
        
        return {
            "sharpe": float(result.sharpe_ratio),
            "max_drawdown": float(result.max_drawdown),
            "worst_30d_window_start": worst_30d_date,
            "best_30d_window_start": best_30d_date,
            "crisis_dates": crisis_dates
        }

    def run_regime_split(
        self,
        result: BacktestResult,
        regime_history: pd.DataFrame
    ) -> dict[str, dict[str, float]]:
        """
        Evaluate portfolio performance explicitly separated by market regimes.
        
        Args:
            result: A completed BacktestResult object.
            regime_history: DataFrame with a 'regime' column and datetime index.
            
        Returns:
            Dict mapping regime string to performance metrics.
        """
        daily_returns = result.daily_returns
        
        if "regime" not in regime_history.columns:
            logger.warning("regime_history missing 'regime' column. Cannot split performance.")
            return {}
            
        # Align returns and regimes by date
        aligned = pd.concat([daily_returns.rename("ret"), regime_history["regime"]], axis=1).dropna()
        
        regime_perf = {}
        for regime in aligned["regime"].unique():
            regime_rets = aligned.loc[aligned["regime"] == regime, "ret"]
            
            ann_ret = _annualised_return(regime_rets)
            ann_vol = _annualised_volatility(regime_rets)
            sharpe = _sharpe_ratio(regime_rets)
            win_rate = _win_rate(regime_rets)
            
            regime_perf[str(regime)] = {
                "annualised_return": float(ann_ret),
                "annualised_volatility": float(ann_vol),
                "sharpe_ratio": float(sharpe),
                "win_rate": float(win_rate),
                "days_in_regime": len(regime_rets)
            }
            
        return regime_perf


# ════════════════════════════════════════════════════════════
# LEGACY SHIM  (backward compat with old NSEPortfolioBacktester)
# ════════════════════════════════════════════════════════════

class NSEPortfolioBacktester(DhanNitiBacktester):
    """
    Backward-compatible alias for NSEPortfolioBacktester.
    Delegates to DhanNitiBacktester.run_from_weights().
    """

    def __init__(
        self,
        brokerage_pct  : float = BACKTEST_CONFIG["brokerage_rate"],
        stt_pct        : float = BACKTEST_CONFIG["stt_rate"],
        stamp_duty_pct : float = 0.00015,
        other_charges_pct: float = 0.00005,
        initial_capital: float = BACKTEST_CONFIG["initial_capital"],
    ) -> None:
        cost_model = NSECostModel(
            brokerage_rate = brokerage_pct,
            stt_rate       = stt_pct,
            stamp_duty_rate= stamp_duty_pct,
            impact_cost    = other_charges_pct,
        )
        super().__init__(initial_capital=initial_capital, cost_model=cost_model)

    def compute_transaction_costs(
        self,
        old_weights    : pd.Series,
        new_weights    : pd.Series,
        portfolio_value: float,
    ) -> float:
        """Legacy API: compute rebalance cost."""
        return self.cost_model.rebalance_cost(old_weights, new_weights, portfolio_value)

    def run_backtest(
        self,
        historical_prices: pd.DataFrame,
        weights_history  : pd.DataFrame,
    ) -> dict:
        """Legacy API: run backtest and return flat metrics dict."""
        result = self.run_from_weights(historical_prices, weights_history)
        return {
            "dates"         : result.equity_curve.index.tolist(),
            "portfolio_values": result.equity_curve.tolist(),
            "total_return"  : result.total_return,
            "sharpe_ratio"  : result.sharpe_ratio,
            "max_drawdown"  : result.max_drawdown,
            "total_fees_paid": result.total_fees_inr,
            "final_value"   : result.final_value,
        }
