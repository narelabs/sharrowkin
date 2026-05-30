// Prevents additional console window on Windows in release and debug
#![cfg_attr(all(windows), windows_subsystem = "windows")]

use tauri::Manager;
use tauri_plugin_shell::process::CommandChild;
use tauri_plugin_shell::ShellExt;
use std::sync::Mutex;

/// Holds the spawned backend sidecar process so we can kill it on exit.
struct BackendProcess(Mutex<Option<CommandChild>>);

#[tauri::command]
fn greet(name: &str) -> String {
    format!("Hello, {}! Welcome to Sharrowkin Agent.", name)
}

fn main() {
    tauri::Builder::default()
        .plugin(tauri_plugin_shell::init())
        .plugin(tauri_plugin_dialog::init())
        .manage(BackendProcess(Mutex::new(None)))
        .invoke_handler(tauri::generate_handler![greet])
        .setup(|app| {
            // Launch the bundled Python backend as a sidecar process.
            let sidecar = app
                .shell()
                .sidecar("sharrowkin-backend")
                .expect("failed to create `sharrowkin-backend` sidecar command");

            let (mut rx, child) = sidecar
                .spawn()
                .expect("failed to spawn sharrowkin-backend sidecar");

            // Store the child so we can terminate it when the app closes.
            app.state::<BackendProcess>()
                .0
                .lock()
                .unwrap()
                .replace(child);

            // Drain sidecar stdout/stderr into the Tauri log (debug only).
            tauri::async_runtime::spawn(async move {
                use tauri_plugin_shell::process::CommandEvent;
                while let Some(event) = rx.recv().await {
                    match event {
                        CommandEvent::Stdout(line) => {
                            println!("[backend] {}", String::from_utf8_lossy(&line));
                        }
                        CommandEvent::Stderr(line) => {
                            eprintln!("[backend] {}", String::from_utf8_lossy(&line));
                        }
                        _ => {}
                    }
                }
            });

            #[cfg(debug_assertions)]
            {
                let window = app.get_webview_window("main").unwrap();
                window.open_devtools();
            }
            Ok(())
        })
        .on_window_event(|window, event| {
            // Kill the backend when the main window is closed.
            if let tauri::WindowEvent::Destroyed = event {
                if let Some(child) = window
                    .state::<BackendProcess>()
                    .0
                    .lock()
                    .unwrap()
                    .take()
                {
                    let _ = child.kill();
                }
            }
        })
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
