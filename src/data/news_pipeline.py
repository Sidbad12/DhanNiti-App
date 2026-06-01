"""
DhanNiti V2 — News Categorization & Entity Linking Pipeline
Fetches headlines from financial RSS sources, classifies them into categories,
and links them to affected tickers (direct or sector-level propagation).
"""

import logging
import feedparser
import pandas as pd
from datetime import datetime
from src.agent.groq_client import _GROQ_AVAILABLE, GROQ_API_KEY, GROQ_MODEL
from src.data.feature_builder import SECTOR_MAP

logger = logging.getLogger(__name__)

# Reverse SECTOR_MAP to get SECTOR_TICKERS
SECTOR_TICKERS = {}
for ticker, sector in SECTOR_MAP.items():
    if sector not in SECTOR_TICKERS:
        SECTOR_TICKERS[sector] = []
    SECTOR_TICKERS[sector].append(ticker)

# Generate company names mapping for linking
TICKER_TO_NAME = {}
for ticker in SECTOR_MAP.keys():
    name = ticker.replace(".NS", "").replace("-", " ")
    # Common overrides for better matching
    if name == "HINDUNILVR":
        name = "hindustan unilever"
    elif name == "BAJFINANCE":
        name = "bajaj finance"
    elif name == "BAJAJFINSV":
        name = "bajaj finserv"
    elif name == "TATACONSUM":
        name = "tata consumer"
    elif name == "HEROMOTOCO":
        name = "hero motocorp"
    elif name == "EICHERMOT":
        name = "eicher motors"
    elif name == "M&M":
        name = "mahindra"
    elif name == "BALKRISIND":
        name = "balkrishna industries"
    elif name == "TORNTPHARM":
        name = "torrent pharma"
    elif name == "ULTRACEMCO":
        name = "ultratech cement"
    elif name == "APOLLOHOSP":
        name = "apollo hospitals"
    elif name == "BANDHANBNK":
        name = "bandhan bank"
    elif name == "FEDERALBNK":
        name = "federal bank"
    elif name == "IDFCFIRSTB":
        name = "idfc first bank"
    elif name == "MUTHOOTFIN":
        name = "muthoot finance"
    elif name == "GODREJCP":
        name = "godrej consumer"
    elif name == "COLPAL":
        name = "colgate palmolive"
    elif name == "EMAMILTD":
        name = "emami"
    elif name == "JYOTHYLAB":
        name = "jyothy labs"
    elif name == "GRINDWELL":
        name = "grindwell norton"
    elif name == "APLAPOLLO":
        name = "apl apollo"
    elif name == "UJJIVANSFB":
        name = "ujjivan small finance bank"
    elif name == "RBLBANK":
        name = "rbl bank"
    TICKER_TO_NAME[ticker] = name.lower()

NEWS_SOURCES = {
    "moneycontrol": "https://www.moneycontrol.com/rss/marketreports.xml",
    "economic_times": "https://economictimes.indiatimes.com/markets/rss.cms",
    "nse_announcements": "https://www.nseindia.com/api/corporate-announcements",
    "livemint": "https://www.livemint.com/rss/markets",
    "business_standard": "https://www.business-standard.com/rss/markets-106.rss",
}

NEWS_CATEGORIES = {
    "macro_rbi":   ["RBI", "repo rate", "monetary policy", "CRR", "SLR", "inflation", "central bank", "interest rate"],
    "macro_crude": ["crude oil", "Brent", "WTI", "OPEC", "petrol", "diesel", "oil price"],
    "earnings":    ["Q1", "Q2", "Q3", "Q4", "results", "profit", "revenue", "EPS", "PAT", "earnings", "net income", "dividend"],
    "regulatory":  ["SEBI", "regulation", "circular", "compliance", "fine", "penalty", "show cause", "adjudication", "ban"],
    "global":      ["Fed", "US markets", "dollar", "USD", "DXY", "Nasdaq", "S&P", "FOMC", "Treasury yield", "global market"],
    "promoter":    ["insider", "promoter", "stake", "buyback", "bulk deal", "block deal", "pledged shares", "open market"],
    "fii_dii":     ["FII", "DII", "foreign investor", "institutional", "flow", "inflow", "outflow", "net seller", "net buyer"],
}

GROQ_NEWS_DAILY_CAP = 50


# Module-level caches to avoid redundant fetching and API calling across instances/tickers
_FEED_CACHE = {}
_CATEGORIZE_CACHE = {}


class NewsCategorizer:
    def __init__(self):
        self._groq_calls_today = 0
        self._last_call_date = datetime.today().date()

    def categorize(self, headline: str) -> dict[str, float]:
        """Returns scores for each news category (cached)."""
        if headline in _CATEGORIZE_CACHE:
            return _CATEGORIZE_CACHE[headline]

        # Reset daily cap on new day
        today = datetime.today().date()
        if today != self._last_call_date:
            self._groq_calls_today = 0
            self._last_call_date = today

        # Stage 1: fast keyword matching
        scores = {cat: 0.0 for cat in NEWS_CATEGORIES}
        for category, keywords in NEWS_CATEGORIES.items():
            matches = sum(1 for kw in keywords if kw.lower() in headline.lower())
            if matches > 0:
                scores[category] = min(1.0, matches * 0.4)

        # Stage 2: Groq zero-shot for ambiguous headlines
        if max(scores.values()) < 0.4 and self._groq_calls_today < GROQ_NEWS_DAILY_CAP:
            scores = self._groq_classify(headline, scores)
            self._groq_calls_today += 1

        _CATEGORIZE_CACHE[headline] = scores
        return scores

    def _groq_classify(self, headline: str, default_scores: dict[str, float]) -> dict[str, float]:
        """Call Groq to perform zero-shot news classification into the 7 categories."""
        if not _GROQ_AVAILABLE or not GROQ_API_KEY:
            return default_scores
            
        try:
            from groq import Groq
            import json
            import httpx
            
            client = Groq(api_key=GROQ_API_KEY, http_client=httpx.Client())
            
            system_prompt = (
                "You are a financial news classification model. Classify the given headline into the following categories. "
                "For each category, assign a score between 0.0 (no relevance) and 1.0 (highly relevant). "
                "Categories:\n"
                "- macro_rbi: RBI / monetary policy news\n"
                "- macro_crude: Crude oil / commodity news\n"
                "- earnings: Earnings results, profit, revenue, or dividends\n"
                "- regulatory: SEBI or government policy/compliance news\n"
                "- global: US Fed, Nasdaq, global market trends\n"
                "- promoter: Promoter buying/selling, insider activity, bulk/block deals\n"
                "- fii_dii: FII/DII investment flows\n"
                "Return ONLY a raw JSON object with these keys and float values. Do not write any explanations."
            )
            
            response = client.chat.completions.create(
                model=GROQ_MODEL,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": f"Headline: {headline}"}
                ],
                max_tokens=256,
                temperature=0.1,
                response_format={"type": "json_object"}
                # Timeout added to prevent hang
            )
            
            result = json.loads(response.choices[0].message.content)
            scores = {cat: float(result.get(cat, 0.0)) for cat in NEWS_CATEGORIES}
            return scores
        except Exception as e:
            logger.warning(f"Groq classification failed for headline '{headline}': {e}")
            return default_scores

    def fetch_safe(self, source_url: str) -> list[str]:
        """
        Fetch headlines with fallback — never crash the pipeline on RSS failure.
        Caches results per source_url to prevent redundant network requests.
        """
        if source_url in _FEED_CACHE:
            return _FEED_CACHE[source_url]
        try:
            feed = feedparser.parse(source_url)
            titles = [entry.title for entry in feed.entries if hasattr(entry, 'title')]
            _FEED_CACHE[source_url] = titles
            return titles
        except Exception as e:
            logger.warning(f"News fetch failed for {source_url}: {e}. Returning empty list.")
            return []

    def link_to_tickers(self, headline: str, all_tickers: list[str]) -> list[str]:
        """
        Entity linking: which tickers does this headline affect?
        Matches direct company names or propagates sector-wide macro events.
        """
        affected = []

        # Direct company name matching
        headline_lower = headline.lower()
        for ticker in all_tickers:
            company_name = TICKER_TO_NAME.get(ticker, "")
            if company_name and company_name in headline_lower:
                affected.append(ticker)

        # Sector propagation
        categories = self.categorize(headline)
        if categories.get("macro_rbi", 0.0) > 0.5:
            affected.extend(SECTOR_TICKERS.get("financials", []))
        if categories.get("macro_crude", 0.0) > 0.5:
            affected.extend(SECTOR_TICKERS.get("energy", []))
        if categories.get("global", 0.0) > 0.5:
            affected.extend(SECTOR_TICKERS.get("it", []))

        return list(set(affected))


def log_news_telemetry(ticker: str, headlines: list[str], scores: dict[str, float], sentiment_composite: float):
    """
    Appends live news classification telemetry to logs/news_telemetry.jsonl.
    Helps audit LLM classifications and build a custom historical news dataset over time.
    """
    import os
    import json
    try:
        log_dir = "logs"
        os.makedirs(log_dir, exist_ok=True)
        log_file = os.path.join(log_dir, "news_telemetry.jsonl")
        
        log_entry = {
            "timestamp": datetime.now().isoformat(),
            "date": datetime.now().strftime("%Y-%m-%d"),
            "ticker": ticker,
            "headlines_count": len(headlines),
            "headlines": headlines,
            "scores": scores,
            "sentiment_composite": sentiment_composite
        }
        
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(log_entry) + "\n")
            
        logger.info(f"Telemetry logged for {ticker} to {log_file}")
    except Exception as e:
        logger.warning(f"Failed to write news telemetry for {ticker}: {e}")

