r"""
DhanNiti — Auto-runner: trains then evaluates in one shot.
Run this instead of train + evaluate separately.

Usage:
    .venv\Scripts\python.exe scripts/run_full_pipeline.py
"""
import os
import sys
import time
import logging
import subprocess

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

PYTHON = sys.executable
MODEL_PATH = "models/ppo_dhanniti.zip"


def run(script: str, label: str):
    logger.info("=" * 60)
    logger.info(f"RUNNING: {label}")
    logger.info("=" * 60)
    result = subprocess.run([PYTHON, script], check=False)
    if result.returncode != 0:
        logger.error(f"{label} exited with code {result.returncode}. Check logs above.")
        sys.exit(result.returncode)
    logger.info(f"{label} completed successfully.")


def wait_for_model(timeout_seconds: int = 7200):
    """Poll until ppo_dhanniti.zip appears (training done) or timeout."""
    logger.info(f"Waiting for model checkpoint at: {MODEL_PATH}")
    start = time.time()
    while not os.path.exists(MODEL_PATH):
        elapsed = int(time.time() - start)
        if elapsed > timeout_seconds:
            logger.error("Timed out waiting for model checkpoint!")
            sys.exit(1)
        if elapsed % 30 == 0:
            logger.info(f"  Still waiting... ({elapsed}s elapsed)")
        time.sleep(5)
    # Extra wait to ensure the file is fully written
    time.sleep(3)
    size_mb = os.path.getsize(MODEL_PATH) / 1024 / 1024
    logger.info(f"Model checkpoint found! ({size_mb:.1f} MB) — proceeding to evaluation.")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--skip-train", action="store_true",
                        help="Skip training and go straight to evaluation (model must already exist)")
    args = parser.parse_args()

    if not args.skip_train:
        from src.settings import RL_CONFIG
        steps = RL_CONFIG.get("total_timesteps", 500000)
        run("scripts/train_rl_agent.py", f"PPO Training ({steps} steps)")
    else:
        logger.info("--skip-train flag set. Skipping training, waiting for existing checkpoint...")
        wait_for_model()

    run("scripts/evaluate_rl_agent.py", "Comprehensive Evaluation Suite")

    logger.info("")
    logger.info("=" * 60)
    logger.info("FULL PIPELINE COMPLETE")
    logger.info("  Charts   -> artifacts/charts/")
    logger.info("  Report   -> artifacts/rl_evaluation_report.md")
    logger.info("  DagsHub  -> https://dagshub.com/siddharth.badjate1211/DhanNiti.mlflow")
    logger.info("=" * 60)
