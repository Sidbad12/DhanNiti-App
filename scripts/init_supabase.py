# scripts/init_supabase.py
import os
import sys
from pathlib import Path

def run_init():
    project_root = Path(__file__).resolve().parent.parent
    sql_dir = project_root / "sql"
    
    # Read files in order
    sql_files = ["001_create_tables.sql", "002_create_indexes.sql", "003_rls_policies.sql"]
    
    consolidated_sql = []
    consolidated_sql.append("-- ========================================================")
    consolidated_sql.append("-- DHANNITI CONSOLIDATED DATABASE SETUP SCHEMA")
    consolidated_sql.append(f"-- Generated on: {Path(__file__).name}")
    consolidated_sql.append("-- ========================================================\n")
    
    for filename in sql_files:
        filepath = sql_dir / filename
        if filepath.exists():
            consolidated_sql.append(f"-- --- SECTION: {filename} ---")
            with open(filepath, "r", encoding="utf-8") as f:
                consolidated_sql.append(f.read())
            consolidated_sql.append("\n")
        else:
            print(f"Warning: SQL file {filename} not found in sql/ directory.")
            
    schema_code = "\n".join(consolidated_sql)
    
    # Write consolidated schema file
    output_path = project_root / "sql" / "consolidated_schema.sql"
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(schema_code)
        
    print(f"\n[Database] Consolidated schema written to: {output_path}")
    
    # Check if direct postgres connection details are present
    db_url = os.getenv("DATABASE_URL")
    if db_url:
        print("[Database] DATABASE_URL detected in environment. Attempting direct schema application...")
        try:
            # Try to connect using psycopg2 or pg8000
            import psycopg2
            conn = psycopg2.connect(db_url)
            conn.autocommit = True
            cursor = conn.cursor()
            
            print("  Applying table definitions...")
            cursor.execute(schema_code)
            
            cursor.close()
            conn.close()
            print("[Database] ✓ SQL Schema successfully applied to Supabase database.")
            return True
        except ImportError:
            try:
                import pg8000
                # Split DB connection parameters or use client connection
                # pg8000 is clean pure-python driver
                import urllib.parse as urlparse
                url = urlparse.urlparse(db_url)
                username = url.username
                password = url.password
                database = url.path[1:]
                hostname = url.hostname
                port = url.port or 5432
                
                conn = pg8000.connect(
                    user=username,
                    password=password,
                    host=hostname,
                    port=port,
                    database=database
                )
                cursor = conn.cursor()
                
                # Execute statement by statement since pg8000 doesn't support multiple commands in one query
                statements = [s.strip() for s in schema_code.split(";") if s.strip()]
                for stmt in statements:
                    cursor.execute(stmt)
                    
                conn.commit()
                cursor.close()
                conn.close()
                print("[Database] ✓ SQL Schema successfully applied to Supabase database via pg8000.")
                return True
            except Exception as e:
                print(f"[Database] Failed to execute schema via pg8000: {e}")
        except Exception as e:
            print(f"[Database] Failed to execute schema via psycopg2: {e}")
            
    # If no database URL or direct connection failed, guide the user to the Supabase dashboard
    print("\n" + "=" * 80)
    print(" MANUAL SUPABASE INITIALIZATION REQUIRED")
    print("=" * 80)
    print("Since a direct PostgreSQL database connection could not be established:")
    print("1. Open your Supabase Dashboard: https://supabase.com/dashboard")
    print("2. Navigate to your project, then open 'SQL Editor' in the left menu.")
    print("3. Click 'New query' (or use default SQL file scratchpad).")
    print("4. Copy the complete SQL content from:")
    print(f"   [consolidated_schema.sql]({output_path.as_uri()})")
    print("5. Paste the SQL and click the 'Run' button on the top-right.")
    print("=" * 80 + "\n")
    return True

if __name__ == "__main__":
    run_init()
