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
