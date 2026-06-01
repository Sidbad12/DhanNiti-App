"""
DhanNiti -- Add Ticker and Fine-Tune Model
Allows adding a new asset to the portfolio universe and fine-tuning
the existing permutation-invariant PPO agent.
"""

import argparse
import os
import sys
import logging
from datetime import datetime

# Add project root to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from stable_baselines3 import PPO
from src.agent.gym_env import NSEPortfolioGymEnv
from src.data.extractor import extract_data
from src.features.pipeline import build_full_feature_matrix
from src.settings import PORTFOLIO_TICKERS, START_DATE

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

def add_ticker_and_finetune(new_ticker: str, finetune_steps: int = 100000):
    logger.info("==================================================")
    logger.info(f"Adding {new_ticker} to DhanNiti portfolio universe")
    logger.info("==================================================")
    
    # 1. Check if the model exists
    model_path = "models/ppo_dhanniti.zip"
    if not os.path.exists(model_path):
        logger.error(f"Base model not found at {model_path}! Run run_full_pipeline.py first to pretrain.")
        sys.exit(1)
        
    # 2. Add to PORTFOLIO_TICKERS (warn if not already present in settings.py)
    if new_ticker not in PORTFOLIO_TICKERS:
        logger.warning(
            f"Note: '{new_ticker}' is not currently in PORTFOLIO_TICKERS inside src/settings.py. "
            "Please make sure you edit src/settings.py to add it permanently!"
        )
        tickers_universe = PORTFOLIO_TICKERS + [new_ticker]
    else:
        tickers_universe = PORTFOLIO_TICKERS
        
    # 3. Fetch data for the expanded universe
    end_date_str = datetime.now().strftime("%Y-%m-%d")
    logger.info(f"Fetching historical data for expanded portfolio universe: {tickers_universe}...")
    raw_data = extract_data(tickers_universe, START_DATE, end_date_str)
    
    # 4. Build feature matrix
    logger.info("Rebuilding feature matrix for the updated universe...")
    features_dict = build_full_feature_matrix(raw_data, add_labels=False)
    
    # 5. Build new environment
    logger.info("Initializing new Gymnasium environment with expanded assets...")
    new_env = NSEPortfolioGymEnv(features_dict=features_dict)
    
    # 6. Load model and set environment
    logger.info(f"Loading base PPO model from {model_path}...")
    from src.agent.ppo_policy import PermutationInvariantExtractor, DynamicPortfolioPolicy
    model = PPO.load(
        model_path,
        custom_objects={
            "features_extractor_class": PermutationInvariantExtractor,
            "policy": DynamicPortfolioPolicy
        }
    )
    model.set_env(new_env)
    
    # 7. Fine-tune model (retains previous weights, learns to optimize the new stock)
    logger.info(f"Starting fine-tuning for {finetune_steps} steps...")
    model.learn(total_timesteps=finetune_steps, reset_num_timesteps=False, progress_bar=True)
    
    # 8. Save updated model checkpoint
    logger.info(f"Saving updated model to {model_path}...")
    model.save(model_path)
    logger.info(f"✅ Successful transfer learning! {new_ticker} has been integrated.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Add a new stock and fine-tune the PPO agent.")
    parser.add_argument("ticker", type=str, help="Yahoo Finance ticker symbol, e.g. WIPRO.NS")
    parser.add_argument("--steps", type=int, default=100000, help="Number of fine-tuning timesteps")
    args = parser.parse_args()
    
    add_ticker_and_finetune(args.ticker, args.steps)
