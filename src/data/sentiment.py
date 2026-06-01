"""
DhanNiti — FinBERT Sentiment Pipeline
Fetches latest news headlines for portfolio tickers via RSS
and scores them using ProsusAI/finbert.
"""

import logging
import feedparser
import numpy as np
from typing import Dict, List, Any

logger = logging.getLogger(__name__)

try:
    import torch
    import torch.nn.functional as F
    from transformers import AutoTokenizer, AutoModelForSequenceClassification
    _TRANSFORMERS_AVAILABLE = True
except ImportError:
    _TRANSFORMERS_AVAILABLE = False
    logger.warning("transformers or torch not installed. Sentiment scoring will use fallback.")

from src.settings import FINBERT_MODEL, PORTFOLIO_TICKERS, ALTERNATIVE_DATA_CONFIG

class SentimentPipeline:
    """
    Scrapes live news headlines for Indian stocks and scores their
    financial sentiment using a fine-tuned BERT model.
    """

    def __init__(self, use_gpu: bool = False):
        self.enabled = ALTERNATIVE_DATA_CONFIG.get("fetch_sentiment", True)
        self.model = None
        self.tokenizer = None
        
        if not self.enabled or not _TRANSFORMERS_AVAILABLE:
            logger.info("Sentiment pipeline disabled or missing dependencies.")
            return

        # Setup device (Auto-fallback to CPU)
        try:
            self.device = torch.device("cuda" if use_gpu and torch.cuda.is_available() else "cpu")
            logger.info(f"Loading FinBERT model ({FINBERT_MODEL}) on {self.device}...")
            self.tokenizer = AutoTokenizer.from_pretrained(FINBERT_MODEL)
            self.model = AutoModelForSequenceClassification.from_pretrained(FINBERT_MODEL).to(self.device)
            # FinBERT labels: 0: positive, 1: negative, 2: neutral
        except Exception as e:
            logger.error(f"Failed to load FinBERT: {e}")
            self.model = None

    def fetch_headlines(self, ticker: str, max_items: int = 5) -> List[str]:
        """Fetch latest news headlines for a ticker via Google News RSS."""
        clean_ticker = ticker.replace(".NS", "")
        # Google News RSS tailored for Indian financial news
        url = f"https://news.google.com/rss/search?q={clean_ticker}+stock+india&hl=en-IN&gl=IN&ceid=IN:en"
        
        try:
            feed = feedparser.parse(url)
            headlines = []
            for entry in feed.entries[:max_items]:
                # Google News sometimes appends source to title separated by " - "
                title = entry.title.rsplit(" - ", 1)[0]
                headlines.append(title)
            return headlines
        except Exception as e:
            logger.warning(f"Failed to fetch headlines for {ticker}: {e}")
            return []

    def score_sentiment(self, headlines: List[str]) -> Dict[str, float]:
        """
        Score a list of headlines using FinBERT.
        Returns aggregated probability distributions.
        """
        if not headlines:
            return {"positive": 0.0, "negative": 0.0, "neutral": 1.0, "composite": 0.0}
            
        if self.model is None or self.tokenizer is None:
            return {"positive": 0.0, "negative": 0.0, "neutral": 1.0, "composite": 0.0}
            
        try:
            inputs = self.tokenizer(headlines, padding=True, truncation=True, return_tensors="pt", max_length=512)
            inputs = {k: v.to(self.device) for k, v in inputs.items()}
            
            with torch.no_grad():
                outputs = self.model(**inputs)
                logits = outputs.logits
                probs = F.softmax(logits, dim=-1).cpu().numpy()
                
            # Average probabilities across all headlines
            avg_probs = np.mean(probs, axis=0)
            
            # FinBERT default label mapping: 0=positive, 1=negative, 2=neutral
            pos = float(avg_probs[0])
            neg = float(avg_probs[1])
            neu = float(avg_probs[2])
            
            # Composite score bounded [-1, 1]
            composite = pos - neg
            
            return {
                "positive": round(pos, 3),
                "negative": round(neg, 3),
                "neutral": round(neu, 3),
                "composite": round(composite, 3)
            }
        except Exception as e:
            logger.error(f"Sentiment scoring failed: {e}")
            return {"positive": 0.0, "negative": 0.0, "neutral": 1.0, "composite": 0.0}

    def get_portfolio_sentiment(self) -> Dict[str, float]:
        """
        Fetch and score sentiment for all portfolio tickers.
        Returns a dict mapping ticker to its composite sentiment score [-1, 1].
        """
        if not self.enabled:
            return {t: 0.0 for t in PORTFOLIO_TICKERS}
            
        logger.info("Starting portfolio sentiment analysis (Scraping + FinBERT)...")
        results = {}
        
        for ticker in PORTFOLIO_TICKERS:
            headlines = self.fetch_headlines(ticker)
            if headlines:
                scores = self.score_sentiment(headlines)
                results[ticker] = scores["composite"]
                logger.info(f"{ticker} Sentiment: {scores['composite']:+.2f} ({len(headlines)} headlines)")
            else:
                results[ticker] = 0.0
                
        return results
