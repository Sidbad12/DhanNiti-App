"""
DhanNiti — Agent Memory System
Utilizes Qdrant vector database and Mem0 episodic logs with real sentence-transformers.
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime
from typing import Any

import numpy as np
from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance,
    FieldCondition,
    Filter,
    MatchValue,
    PayloadSchemaType,
    PointStruct,
    VectorParams,
)

from src.settings import (
    MEMORY_CONFIG,
    QDRANT_URL,
    QDRANT_API_KEY,
    MEM0_API_KEY
)

logger = logging.getLogger(__name__)

# Lazy load sentence_transformers (SOTA local embeddings)
try:
    from sentence_transformers import SentenceTransformer
    _EMBEDDER = SentenceTransformer("all-MiniLM-L6-v2")
    _ST_AVAILABLE = True
except ImportError:
    _ST_AVAILABLE = False
    _EMBEDDER = None
    logger.warning("sentence-transformers not installed. Embeddings will fail gracefully.")

# Lazy load mem0
try:
    from mem0 import Memory
    _MEM0_AVAILABLE = True
except ImportError:
    _MEM0_AVAILABLE = False
    logger.warning("mem0ai not installed. Structured Mem0 fallback disabled.")


class DhanNitiAgentMemory:
    """Episodic memory store for logging trading decisions and market contexts."""

    def __init__(self, collection_name: str = None, use_qdrant: bool = True) -> None:
        self.collection_name = collection_name or MEMORY_CONFIG.get("qdrant_collection", "dhanniti_episodes")
        self.vector_size = MEMORY_CONFIG.get("qdrant_vector_size", 384)
        self.use_qdrant = use_qdrant
        self.qdrant_client = None
        self.mem0_client = None
        self.local_fallback_path = "models/memory_fallback.json"

        # 1. Initialize Qdrant
        if self.use_qdrant:
            try:
                if QDRANT_URL and QDRANT_API_KEY:
                    self.qdrant_client = QdrantClient(url=QDRANT_URL, api_key=QDRANT_API_KEY)
                else:
                    self.qdrant_client = QdrantClient(path="models/qdrant_db")
                
                collections = self.qdrant_client.get_collections().collections
                exists = any(c.name == self.collection_name for c in collections)
                
                if not exists:
                    self.qdrant_client.create_collection(
                        collection_name=self.collection_name,
                        vectors_config=VectorParams(size=self.vector_size, distance=Distance.COSINE),
                    )
                    logger.info(f"Created new Qdrant memory collection: {self.collection_name}")
                self._ensure_payload_indexes()
            except Exception as e:
                logger.warning(f"Failed to start Qdrant client: {e}. Falling back to JSON local file.")
                self.qdrant_client = None

        # 2. Initialize Mem0
        if _MEM0_AVAILABLE and MEM0_API_KEY:
            try:
                # If the key starts with m0-, it's a Mem0 Cloud key, use MemoryClient
                if MEM0_API_KEY.startswith("m0-"):
                    from mem0 import MemoryClient
                    self.mem0_client = MemoryClient(api_key=MEM0_API_KEY)
                else:
                    os.environ["OPENAI_API_KEY"] = MEM0_API_KEY
                    self.mem0_client = Memory()
                logger.info("Mem0 client initialized successfully.")
            except Exception as e:
                logger.warning(f"Failed to initialize Mem0: {e}")

    def _ensure_payload_indexes(self) -> None:
        """Keyword index on regime for filtered scroll (required on Qdrant Cloud)."""
        if not self.qdrant_client:
            return
        try:
            self.qdrant_client.create_payload_index(
                collection_name=self.collection_name,
                field_name="regime",
                field_schema=PayloadSchemaType.KEYWORD,
            )
            logger.info("Qdrant payload index ensured for field 'regime'")
        except Exception as exc:
            # Already exists or cloud API variation
            logger.debug("Regime payload index: %s", exc)

    def _get_embedding(self, text: str) -> list[float]:
        """Generate actual 384-dim semantic embeddings using all-MiniLM-L6-v2."""
        if not _ST_AVAILABLE or _EMBEDDER is None:
            # Fallback array if library is completely missing to prevent hard crashes
            return [0.0] * self.vector_size
            
        vector = _EMBEDDER.encode(text)
        return vector.tolist()

    def build_dynamic_query(self, signals: dict[str, Any], regime: str) -> str:
        """
        Construct a meaningful semantic query string from top BUY signals + detected regime.
        """
        top_buys = [t for t, s in signals.items() if s.get("action") == "BUY"]
        buys_str = " ".join(top_buys) if top_buys else "no strong buys"
        return f"NSE regime={regime} bullish tickers: {buys_str}"

    def log_episode(
        self,
        date: datetime,
        market_summary: str,
        ml_predictions: dict[str, float],
        weights_allocated: dict[str, float],
        reward: float,
        regime: str = "unknown"
    ) -> None:
        """
        Store a daily episodic memory of the agent's actions and market context.
        """
        date_str = date.strftime("%Y-%m-%d") if isinstance(date, datetime) else str(date)
        
        episode_data = {
            "date": date_str,
            "market_summary": market_summary,
            "regime": regime,
            "ml_predictions": ml_predictions,
            "weights_allocated": weights_allocated,
            "reward": float(reward),
            "timestamp": datetime.now().isoformat()
        }

        # 1. Log to Qdrant Vector Store
        if self.qdrant_client:
            try:
                text_to_embed = f"Date: {date_str}. Regime: {regime}. Market: {market_summary}. Reward: {reward:.4%}"
                vector = self._get_embedding(text_to_embed)
                
                point_id = hash(date_str) & 0xffffffffffffffff
                
                self.qdrant_client.upsert(
                    collection_name=self.collection_name,
                    points=[
                        PointStruct(
                            id=point_id,
                            vector=vector,
                            payload=episode_data
                        )
                    ]
                )
                logger.info(f"Episode logged in Qdrant Vector memory for {date_str}")
            except Exception as e:
                logger.error(f"Error saving episode to Qdrant: {e}")
                self._save_to_local_fallback(episode_data)
        else:
            self._save_to_local_fallback(episode_data)

        # 2. Log to Mem0 (parallel episodic store)
        if self.mem0_client:
            try:
                mem0_text = f"On {date_str}, during a '{regime}' regime, the portfolio achieved a reward of {reward:.4%}. Allocations: {weights_allocated}."
                self.mem0_client.add(mem0_text, user_id="dhanniti_agent")
            except Exception as e:
                logger.warning(f"Failed to log to Mem0: {e}")

    def _save_to_local_fallback(self, episode_data: dict[str, Any]) -> None:
        """Save episode log to a flat JSON file if Qdrant isn't working."""
        try:
            episodes = []
            if os.path.exists(self.local_fallback_path):
                with open(self.local_fallback_path, "r") as f:
                    try:
                        episodes = json.load(f)
                    except json.JSONDecodeError:
                        episodes = []
            
            # Upsert by date
            episodes = [ep for ep in episodes if ep.get("date") != episode_data["date"]]
            episodes.append(episode_data)

            os.makedirs(os.path.dirname(self.local_fallback_path), exist_ok=True)
            with open(self.local_fallback_path, "w") as f:
                json.dump(episodes, f, indent=4)
                
            logger.info(f"Episode logged in local JSON fallback for {episode_data['date']}")
        except Exception as e:
            logger.error(f"Failed to log episode in local fallback file: {e}")

    def query_similar_episodes(self, query_text: str, limit: int = 3) -> list[dict[str, Any]]:
        """Query vector memory for past episodes sharing a similar market context."""
        if self.qdrant_client:
            try:
                vector = self._get_embedding(query_text)
                response = self.qdrant_client.query_points(
                    collection_name=self.collection_name,
                    query=vector,
                    limit=limit,
                    with_payload=True,
                )
                return [
                    point.payload
                    for point in response.points
                    if point.payload is not None
                ]
            except Exception as e:
                logger.error(f"Failed to query Qdrant: {e}")
                
        # JSON fallback query
        if os.path.exists(self.local_fallback_path):
            try:
                with open(self.local_fallback_path, "r") as f:
                    episodes = json.load(f)
                
                matches = []
                keywords = query_text.lower().split()
                for ep in episodes:
                    summary = ep.get("market_summary", "").lower()
                    score = sum(1 for kw in keywords if kw in summary)
                    if score > 0:
                        matches.append((score, ep))
                
                matches.sort(key=lambda x: x[0], reverse=True)
                return [m[1] for m in matches[:limit]]
            except Exception as e:
                logger.error(f"Failed to query fallback memory: {e}")
                
        return []

    def get_regime_filtered_episodes(self, regime: str, limit: int = 3) -> list[dict[str, Any]]:
        """Query memory but only return episodes that match the current regime label."""
        if self.qdrant_client:
            try:
                results, _ = self.qdrant_client.scroll(
                    collection_name=self.collection_name,
                    scroll_filter=Filter(
                        must=[
                            FieldCondition(
                                key="regime",
                                match=MatchValue(value=regime)
                            )
                        ]
                    ),
                    limit=limit,
                    with_payload=True
                )
                return [hit.payload for hit in results]
            except Exception as e:
                logger.error(f"Failed to scroll Qdrant for regime: {e}")

        # JSON fallback query
        if os.path.exists(self.local_fallback_path):
            try:
                with open(self.local_fallback_path, "r") as f:
                    episodes = json.load(f)
                
                filtered = [ep for ep in episodes if ep.get("regime") == regime]
                # Return newest first
                return sorted(filtered, key=lambda x: x.get("date", ""), reverse=True)[:limit]
            except Exception as e:
                logger.error(f"Failed to filter fallback memory by regime: {e}")

        return []
