"""
DhanNiti — Supabase Database Client
Handles saving and retrieving ML predictions, portfolio weights,
and advisory reports from the Supabase Postgres instance.
"""

import logging
from typing import Dict, Any, Optional

from supabase import create_client, Client
from src.settings import SUPABASE_URL, SUPABASE_KEY, SUPABASE_TABLE_NAME

logger = logging.getLogger(__name__)

class DhanNitiDatabase:
    """Connection to Supabase. Re-instantiated per request to avoid httpx thread deadlocks."""

    def __init__(self):
        self.client: Optional[Client] = None
        if SUPABASE_URL and SUPABASE_KEY:
            try:
                self.client = create_client(SUPABASE_URL, SUPABASE_KEY)
                # logger.info("Supabase client initialized.")
            except Exception as e:
                logger.error(f"Failed to initialize Supabase client: {e}")
        else:
            logger.warning("SUPABASE_URL or SUPABASE_KEY missing.")

    def upsert_advisory_report(self, report: Dict[str, Any]) -> bool:
        """
        Saves the complete LangGraph pipeline output to Supabase.
        Upserts based on the report_date.
        """
        if self.client is None:
            logger.error(
                "Supabase not configured — advisory report not saved. "
                "Set SUPABASE_URL and SUPABASE_KEY in .env at repo root."
            )
            return False
            
        try:
            # Match actual columns in 'advisory_reports':
            # report_date, reasoning, regime, llm_confidence, risk_flags, memory_citations, expected_return, full_report
            data = {
                "report_date": report.get("date"),
                "regime": report.get("regime", "neutral"),
                "expected_return": report.get("expected_return", 0.0),
                "reasoning": report.get("reasoning", ""),
                "risk_flags": report.get("risk_flags", []),
                "llm_confidence": report.get("llm_confidence", 0.0),
                "memory_citations": report.get("memory_citations", []),
                "full_report": report
            }
            
            # Using upsert requires a unique constraint on 'report_date' in Postgres
            self.client.table("advisory_reports").upsert(data, on_conflict="report_date").execute()
            logger.info(f"Successfully upserted report for {data['report_date']} to Supabase.")
            return True
        except Exception as e:
            logger.error(f"Failed to upsert report to Supabase: {e}")
            return False

    def upsert_predictions(self, predictions: list[Dict[str, Any]]) -> bool:
        """
        Saves individual ticker-level predictions to the portfolio_predictions table.
        """
        if self.client is None:
            logger.error(
                "Supabase not configured — %d predictions not saved.",
                len(predictions),
            )
            return False
            
        try:
            # Format predictions to match columns in 'portfolio_predictions'
            # as_of_date, ticker, predicted_price, predicted_return, actual_prices_last_month, portfolio_weight
            self.client.table("portfolio_predictions").upsert(predictions, on_conflict="as_of_date,ticker").execute()
            logger.info(f"Successfully upserted {len(predictions)} predictions to Supabase.")
            return True
        except Exception as e:
            logger.error(f"Failed to upsert predictions to Supabase: {e}")
            return False

    def get_latest_report(self) -> Dict[str, Any]:
        """
        Fetches the most recent advisory report from the advisory_reports table.
        """
        if self.client is None:
            return {}

        try:
            response = (
                self.client.table("advisory_reports")
                .select("full_report")
                .order("report_date", desc=True)
                .limit(1)
                .execute()
            )

            if response.data:
                return response.data[0].get("full_report", {})
            return {}
        except Exception as e:
            logger.error(f"Failed to fetch latest report from Supabase: {e}")
            return {}

    def get_latest_v1_recommend_report(self) -> Dict[str, Any]:
        """
        Newest V1 portfolio snapshot (v1_ppo_recommend or v1_ppo_groq).
        Picks the row with latest full_report.generated_at when multiple exist.
        """
        if self.client is None:
            return {}

        try:
            response = (
                self.client.table("advisory_reports")
                .select("full_report")
                .order("report_date", desc=True)
                .limit(20)
                .execute()
            )
            rows = response.data or []
            fallback: Dict[str, Any] = {}
            candidates: list[Dict[str, Any]] = []
            for row in rows:
                report = row.get("full_report") or {}
                if not fallback and report:
                    fallback = report
                source = report.get("source", "")
                if source in ("v1_ppo_recommend", "v1_ppo_groq") or report.get("model_version") == "v1":
                    candidates.append(report)
            if candidates:
                return max(candidates, key=lambda r: r.get("generated_at", ""))
            return fallback
        except Exception as e:
            logger.error(f"Failed to fetch latest V1 recommend from Supabase: {e}")
            return {}

    def get_latest_v2_recommend_report(self) -> Dict[str, Any]:
        """
        Newest V2 portfolio snapshot (v2_sac_recommend).
        Picks the row with latest full_report.generated_at when multiple exist.
        """
        if self.client is None:
            return {}

        try:
            response = (
                self.client.table("advisory_reports")
                .select("full_report")
                .order("report_date", desc=True)
                .limit(20)
                .execute()
            )
            rows = response.data or []
            fallback: Dict[str, Any] = {}
            candidates: list[Dict[str, Any]] = []
            for row in rows:
                report = row.get("full_report") or {}
                if not fallback and report:
                    fallback = report
                source = report.get("source", "")
                if source == "v2_sac_recommend" or report.get("model_version") == "v2":
                    candidates.append(report)
            if candidates:
                return max(candidates, key=lambda r: r.get("generated_at", ""))
            return fallback
        except Exception as e:
            logger.error(f"Failed to fetch latest V2 recommend from Supabase: {e}")
            return {}

    def get_all_holdings(self) -> list[Dict[str, Any]]:
        """
        Fetch all user portfolio holdings from the holdings table.
        """
        if self.client is None:
            return []
        try:
            response = self.client.table("holdings").select("*").order("ticker").execute()
            return response.data or []
        except Exception as e:
            logger.error(f"Failed to fetch holdings: {e}")
            return []

    def add_holding(self, holding: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Add a new holding row to the holdings table.
        """
        if self.client is None:
            return None
        try:
            response = self.client.table("holdings").insert(holding).execute()
            if response.data:
                return response.data[0]
            return None
        except Exception as e:
            logger.error(f"Failed to add holding: {e}")
            raise e

    def update_holding(self, id: str, updates: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Update an existing holding by id.
        """
        if self.client is None:
            return None
        try:
            response = self.client.table("holdings").update(updates).eq("id", id).execute()
            if response.data:
                return response.data[0]
            return None
        except Exception as e:
            logger.error(f"Failed to update holding {id}: {e}")
            raise e

    def delete_holding(self, id: str) -> Optional[Dict[str, Any]]:
        """
        Delete a holding by id.
        """
        if self.client is None:
            return None
        try:
            response = self.client.table("holdings").delete().eq("id", id).execute()
            if response.data:
                return response.data[0]
            return None
        except Exception as e:
            logger.error(f"Failed to delete holding {id}: {e}")
            raise e

    def get_historical_candles(self, ticker: str, start_date: str, end_date: str) -> list[Dict[str, Any]]:
        """Fetch historical daily candles for a ticker within a date range."""
        if self.client is None:
            return []
        try:
            response = (
                self.client.table("historical_candles")
                .select("date,open,high,low,close,volume")
                .eq("ticker", ticker)
                .gte("date", start_date)
                .lte("date", end_date)
                .order("date", desc=False)
                .execute()
            )
            return response.data or []
        except Exception as e:
            logger.error(f"Failed to fetch historical candles for {ticker}: {e}")
            return []

    def upsert_historical_candles(self, candles: list[Dict[str, Any]]) -> bool:
        """Upsert raw daily candles to historical_candles table."""
        if self.client is None or not candles:
            return False
        try:
            self.client.table("historical_candles").upsert(candles, on_conflict="ticker,date").execute()
            return True
        except Exception as e:
            logger.error(f"Failed to upsert historical candles: {e}")
            return False
