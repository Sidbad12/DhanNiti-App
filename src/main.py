"""
DhanNiti — Application Entry Point
Executes the LangGraph-based state machine pipeline.
"""

import logging
import argparse
from datetime import datetime

from src.settings import validate_settings
from src.graph.pipeline import build_pipeline_graph
from src.logger import setup_logging

setup_logging()
logger = logging.getLogger(__name__)


def main() -> None:
    """Main execution block."""
    parser = argparse.ArgumentParser(description="Run DhanNiti AI Pipeline.")
    parser.add_argument("--date", type=str, help="YYYY-MM-DD to run pipeline as-of. Defaults to today.")
    args = parser.parse_args()

    # 1. Validate configuration
    try:
        validate_settings()
        logger.info("Configuration validated.")
    except Exception as e:
        logger.error(f"Configuration error: {e}")
        return

    # 2. Determine execution date
    run_date = datetime.now()
    if args.date:
        try:
            run_date = datetime.strptime(args.date, "%Y-%m-%d")
        except ValueError:
            logger.error("Invalid date format. Use YYYY-MM-DD.")
            return

    logger.info(f"🚀 Initializing DhanNiti LangGraph Pipeline for {run_date.strftime('%Y-%m-%d')}")

    # 3. Compile Graph
    app = build_pipeline_graph()

    # 4. Initialize State
    initial_state = {
        "date": run_date,
        "raw_price_data": {},
        "alternative_data": {},
        "regime": "unknown",
        "regime_probs": {},
        "features": {},
        "shap_features": {},
        "drift_detected": False,
        "hyperparams_tuned": False,
        "xgboost_signals": {},
        "prophet_forecasts": {},
        "markowitz_weights": {},
        "rl_weights": {},
        "rl_feedback": {},
        "memory_episodes": [],
        "advisory_report": {},
        "validation_attempts": 0
    }

    # 5. Execute Pipeline
    try:
        logger.info("Starting State Machine Execution...")
        
        # Invoke runs the graph synchronously from START to END
        final_state = app.invoke(initial_state)
        
        logger.info("✅ Pipeline completed successfully.")
        
        # Log final outcome summary
        report = final_state.get("advisory_report", {})
        if report and report.get("status") != "error":
            logger.info(f"Final Regime: {final_state.get('regime')}")
            logger.info(f"Final Confidence: {report.get('llm_confidence', 0.0):.2f}")
            logger.info(f"Final Allocations: {report.get('allocations', {})}")
        else:
            logger.warning("Pipeline completed but advisory report generation failed.")
            
    except Exception as e:
        logger.exception(f"❌ Pipeline failed during execution: {e}")

if __name__ == "__main__":
    main()