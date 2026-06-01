"""
DhanNiti — FastAPI Server
Exposes REST endpoints for the UI and wraps the LangGraph pipeline
in an asynchronous background task with WebSocket streaming.
"""

import logging
import asyncio
from contextlib import asynccontextmanager
from datetime import datetime
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, BackgroundTasks, Query, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import pandas as pd

from src.api.websocket import manager
from src.logger import setup_logging

# LangGraph pipeline imports FinBERT/transformers — load only when /pipeline/trigger runs.

setup_logging()
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    from src.api.scheduler import start_portfolio_scheduler, stop_portfolio_scheduler

    start_portfolio_scheduler()
    yield
    stop_portfolio_scheduler()


app = FastAPI(
    title="DhanNiti AI API",
    description=(
        "FastAPI backend for DhanNiti Portfolio Optimizer. "
        "V2 endpoints (/v2/*) use the winning SAC ticker-agnostic agent "
        "trained over 2M steps (Sharpe 1.32, AvgReturn 118%). "
        "Legacy V1 PPO endpoints remain active for backward compatibility."
    ),
    version="2.0.0",
    lifespan=lifespan,
)

# ── RATE LIMITER ──────────────────────────────────────────────────────
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# Allow Next.js frontend (localhost and vercel) and Tauri local protocol
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://localhost:1420",
        "tauri://localhost",
        "http://tauri.localhost",
        "https://tauri.localhost",
    ],
    allow_origin_regex=r"https://.*\.vercel\.app",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class TriggerRequest(BaseModel):
    date: str | None = None

# ── PIPELINE RUNNER ───────────────────────────────────────────────────

async def run_langgraph_pipeline(run_date: datetime):
    """Run pipeline and stream progress to websockets."""
    logger.info(f"Background Pipeline started for {run_date.strftime('%Y-%m-%d')}")
    
    await manager.broadcast({
        "type": "system", 
        "message": f"Pipeline started for {run_date.strftime('%Y-%m-%d')}",
        "status": "running"
    })

    try:
        from src.graph.pipeline import build_pipeline_graph

        graph = build_pipeline_graph()
        
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
        
        # LangGraph native stream yields output from each node
        for output in graph.stream(initial_state):
            for node_name, state_update in output.items():
                logger.info(f"Graph completed node: {node_name}")
                await manager.broadcast({
                    "type": "progress",
                    "node": node_name,
                    "status": "completed",
                    "timestamp": datetime.now().isoformat()
                })
                # Simulate tiny delay for UI visualization
                await asyncio.sleep(0.5)
                
        await manager.broadcast({
            "type": "system",
            "message": "Pipeline completed successfully.",
            "status": "completed"
        })
        
    except Exception as e:
        logger.exception("Pipeline failed in background task.")
        await manager.broadcast({
            "type": "system",
            "message": f"Pipeline failed: {str(e)}",
            "status": "error"
        })

# ── ROUTES ────────────────────────────────────────────────────────────

@app.get("/health")
def health_check():
    """Returns system status."""
    return {"status": "healthy", "timestamp": datetime.now().isoformat()}

@app.post("/pipeline/trigger")
async def trigger_pipeline(req: TriggerRequest, background_tasks: BackgroundTasks):
    """Starts the LangGraph pipeline in the background."""
    run_date = datetime.now()
    if req.date:
        try:
            run_date = datetime.strptime(req.date, "%Y-%m-%d")
        except ValueError:
            return {"error": "Invalid date format. Use YYYY-MM-DD"}
            
    background_tasks.add_task(run_langgraph_pipeline, run_date)
    return {"status": "accepted", "message": "Pipeline triggered in background."}

@app.get("/portfolio/recommend")
def portfolio_recommend(
    as_of: str | None = Query(
        default=None,
        description="As-of date YYYY-MM-DD for feature history; defaults to today.",
    ),
    persist: bool = Query(
        default=True,
        description="Save result to Supabase (advisory_reports + portfolio_predictions).",
    ),
    use_groq: bool = Query(
        default=True,
        description="If false, PPO + quant signals only (no Groq narrative).",
    ),
):
    """
    Fresh portfolio recommendation: PPO inference + HMM regime + XGBoost +
    Qdrant memory + Groq synthesis. Persists to Supabase by default.
    May take 30–90s on cold cache (yfinance + Prophet + LLM).
    """
    from src.services.portfolio_persistence import run_portfolio_recommend

    as_of_str = as_of or datetime.now().strftime("%Y-%m-%d")
    if as_of:
        try:
            datetime.strptime(as_of, "%Y-%m-%d")
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="as_of must be YYYY-MM-DD") from exc

    try:
        return run_portfolio_recommend(
            as_of=as_of_str,
            persist=persist,
            use_groq=use_groq,
        )
    except Exception as exc:
        logger.exception("portfolio/recommend failed")
        raise HTTPException(status_code=500, detail=str(exc)) from exc


# ── V2 SAC ENDPOINTS ──────────────────────────────────────────────────────

@app.get("/v2/portfolio/recommend")
async def v2_portfolio_recommend(
    as_of: str | None = Query(
        default=None,
        description="As-of date YYYY-MM-DD for feature history; defaults to today.",
    ),
    persist: bool = Query(
        default=True,
        description="Save result to Supabase (advisory_reports + portfolio_predictions).",
    ),
    use_groq: bool = Query(
        default=True,
        description="If false, SAC + quant signals only (no Groq narrative).",
    ),
    tickers: str | None = Query(
        default=None,
        description="Comma-separated NSE tickers list, e.g. 'RELIANCE.NS,TCS.NS'",
    ),
    start_date: str | None = Query(
        default=None,
        description="Start date YYYY-MM-DD for historical features window",
    ),
    force_retrain: bool = Query(
        default=True,
        description="Force fit/train fresh XGBoost classifiers instead of loading cached versions.",
    ),
):
    """
    **V2 Portfolio Recommendation — SAC ticker-agnostic agent.**
    """
    from src.services.portfolio_persistence import run_portfolio_recommend_v2
    from fastapi.concurrency import run_in_threadpool
    import asyncio
    from src.api.websocket import manager

    as_of_str = as_of or datetime.now().strftime("%Y-%m-%d")
    if as_of:
        try:
            datetime.strptime(as_of, "%Y-%m-%d")
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="as_of must be YYYY-MM-DD") from exc

    if start_date:
        try:
            datetime.strptime(start_date, "%Y-%m-%d")
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="start_date must be YYYY-MM-DD") from exc

    ticker_list = [t.strip() for t in tickers.split(",") if t.strip()] if tickers else None

    if manager.running:
        logger.warning("V2 recommendation request rejected: pipeline already running")
        raise HTTPException(
            status_code=409,
            detail="A portfolio recommendation run is already in progress."
        )

    # Emit WS progress ticks while the threadpool inference runs.
    # Node names MUST match WS_NODE_LABELS keys in the frontend exactly.
    manager.running = True
    manager.completed_nodes = []
    manager.current_node = "Starting..."

    async def fake_progress():
        # (node_name, seconds_to_wait_before_next)
        # Total budget ≈ 240s — covers a typical 3-4 min cold run.
        steps = [
            ("fetch_data",               15),
            ("fetch_alternative_data",   20),
            ("detect_regime",             8),
            ("feature_engineering",      35),
            ("drift_check",               5),
            ("tune_hyperparams",         30),
            ("train_classifiers",        45),
            ("run_predictions",          20),
            ("backtest_and_rl_feedback", 12),
            ("query_memory",              8),
            ("call_advisor",             25),
            ("persist_results",          10),
            ("broadcast_websocket",       2),
        ]
        await manager.broadcast({"type": "system", "status": "running"})
        for node, delay in steps:
            if not manager.running:
                break
            manager.current_node = node
            if node not in manager.completed_nodes:
                manager.completed_nodes.append(node)
            await manager.broadcast({"type": "progress", "node": node})
            # Sleep in small increments so we can react to cancellation quickly
            for _ in range(delay * 2):
                if not manager.running:
                    break
                await asyncio.sleep(0.5)

    progress_task = asyncio.create_task(fake_progress())

    try:
        report = await run_in_threadpool(
            run_portfolio_recommend_v2,
            as_of=as_of_str,
            persist=persist,
            use_groq=use_groq,
            tickers=ticker_list,
            start_date=start_date,
            force_retrain=force_retrain,
        )
        return report
    except Exception as exc:
        logger.exception("v2/portfolio/recommend failed")
        await manager.broadcast({"type": "system", "status": "error", "message": str(exc)})
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    finally:
        # Stop the progress ticker first so it doesn't race with "completed"
        manager.running = False
        manager.completed_nodes = []
        manager.current_node = ""
        progress_task.cancel()
        try:
            await progress_task
        except asyncio.CancelledError:
            pass
        await manager.broadcast({"type": "system", "status": "completed"})


@app.get("/v2/portfolio/current")
async def get_current_v2_portfolio():
    """Last persisted V2 SAC portfolio snapshot from Supabase (no live inference)."""
    from src.database.supabase_client import DhanNitiDatabase

    db = DhanNitiDatabase()
    report = db.get_latest_v2_recommend_report()

    if report:
        return report

    raise HTTPException(
        status_code=404,
        detail="No V2 portfolio saved yet. Call GET /v2/portfolio/recommend first.",
    )


# ── V1 LEGACY ENDPOINTS ───────────────────────────────────────────────────

@app.get("/portfolio/current")
def get_current_portfolio():
    """Last persisted portfolio snapshot from Supabase (no live inference)."""
    from src.database.supabase_client import DhanNitiDatabase

    db = DhanNitiDatabase()
    report = db.get_latest_v1_recommend_report()

    if report:
        return report

    raise HTTPException(
        status_code=404,
        detail="No V1 portfolio saved. Call GET /portfolio/recommend first.",
    )

@app.get("/data/candlesticks/{ticker}")
def get_candlesticks(ticker: str):
    """Fetch recent OHLCV data for TradingView chart with Supabase caching."""
    try:
        import yfinance as yf
        
        # Clean ticker for Yahoo Finance format
        yf_ticker = ticker
        if ":" in yf_ticker:
            yf_ticker = yf_ticker.split(":")[-1]
        if yf_ticker.endswith("-EQ"):
            yf_ticker = yf_ticker.replace("-EQ", "")
        
        # If it doesn't end with .NS and isn't an index, append .NS
        if not yf_ticker.endswith(".NS") and not yf_ticker.startswith("^"):
            if "NIFTY" in yf_ticker.upper():
                yf_ticker = "^NSEI"
            else:
                yf_ticker = f"{yf_ticker}.NS"

        # 1. Try to load from Supabase first
        from src.database.supabase_client import DhanNitiDatabase
        from datetime import datetime, timedelta
        db = DhanNitiDatabase()
        
        end_dt = datetime.now()
        start_dt = end_dt - timedelta(days=365)
        start_str = start_dt.strftime("%Y-%m-%d")
        end_str = end_dt.strftime("%Y-%m-%d")
        
        db_candles = db.get_historical_candles(yf_ticker, start_str, end_str)
        if db_candles and len(db_candles) >= 200:
            logger.info(f"Loaded {len(db_candles)} candles for {yf_ticker} from Supabase for chart.")
            data = []
            for row in db_candles:
                data.append({
                    "time": str(row["date"]),
                    "open": float(row["open"]),
                    "high": float(row["high"]),
                    "low": float(row["low"]),
                    "close": float(row["close"]),
                    "volume": float(row["volume"]),
                })
            return {"ticker": ticker, "data": data}

        # 2. Cache miss: Fetch from yfinance
        from src.data.extractor import get_yfinance_session
        session = get_yfinance_session()
        df = yf.download(yf_ticker, period="1y", interval="1d", progress=False, session=session)
        if df.empty:
            if db_candles:
                logger.warning(f"yfinance returned empty for {yf_ticker}, falling back to DB.")
                data = [{
                    "time": str(row["date"]),
                    "open": float(row["open"]),
                    "high": float(row["high"]),
                    "low": float(row["low"]),
                    "close": float(row["close"]),
                    "volume": float(row["volume"]),
                } for row in db_candles]
                return {"ticker": ticker, "data": data}
            return {"ticker": ticker, "data": []}
            
        data = []
        db_rows = []
        for date, row in df.iterrows():
            open_val = float(row["Open"].iloc[0] if isinstance(row["Open"], pd.Series) else row["Open"])
            high_val = float(row["High"].iloc[0] if isinstance(row["High"], pd.Series) else row["High"])
            low_val = float(row["Low"].iloc[0] if isinstance(row["Low"], pd.Series) else row["Low"])
            close_val = float(row["Close"].iloc[0] if isinstance(row["Close"], pd.Series) else row["Close"])
            vol_val = float(row["Volume"].iloc[0] if isinstance(row["Volume"], pd.Series) else row["Volume"])
            
            date_str = date.strftime("%Y-%m-%d")
            data.append({
                "time": date_str,
                "open": open_val,
                "high": high_val,
                "low": low_val,
                "close": close_val,
                "volume": vol_val,
            })
            
            db_rows.append({
                "ticker": yf_ticker,
                "date": date_str,
                "open": open_val,
                "high": high_val,
                "low": low_val,
                "close": close_val,
                "volume": vol_val,
            })
            
        # 3. Save to Supabase for future requests
        if db_rows:
            db.upsert_historical_candles(db_rows)
            logger.info(f"Saved {len(db_rows)} downloaded candles for {yf_ticker} to Supabase.")
            
        return {"ticker": ticker, "data": data}
    except Exception as e:
        logger.error(f"Failed to fetch candlesticks for {ticker}: {e}")
        return {"ticker": ticker, "data": []}

@app.get("/data/vix")
def get_vix():
    """Fetch live India VIX for fear gauge."""
    try:
        import yfinance as yf
        from src.data.extractor import get_yfinance_session
        session = get_yfinance_session()
        df = yf.download("^INDIAVIX", period="5d", progress=False, session=session)
        if not df.empty:
            vix_val = float(df.iloc[-1].iloc[0] if isinstance(df["Close"], pd.DataFrame) else df["Close"].iloc[-1])
            status = "fear" if vix_val > 20 else "caution" if vix_val > 15 else "calm"
            return {"vix": round(vix_val, 2), "status": status}
    except Exception as e:
        logger.error(f"Failed to fetch VIX: {e}")
    return {"vix": 14.50, "status": "calm"}

@app.post("/simulate/rebalance-cost")
def simulate_rebalance_cost(req: dict):
    """Calculates exactly how much STT + brokerage + impact cost you'd pay."""
    try:
        from src.ml.backtester import NSECostModel
        import pandas as pd
        
        current = pd.Series(req.get("current_weights", {}))
        target = pd.Series(req.get("target_weights", {}))
        val = req.get("portfolio_value", 1000000)
        
        model = NSECostModel()
        cost = model.rebalance_cost(current, target, val)
        return {"estimated_cost_inr": round(cost, 2), "portfolio_value": val}
    except Exception as e:
        return {"error": str(e)}

@app.get("/data/news/{ticker}")
def get_news(ticker: str):
    """Fetch live news headlines and FinBERT sentiment for the stock."""
    try:
        from src.data.sentiment import SentimentPipeline
        pipeline = SentimentPipeline()
        headlines = pipeline.fetch_headlines(ticker, max_items=5)
        scores = pipeline.score_sentiment(headlines)
        return {
            "ticker": ticker,
            "headlines": headlines,
            "sentiment": scores
        }
    except Exception as e:
        logger.error(f"Failed to fetch news for {ticker}: {e}")
        return {"ticker": ticker, "headlines": [], "sentiment": {"composite": 0.0, "positive": 0.0, "negative": 0.0, "neutral": 1.0}}

# ── HOLDINGS ENDPOINTS (D1.2) ──────────────────────────────────────────

class HoldingCreateRequest(BaseModel):
    ticker: str
    quantity: float
    buy_price: float
    buy_date: str  # YYYY-MM-DD
    notes: str | None = None

class HoldingUpdateRequest(BaseModel):
    ticker: str | None = None
    quantity: float | None = None
    buy_price: float | None = None
    buy_date: str | None = None
    notes: str | None = None

@app.get("/portfolio/holdings")
def get_holdings():
    from src.database.supabase_client import DhanNitiDatabase
    db = DhanNitiDatabase()
    holdings = db.get_all_holdings()

    if not holdings:
        return {"holdings": [], "summary": {
            "total_invested": 0.0,
            "total_current_value": 0.0,
            "total_unrealised_pnl": 0.0,
            "total_unrealised_pnl_pct": 0.0
        }}

    tickers = list(set(h["ticker"] for h in holdings))

    # Fetch live prices via yfinance
    import yfinance as yf
    from src.data.extractor import get_yfinance_session
    session = get_yfinance_session()
    prices = {}
    for ticker in tickers:
        try:
            t = yf.Ticker(ticker, session=session)
            prices[ticker] = float(t.fast_info["last_price"])
        except Exception as e:
            logger.error(f"Failed to fetch live price for {ticker}: {e}")
            prices[ticker] = None

    # Compute P&L per holding
    enriched = []
    total_invested = 0.0
    total_current = 0.0

    for h in holdings:
        ticker = h["ticker"]
        qty = float(h["quantity"])
        buy_price = float(h["buy_price"])
        current_price = prices.get(ticker)

        invested = qty * buy_price
        current_value = qty * current_price if current_price is not None else None
        pnl = current_value - invested if current_value is not None else None
        pnl_pct = (pnl / invested * 100) if pnl is not None else None

        enriched.append({
            **h,
            "quantity": qty,
            "buy_price": buy_price,
            "current_price": current_price,
            "invested_value": round(invested, 2),
            "current_value": round(current_value, 2) if current_value is not None else None,
            "unrealised_pnl": round(pnl, 2) if pnl is not None else None,
            "unrealised_pnl_pct": round(pnl_pct, 2) if pnl_pct is not None else None,
        })

        total_invested += invested
        if current_value is not None:
            total_current += current_value
        else:
            total_current += invested  # Fallback to invested if current price is missing

    return {
        "holdings": enriched,
        "summary": {
            "total_invested": round(total_invested, 2),
            "total_current_value": round(total_current, 2),
            "total_unrealised_pnl": round(total_current - total_invested, 2),
            "total_unrealised_pnl_pct": round(
                (total_current - total_invested) / total_invested * 100, 2
            ) if total_invested > 0 else 0.0,
        }
    }

@app.post("/portfolio/holdings")
def add_holding(req: HoldingCreateRequest):
    from src.database.supabase_client import DhanNitiDatabase
    db = DhanNitiDatabase()
    
    data = {
        "ticker": req.ticker,
        "quantity": req.quantity,
        "buy_price": req.buy_price,
        "buy_date": req.buy_date,
        "notes": req.notes
    }
    
    res = db.add_holding(data)
    if res:
        return res
    raise HTTPException(status_code=500, detail="Failed to create holding record.")

@app.put("/portfolio/holdings/{id}")
def update_holding(id: str, req: HoldingUpdateRequest):
    from src.database.supabase_client import DhanNitiDatabase
    db = DhanNitiDatabase()
    
    updates = {k: v for k, v in req.model_dump().items() if v is not None}
    if not updates:
        raise HTTPException(status_code=400, detail="No updates provided.")
        
    res = db.update_holding(id, updates)
    if res:
        return res
    raise HTTPException(status_code=404, detail="Holding not found.")

@app.delete("/portfolio/holdings/{id}")
def delete_holding_endpoint(id: str):
    from src.database.supabase_client import DhanNitiDatabase
    db = DhanNitiDatabase()
    
    res = db.delete_holding(id)
    if res:
        return {"status": "success", "deleted_id": id, "holding": res}
    raise HTTPException(status_code=404, detail="Holding not found.")

@app.get("/portfolio/holdings/gap")
def get_holdings_gap():
    from src.database.supabase_client import DhanNitiDatabase
    
    # 1. Get current holdings weights (by value)
    holdings_resp = get_holdings()
    holdings = holdings_resp["holdings"]
    total_value = holdings_resp["summary"]["total_current_value"]

    held_weights = {}
    for h in holdings:
        if h["current_value"] is not None and total_value > 0:
            held_weights[h["ticker"]] = h["current_value"] / total_value

    # 2. Get latest V2 recommended weights from Supabase
    db = DhanNitiDatabase()
    report = db.get_latest_v2_recommend_report()
    target_weights = report.get("allocations", {}) if report else {}

    # 3. Compute gap
    all_tickers = set(list(held_weights.keys()) + list(target_weights.keys()))
    gap_analysis = []

    for ticker in all_tickers:
        held = held_weights.get(ticker, 0.0)
        target = target_weights.get(ticker, 0.0)
        gap = target - held  # positive = need to buy more, negative = need to sell

        if gap > 0.01:
            action = "buy"
        elif gap < -0.01:
            action = "sell"
        else:
            action = "hold"

        gap_analysis.append({
            "ticker": ticker,
            "held_weight": round(held, 4),
            "ppo_weight": round(target, 4),  # Keep key as ppo_weight for frontend compatibility
            "gap": round(gap, 4),
            "action": action,
            "delta_inr": round(gap * total_value, 2),  # ₹ to buy/sell
        })

    # Sort by abs gap descending — biggest rebalance needs first
    gap_analysis.sort(key=lambda x: abs(x["gap"]), reverse=True)

    return {
        "gap_analysis": gap_analysis,
        "portfolio_value": total_value,
        "as_of": datetime.now().isoformat(),
    }

class ChatMessage(BaseModel):
    role: str
    content: str

class ChatRequest(BaseModel):
    messages: list[ChatMessage]

@app.post("/v2/chat")
@limiter.limit("10/minute")
async def chat_endpoint(request: Request, req: ChatRequest):
    """Streaming chat endpoint powered by Groq Llama-3."""
    from fastapi.responses import StreamingResponse
    from src.settings import GROQ_API_KEY, GROQ_MODEL
    import json
    
    async def generate():
        try:
            from groq import AsyncGroq
            from src.agent.memory import DhanNitiAgentMemory
            
            client = AsyncGroq(api_key=GROQ_API_KEY)
            
            # Fetch mem0 context based on last user message
            mem0_context = ""
            if len(req.messages) > 0:
                last_msg = req.messages[-1].content
                try:
                    memory = DhanNitiAgentMemory()
                    if memory.mem0_client:
                        # Search mem0 for relevant past episodes
                        memories = memory.mem0_client.search(last_msg, user_id="dhanniti_agent", limit=3)
                        if memories:
                            mem_texts = [m["text"] for m in memories]
                            mem0_context = "\n\nPAST PORTFOLIO MEMORY (from Mem0):\n" + "\n".join(mem_texts)
                except Exception as e:
                    logger.warning(f"Failed to fetch Mem0 context: {e}")

            # Fetch live portfolio context & recommendations
            portfolio_context = ""
            try:
                from src.database.supabase_client import DhanNitiDatabase
                db = DhanNitiDatabase()
                latest_report = db.get_latest_v2_recommend_report()
                holdings = db.get_all_holdings()
                
                context_parts = []
                if latest_report:
                    regime = latest_report.get("regime", "unknown")
                    allocations = latest_report.get("allocations", {})
                    metrics = latest_report.get("metrics", {})
                    context_parts.append(f"LATEST PORTFOLIO RECOMMENDATIONS (Regime: {regime}):")
                    context_parts.append(f"- Recommended Allocations: {json.dumps(allocations)}")
                    if metrics:
                        context_parts.append(f"- Performance Metrics: {json.dumps(metrics)}")
                
                if holdings:
                    holdings_summary = []
                    for h in holdings:
                        holdings_summary.append(
                            f"Ticker: {h.get('ticker')}, Qty: {h.get('quantity')}, Buy Price: {h.get('buy_price')}, Buy Date: {h.get('buy_date')}"
                        )
                    context_parts.append("CURRENT USER PORTFOLIO HOLDINGS:")
                    context_parts.append("\n".join(f"- {h}" for h in holdings_summary))
                
                if context_parts:
                    portfolio_context = "\n\nLIVE SYSTEM CONTEXT:\n" + "\n".join(context_parts)
            except Exception as e:
                logger.warning(f"Failed to fetch portfolio context for chat: {e}")

            system_prompt = (
                "You are DhanNiti, an elite AI quantitative stock market advisor for NSE India. "
                "Keep answers concise, factual, and strictly based on stock market dynamics, "
                "algorithmic trading, or portfolio management. "
                "Do not answer general knowledge questions outside of finance. "
                "Use the provided Live System Context to answer specific queries about the user's portfolio, holdings, and recommended model weights. "
                "If a user asks whether they should buy or sell a specific ticker (e.g. ICICIBANK, TCS), compare their current holdings with the recommended allocations. "
                "State your findings clearly and ground your recommendations in this live context."
                f"{portfolio_context}"
                f"{mem0_context}"
            )
            
            api_msgs = [{"role": "system", "content": system_prompt}]
            for msg in req.messages:
                api_msgs.append({"role": msg.role, "content": msg.content})
                
            stream = await client.chat.completions.create(
                model=GROQ_MODEL,
                messages=api_msgs,
                stream=True
            )
            
            async for chunk in stream:
                if chunk.choices[0].delta.content is not None:
                    # SSE format
                    yield f"data: {json.dumps({'content': chunk.choices[0].delta.content})}\n\n"
            
            yield "data: [DONE]\n\n"
        except Exception as e:
            logger.error(f"Chat error: {e}")
            yield f"data: {json.dumps({'error': str(e)})}\n\n"
            yield "data: [DONE]\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream")

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """Real-time UI progress stream."""
    await manager.connect(websocket)
    try:
        while True:
            data = await websocket.receive_text()
            # Handle incoming client messages if necessary
            logger.info(f"Received from WS client: {data}")
    except WebSocketDisconnect:
        manager.disconnect(websocket)
