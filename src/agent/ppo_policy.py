import torch
import torch.nn as nn
from stable_baselines3.common.torch_layers import BaseFeaturesExtractor
from src.agent.stock_encoder import StockEncoder

class PermutationInvariantExtractor(BaseFeaturesExtractor):
    """
    Custom feature extractor for SB3.
    Replaces the standard flat MLP feature extractor with a shared,
    permutation-invariant stock encoder (LSTM).
    """
    
    def __init__(self, observation_space, n_stocks: int, 
                 n_features: int, lookback: int = 30, embedding_dim: int = 64):
        # We output (n_stocks * embedding_dim) features to the standard policy heads
        super().__init__(observation_space, features_dim=n_stocks * embedding_dim)
        
        self.n_stocks = n_stocks
        self.n_features = n_features
        self.lookback = lookback
        self.embedding_dim = embedding_dim
        
        self.encoder = StockEncoder(n_features, lookback, embedding_dim)
        
    def forward(self, observations: torch.Tensor) -> torch.Tensor:
        """
        observations: (batch, n_stocks * lookback * n_features) -- flat from SB3
        returns: (batch, n_stocks * embedding_dim)
        """
        batch_size = observations.shape[0]
        
        # Reshape flat observation back to (batch, n_stocks, lookback, n_features)
        x = observations.reshape(
            batch_size, self.n_stocks, self.lookback, self.n_features
        )
        
        # Reshape to run all batches and stocks through the shared LSTM
        x_flat = x.reshape(batch_size * self.n_stocks, self.lookback, self.n_features)
        
        # Pass through temporal LSTM
        _, (h_n, _) = self.encoder.temporal(x_flat)
        
        # Extract last hidden state
        embeddings = h_n[-1].reshape(batch_size, self.n_stocks, self.embedding_dim)
        
        # Flatten the embeddings for the final policy heads (pi and vf)
        return embeddings.reshape(batch_size, self.n_stocks * self.embedding_dim)


from stable_baselines3.common.policies import ActorCriticPolicy

class DynamicPortfolioPolicy(ActorCriticPolicy):
    """
    Custom policy that dynamically builds the final action head based on 
    the number of stocks extracted from the environment/features extractor.
    This enables dynamic scaling without retraining from scratch.
    """
    def _build(self, lr_schedule):
        super()._build(lr_schedule)
        # Replace fixed action_net with dynamic one based on current features extractor
        self.action_net = nn.Linear(
            self.mlp_extractor.latent_dim_pi,
            self.features_extractor.n_stocks
        )

def make_pi_policy_kwargs(n_stocks: int, n_features: int, 
                           lookback: int = 30, embedding_dim: int = 64) -> dict:
    """
    Returns policy_kwargs dictionary to pass into the SB3 PPO constructor.
    """
    return dict(
        features_extractor_class=PermutationInvariantExtractor,
        features_extractor_kwargs=dict(
            n_stocks=n_stocks,
            n_features=n_features,
            lookback=lookback,
            embedding_dim=embedding_dim,
        ),
        net_arch=dict(pi=[128, 64], vf=[128, 64]),
        activation_fn=nn.ReLU,
    )
