import torch
import torch.nn as nn

class StockEncoder(nn.Module):
    """
    Shared encoder applied identically to every stock.
    Input:  (batch, n_stocks, lookback, n_features)
    Output: (batch, n_stocks) -- raw conviction scores
    
    Because the weights of this network are shared across all assets,
    we can scale the universe dynamically without changing model parameters.
    """
    
    def __init__(self, n_features: int, lookback: int = 30, embedding_dim: int = 64):
        super().__init__()
        self.lookback = lookback
        self.embedding_dim = embedding_dim
        
        # Temporal encoder - processes the sequence (lookback) per stock
        self.temporal = nn.LSTM(
            input_size=n_features,
            hidden_size=embedding_dim,
            num_layers=2,
            batch_first=True,
            dropout=0.1
        )
        
        # Score head - maps the final hidden embedding to a single score
        self.score_head = nn.Sequential(
            nn.Linear(embedding_dim, 32),
            nn.ReLU(),
            nn.Linear(32, 1)
        )
        
    def forward(self, x: torch.Tensor) -> torch.Tensor:
        """
        x: (batch, n_stocks, lookback, n_features)
        returns: (batch, n_stocks) -- allocation weights
        """
        batch_size, n_stocks, lookback, n_features = x.shape
        
        # Reshape to process all stocks through the same shared LSTM weights
        # (batch * n_stocks, lookback, n_features)
        x_flat = x.reshape(batch_size * n_stocks, lookback, n_features)
        
        # LSTM - take final hidden state of the last layer
        _, (h_n, _) = self.temporal(x_flat)
        # h_n is (num_layers, batch * n_stocks, embedding_dim)
        embeddings = h_n[-1]  # (batch * n_stocks, embedding_dim)
        
        # Score each stock
        scores = self.score_head(embeddings)  # (batch * n_stocks, 1)
        scores = scores.reshape(batch_size, n_stocks)  # (batch, n_stocks)
        
        # Softmax to yield dynamic weights summing to 1.0
        weights = torch.softmax(scores, dim=-1)
        
        return weights
