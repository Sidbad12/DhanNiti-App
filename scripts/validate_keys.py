# scripts/validate_keys.py
import os
import requests
import sys

def validate_groq(key):
    """Verify Groq API Key by sending a ping completion request."""
    if not key or not key.startswith("gsk_"):
        return False, "Groq API key must start with 'gsk_'"
    
    url = "https://api.groq.com/openai/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json"
    }
    data = {
        "model": "llama3-8b-8192",
        "messages": [{"role": "user", "content": "ping"}],
        "max_tokens": 5
    }
    
    try:
        response = requests.post(url, headers=headers, json=data, timeout=8)
        if response.status_code == 200:
            return True, "Groq connection successful"
        else:
            err_msg = response.json().get("error", {}).get("message", "Unknown error")
            return False, f"Groq validation failed (HTTP {response.status_code}): {err_msg}"
    except Exception as e:
        return False, f"Groq request failed: {str(e)}"

def validate_supabase(url, anon_key):
    """Verify Supabase connection and authorization key."""
    if not url or not url.startswith("https://"):
        return False, "Supabase URL must start with 'https://'"
    if not anon_key:
        return False, "Supabase key cannot be empty"
        
    endpoint = f"{url.rstrip('/')}/rest/v1/"
    headers = {
        "apikey": anon_key,
        "Authorization": f"Bearer {anon_key}"
    }
    
    try:
        # Check standard Supabase REST endpoint response
        response = requests.get(endpoint, headers=headers, timeout=8)
        if response.status_code == 200:
            return True, "Supabase connected successfully"
        else:
            return False, f"Supabase auth failed (HTTP {response.status_code})"
    except Exception as e:
        return False, f"Supabase request failed: {str(e)}"

def validate_yfinance():
    """Verify internet connectivity and yfinance pricing fetches."""
    try:
        import yfinance as yf
        ticker = yf.Ticker("RELIANCE.NS")
        # Use a custom session header similar to DhanNiti's extractor.py to bypass blocks
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        }
        session = requests.Session()
        session.headers.update(headers)
        
        hist = ticker.history(period="5d", session=session)
        if hist.empty:
            return False, "yfinance returned empty historical data frame"
        last_close = hist['Close'].iloc[-1]
        return True, f"yfinance working (RELIANCE last close: ₹{last_close:.2f})"
    except Exception as e:
        return False, f"yfinance failed: {str(e)}"

def validate_fyers(client_id, secret):
    """Perform structure validations on Fyers API credentials."""
    if not client_id or len(client_id) < 6:
        return False, "Fyers Client ID is too short or invalid"
    if not secret or len(secret) < 8:
        return False, "Fyers App Secret is too short or invalid"
    return True, "Fyers credentials format valid (interactive OAuth will verify keys during first execution)"

if __name__ == "__main__":
    # Smoke test of validation helpers using env variables if run directly
    print("Smoke testing key validation script...")
    
    groq_key = os.getenv("GROQ_API_KEY")
    if groq_key:
        ok, msg = validate_groq(groq_key)
        print(f"Groq: {'[OK]' if ok else '[FAILED]'} - {msg}")
        
    sb_url = os.getenv("SUPABASE_URL")
    sb_key = os.getenv("SUPABASE_KEY") or os.getenv("SUPABASE_ANON_KEY")
    if sb_url and sb_key:
        ok, msg = validate_supabase(sb_url, sb_key)
        print(f"Supabase: {'[OK]' if ok else '[FAILED]'} - {msg}")
        
    ok, msg = validate_yfinance()
    print(f"yfinance: {'[OK]' if ok else '[FAILED]'} - {msg}")
