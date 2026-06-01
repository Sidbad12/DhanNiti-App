"""
DhanNiti — Agent Tools
Token-efficient codebase and signal search for the advisor agent.
Uses rgx (https://github.com/ParthAeron/rgx) when available,
falls back to ripgrep (rg), then Python glob.

# fm-key: src/agent/tools.py
# fm-value: Search pipeline that implements token-efficient codebase query tools. Interfaces with rgx and raw ripgrep.
# fm-scope: file
# fm-links: src/settings.py
"""

from __future__ import annotations

import glob
import json
import logging
import subprocess
from pathlib import Path
from typing import Any

from src.settings import SEARCH_CONFIG

logger = logging.getLogger(__name__)

# Token budget defaults (keep agent calls cheap)
_DEFAULT_BUDGET = SEARCH_CONFIG["default_budget"]
_SIGNAL_BUDGET  = SEARCH_CONFIG["signal_budget"]
_CONFIG_BUDGET  = SEARCH_CONFIG["config_budget"]
_COLLAPSE_THRESHOLD = SEARCH_CONFIG["collapse_threshold"]


# ─────────────────────────────────────────────────────────────
# INTERNAL RUNNER
# ─────────────────────────────────────────────────────────────

def _run_rgx(
    pattern: str,
    path: str,
    token_budget: int,
) -> dict[str, Any]:
    """
    Try rgx → rg → Python fallback in order.
    Always returns a dict with keys: matches, truncated, tool_used.
    """

    # ── 1. Try rgx ────────────────────────────────────────────
    try:
        result = subprocess.run(
            [
                "rgx", pattern, path,
                "--max-tokens", str(token_budget),  # hard token budget cap
                "--collapse-threshold", str(_COLLAPSE_THRESHOLD),  # collapse noisy dir prefixes
            ],
            capture_output=True, text=True, timeout=15,
        )
        if result.returncode == 0 and result.stdout.strip():
            data = json.loads(result.stdout)
            data["tool_used"] = "rgx"
            return data
    except FileNotFoundError:
        pass  # rgx not installed
    except Exception as exc:
        logger.debug(f"rgx failed: {exc}")

    # ── 2. Try ripgrep (rg) ───────────────────────────────────
    try:
        result = subprocess.run(
            ["rg", pattern, path, "--json", "-m", "30"],
            capture_output=True, text=True, timeout=10,
        )
        lines = [
            l for l in result.stdout.strip().split("\n")
            if l and '"type":"match"' in l
        ]
        # Crude token budget: 4 chars ≈ 1 token
        budget_chars = token_budget * 4
        kept, total_chars = [], 0
        for line in lines:
            if total_chars + len(line) > budget_chars:
                break
            kept.append(line)
            total_chars += len(line)

        return {
            "matches"  : kept,
            "truncated": len(kept) < len(lines),
            "tool_used": "rg",
        }
    except FileNotFoundError:
        pass  # rg not installed
    except Exception as exc:
        logger.debug(f"rg failed: {exc}")

    # ── 3. Python glob fallback ───────────────────────────────
    try:
        import re
        compiled  = re.compile(pattern, re.IGNORECASE)
        matches   = []
        py_files  = glob.glob(f"{path}/**/*.py", recursive=True)

        for fp in py_files[:50]:
            try:
                text = Path(fp).read_text(encoding="utf-8", errors="ignore")
                for i, line in enumerate(text.splitlines(), 1):
                    if compiled.search(line):
                        matches.append(f"{fp}:{i}: {line.strip()}")
                        if len(matches) >= 100:
                            break
            except Exception:
                continue
            if len(matches) >= 100:
                break

        # Token budget trim
        budget_chars = token_budget * 4
        kept, chars = [], 0
        for m in matches:
            if chars + len(m) > budget_chars:
                break
            kept.append(m)
            chars += len(m)

        return {
            "matches"  : kept,
            "truncated": len(kept) < len(matches),
            "tool_used": "python_glob",
        }
    except Exception as exc:
        logger.error(f"Python fallback search failed: {exc}")
        return {"matches": [], "truncated": False, "tool_used": "none", "error": str(exc)}


# ─────────────────────────────────────────────────────────────
# PUBLIC TOOLS
# ─────────────────────────────────────────────────────────────

def search_codebase(
    pattern: str,
    path: str = "src/",
    token_budget: int = _DEFAULT_BUDGET,
) -> dict[str, Any]:
    """
    Search DhanNiti codebase with token-efficient output.

    # fm-key: search_codebase
    # fm-value: Regex search across DhanNiti modules. Uses rgx to truncate results to match agent token constraints.
    # fm-scope: function
    # fm-links: _run_rgx

    Agent use cases:
    - "Which tickers are configured?" → search PORTFOLIO_TICKERS
    - "What indicators does feature engineering use?" → search pandas_ta
    - "Where is the Groq call?" → search GROQ_MODEL

    Args:
        pattern     : Regex / literal pattern
        path        : Directory to search (default: src/)
        token_budget: Max tokens in response

    Returns:
        {matches, truncated, tool_used}
    """
    logger.debug(f"search_codebase(pattern={pattern!r}, path={path!r})")
    return _run_rgx(pattern, path, token_budget)


def search_signal_history(
    ticker: str,
    date: str,
    path: str = "models/",
) -> dict[str, Any]:
    """
    Search saved model outputs / signal logs for a ticker+date pair.

    Args:
        ticker: NSE ticker (e.g. "RELIANCE.NS")
        date  : ISO date string (e.g. "2025-05-17")
        path  : Where model artifacts are stored

    Returns:
        {matches, truncated, tool_used}
    """
    pattern = rf"{ticker}.*{date}|{date}.*{ticker}"
    return _run_rgx(pattern, path, _SIGNAL_BUDGET)


def search_config(key: str) -> dict[str, Any]:
    """
    Search settings.py for a specific config key.
    Useful for the advisor to verify constraints before making recommendations.

    Args:
        key: Config key name (e.g. "MINIMUM_ALLOCATION")

    Returns:
        {matches, truncated, tool_used}
    """
    return _run_rgx(key, "src/settings.py", _CONFIG_BUDGET)


def get_portfolio_tickers() -> list[str]:
    """
    Return the current portfolio ticker list directly from settings.
    Zero search cost — direct import.
    """
    try:
        from src.settings import PORTFOLIO_TICKERS
        return list(PORTFOLIO_TICKERS)
    except Exception:
        return []


def get_tool_status() -> dict[str, bool]:
    """
    Check which search tools are available on this machine.
    Useful for debugging agent environment.
    """
    status: dict[str, bool] = {}

    for tool in ["rgx", "rg"]:
        try:
            subprocess.run([tool, "--version"], capture_output=True, timeout=5)
            status[tool] = True
        except (FileNotFoundError, subprocess.TimeoutExpired):
            status[tool] = False

    status["python_glob"] = True  # always available
    return status