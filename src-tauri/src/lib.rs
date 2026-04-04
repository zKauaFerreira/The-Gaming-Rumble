#![cfg_attr(
    all(not(debug_assertions), target_os = "windows"),
    windows_subsystem = "windows"
)]

mod commands;

use tauri::{Manager, Emitter};

use commands::{
    system::{check_is_admin, add_defender_exclusion, create_gaming_rumble_folder, play_game, open_path, update_executable, show_exe_picker, create_shortcut, remove_shortcut},
    disk::{list_drives, get_disk_space},
    torrent::{start_torrent, stop_torrent},
    archive::{extract_game, delete_folder, finalize_installation},
    library::{get_library, add_to_library, remove_from_library}
};

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_single_instance::init(|app, argv, _cwd| {
            if let Some(uri) = argv.iter().find(|arg| arg.starts_with("gaming-rumble://")) {
                let _ = app.emit("deep-link://new-url", vec![uri.clone()]);
            }
            if let Some(window) = app.get_webview_window("main") {
                let _ = window.show();
                let _ = window.set_focus();
                let _ = window.set_always_on_top(true);
                let _ = window.set_always_on_top(false);
            }
        }))
        .invoke_handler(tauri::generate_handler![
            list_drives,
            get_disk_space,
            check_is_admin,
            add_defender_exclusion,
            create_gaming_rumble_folder,
            extract_game,
            delete_folder,
            finalize_installation,
            start_torrent,
            stop_torrent,
            get_library,
            add_to_library,
            remove_from_library,
            play_game,
            open_path,
            show_exe_picker,
            update_executable,
            create_shortcut,
            remove_shortcut
        ])
        .setup(|_| {
            Ok(())
        })
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
