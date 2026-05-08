use serde::{Deserialize, Serialize};
use std::fs;
use std::path::PathBuf;

#[derive(Serialize, Deserialize, Clone)]
pub struct LibraryEntry {
    pub title: String,
    pub install_path: String,
    pub executable: String,
    pub banner: String,
    pub size_gb: f64,
}

#[derive(Serialize, Deserialize)]
pub struct LibraryConfig {
    pub games: Vec<LibraryEntry>,
}

fn get_library_path(drive: &str) -> PathBuf {
    PathBuf::from(drive).join("Gaming Rumble").join("library.json")
}

#[tauri::command]
pub fn get_library(drive: String) -> Result<Vec<LibraryEntry>, String> {
    let path = get_library_path(&drive);
    if !path.exists() {
        return Ok(Vec::new());
    }
    
    let content = fs::read_to_string(&path).map_err(|e| e.to_string())?;
    let config: LibraryConfig = serde_json::from_str(&content).map_err(|e| e.to_string())?;
    Ok(config.games)
}

#[tauri::command]
pub fn add_to_library(drive: String, entry: LibraryEntry) -> Result<(), String> {
    let path = get_library_path(&drive);
    let mut config = LibraryConfig { games: Vec::new() };

    if path.exists() {
        if let Ok(content) = fs::read_to_string(&path) {
            if let Ok(c) = serde_json::from_str::<LibraryConfig>(&content) {
                config = c;
            }
        }
    }
    
    // Atualiza se já existir (mesmo title), senão adiciona
    config.games.retain(|g| g.title != entry.title);
    config.games.push(entry);

    let json = serde_json::to_string_pretty(&config).map_err(|e| e.to_string())?;
    fs::write(&path, json).map_err(|e| e.to_string())?;
    
    Ok(())
}

#[tauri::command]
pub fn remove_from_library(drive: String, title: String) -> Result<(), String> {
    let path = get_library_path(&drive);
    if !path.exists() {
        return Ok(());
    }

    if let Ok(content) = fs::read_to_string(&path) {
        if let Ok(mut config) = serde_json::from_str::<LibraryConfig>(&content) {
            config.games.retain(|g| g.title != title);
            let json = serde_json::to_string_pretty(&config).map_err(|e| e.to_string())?;
            fs::write(&path, json).map_err(|e| e.to_string())?;
        }
    }
    Ok(())
}

fn make_writable_recursive(path: &std::path::Path) {
    if path.is_dir() {
        if let Ok(entries) = fs::read_dir(path) {
            for entry in entries.flatten() {
                make_writable_recursive(&entry.path());
            }
        }
    }

    if let Ok(metadata) = fs::metadata(path) {
        let mut permissions = metadata.permissions();
        if permissions.readonly() {
            permissions.set_readonly(false);
            let _ = fs::set_permissions(path, permissions);
        }
    }
}

#[tauri::command]
pub fn delete_all_games(drive: String) -> Result<(), String> {
    let path = get_library_path(&drive);
    let mut config = LibraryConfig { games: Vec::new() };

    if path.exists() {
        let content = fs::read_to_string(&path).map_err(|e| e.to_string())?;
        if let Ok(parsed) = serde_json::from_str::<LibraryConfig>(&content) {
            config = parsed;
        }
    }

    for game in &config.games {
        let install_path = PathBuf::from(&game.install_path);
        if install_path.exists() {
            make_writable_recursive(&install_path);
            let _ = fs::remove_dir_all(&install_path);
        }

        #[cfg(target_os = "windows")]
        {
            let programs_dir = std::env::var("APPDATA")
                .ok()
                .map(|appdata| PathBuf::from(appdata).join("Microsoft").join("Windows").join("Start Menu").join("Programs"));

            if let Some(programs_dir) = programs_dir {
                let shortcut = programs_dir.join(format!("{}.lnk", game.title));
                if shortcut.exists() {
                    let _ = fs::remove_file(shortcut);
                }
            }
        }
    }

    let empty_config = LibraryConfig { games: Vec::new() };
    let json = serde_json::to_string_pretty(&empty_config).map_err(|e| e.to_string())?;

    if let Some(parent) = path.parent() {
      let _ = fs::create_dir_all(parent);
    }
    fs::write(&path, json).map_err(|e| e.to_string())?;
    Ok(())
}
