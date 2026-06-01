-- ========================================================
-- DHANNITI CONSOLIDATED DATABASE SETUP SCHEMA
-- Generated on: init_supabase.py
-- ========================================================

-- --- SECTION: 001_create_tables.sql ---
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



-- --- SECTION: 002_create_indexes.sql ---
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



-- --- SECTION: 003_rls_policies.sql ---
-- 003_rls_policies.sql
-- Row Level Security (RLS) policies for Vercel Demo and Local settings

-- Enable RLS for all core tables
ALTER TABLE advisory_reports ENABLE ROW LEVEL SECURITY;
ALTER TABLE portfolio_predictions ENABLE ROW LEVEL SECURITY;
ALTER TABLE holdings ENABLE ROW LEVEL SECURITY;
ALTER TABLE historical_candles ENABLE ROW LEVEL SECURITY;
ALTER TABLE rl_episodes ENABLE ROW LEVEL SECURITY;
ALTER TABLE groq_advisory_cache ENABLE ROW LEVEL SECURITY;

-- 1. PUBLIC READ ACCESS (For both Demo and Local instances)
CREATE POLICY "Allow public read access on advisory_reports" ON advisory_reports FOR SELECT USING (true);
CREATE POLICY "Allow public read access on portfolio_predictions" ON portfolio_predictions FOR SELECT USING (true);
CREATE POLICY "Allow public read access on holdings" ON holdings FOR SELECT USING (true);
CREATE POLICY "Allow public read access on historical_candles" ON historical_candles FOR SELECT USING (true);
CREATE POLICY "Allow public read access on rl_episodes" ON rl_episodes FOR SELECT USING (true);
CREATE POLICY "Allow public read access on groq_advisory_cache" ON groq_advisory_cache FOR SELECT USING (true);

-- 2. WRITE PRIVILEGES (Depends on configuration)
-- In a private local deployment, we allow the anon/authenticated key to perform writes.
-- In a public demo deployment, RLS policies should block writes (inserts/updates/deletes) by default.

-- Default Local Write Policies (allow all for personal DBs)
CREATE POLICY "Allow anon inserts on holdings" ON holdings FOR INSERT WITH CHECK (true);
CREATE POLICY "Allow anon updates on holdings" ON holdings FOR UPDATE USING (true);
CREATE POLICY "Allow anon deletes on holdings" ON holdings FOR DELETE USING (true);

CREATE POLICY "Allow anon writes on advisory_reports" ON advisory_reports FOR INSERT WITH CHECK (true);
CREATE POLICY "Allow anon writes on portfolio_predictions" ON portfolio_predictions FOR INSERT WITH CHECK (true);
CREATE POLICY "Allow anon writes on historical_candles" ON historical_candles FOR INSERT WITH CHECK (true);
CREATE POLICY "Allow anon writes on rl_episodes" ON rl_episodes FOR INSERT WITH CHECK (true);
CREATE POLICY "Allow anon writes on groq_advisory_cache" ON groq_advisory_cache FOR INSERT WITH CHECK (true);


