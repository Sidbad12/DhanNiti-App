# setup.py
import os
import sys
import shutil
import subprocess
import webbrowser
import time
from pathlib import Path

def print_banner():
    banner = """
══════════════════════════════════════════════════════════════════════
               DhanNiti — AI Quant Portfolio Optimizer                
                   Local Installer & Configuration                    
══════════════════════════════════════════════════════════════════════
"""
    print(banner)

def check_dependencies():
    print("[1/7] Verifying System Dependencies...")
    
    # 1. Check Python version
    py_version = sys.version_info
    if py_version.major < 3 or (py_version.major == 3 and py_version.minor < 10):
        print(f"  ✗ Python version {sys.version} is not supported. Please use Python >= 3.10.")
        return False
    print(f"  ✓ Python version: {py_version.major}.{py_version.minor}.{py_version.micro}")
    
    # 2. Check Node version
    try:
        node_ver_proc = subprocess.run(["node", "--version"], capture_output=True, text=True, check=True)
        node_version = node_ver_proc.stdout.strip().lstrip("v")
        major_node = int(node_version.split(".")[0])
        if major_node < 18:
            print(f"  ✗ Node version {node_version} is too old. Please use Node.js >= 18.")
            return False
        print(f"  ✓ Node.js version: v{node_version}")
    except (subprocess.SubprocessError, FileNotFoundError):
        print("  ✗ Node.js not found in system path. Please install Node.js >= 18.")
        return False
        
    # 3. Check npm
    try:
        subprocess.run(["npm", "--version"], capture_output=True, check=True)
        print("  ✓ npm is installed and accessible.")
    except (subprocess.SubprocessError, FileNotFoundError):
        print("  ✗ npm package manager not found. Please install npm/Node.")
        return False
        
    print("  ✓ System dependency checks passed successfully.\n")
    return True

def install_dependencies():
    print("[2/7] Installing Project Dependencies...")
    project_root = Path(__file__).resolve().parent
    
    # Python dependencies
    print("  Installing Python backend dependencies...")
    has_poetry = shutil.which("poetry") is not None
    
    try:
        if has_poetry:
            print("  Running: poetry install")
            subprocess.run(["poetry", "install"], cwd=project_root, check=True)
        else:
            print("  Running: pip install -r requirements.txt")
            subprocess.run([sys.executable, "-m", "pip", "install", "-r", "requirements.txt"], cwd=project_root, check=True)
        print("  ✓ Python dependencies installed.")
    except subprocess.CalledProcessError as e:
        print(f"  ✗ Error installing Python dependencies: {e}")
        return False
        
    # Node dependencies
    print("\n  Installing Next.js frontend dependencies (in frontend/)...")
    frontend_dir = project_root / "frontend"
    try:
        print("  Running: npm install")
        subprocess.run(["npm", "install"], cwd=frontend_dir, check=True)
        print("  ✓ Next.js dependencies installed.")
    except subprocess.CalledProcessError as e:
        print(f"  ✗ Error installing Next.js dependencies: {e}")
        return False
        
    print("  ✓ Dependency installations complete.\n")
    return True

def run_env_wizard():
    print("[3/7] Running Interactive Environment Wizard...")
    project_root = Path(__file__).resolve().parent
    script_path = project_root / "scripts" / "generate_env.py"
    
    # We execute this in the same process or a subprocess, but since it is interactive, 
    # we run it directly by importing its main logic or calling it as subprocess
    # A subprocess with sys.executable ensures standard input streams work perfectly
    try:
        subprocess.run([sys.executable, str(script_path)], check=True)
        return True
    except subprocess.CalledProcessError:
        print("  ✗ Environment setup failed.")
        return False

def init_database_schema():
    print("[4/7] Initializing Database Tables...")
    project_root = Path(__file__).resolve().parent
    script_path = project_root / "scripts" / "init_supabase.py"
    try:
        subprocess.run([sys.executable, str(script_path)], check=True)
        return True
    except subprocess.CalledProcessError:
        print("  ✗ Database initialization failed.")
        return False

def seed_price_candles():
    print("[5/7] Seeding Historical Price Data...")
    project_root = Path(__file__).resolve().parent
    script_path = project_root / "scripts" / "seed_yfinance.py"
    
    # Ask if user wants to run seeder now
    response = input("  Would you like to seed 1-year daily candlestick data now? (y/n) [y]: ").strip().lower()
    if response in ('n', 'no'):
        print("  Skipping historical price seeding. You can seed manually using 'python scripts/seed_yfinance.py'.\n")
        return True
        
    try:
        subprocess.run([sys.executable, str(script_path)], check=True)
        return True
    except subprocess.CalledProcessError:
        print("  ✗ Price seeding failed.")
        return False

def run_pipeline_smoke_test():
    print("[6/7] Running Pipeline Smoke Tests...")
    project_root = Path(__file__).resolve().parent
    script_path = project_root / "scripts" / "test_pipeline.py"
    try:
        subprocess.run([sys.executable, str(script_path)], check=True)
        return True
    except subprocess.CalledProcessError:
        print("  ✗ Smoke test returned errors.")
        return False

def launch_application():
    print("[7/7] Starting DhanNiti Platform...")
    project_root = Path(__file__).resolve().parent
    
    print("\n  FastAPI backend server starts on:  http://127.0.0.1:8000")
    print("  Next.js frontend server starts on: http://127.0.0.1:3000")
    print("  Websockets charting server on:     http://127.0.0.1:5000\n")
    
    print("  Starting background processes...")
    
    # Check if poetry or virtualenv executable is used
    has_poetry = shutil.which("poetry") is not None
    python_cmd = ["poetry", "run", "python"] if has_poetry else [sys.executable]
    uvicorn_cmd = ["poetry", "run", "uvicorn"] if has_poetry else ["uvicorn"]
    
    # 1. Start charting socket server
    chart_script = project_root / "src" / "charting" / "server.py"
    chart_proc = subprocess.Popen(python_cmd + [str(chart_script), "--port", "5000"], cwd=project_root)
    
    # 2. Start API server
    api_proc = subprocess.Popen(uvicorn_cmd + ["src.api.server:app", "--host", "127.0.0.1", "--port", "8000"], cwd=project_root)
    
    # 3. Start Next.js dev server
    npm_cmd = shutil.which("npm")
    frontend_dir = project_root / "frontend"
    next_proc = subprocess.Popen([npm_cmd, "run", "dev"], cwd=frontend_dir)
    
    print("  Waiting 5 seconds for systems to warm up...")
    time.sleep(5)
    
    # Launch browser
    try:
        webbrowser.open("http://127.0.0.1:3000/dashboard")
    except Exception:
        pass
        
    print("\n" + "=" * 60)
    print(" DHANNITI RUNNING SUCCESSFULLY")
    print("=" * 60)
    print("Press Ctrl+C inside the terminal to shut down all processes.")
    print("=" * 60 + "\n")
    
    try:
        # Keep process alive until interrupted
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nShutting down DhanNiti services...")
        chart_proc.terminate()
        api_proc.terminate()
        next_proc.terminate()
        print("Goodbye!")
        sys.exit(0)

def main():
    print_banner()
    
    if not check_dependencies():
        print("\n✗ Setup aborted due to missing dependencies.")
        sys.exit(1)
        
    if not install_dependencies():
        print("\n✗ Setup aborted during package installation.")
        sys.exit(1)
        
    if not run_env_wizard():
        print("\n✗ Setup aborted during environment configuration.")
        sys.exit(1)
        
    if not init_database_schema():
        print("\n✗ Setup aborted during database initialization.")
        sys.exit(1)
        
    if not seed_price_candles():
        print("\n✗ Setup aborted during price seeding.")
        sys.exit(1)
        
    if not run_pipeline_smoke_test():
        print("\n✗ Warning: Pipeline smoke test failed. Check configurations.")
        proceed = input("Do you still want to try launching the application? (y/n) [y]: ").strip().lower()
        if proceed in ('n', 'no'):
            sys.exit(1)
            
    launch_application()

if __name__ == "__main__":
    main()
