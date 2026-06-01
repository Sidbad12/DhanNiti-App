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
