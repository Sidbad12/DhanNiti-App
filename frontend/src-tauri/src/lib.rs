// DhanNiti — Tauri application library
// Manages: window creation, Python sidecar startup, IPC commands, and app lifecycle.

mod sidecar;

use tauri::{Manager, Emitter};
use sidecar::{Sidecars, python_cmd, uvicorn_cmd};
use std::sync::Arc;
use std::process::Command;
use std::path::PathBuf;
use std::time::Duration;
use std::thread;

// ── IPC Commands (callable from JavaScript via invoke()) ──────────────────────

/// Check if the backend is up (FastAPI /health returns 200).
#[tauri::command]
async fn check_backend_health() -> Result<bool, String> {
    let client = reqwest::Client::builder()
        .timeout(Duration::from_secs(2))
        .build()
        .map_err(|e| e.to_string())?;
    
    match client.get("http://127.0.0.1:8000/health").send().await {
        Ok(res) => Ok(res.status().is_success()),
        Err(_) => Ok(false),
    }
}

/// Check if a .env file exists in the writeable configuration folder.
#[tauri::command]
fn check_env_exists(app: tauri::AppHandle) -> bool {
    let app_data_dir = get_app_data_dir(&app);
    app_data_dir.join(".env").exists()
}

/// Run the generate_env.py wizard in a new terminal window.
/// The terminal stays open so the user can type their credentials.
#[tauri::command]
fn open_setup_wizard(app: tauri::AppHandle) -> Result<(), String> {
    let project_root = get_project_root(&app);
    let app_data_dir = get_app_data_dir(&app);
    let python = python_cmd(&project_root);
    let script = project_root.join("scripts").join("generate_env.py");
    
    // Open a new PowerShell window, set DHANNITI_CONFIG_DIR, and run the wizard interactively
    Command::new("powershell")
        .args([
            "-NoExit",
            "-Command",
            &format!(
                "$env:DHANNITI_CONFIG_DIR='{}'; Set-Location '{}'; {} '{}'",
                app_data_dir.display(),
                project_root.display(),
                python.join(" "),
                script.display(),
            ),
        ])
        .spawn()
        .map_err(|e| e.to_string())?;
    
    Ok(())
}

/// Save environment variables to .env and optionally frontend/.env.local (if in dev mode)
#[tauri::command]
fn save_env_file(
    app: tauri::AppHandle,
    supabase_url: String,
    supabase_key: String,
    groq_key: String,
    qdrant_url: String,
    qdrant_key: String,
    mem0_key: String,
    fyers_client: String,
    fyers_secret: String,
    portfolio_tickers: String,
) -> Result<(), String> {
    let app_data_dir = get_app_data_dir(&app);
    
    // 1. Write root .env inside AppData directory (or project root in dev mode)
    let env_path = app_data_dir.join(".env");
    let mut env_content = String::new();
    
    env_content.push_str("# ── Supabase (Database) ───────────────────────\n");
    env_content.push_str(&format!("SUPABASE_URL=\"{}\"\n", supabase_url));
    env_content.push_str(&format!("SUPABASE_KEY=\"{}\"\n", supabase_key));
    env_content.push_str(&format!("SUPABASE_ANON_KEY=\"{}\"\n\n", supabase_key));
    
    env_content.push_str("# ── Groq LLM (Advisor) ────────────────────────\n");
    env_content.push_str(&format!("GROQ_API_KEY=\"{}\"\n\n", groq_key));
    
    env_content.push_str("# ── Qdrant Vector Database (Required) ─────────\n");
    env_content.push_str(&format!("QDRANT_URL=\"{}\"\n", qdrant_url));
    env_content.push_str(&format!("QDRANT_API_KEY=\"{}\"\n\n", qdrant_key));
    
    if !mem0_key.is_empty() {
        env_content.push_str("# ── Mem0 AI Memory (Optional) ─────────────────\n");
        env_content.push_str(&format!("MEM0_API_KEY=\"{}\"\n\n", mem0_key));
    }
    
    if !fyers_client.is_empty() {
        env_content.push_str("# ── Fyers API (Live Data Mode) ─────────────────\n");
        env_content.push_str(&format!("FYERS_CLIENT_ID=\"{}\"\n", fyers_client));
        env_content.push_str(&format!("FYERS_SECRET_KEY=\"{}\"\n\n", fyers_secret));
    } else {
        env_content.push_str("# ── Fyers API — not configured (yfinance EOD fallback active) ──\n");
        env_content.push_str("# FYERS_CLIENT_ID=\"\"\n");
        env_content.push_str("# FYERS_SECRET_KEY=\"\"\n\n");
    }

    if !portfolio_tickers.is_empty() {
        env_content.push_str("# ── Custom Stock Universe ───────────────────────\n");
        env_content.push_str(&format!("PORTFOLIO_TICKERS=\"{}\"\n\n", portfolio_tickers));
    }
    
    std::fs::write(&env_path, env_content)
        .map_err(|e| format!("Failed to write backend .env: {}", e))?;
        
    // 2. Write frontend/.env.local (only during development)
    if cfg!(debug_assertions) {
        let project_root = get_project_root(&app);
        let frontend_env_path = project_root.join("frontend").join(".env.local");
        let mut frontend_content = String::new();
        frontend_content.push_str(&format!("NEXT_PUBLIC_SUPABASE_URL={}\n", supabase_url));
        frontend_content.push_str(&format!("NEXT_PUBLIC_SUPABASE_ANON_KEY={}\n", supabase_key));
        frontend_content.push_str("NEXT_PUBLIC_API_URL=http://127.0.0.1:8000\n");
        frontend_content.push_str("NEXT_PUBLIC_CHARTING_SOCKET_URL=http://127.0.0.1:5000\n");
        frontend_content.push_str("NEXT_PUBLIC_CHARTING_API_URL=http://127.0.0.1:5000\n");
        if fyers_client.is_empty() {
            frontend_content.push_str("NEXT_PUBLIC_FYERS_MODE=disabled\n");
        } else {
            frontend_content.push_str("NEXT_PUBLIC_FYERS_MODE=enabled\n");
        }
        
        let _ = std::fs::create_dir_all(frontend_env_path.parent().unwrap());
        let _ = std::fs::write(&frontend_env_path, frontend_content);
    }
        
    Ok(())
}

/// Run direct PostgreSQL schema migration via python init_supabase.py
#[tauri::command]
fn run_supabase_init(app: tauri::AppHandle, database_url: String) -> Result<String, String> {
    let project_root = get_project_root(&app);
    let python = python_cmd(&project_root);
    let script = project_root.join("scripts").join("init_supabase.py");
    
    let mut cmd = Command::new(&python[0]);
    if python.len() > 1 {
        cmd.args(&python[1..]);
    }
    
    let output = cmd
        .arg(script)
        .env("DATABASE_URL", database_url)
        .current_dir(&project_root)
        .output()
        .map_err(|e| format!("Failed to run init_supabase.py: {}", e))?;
        
    let stdout = String::from_utf8_lossy(&output.stdout).to_string();
    let stderr = String::from_utf8_lossy(&output.stderr).to_string();
    
    if output.status.success() {
        Ok(stdout)
    } else {
        Err(format!("Error: {}\nStderr: {}", stdout, stderr))
    }
}

/// Get the current Fyers mode from the .env file.
#[tauri::command]
fn get_fyers_mode(app: tauri::AppHandle) -> String {
    let app_data_dir = get_app_data_dir(&app);
    let env_path = app_data_dir.join(".env");
    
    if let Ok(content) = std::fs::read_to_string(env_path) {
        for line in content.lines() {
            if line.starts_with("FYERS_CLIENT_ID=") {
                let val = line.trim_start_matches("FYERS_CLIENT_ID=").trim_matches('"');
                if !val.is_empty() {
                    return "enabled".to_string();
                }
            }
        }
    }
    "disabled".to_string()
}

/// IPC command to reload environment variables and restart python sidecars dynamically
#[tauri::command]
fn restart_sidecars(app: tauri::AppHandle) -> Result<(), String> {
    if let Some(sidecars) = app.try_state::<Arc<Sidecars>>() {
        println!("[DhanNiti] Restarting python sidecar servers...");
        sidecars.kill_all();
        
        load_env_into_process(&app);
        
        let project_root = get_project_root(&app);
        let new_sidecars = spawn_sidecars(&project_root);
        
        let mut api_guard = sidecars.api.lock().unwrap();
        let mut charting_guard = sidecars.charting.lock().unwrap();
        
        let mut new_api_guard = new_sidecars.api.lock().unwrap();
        let mut new_charting_guard = new_sidecars.charting.lock().unwrap();
        
        *api_guard = new_api_guard.take();
        *charting_guard = new_charting_guard.take();
        
        println!("[DhanNiti] Python sidecar servers successfully restarted.");
        
        // Wait a brief moment and emit the servers-ready event again
        let app_handle = app.clone();
        thread::spawn(move || {
            thread::sleep(Duration::from_secs(3));
            let _ = app_handle.emit("servers-ready", ());
        });
    } else {
        return Err("Sidecar manager state was not initialized.".to_string());
    }
    Ok(())
}

// ── App lifecycle ─────────────────────────────────────────────────────────────

fn get_project_root(app: &tauri::AppHandle) -> PathBuf {
    // In dev: go up from frontend/src-tauri/ to the project root
    // In release: app is installed, project root = resource directory (read-only)
    if cfg!(debug_assertions) {
        PathBuf::from(env!("CARGO_MANIFEST_DIR"))
            .parent() // frontend/
            .and_then(|p| p.parent()) // project root
            .unwrap_or(&PathBuf::from("."))
            .to_path_buf()
    } else {
        app.path().resource_dir()
            .unwrap_or_else(|_| PathBuf::from("."))
    }
}

fn get_app_data_dir(app: &tauri::AppHandle) -> PathBuf {
    // In dev: same as project root for easier local development/inspections
    // In release: standard writeable AppData folder for the user
    if cfg!(debug_assertions) {
        get_project_root(app)
    } else {
        let path = app.path().app_data_dir().unwrap_or_else(|_| PathBuf::from("."));
        let _ = std::fs::create_dir_all(&path);
        path
    }
}

fn load_env_into_process(app: &tauri::AppHandle) {
    let app_data_dir = get_app_data_dir(app);
    let env_path = app_data_dir.join(".env");
    if let Ok(content) = std::fs::read_to_string(&env_path) {
        for line in content.lines() {
            let trimmed = line.trim();
            if trimmed.is_empty() || trimmed.starts_with('#') {
                continue;
            }
            if let Some((key, val)) = trimmed.split_once('=') {
                let key = key.trim();
                let val = val.trim().trim_matches('"').trim_matches('\'');
                std::env::set_var(key, val);
            }
        }
        println!("[DhanNiti] Process environment variables loaded from: {}", env_path.display());
    } else {
        println!("[DhanNiti] No existing environment file to load at: {}", env_path.display());
    }
}

fn spawn_sidecars(project_root: &PathBuf) -> Arc<Sidecars> {
    let sidecars = Arc::new(Sidecars::new());
    
    let uvicorn = uvicorn_cmd(project_root);
    let python = python_cmd(project_root);
    let root = project_root.clone();
    
    // ── FastAPI server (:8000) ──────────────────────────────────
    {
        let mut args = uvicorn.clone();
        args.extend(["src.api.server:app".to_string(), "--host".to_string(), "127.0.0.1".to_string(), "--port".to_string(), "8000".to_string()]);
        
        let child = Command::new(&args[0])
            .args(&args[1..])
            .current_dir(&root)
            .spawn();
        
        match child {
            Ok(c) => {
                *sidecars.api.lock().unwrap() = Some(c);
                println!("[DhanNiti] FastAPI server started on :8000");
            }
            Err(e) => eprintln!("[DhanNiti] Failed to start FastAPI: {e}"),
        }
    }
    
    // ── Charting server (:5000) ─────────────────────────────────
    {
        let chart_script = root.join("src").join("charting").join("server.py");
        let mut args = python.clone();
        args.push(chart_script.to_string_lossy().to_string());
        args.extend(["--port".to_string(), "5000".to_string()]);
        
        let child = Command::new(&args[0])
            .args(&args[1..])
            .current_dir(&root)
            .spawn();
        
        match child {
            Ok(c) => {
                *sidecars.charting.lock().unwrap() = Some(c);
                println!("[DhanNiti] Charting server started on :5000");
            }
            Err(e) => eprintln!("[DhanNiti] Failed to start charting server: {e}"),
        }
    }
    
    sidecars
}

// ── Tauri app entry ───────────────────────────────────────────────────────────

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_shell::init())
        .plugin(tauri_plugin_fs::init())
        .plugin(tauri_plugin_dialog::init())
        .plugin(tauri_plugin_process::init())
        .invoke_handler(tauri::generate_handler![
            check_backend_health,
            check_env_exists,
            open_setup_wizard,
            get_fyers_mode,
            save_env_file,
            run_supabase_init,
            restart_sidecars,
        ])
        .setup(|app| {
            let app_handle = app.handle();
            
            // Load environment keys into Rust process space so Python subprocesses inherit them
            load_env_into_process(app_handle);
            
            let project_root = get_project_root(app_handle);
            println!("[DhanNiti] Project root: {}", project_root.display());
            
            // Spawn Python sidecar processes
            let sidecars = spawn_sidecars(&project_root);
            
            // Store sidecars in app state so we can kill them on exit
            app.manage(sidecars.clone());
            
            // Wait a moment for servers to warm up, then emit ready event
            let app_handle_clone = app_handle.clone();
            thread::spawn(move || {
                thread::sleep(Duration::from_secs(3));
                let _ = app_handle_clone.emit("servers-ready", ());
            });
            
            Ok(())
        })
        .on_window_event(|window, event| {
            if let tauri::WindowEvent::CloseRequested { .. } = event {
                // Kill Python sidecars cleanly
                if let Some(sidecars) = window.app_handle().try_state::<Arc<Sidecars>>() {
                    sidecars.kill_all();
                    println!("[DhanNiti] Sidecars killed. Goodbye.");
                }
            }
        })
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
