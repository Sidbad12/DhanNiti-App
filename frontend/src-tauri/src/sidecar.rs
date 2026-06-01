// DhanNiti — Python sidecar process management
// Spawns and tracks uvicorn (FastAPI :8000) and charting server (:5000).
// All processes are killed cleanly when the Tauri window closes.

use std::process::{Child, Command};
use std::sync::Mutex;

pub struct Sidecars {
    pub api: Mutex<Option<Child>>,
    pub charting: Mutex<Option<Child>>,
}

impl Sidecars {
    pub fn new() -> Self {
        Self {
            api: Mutex::new(None),
            charting: Mutex::new(None),
        }
    }

    /// Kill all sidecar processes — called on app exit.
    pub fn kill_all(&self) {
        if let Ok(mut guard) = self.api.lock() {
            if let Some(mut child) = guard.take() {
                let _ = child.kill();
            }
        }
        if let Ok(mut guard) = self.charting.lock() {
            if let Some(mut child) = guard.take() {
                let _ = child.kill();
            }
        }
    }
}

/// Resolve the Python/poetry executable path for the project.
/// Prefers `.venv` python if available, then `poetry run python`, falls back to `python`.
pub fn python_cmd(project_root: &std::path::Path) -> Vec<String> {
    // 1. Check if .venv exists in project root
    let venv_dir = project_root.join(".venv");
    if venv_dir.exists() {
        let bin_path = if cfg!(windows) {
            venv_dir.join("Scripts").join("python.exe")
        } else {
            venv_dir.join("bin").join("python")
        };
        if bin_path.exists() {
            return vec![bin_path.to_string_lossy().to_string()];
        }
    }

    // 2. Check if poetry is on PATH
    if Command::new("poetry").arg("--version").output().is_ok() {
        vec!["poetry".to_string(), "run".to_string(), "python".to_string()]
    } else {
        // Fall back to python3 / python on PATH
        if Command::new("python3").arg("--version").output().is_ok() {
            vec!["python3".to_string()]
        } else {
            vec!["python".to_string()]
        }
    }
}

/// Resolve the uvicorn executable (local .venv uvicorn, poetry run uvicorn or system uvicorn).
pub fn uvicorn_cmd(project_root: &std::path::Path) -> Vec<String> {
    // 1. Check if .venv exists in project root
    let venv_dir = project_root.join(".venv");
    if venv_dir.exists() {
        let bin_path = if cfg!(windows) {
            venv_dir.join("Scripts").join("uvicorn.exe")
        } else {
            venv_dir.join("bin").join("uvicorn")
        };
        if bin_path.exists() {
            return vec![bin_path.to_string_lossy().to_string()];
        }
    }

    if Command::new("poetry").arg("--version").output().is_ok() {
        vec!["poetry".to_string(), "run".to_string(), "uvicorn".to_string()]
    } else {
        vec!["uvicorn".to_string()]
    }
}
