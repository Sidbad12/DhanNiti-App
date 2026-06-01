.PHONY: install install-dev lint format type-check test clean run dashboard frontend backfill shap

# ── Setup ─────────────────────────────────────────────────────
install:
	poetry install --only main

install-dev:
	poetry install
	poetry run python -c "import cmdstanpy; cmdstanpy.install_cmdstan()" || true

# ── Code quality ─────────────────────────────────────────────
lint:
	poetry run ruff check src tests
	poetry run black --check src tests

format:
	poetry run ruff check --fix src tests
	poetry run black src tests

type-check:
	poetry run mypy src

# ── Tests ─────────────────────────────────────────────────────
test:
	poetry run pytest

test-fast:
	poetry run pytest -x --no-cov -q

# ── Pipeline ──────────────────────────────────────────────────
run:
	poetry run python -m src.main

backfill:
	poetry run python -m src.backfill_historical_data --days 30

shap:
	poetry run python - <<'EOF'
	from src.data.extractor import extract_data
	from src.data.processor import preprocess_data
	from src.features.pipeline import build_full_feature_matrix
	from src.features.technical import get_feature_columns
	from src.ml.classifier import DhanNitiClassifier
	from src.ml.explainer import XGBoostModelExplainer
	from src.settings import PORTFOLIO_TICKERS, START_DATE, END_DATE
	raw  = extract_data(PORTFOLIO_TICKERS, START_DATE, END_DATE)
	aln  = preprocess_data(raw)
	feat = build_full_feature_matrix(aln, add_labels=True)
	clf  = DhanNitiClassifier()
	exp  = XGBoostModelExplainer()
	for ticker, df in list(feat.items())[:3]:
		clf.fit(df, tune=False)
		cols = get_feature_columns(df)
		imp  = exp.get_feature_contributions(clf.model, df[cols].dropna())
		print(f"\n{ticker} top 10 features:")
		print(imp.head(10).to_string())
	EOF

# ── Dashboards ────────────────────────────────────────────────
dashboard:
	poetry run streamlit run src/streamlit_app.py

frontend:
	cd frontend && npm run dev

# ── Tools ─────────────────────────────────────────────────────
check-tools:
	poetry run python -c "
	from src.agent.tools import get_tool_status
	print('Tool availability:', get_tool_status())
	"

# ── Cleanup ───────────────────────────────────────────────────
clean:
	find . -type d -name "__pycache__"  -exec rm -r {} + 2>/dev/null || true
	find . -type f -name "*.pyc"        -delete 2>/dev/null || true
	find . -type d -name ".pytest_cache" -exec rm -r {} + 2>/dev/null || true
	find . -type d -name ".mypy_cache"  -exec rm -r {} + 2>/dev/null || true
	find . -type d -name "htmlcov"      -exec rm -r {} + 2>/dev/null || true
	find . -type f -name ".coverage"    -delete 2>/dev/null || true

check: format lint type-check test
