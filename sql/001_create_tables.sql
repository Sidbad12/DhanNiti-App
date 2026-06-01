-- 001_create_tables.sql
-- Core schema definitions for DhanNiti

-- 1. Advisory Reports table
CREATE TABLE IF NOT EXISTS advisory_reports (
  id                UUID DEFAULT gen_random_uuid() PRIMARY KEY,
  report_date       TEXT UNIQUE NOT NULL,
  regime            TEXT DEFAULT 'neutral',
  expected_return   NUMERIC DEFAULT 0.0,
  reasoning         TEXT,
  risk_flags        JSONB DEFAULT '[]'::jsonb,
  llm_confidence    NUMERIC DEFAULT 0.0,
  memory_citations  JSONB DEFAULT '[]'::jsonb,
  full_report       JSONB NOT NULL,
  created_at        TIMESTAMPTZ DEFAULT NOW()
);

-- 2. Portfolio Predictions table
CREATE TABLE IF NOT EXISTS portfolio_predictions (
  id                       UUID DEFAULT gen_random_uuid() PRIMARY KEY,
  as_of_date               TEXT NOT NULL,
  ticker                   TEXT NOT NULL,
  predicted_price          NUMERIC,
  predicted_return         NUMERIC,
  actual_prices_last_month JSONB DEFAULT '[]'::jsonb,
  portfolio_weight         NUMERIC,
  created_at               TIMESTAMPTZ DEFAULT NOW(),
  UNIQUE(as_of_date, ticker)
);

-- 3. User Holdings table
CREATE TABLE IF NOT EXISTS holdings (
  id          UUID DEFAULT gen_random_uuid() PRIMARY KEY,
  ticker      TEXT UNIQUE NOT NULL,
  quantity    NUMERIC NOT NULL,
  avg_cost    NUMERIC NOT NULL,
  created_at  TIMESTAMPTZ DEFAULT NOW(),
  updated_at  TIMESTAMPTZ DEFAULT NOW()
);

-- 4. Historical Candles table (caching for chart data)
CREATE TABLE IF NOT EXISTS historical_candles (
  id          UUID DEFAULT gen_random_uuid() PRIMARY KEY,
  ticker      TEXT NOT NULL,
  date        TEXT NOT NULL,
  open        NUMERIC,
  high        NUMERIC,
  low         NUMERIC,
  close       NUMERIC NOT NULL,
  volume      NUMERIC,
  source      TEXT DEFAULT 'yfinance',
  created_at  TIMESTAMPTZ DEFAULT NOW(),
  UNIQUE(ticker, date)
);

-- 5. RL Episodes memory table
CREATE TABLE IF NOT EXISTS rl_episodes (
  id              UUID DEFAULT gen_random_uuid() PRIMARY KEY,
  episode_num     INTEGER NOT NULL,
  actions         JSONB NOT NULL,
  rewards         JSONB NOT NULL,
  portfolio_state JSONB NOT NULL,
  created_at      TIMESTAMPTZ DEFAULT NOW()
);

-- 6. Groq Advisor Cache table
CREATE TABLE IF NOT EXISTS groq_advisory_cache (
  id          UUID DEFAULT gen_random_uuid() PRIMARY KEY,
  prompt_hash TEXT UNIQUE NOT NULL,
  response    TEXT NOT NULL,
  created_at  TIMESTAMPTZ DEFAULT NOW()
);
