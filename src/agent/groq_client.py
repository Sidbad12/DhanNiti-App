"""
DhanNiti — Groq LLM Client
Thin wrapper around groq-python SDK, upgraded with instructor and Pydantic.

L4 (Groq) produces narrative only — portfolio weights are owned by PPO (L3).
"""

from __future__ import annotations

import logging
from typing import Any, Literal, Dict, List
from pydantic import BaseModel, Field

from src.settings import GROQ_API_KEY, GROQ_MAX_TOKENS, GROQ_MODEL, GROQ_TEMPERATURE

logger = logging.getLogger(__name__)

try:
    from groq import Groq
    import instructor
    _GROQ_AVAILABLE = True
except ImportError:
    _GROQ_AVAILABLE = False
    logger.warning("groq or instructor package not installed.")


# ─────────────────────────────────────────────────────────────
# SCHEMA (narrative only — no weights)
# ─────────────────────────────────────────────────────────────

class MemoryCitation(BaseModel):
    date: str = Field(description="YYYY-MM-DD")
    similarity: str = Field(description="why this episode is relevant")
    outcome: str = Field(description="what happened after")


class AdvisoryNarrative(BaseModel):
    reasoning: str = Field(
        description="2-4 sentence explanation of the PPO allocation and key risks"
    )
    risk_flags: List[str] = Field(
        description="list of risk warnings, empty list if none"
    )
    regime_commentary: Literal[
        "bull_trending", "bear_trending", "high_volatility", "range_bound", "neutral"
    ] = Field(
        description="Your read on current regime given the signals (commentary only)"
    )
    confidence: float = Field(
        description="Confidence in your narrative synthesis (0.0-1.0), not in PPO weights",
        ge=0.0,
        le=1.0,
    )
    stock_notes: Dict[str, str] = Field(
        description="brief per-stock rationale tied to the fixed PPO weights"
    )
    memory_citations: List[MemoryCitation] = Field(
        description="Only cite memory episodes that genuinely influenced your commentary"
    )


# ─────────────────────────────────────────────────────────────
# SYSTEM PROMPT
# ─────────────────────────────────────────────────────────────

ADVISOR_SYSTEM_PROMPT = """
You are DhanNiti, an AI portfolio advisor for NSE India (National Stock Exchange).

Your role is NARRATIVE ONLY. You do NOT choose or output portfolio weights.
The PPO reinforcement-learning agent has already produced the authoritative allocation.
Your job is to explain that allocation and surface risks.

You receive:
- Structured ML signals (XGBoost probabilities + SHAP features)
- Prophet price forecasts
- Markowitz and PPO (RL) weight suggestions — the PPO weights are final
- Similar past market episodes from episodic memory (Qdrant)
- Alternative Data (FII/DII, PCR, India VIX, Sentiment)

Rules:
1. Do NOT output portfolio weights or allocations — they are fixed by PPO
2. Explain the PPO allocation logic using the signals provided
3. Only cite memory episodes that genuinely influenced your commentary
4. Flag risk if XGBoost confidence < 0.60 for a BUY recommendation
5. If signals conflict with memory or alternative data, explain which you trusted and why
"""


# ─────────────────────────────────────────────────────────────
# CLIENT
# ─────────────────────────────────────────────────────────────

class GroqAdvisorClient:
    """
    Wraps Groq SDK using instructor for type-safe DhanNiti narrative calls.
    Falls back when Groq is unavailable (confidence 0.0, no weight suggestions).
    """

    def __init__(self) -> None:
        self._client = None
        if _GROQ_AVAILABLE and GROQ_API_KEY:
            import httpx
            try:
                self._client = instructor.from_groq(Groq(api_key=GROQ_API_KEY, http_client=httpx.Client()), mode=instructor.Mode.TOOLS)
                self.model = GROQ_MODEL
                logger.info(f"Groq + Instructor client initialised (model={self.model})")
            except Exception as exc:
                logger.warning(f"Groq client init failed: {exc}")

    def call(self, user_prompt: str) -> dict[str, Any]:
        """
        Call Groq LLM with the advisor system prompt + user prompt using Instructor.
        """
        if self._client is None:
            logger.warning("Groq unavailable — returning fallback response.")
            return self._fallback_response()

        try:
            response_obj: AdvisoryNarrative = self._client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": ADVISOR_SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt},
                ],
                response_model=AdvisoryNarrative,
                max_retries=2,
                max_tokens=GROQ_MAX_TOKENS,
                temperature=GROQ_TEMPERATURE,
            )
            data = response_obj.model_dump()
            # Back-compat keys for advisor layer
            data["regime"] = data.get("regime_commentary", "neutral")
            return data

        except Exception as exc:
            logger.error(f"Groq API call or validation failed: {exc}", exc_info=True)
            return self._fallback_response()

    @staticmethod
    def _fallback_response() -> dict[str, Any]:
        """Fallback when Groq is unavailable — narrative unavailable, confidence 0."""
        return {
            "reasoning": "Groq LLM unavailable. Portfolio weights are unchanged (PPO). No narrative synthesis.",
            "stock_notes": {},
            "risk_flags": ["LLM synthesis unavailable"],
            "memory_citations": [],
            "confidence": 0.0,
            "regime_commentary": "neutral",
            "regime": "neutral",
        }
