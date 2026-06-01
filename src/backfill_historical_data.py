"""
Backfill script to populate Supabase with historical predictions
This will run the optimization for the last N days to build historical data
"""
import logging
from datetime import datetime, timedelta
from dotenv import load_dotenv
import pandas as pd

load_dotenv()

from src.graph.pipeline import build_pipeline_graph
from src.settings import PORTFOLIO_TICKERS
from src.logger import setup_logging

setup_logging()
logger = logging.getLogger(__name__)


def backfill_historical_predictions(days_back: int = 10):
    """
    Run optimization for the last N days to build historical data
    
    Args:
        days_back: Number of days to backfill (default: 10)
    """
    logger.info(f"Starting backfill for last {days_back} days...")
    logger.info(f"Portfolio tickers: {PORTFOLIO_TICKERS}")
    
    # Get market days (weekdays only)
    end_date = datetime.now()
    dates_to_process = []
    
    current_date = end_date
    while len(dates_to_process) < days_back:
        # Only include weekdays (Monday=0 to Friday=4)
        if current_date.weekday() < 5:
            dates_to_process.append(current_date)
        current_date -= timedelta(days=1)
    
    # Reverse to process oldest to newest
    dates_to_process.reverse()
    
    logger.info(f"Will process {len(dates_to_process)} trading days")
    
    successful_runs = 0
    failed_runs = 0
    
    # Compile graph
    app = build_pipeline_graph()
    
    for i, target_date in enumerate(dates_to_process, 1):
        date_str = target_date.strftime("%Y-%m-%d")
        
        logger.info(f"\n{'='*70}")
        logger.info(f"Processing day {i}/{len(dates_to_process)}: {date_str}")
        logger.info(f"{'='*70}")
        
        try:
            initial_state = {
                "date": target_date,
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
            
            logger.info("Invoking LangGraph pipeline...")
            app.invoke(initial_state)
            successful_runs += 1
            
        except Exception as e:
            logger.error(f"Error processing {date_str}: {e}")
            failed_runs += 1
            continue
    
    logger.info(f"\n{'='*70}")
    logger.info("BACKFILL SUMMARY")
    logger.info(f"{'='*70}")
    logger.info(f"Total days attempted: {len(dates_to_process)}")
    logger.info(f"✅ Successful: {successful_runs}")
    logger.info(f"❌ Failed: {failed_runs}")
    logger.info(f"Success rate: {(successful_runs/len(dates_to_process)*100):.1f}%")
    logger.info(f"{'='*70}\n")
    
    if successful_runs > 0:
        logger.info("🎉 Backfill complete! You can now view trends in the dashboard:")
        logger.info("   poetry run streamlit run src/streamlit_app.py")
    else:
        logger.error("⚠️  No data was successfully saved. Check errors above.")


def main():
    """Main entry point"""
    import argparse
    
    parser = argparse.ArgumentParser(description="Backfill historical predictions")
    parser.add_argument(
        "--days",
        type=int,
        default=10,
        help="Number of days to backfill (default: 10)"
    )
    
    args = parser.parse_args()

    print(f"\n{'='*70}")
    print("BACKFILL HISTORICAL PREDICTIONS")
    print(f"{'='*70}")
    print(f"This will run portfolio optimization for the last {args.days} trading days.")
    print(f"Tickers: {', '.join(PORTFOLIO_TICKERS)}")
    print(f"\nThis may take several minutes...")
    print(f"{'='*70}\n")
    
    response = input("Continue? (y/n): ")
    if response.lower() != 'y':
        print("Cancelled.")
        return
    
    backfill_historical_predictions(days_back=args.days)


if __name__ == "__main__":
    main()