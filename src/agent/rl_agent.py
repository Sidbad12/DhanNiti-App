"""Reinforcement Learning PPO portfolio allocation agent using Stable-Baselines3."""

import logging
import os
import pandas as pd
import numpy as np
from datetime import datetime
from stable_baselines3 import PPO
from stable_baselines3.common.callbacks import CheckpointCallback, BaseCallback, CallbackList

class TimestampCallback(BaseCallback):
    def _on_step(self) -> bool:
        return True
    
    def _on_rollout_end(self) -> None:
        self.logger.record("time/timestamp", datetime.now().strftime('%Y-%m-%d %H:%M:%S'))

from src.agent.gym_env import NSEPortfolioGymEnv
from src.agent.ppo_policy import PermutationInvariantExtractor

logger = logging.getLogger(__name__)


class RLPortfolioAgent:
    """Wrapper class managing PPO agent training, checkpoints, and production inferences."""

    def __init__(self, tensorboard_log: str = "./tensorboard_logs") -> None:
        """Initialise agent settings."""
        self.tensorboard_log = tensorboard_log
        self.model: PPO | None = None
        os.makedirs("models", exist_ok=True)

    def train_agent(
        self,
        features_dict: dict[str, pd.DataFrame],
        total_timesteps: int = 10000,
        model_name: str = "ppo_dhanniti"
    ) -> PPO:
        """
        Train the PPO agent on the NSE Gymnasium environment.

        Args:
            features_dict: Dictionary of feature DataFrames per ticker
            total_timesteps: Number of timesteps to train
            model_name: File name for saving model checkpoints

        Returns:
            Trained PPO model
        """
        logger.info("Initializing Gym environment for RL training...")
        env = NSEPortfolioGymEnv(features_dict=features_dict)
        
        from src.agent.ppo_policy import make_pi_policy_kwargs, DynamicPortfolioPolicy
        
        n_stocks = len(env.tickers)
        n_features = env.num_features
        lookback = env.lookback_window
        
        policy_kwargs = make_pi_policy_kwargs(
            n_stocks=n_stocks,
            n_features=n_features,
            lookback=lookback,
            embedding_dim=64
        )
        
        # Configure PPO model with optimized parameters
        logger.info(f"Setting up PPO model. Training for {total_timesteps} steps...")
        self.model = PPO(
            DynamicPortfolioPolicy,
            env,
            policy_kwargs=policy_kwargs,
            verbose=1,
            learning_rate=0.0003,
            n_steps=2048,
            batch_size=64,
            n_epochs=10,
            gamma=0.99,
            ent_coef=0.01,
            vf_coef=0.5,
            max_grad_norm=0.5,
            tensorboard_log=self.tensorboard_log if self.tensorboard_log else None
        )

        # Setup checkpointing every 50k steps to prevent progress loss
        os.makedirs("models/checkpoints", exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        checkpoint_callback = CheckpointCallback(
            save_freq=50_000,
            save_path="./models/checkpoints/",
            name_prefix=f"{model_name}_{timestamp}"
        )
        
        callback_list = CallbackList([checkpoint_callback, TimestampCallback()])

        # Train PPO model
        self.model.learn(
            total_timesteps=total_timesteps,
            callback=callback_list
        )
        
        # Save checkpoint
        checkpoint_path = f"models/{model_name}.zip"
        self.model.save(checkpoint_path)
        logger.info(f"PPO Model checkpoint saved to: {checkpoint_path}")

        try:
            import mlflow
            # Log the .zip file to the active MLflow run (DagsHub or local)
            mlflow.log_artifact(checkpoint_path, artifact_path="models/rl_agent")
            logger.info("Successfully uploaded PPO model to MLflow registry.")
        except Exception as e:
            logger.warning(f"Could not log PPO model to MLflow: {e}")

        return self.model

    def predict_weights(self, features_dict: dict[str, pd.DataFrame], model_name: str = "ppo_dhanniti") -> dict[str, float]:
        """
        Predict portfolio weights using the trained PPO agent for the latest available date.

        Args:
            features_dict: Dictionary of feature DataFrames per ticker
            model_name: File name for loading model checkpoints

        Returns:
            Dictionary mapping ticker to optimal weight
        """
        checkpoint_path = f"models/{model_name}.zip"

        # Load model if not in memory
        if self.model is None:
            if os.path.exists(checkpoint_path):
                self.model = PPO.load(
                    checkpoint_path,
                    custom_objects={
                        "features_extractor_class": PermutationInvariantExtractor
                    }
                )
                logger.info(f"PPO Model successfully loaded from: {checkpoint_path}")
            else:
                logger.warning("No PPO checkpoint found! Falling back to equal weight allocation.")
                tickers = sorted(list(features_dict.keys()))
                return {ticker: 1.0 / len(tickers) for ticker in tickers}

        # Initialize environment to extract latest observation
        env = NSEPortfolioGymEnv(features_dict=features_dict)
        # Ensure we use full dates and point to the latest day for inference
        env.dates = env.all_dates.copy()
        env.current_step = len(env.dates) - 1
        obs = env._get_observation()

        # Run PPO model to predict action
        action, _states = self.model.predict(obs, deterministic=True)

        # Map and normalize action to portfolio weights
        weights = env._normalize_weights(action)
        
        # Build weight dictionary
        weight_dict = {
            ticker: float(w) for ticker, w in zip(env.tickers, weights)
        }
        
        return weight_dict
