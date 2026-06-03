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

// Scheduler & Notification imports
use tokio_cron_scheduler::{Job, JobScheduler};
use tauri_plugin_notification::NotificationExt;
use tauri::menu::{Menu, MenuItem};
use tauri::tray::{TrayIconBuilder, TrayIconEvent};

// Process priority controls
#[cfg(windows)]
fn set_idle_priority(child: &std::process::Child) {
    use winapi::um::processthreadsapi::SetPriorityClass;
    use winapi::um::winbase::IDLE_PRIORITY_CLASS;
    use std::os::windows::io::AsRawHandle;
    
    let handle = child.as_raw_handle();
    unsafe {
        let ok = SetPriorityClass(handle as _, IDLE_PRIORITY_CLASS);
        if ok == 0 {
            eprintln!("[DhanNiti] Failed to set process priority to IDLE_PRIORITY_CLASS.");
        } else {
            println!("[DhanNiti] Process priority set to IDLE successfully.");
        }
    }
}

#[cfg(not(windows))]
fn set_idle_priority(child: &std::process::Child) {
    #[cfg(unix)]
    {
        use libc::{setpriority, PRIO_PROCESS};
        unsafe {
            let res = setpriority(PRIO_PROCESS, child.id() as _, 19);
            if res != 0 {
                eprintln!("[DhanNiti] Failed to set process nice value to 19.");
            } else {
                println!("[DhanNiti] Process nice value set to 19 successfully.");
            }
        }
    }
}

#[derive(serde::Serialize, serde::Deserialize, Clone, Debug)]
pub struct SchedulerConfig {
    pub enabled: bool,
    pub cron_expression: String,
}

impl Default for SchedulerConfig {
    fn default() -> Self {
        Self {
            enabled: true,
            cron_expression: "0 0 11 * * 1-5".to_string(), // Mon–Fri 11:00 UTC (4:30 PM IST)
        }
    }
}

#[derive(serde::Serialize, serde::Deserialize, Clone, Debug)]
pub struct SchedulerStatus {
    pub enabled: bool,
    pub cron_expression: String,
    pub last_run_time: Option<String>,
    pub last_run_status: Option<String>,
    pub is_running: bool,
}

pub struct SchedulerState {
    pub scheduler: JobScheduler,
    pub config: std::sync::Mutex<SchedulerConfig>,
    pub job_id: tokio::sync::Mutex<Option<uuid::Uuid>>,
    pub last_run_time: std::sync::Mutex<Option<String>>,
    pub last_run_status: std::sync::Mutex<Option<String>>,
    pub is_running: std::sync::Mutex<bool>,
}

fn run_pipeline_job(app_handle: tauri::AppHandle) -> Result<std::process::Child, String> {
    let project_root = get_project_root(&app_handle);
    
    // 1. Send start notification
    let _ = app_handle.notification()
        .builder()
        .title("DhanNiti Sentinel")
        .body("Daily portfolio rebalance pipeline has started in background (low CPU priority).")
        .show();
        
    // 2. Perform git pull
    println!("[DhanNiti Scheduler] Running git pull to fetch latest models...");
    let git_status = Command::new("git")
        .arg("pull")
        .current_dir(&project_root)
        .status();
    match git_status {
        Ok(status) => {
            if status.success() {
                println!("[DhanNiti Scheduler] git pull completed successfully.");
            } else {
                eprintln!("[DhanNiti Scheduler] git pull failed with status: {:?}", status);
            }
        }
        Err(e) => {
            eprintln!("[DhanNiti Scheduler] Failed to run git pull (continuing anyway): {}", e);
        }
    }
    
    // 3. Resolve python command
    let python = python_cmd(&project_root);
    let mut cmd = Command::new(&python[0]);
    if python.len() > 1 {
        cmd.args(&python[1..]);
    }
    
    cmd.args(["-m", "src.main"])
       .current_dir(&project_root);
       
    // Spawning the process
    println!("[DhanNiti Scheduler] Spawning python pipeline process: {:?}", cmd);
    let child = cmd.spawn().map_err(|e| format!("Failed to spawn python pipeline: {}", e))?;
    
    // Set low process priority
    set_idle_priority(&child);
    
    Ok(child)
}

async fn start_scheduler_job(state: Arc<SchedulerState>, app_handle: tauri::AppHandle) -> Result<(), String> {
    let mut job_id_guard = state.job_id.lock().await;
    
    // Stop existing job if any
    if let Some(id) = job_id_guard.take() {
        let _ = state.scheduler.remove(&id).await;
    }
    
    let cron = {
        let config = state.config.lock().unwrap();
        config.cron_expression.clone()
    };
    
    let state_weak = Arc::downgrade(&state);
    let app_handle_weak = app_handle.clone();
    
    let job = Job::new_async(cron.as_str(), move |_uuid, _l| {
        let state_opt = state_weak.upgrade();
        let app_handle = app_handle_weak.clone();
        Box::pin(async move {
            if let Some(state) = state_opt {
                println!("[DhanNiti Scheduler] Cron job triggered!");
                
                // Check if already running to prevent overlap
                {
                    let mut is_running = state.is_running.lock().unwrap();
                    if *is_running {
                        println!("[DhanNiti Scheduler] Job already in progress, skipping.");
                        return;
                    }
                    *is_running = true;
                }
                
                // Update state variables
                {
                    let now = chrono::Local::now().format("%Y-%m-%d %H:%M:%S").to_string();
                    *state.last_run_time.lock().unwrap() = Some(now);
                    *state.last_run_status.lock().unwrap() = Some("Running...".to_string());
                }
                
                let _ = app_handle.emit("scheduler-run-started", ());
                
                // Run the pipeline
                let run_result = run_pipeline_job(app_handle.clone());
                
                match run_result {
                    Ok(child) => {
                        // Wait for child in separate async task
                        let state_clone = state.clone();
                        let app_handle_clone = app_handle.clone();
                        tauri::async_runtime::spawn(async move {
                            let mut child = child;
                            let exit_status = child.wait();
                            
                            let mut is_running = state_clone.is_running.lock().unwrap();
                            *is_running = false;
                            
                            match exit_status {
                                Ok(status) => {
                                    if status.success() {
                                        println!("[DhanNiti Scheduler] Pipeline run succeeded.");
                                        *state_clone.last_run_status.lock().unwrap() = Some("Success".to_string());
                                        let _ = app_handle_clone.notification()
                                            .builder()
                                            .title("DhanNiti Daily Run")
                                            .body("Daily optimization pipeline completed successfully.")
                                            .show();
                                        let _ = app_handle_clone.emit("scheduler-run-finished", "success".to_string());
                                    } else {
                                        let code_str = status.code().map(|c| c.to_string()).unwrap_or_else(|| "unknown".to_string());
                                        eprintln!("[DhanNiti Scheduler] Pipeline run failed with status: {}", code_str);
                                        *state_clone.last_run_status.lock().unwrap() = Some(format!("Failed (code {})", code_str));
                                        let _ = app_handle_clone.notification()
                                            .builder()
                                            .title("DhanNiti Daily Run")
                                            .body(format!("Daily optimization pipeline failed (code {}).", code_str))
                                            .show();
                                        let _ = app_handle_clone.emit("scheduler-run-finished", format!("failed: exit code {}", code_str));
                                    }
                                }
                                Err(e) => {
                                    eprintln!("[DhanNiti Scheduler] Error waiting for pipeline: {}", e);
                                    *state_clone.last_run_status.lock().unwrap() = Some(format!("Error: {}", e));
                                    let _ = app_handle_clone.notification()
                                        .builder()
                                        .title("DhanNiti Daily Run")
                                        .body(format!("Daily optimization pipeline error: {}.", e))
                                        .show();
                                    let _ = app_handle_clone.emit("scheduler-run-finished", format!("error: {}", e));
                                }
                            }
                        });
                    }
                    Err(e) => {
                        let mut is_running = state.is_running.lock().unwrap();
                        *is_running = false;
                        *state.last_run_status.lock().unwrap() = Some(format!("Failed to start: {}", e));
                        
                        let _ = app_handle.notification()
                            .builder()
                            .title("DhanNiti Daily Run")
                            .body(format!("Failed to start daily optimization: {}.", e))
                            .show();
                        let _ = app_handle.emit("scheduler-run-finished", format!("failed to start: {}", e));
                    }
                }
            }
        })
    })
    .map_err(|e| format!("Failed to create job: {}", e))?;
    
    let id = job.guid();
    state.scheduler.add(job).await.map_err(|e| format!("Failed to add job: {}", e))?;
    *job_id_guard = Some(id);
    
    // Make sure the scheduler itself is started
    let _ = state.scheduler.start().await;
    
    Ok(())
}

// ── Scheduler IPC Commands ───────────────────────────────────────────────────

#[tauri::command]
async fn get_scheduler_status(state: tauri::State<'_, Arc<SchedulerState>>) -> Result<SchedulerStatus, String> {
    let config = state.config.lock().unwrap().clone();
    let last_run_time = state.last_run_time.lock().unwrap().clone();
    let last_run_status = state.last_run_status.lock().unwrap().clone();
    let is_running = state.is_running.lock().unwrap().clone();
    
    Ok(SchedulerStatus {
        enabled: config.enabled,
        cron_expression: config.cron_expression,
        last_run_time,
        last_run_status,
        is_running,
    })
}

#[tauri::command]
async fn toggle_scheduler(
    app: tauri::AppHandle,
    state: tauri::State<'_, Arc<SchedulerState>>,
    enabled: bool,
) -> Result<SchedulerStatus, String> {
    let cron_expression = {
        let mut config = state.config.lock().unwrap();
        config.enabled = enabled;
        let cron = config.cron_expression.clone();
        
        // Save to file
        let app_data_dir = get_app_data_dir(&app);
        let config_path = app_data_dir.join("scheduler_config.json");
        if let Ok(content) = serde_json::to_string_pretty(&*config) {
            let _ = std::fs::write(config_path, content);
        }
        cron
    };
    
    if enabled {
        let state_clone = state.inner().clone();
        let app_handle = app.clone();
        start_scheduler_job(state_clone, app_handle).await?;
        println!("[DhanNiti Scheduler] Scheduler enabled and started.");
    } else {
        let mut job_id_guard = state.job_id.lock().await;
        if let Some(id) = job_id_guard.take() {
            let _ = state.scheduler.remove(&id).await;
            println!("[DhanNiti Scheduler] Scheduler job removed.");
        }
    }
    
    let last_run_time = state.last_run_time.lock().unwrap().clone();
    let last_run_status = state.last_run_status.lock().unwrap().clone();
    let is_running = state.is_running.lock().unwrap().clone();
    
    Ok(SchedulerStatus {
        enabled,
        cron_expression,
        last_run_time,
        last_run_status,
        is_running,
    })
}

#[tauri::command]
async fn trigger_scheduler_now(
    app: tauri::AppHandle,
    state: tauri::State<'_, Arc<SchedulerState>>,
) -> Result<String, String> {
    // Check if already running
    {
        let mut is_running = state.is_running.lock().unwrap();
        if *is_running {
            return Err("A scheduler run is already in progress.".to_string());
        }
        *is_running = true;
    }
    
    // Update state variables
    {
        let now = chrono::Local::now().format("%Y-%m-%d %H:%M:%S").to_string();
        *state.last_run_time.lock().unwrap() = Some(now);
        *state.last_run_status.lock().unwrap() = Some("Running (manual trigger)...".to_string());
    }
    
    let _ = app.emit("scheduler-run-started", ());
    
    let run_result = run_pipeline_job(app.clone());
    
    match run_result {
        Ok(child) => {
            let state_clone = state.inner().clone();
            let app_handle_clone = app.clone();
            tauri::async_runtime::spawn(async move {
                let mut child = child;
                let exit_status = child.wait();
                
                let mut is_running = state_clone.is_running.lock().unwrap();
                *is_running = false;
                
                match exit_status {
                    Ok(status) => {
                        if status.success() {
                            println!("[DhanNiti Scheduler] Manual pipeline run succeeded.");
                            *state_clone.last_run_status.lock().unwrap() = Some("Success (manual)".to_string());
                            let _ = app_handle_clone.notification()
                                .builder()
                                .title("DhanNiti Sentinel")
                                .body("Manual portfolio optimization completed successfully.")
                                .show();
                            let _ = app_handle_clone.emit("scheduler-run-finished", "success".to_string());
                        } else {
                            let code_str = status.code().map(|c| c.to_string()).unwrap_or_else(|| "unknown".to_string());
                            eprintln!("[DhanNiti Scheduler] Manual pipeline run failed: {}", code_str);
                            *state_clone.last_run_status.lock().unwrap() = Some(format!("Failed (code {})", code_str));
                            let _ = app_handle_clone.notification()
                                .builder()
                                .title("DhanNiti Sentinel")
                                .body(format!("Manual optimization failed (code {}).", code_str))
                                .show();
                            let _ = app_handle_clone.emit("scheduler-run-finished", format!("failed: exit code {}", code_str));
                        }
                    }
                    Err(e) => {
                        eprintln!("[DhanNiti Scheduler] Error waiting for manual pipeline: {}", e);
                        *state_clone.last_run_status.lock().unwrap() = Some(format!("Error: {}", e));
                        let _ = app_handle_clone.notification()
                            .builder()
                            .title("DhanNiti Sentinel")
                            .body(format!("Manual optimization error: {}.", e))
                            .show();
                        let _ = app_handle_clone.emit("scheduler-run-finished", format!("error: {}", e));
                    }
                }
            });
            Ok("Pipeline triggered successfully.".to_string())
        }
        Err(e) => {
            let mut is_running = state.is_running.lock().unwrap();
            *is_running = false;
            *state.last_run_status.lock().unwrap() = Some(format!("Manual trigger failed to start: {}", e));
            
            let _ = app.notification()
                .builder()
                .title("DhanNiti Sentinel")
                .body(format!("Manual optimization failed to start: {}.", e))
                .show();
            let _ = app.emit("scheduler-run-finished", format!("failed to start: {}", e));
            Err(e)
        }
    }
}

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
        .plugin(tauri_plugin_notification::init())
        .invoke_handler(tauri::generate_handler![
            check_backend_health,
            check_env_exists,
            open_setup_wizard,
            get_fyers_mode,
            save_env_file,
            run_supabase_init,
            restart_sidecars,
            get_scheduler_status,
            toggle_scheduler,
            trigger_scheduler_now,
        ])
        .setup(|app| {
            let app_handle = app.handle().clone();
            
            // Load environment keys into Rust process space so Python subprocesses inherit them
            load_env_into_process(&app_handle);
            
            let project_root = get_project_root(&app_handle);
            println!("[DhanNiti] Project root: {}", project_root.display());
            
            // Spawn Python sidecar processes
            let sidecars = spawn_sidecars(&project_root);
            
            // Store sidecars in app state so we can kill them on exit
            app.manage(sidecars.clone());
            
            // Initialize scheduler state
            let app_data_dir = get_app_data_dir(&app_handle);
            let config_path = app_data_dir.join("scheduler_config.json");
            
            let config = if config_path.exists() {
                std::fs::read_to_string(&config_path)
                    .ok()
                    .and_then(|s| serde_json::from_str::<SchedulerConfig>(&s).ok())
                    .unwrap_or_default()
            } else {
                SchedulerConfig::default()
            };

            if !config_path.exists() {
                let _ = std::fs::write(&config_path, serde_json::to_string_pretty(&config).unwrap_or_default());
            }

            let scheduler = tauri::async_runtime::block_on(async {
                JobScheduler::new().await.expect("Failed to create scheduler")
            });

            let state = Arc::new(SchedulerState {
                scheduler,
                config: std::sync::Mutex::new(config.clone()),
                job_id: tokio::sync::Mutex::new(None),
                last_run_time: std::sync::Mutex::new(None),
                last_run_status: std::sync::Mutex::new(None),
                is_running: std::sync::Mutex::new(false),
            });

            app.manage(state.clone());

            if config.enabled {
                let state_clone = state.clone();
                let app_handle_clone = app_handle.clone();
                tauri::async_runtime::spawn(async move {
                    if let Err(e) = start_scheduler_job(state_clone, app_handle_clone).await {
                        eprintln!("[DhanNiti Scheduler] Error starting job: {}", e);
                    }
                });
            }

            // Create tray menu
            let show_i = MenuItem::with_id(app, "show", "Show Window", true, None::<&str>).expect("menu show failed");
            let quit_i = MenuItem::with_id(app, "quit", "Quit", true, None::<&str>).expect("menu quit failed");
            let menu = Menu::with_items(app, &[&show_i, &quit_i]).expect("menu build failed");

            let mut tray_builder = TrayIconBuilder::new()
                .menu(&menu)
                .on_menu_event(|app, event| {
                    match event.id.as_ref() {
                        "quit" => {
                            if let Some(sidecars) = app.try_state::<Arc<Sidecars>>() {
                                sidecars.kill_all();
                                println!("[DhanNiti] Sidecars killed. Exiting.");
                            }
                            app.exit(0);
                        }
                        "show" => {
                            if let Some(window) = app.get_webview_window("main") {
                                let _ = window.show();
                                let _ = window.set_focus();
                            }
                        }
                        _ => {}
                    }
                })
                .on_tray_icon_event(|tray, event| {
                    if let TrayIconEvent::Click { button_state: tauri::tray::MouseButtonState::Up, .. } = event {
                        let app = tray.app_handle();
                        if let Some(window) = app.get_webview_window("main") {
                            if window.is_visible().unwrap_or(false) {
                                let _ = window.hide();
                            } else {
                                let _ = window.show();
                                let _ = window.set_focus();
                            }
                        }
                    }
                });

            if let Some(icon) = app.default_window_icon() {
                tray_builder = tray_builder.icon(icon.clone());
            }

            let _tray = tray_builder.build(app).expect("Failed to build tray icon");
            
            // Wait a moment for servers to warm up, then emit ready event
            let app_handle_clone = app_handle.clone();
            thread::spawn(move || {
                thread::sleep(Duration::from_secs(3));
                let _ = app_handle_clone.emit("servers-ready", ());
            });
            
            Ok(())
        })
        .on_window_event(|window, event| {
            if let tauri::WindowEvent::CloseRequested { api, .. } = event {
                // Instead of closing, hide the window
                api.prevent_close();
                let _ = window.hide();
            }
        })
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
