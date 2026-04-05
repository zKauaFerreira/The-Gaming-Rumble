#![cfg_attr(
    all(not(debug_assertions), target_os = "windows"),
    windows_subsystem = "windows"
)]

mod commands;

use std::env::current_exe;
use tauri::{Manager, Emitter};
use commands::{
    system::{check_is_admin, add_defender_exclusion, create_gaming_rumble_folder, play_game, open_path, update_executable, show_exe_picker, create_shortcut, remove_shortcut},
    disk::{list_drives, get_disk_space},
    torrent::{start_torrent, stop_torrent, start_fix_download},
    archive::{extract_game, delete_folder, finalize_installation},
    library::{get_library, add_to_library, remove_from_library}
};

#[cfg(windows)]
fn register_deep_link() {
    use std::os::windows::process::CommandExt;
    use std::process::Command;

    let exe = current_exe().unwrap_or_else(|_| std::path::PathBuf::from("GamingRumble.exe"));
    let exe_path = format!("\"{}\"", exe.display());

    let commands = [
        &["add", "HKCU\\Software\\Classes\\gaming-rumble", "/ve", "/d", "URL:gaming-rumble", "/f"][..],
        &["add", "HKCU\\Software\\Classes\\gaming-rumble", "/v", "URL Protocol", "/d", "", "/f"],
        &["add", "HKCU\\Software\\Classes\\gaming-rumble\\shell\\open\\command", "/ve", "/d", &format!("{} \"%1\"", exe_path), "/f"],
    ];

    for args in commands {
        let _ = Command::new("cmd")
            .args(&["/C", "reg"].iter().chain(args.iter()).map(|s| s.as_ref()).collect::<Vec<&str>>())
            .creation_flags(0x08000000)
            .stdout(std::process::Stdio::null())
            .stderr(std::process::Stdio::null())
            .status();
    }
}

#[cfg(not(windows))]
fn register_deep_link() {}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    register_deep_link();

    tauri::Builder::default()
        .plugin(tauri_plugin_single_instance::init(|app, argv, _cwd| {
            eprintln!("[SINGLE-INSTANCE] args: {:?}", argv);
            if let Some(uri) = argv.iter().find(|arg| arg.starts_with("gaming-rumble://")) {
                eprintln!("[DEEP-LINK] URI received: {}", uri);
                let _ = app.emit("deeplink", uri);
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
            start_fix_download,
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
        .setup(|_app| {
            Ok(())
        })
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
