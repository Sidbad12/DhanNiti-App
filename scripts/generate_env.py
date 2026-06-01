# scripts/generate_env.py
import os
import sys
from pathlib import Path

# Adjust Python path to import from src
project_root = Path(__file__).resolve().parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from scripts.validate_keys import validate_groq, validate_supabase, validate_fyers

def prompt_key(prompt_text, validator_fn=None, is_required=False, default_val=None):
    """Prompt the user for a value, validate it, and retry if invalid and required."""
    while True:
        try:
            val = input(f"{prompt_text}").strip()
        except (KeyboardInterrupt, EOFError):
            print("\nSetup cancelled.")
            sys.exit(1)
            
        if not val:
            if default_val is not None:
                val = default_val
            elif not is_required:
                return ""
            else:
                print("  ✗ This setting is required. Please enter a valid value.")
                continue
                
        if validator_fn:
            print("  Validating key...")
            # If supabase validation, it needs URL + KEY, handle specially
            if validator_fn == validate_supabase:
                # We validate it inside generate_env main flow since it takes two args
                return val
            ok, msg = validator_fn(val)
            if ok:
                print(f"  ✓ {msg}")
                return val
            else:
                print(f"  ✗ {msg}")
                if is_required:
                    retry = input("  Would you like to use this key anyway? (y/n): ").strip().lower()
                    if retry in ('y', 'yes'):
                        return val
                    continue
                else:
                    return val
        return val

def generate():
    print("=" * 60)
    print(" DHANNITI INTERACTIVE ENVIRONMENT CONFIGURATION")
    print("=" * 60)
    print("This wizard will help you configure your .env file.")
    print("Optional keys can be skipped by pressing [Enter].\n")
    
    env_data = {}
    
    # 1. Supabase URL & Key
    print("--- Supabase Configurations (Database) ---")
    sb_url = prompt_key("Enter your Supabase URL (e.g. https://xxxx.supabase.co): ", is_required=True)
    
    # We loop to get a valid Supabase Anon key
    while True:
        sb_key = prompt_key("Enter your Supabase Anon Key: ", is_required=True)
        print("  Verifying Supabase connection...")
        ok, msg = validate_supabase(sb_url, sb_key)
        if ok:
            print(f"  ✓ {msg}")
            break
        else:
            print(f"  ✗ Connection failed: {msg}")
            retry = input("  Would you like to retry? (y/n) [y]: ").strip().lower()
            if retry in ('n', 'no'):
                break
                
    env_data["SUPABASE_URL"] = sb_url
    env_data["SUPABASE_KEY"] = sb_key
    env_data["SUPABASE_ANON_KEY"] = sb_key
    
    # 2. Groq
    print("\n--- Groq Configurations (AI Advisor) ---")
    groq_key = prompt_key("Enter your Groq API Key (starts with gsk_): ", validator_fn=validate_groq, is_required=True)
    env_data["GROQ_API_KEY"] = groq_key
    
    # 3. Qdrant — REQUIRED (episodic memory powers the RL agent's similarity recall)
    print("\n--- Qdrant Vector Database (Required — powers RL episodic memory) ---")
    print("  Sign up free at: https://cloud.qdrant.io")
    qdrant_url = prompt_key("Enter your Qdrant Cluster URL (e.g. https://xxx.aws.cloud.qdrant.io): ", is_required=True)
    qdrant_key = prompt_key("Enter your Qdrant API Key: ", is_required=True)
    env_data["QDRANT_URL"] = qdrant_url
    env_data["QDRANT_API_KEY"] = qdrant_key

    # 4. Mem0 (optional — enhanced long-term memory layer)
    print("\n--- Mem0 AI Memory (Optional — enhanced long-term memory) ---")
    mem0_key = prompt_key("Enter your Mem0 API Key (optional, press Enter to skip): ")
    if mem0_key:
        env_data["MEM0_API_KEY"] = mem0_key
        
    # 5. Fyers Trading API
    print("\n--- Fyers Trading API (Optional, but STRONGLY recommended) ---")
    print("  Without Fyers: live prices, real-time charts, and portfolio sync are unavailable.")
    print("  yfinance fallback will be used — EOD data only, manual holdings input.")
    fyers_client = prompt_key("Enter your Fyers Client ID (optional, press Enter to skip): ")
    if fyers_client:
        fyers_secret = prompt_key("Enter your Fyers App Secret: ")
        ok, msg = validate_fyers(fyers_client, fyers_secret)
        if ok:
            env_data["FYERS_CLIENT_ID"] = fyers_client
            env_data["FYERS_SECRET_KEY"] = fyers_secret
            print("  ✓ Fyers credentials saved — full live data mode enabled.")
        else:
            print(f"  ⚠  {msg}")
            save_anyway = input("  Save Fyers credentials anyway? (y/n): ").strip().lower()
            if save_anyway in ('y', 'yes'):
                env_data["FYERS_CLIENT_ID"] = fyers_client
                env_data["FYERS_SECRET_KEY"] = fyers_secret
    else:
        print("  ⚠  No Fyers credentials — running in LIMITED MODE (yfinance EOD only).")
        env_data["FYERS_MODE"] = "disabled"
            
    # ── Write backend .env ──────────────────────────────────────
    config_dir_env = os.environ.get("DHANNITI_CONFIG_DIR")
    if config_dir_env:
        output_dir = Path(config_dir_env)
        output_dir.mkdir(parents=True, exist_ok=True)
    else:
        output_dir = project_root

    output_path = output_dir / ".env"
    import shutil
    if output_path.exists():
        backup_path = output_dir / ".env.backup"
        try:
            shutil.copy(output_path, backup_path)
            print(f"\n[Config] Backed up existing .env to .env.backup")
        except Exception:
            pass

    with open(output_path, "w", encoding="utf-8") as f:
        f.write("# ── Supabase (Database) ───────────────────────\n")
        f.write(f"SUPABASE_URL=\"{env_data.get('SUPABASE_URL', '')}\"\n")
        f.write(f"SUPABASE_KEY=\"{env_data.get('SUPABASE_KEY', '')}\"\n")
        f.write(f"SUPABASE_ANON_KEY=\"{env_data.get('SUPABASE_ANON_KEY', '')}\"\n\n")

        f.write("# ── Groq LLM (Advisor) ────────────────────────\n")
        f.write(f"GROQ_API_KEY=\"{env_data.get('GROQ_API_KEY', '')}\"\n\n")

        f.write("# ── Qdrant Vector Database (Required) ─────────\n")
        f.write(f"QDRANT_URL=\"{env_data.get('QDRANT_URL', '')}\"\n")
        f.write(f"QDRANT_API_KEY=\"{env_data.get('QDRANT_API_KEY', '')}\"\n\n")

        if "MEM0_API_KEY" in env_data:
            f.write("# ── Mem0 AI Memory (Optional) ─────────────────\n")
            f.write(f"MEM0_API_KEY=\"{env_data.get('MEM0_API_KEY', '')}\"\n\n")

        if "FYERS_CLIENT_ID" in env_data:
            f.write("# ── Fyers API (Live Data Mode) ─────────────────\n")
            f.write(f"FYERS_CLIENT_ID=\"{env_data.get('FYERS_CLIENT_ID', '')}\"\n")
            f.write(f"FYERS_SECRET_KEY=\"{env_data.get('FYERS_SECRET_KEY', '')}\"\n\n")
        else:
            f.write("# ── Fyers API — not configured (yfinance EOD fallback active) ──\n")
            f.write("# FYERS_CLIENT_ID=\"\"\n")
            f.write("# FYERS_SECRET_KEY=\"\"\n\n")

    print(f"\n[Config] ✓ Backend .env written → {output_path}")

    # ── Write frontend .env.local ────────────────────────────────
    # Next.js requires NEXT_PUBLIC_ prefix for browser-accessible vars.
    # Only write in dev environment where config_dir_env is NOT set
    if not config_dir_env:
        frontend_env_path = project_root / "frontend" / ".env.local"
        with open(frontend_env_path, "w", encoding="utf-8") as f:
            f.write(f"NEXT_PUBLIC_SUPABASE_URL={env_data.get('SUPABASE_URL', '')}\n")
            f.write(f"NEXT_PUBLIC_SUPABASE_ANON_KEY={env_data.get('SUPABASE_ANON_KEY', '')}\n")
            f.write("NEXT_PUBLIC_API_URL=http://127.0.0.1:8000\n")
            f.write("NEXT_PUBLIC_CHARTING_SOCKET_URL=http://127.0.0.1:5000\n")
            f.write("NEXT_PUBLIC_CHARTING_API_URL=http://127.0.0.1:5000\n")
            if "FYERS_CLIENT_ID" not in env_data:
                f.write("NEXT_PUBLIC_FYERS_MODE=disabled\n")
            else:
                f.write("NEXT_PUBLIC_FYERS_MODE=enabled\n")
        print(f"[Config] ✓ Frontend .env.local written → {frontend_env_path}")
    print("\n" + "=" * 60)
    print(" CONFIGURATION COMPLETE")
    print("=" * 60)

if __name__ == "__main__":
    generate()
