# scripts/test_pipeline.py
import os
import sys
from pathlib import Path

# Adjust Python path to import from src
project_root = Path(__file__).resolve().parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from src.database.supabase_client import DhanNitiDatabase
from scripts.validate_keys import validate_groq, validate_supabase, validate_yfinance

def run_tests():
    print("=" * 60)
    print(" DHANNITI PIPELINE SMOKE TEST")
    print("=" * 60)
    
    all_pass = True
    
    # 1. Supabase Check
    print("\n[Test 1/5] Checking Supabase connection...")
    sb_url = os.getenv("SUPABASE_URL")
    sb_key = os.getenv("SUPABASE_KEY") or os.getenv("SUPABASE_ANON_KEY")
    if not sb_url or not sb_key:
        print("  ✗ Supabase credentials missing from environment.")
        all_pass = False
    else:
        ok, msg = validate_supabase(sb_url, sb_key)
        print(f"  {'✓' if ok else '✗'} {msg}")
        if not ok:
            all_pass = False
            
    # 2. yfinance Check
    print("\n[Test 2/5] Checking yfinance data retrieval...")
    ok, msg = validate_yfinance()
    print(f"  {'✓' if ok else '✗'} {msg}")
    if not ok:
        all_pass = False
        
    # 3. Groq LLM Check
    print("\n[Test 3/5] Checking Groq LLM inference...")
    groq_key = os.getenv("GROQ_API_KEY")
    if not groq_key:
        print("  ✗ Groq API key (GROQ_API_KEY) missing from environment.")
        all_pass = False
    else:
        ok, msg = validate_groq(groq_key)
        print(f"  {'✓' if ok else '✗'} {msg}")
        if not ok:
            all_pass = False
            
    # 4. Qdrant Memory Check
    print("\n[Test 4/5] Checking Qdrant memory database...")
    qdrant_url = os.getenv("QDRANT_URL")
    qdrant_key = os.getenv("QDRANT_API_KEY")
    if not qdrant_url:
        print("  ! Qdrant URL missing. Episodic memory indexing will run in local/fallback mode.")
    else:
        try:
            from qdrant_client import QdrantClient
            client = QdrantClient(url=qdrant_url, api_key=qdrant_key, timeout=5)
            collections = client.get_collections()
            names = [c.name for c in collections.collections]
            print(f"  ✓ Qdrant connected. Collections found: {names}")
        except Exception as e:
            print(f"  ✗ Qdrant connection failed: {e}")
            all_pass = False
            
    # 5. Local Model weights Check
    print("\n[Test 5/5] Checking local model checkpoints...")
    models_dir = project_root / "models"
    hmm_model = models_dir / "hmm_regime.pkl"
    xgb_model = models_dir / "xgb_signals.pkl" # adjust filenames based on actual files
    
    found_any = False
    for filename in ["hmm_regime.pkl", "xgb_signals.pkl", "xgb_model.json", "ppo_dhanniti.zip"]:
        path = models_dir / filename
        if path.exists():
            print(f"  ✓ Model checkpoint found: models/{filename}")
            found_any = True
            
    if not found_any:
        print("  ! No trained model files found under models/. The optimization pipeline will retrain/download on launch.")
        
    print("\n" + "=" * 60)
    if all_pass:
        print(" SUCCESS: All primary pipeline tests passed!")
        print("=" * 60 + "\n")
        return True
    else:
        print(" WARNING: Some pipeline connection tests failed.")
        print(" Please verify the environment settings in your .env file.")
        print("=" * 60 + "\n")
        return False

if __name__ == "__main__":
    run_tests()
