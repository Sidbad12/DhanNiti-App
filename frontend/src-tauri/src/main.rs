// DhanNiti — Tauri main entry point
// Spawns Python sidecars (FastAPI + charting server), then shows the webview.

#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

mod sidecar;

fn main() {
    dhanniti_lib::run()
}
