-- 002_create_indexes.sql
-- Optimizes query performance on frequently queried columns

-- Advisory Reports indexing
CREATE INDEX IF NOT EXISTS idx_advisory_reports_date ON advisory_reports(report_date DESC);

-- Portfolio Predictions indexing
CREATE INDEX IF NOT EXISTS idx_portfolio_pred_lookup ON portfolio_predictions(as_of_date DESC, ticker);

-- Historical Candles indexing
CREATE INDEX IF NOT EXISTS idx_candles_lookup ON historical_candles(ticker, date ASC);

-- Groq Advisor Cache indexing
CREATE INDEX IF NOT EXISTS idx_groq_cache_hash ON groq_advisory_cache(prompt_hash);
