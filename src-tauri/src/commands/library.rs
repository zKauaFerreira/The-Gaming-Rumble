use rusqlite::{params, Connection, OptionalExtension};
use serde::{Deserialize, Serialize};
use std::fs;
use std::path::{Path, PathBuf};

#[derive(Serialize, Deserialize, Clone)]
pub struct LibraryEntry {
    pub title: String,
    pub install_path: String,
    pub executable: String,
    pub banner: String,
    pub size_gb: f64,
    #[serde(default)]
    pub play_time_ms: u64,
}

#[derive(Serialize, Deserialize)]
pub struct LibraryConfig {
    pub games: Vec<LibraryEntry>,
}

fn legacy_library_path(drive: &str) -> PathBuf {
    PathBuf::from(drive).join("Gaming Rumble").join("library.json")
}

fn app_database_dir() -> Result<PathBuf, String> {
    let base = dirs::data_local_dir()
        .or_else(dirs::data_dir)
        .ok_or_else(|| "Nao foi possivel localizar a pasta de dados local do app".to_string())?;
    let dir = base.join("GamingRumble");
    fs::create_dir_all(&dir).map_err(|e| e.to_string())?;
    Ok(dir)
}

fn legacy_import_marker_path() -> Result<PathBuf, String> {
    Ok(app_database_dir()?.join("legacy-library-import.done"))
}

fn database_path() -> Result<PathBuf, String> {
    Ok(app_database_dir()?.join("library.db"))
}

fn open_database() -> Result<Connection, String> {
    let path = database_path()?;
    let conn = Connection::open(path).map_err(|e| e.to_string())?;
    conn.execute_batch(
        r#"
        PRAGMA journal_mode = WAL;
        PRAGMA synchronous = NORMAL;
        CREATE TABLE IF NOT EXISTS games (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            drive TEXT NOT NULL,
            title TEXT NOT NULL,
            install_path TEXT NOT NULL,
            executable TEXT NOT NULL,
            banner TEXT NOT NULL,
            size_gb REAL NOT NULL DEFAULT 0,
            play_time_ms INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(drive, title)
        );
        CREATE INDEX IF NOT EXISTS idx_games_drive_title ON games(drive, title);
        "#,
    )
    .map_err(|e| e.to_string())?;
    Ok(conn)
}

fn normalize_drive(drive: &str) -> String {
    drive.trim().trim_end_matches('\\').to_ascii_uppercase()
}

fn sqlite_u64(value: u64) -> i64 {
    value.min(i64::MAX as u64) as i64
}

fn read_u64(value: i64) -> u64 {
    value.max(0) as u64
}

fn read_legacy_games(drive: &str) -> Result<Vec<LibraryEntry>, String> {
    let path = legacy_library_path(drive);
    if !path.exists() {
        return Ok(Vec::new());
    }

    let content = fs::read_to_string(path).map_err(|e| e.to_string())?;
    let config: LibraryConfig = serde_json::from_str(&content).map_err(|e| e.to_string())?;
    Ok(config.games)
}

fn import_drive_legacy_json(conn: &Connection, drive: &str) -> Result<bool, String> {
    let legacy_games = read_legacy_games(drive)?;
    if legacy_games.is_empty() {
        return Ok(false);
    }

    let normalized_drive = normalize_drive(drive);
    let tx = conn.unchecked_transaction().map_err(|e| e.to_string())?;
    for game in legacy_games {
        tx.execute(
            r#"
            INSERT INTO games (drive, title, install_path, executable, banner, size_gb, play_time_ms, updated_at)
            VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7, CURRENT_TIMESTAMP)
            ON CONFLICT(drive, title) DO UPDATE SET
                install_path = excluded.install_path,
                executable = excluded.executable,
                banner = excluded.banner,
                size_gb = excluded.size_gb,
                play_time_ms = CASE
                    WHEN games.play_time_ms > 0 THEN games.play_time_ms
                    ELSE excluded.play_time_ms
                END,
                updated_at = CURRENT_TIMESTAMP
            "#,
            params![
                normalized_drive,
                game.title,
                game.install_path,
                game.executable,
                game.banner,
                game.size_gb,
                sqlite_u64(game.play_time_ms)
            ],
        )
        .map_err(|e| e.to_string())?;
    }
    tx.commit().map_err(|e| e.to_string())?;
    Ok(true)
}

fn query_games(conn: &Connection, drive: &str) -> Result<Vec<LibraryEntry>, String> {
    let normalized_drive = normalize_drive(drive);
    let mut stmt = conn
        .prepare(
            r#"
            SELECT title, install_path, executable, banner, size_gb, play_time_ms
            FROM games
            WHERE drive = ?1
            ORDER BY LOWER(title) ASC
            "#,
        )
        .map_err(|e| e.to_string())?;

    let rows = stmt
        .query_map([normalized_drive], |row| {
            Ok(LibraryEntry {
                title: row.get(0)?,
                install_path: row.get(1)?,
                executable: row.get(2)?,
                banner: row.get(3)?,
                size_gb: row.get(4)?,
                play_time_ms: read_u64(row.get::<_, i64>(5)?),
            })
        })
        .map_err(|e| e.to_string())?;

    rows.collect::<Result<Vec<_>, _>>().map_err(|e| e.to_string())
}

pub fn run_one_time_legacy_import() -> Result<(), String> {
    let marker = legacy_import_marker_path()?;
    if marker.exists() {
        return Ok(());
    }

    let conn = open_database()?;

    for letter in 'A'..='Z' {
        let drive = format!("{letter}:\\");
        let legacy_path = legacy_library_path(&drive);
        if !legacy_path.exists() {
            continue;
        }

        if import_drive_legacy_json(&conn, &drive)? {
            let _ = fs::remove_file(&legacy_path);
        }
    }

    fs::write(marker, b"done").map_err(|e| e.to_string())?;
    Ok(())
}

fn make_writable_recursive(path: &Path) {
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

pub fn update_executable_path(drive: &str, title: &str, executable: &str) -> Result<(), String> {
    let conn = open_database()?;
    let normalized_drive = normalize_drive(drive);
    let rows = conn
        .execute(
            r#"
            UPDATE games
            SET executable = ?3, updated_at = CURRENT_TIMESTAMP
            WHERE drive = ?1 AND title = ?2
            "#,
            params![normalized_drive, title, executable],
        )
        .map_err(|e| e.to_string())?;

    if rows == 0 {
        return Err("Jogo nao encontrado na biblioteca".into());
    }
    Ok(())
}

pub fn add_play_time(drive: &str, title: &str, delta_ms: u64) -> Result<Option<LibraryEntry>, String> {
    if delta_ms == 0 {
        return Ok(None);
    }

    let conn = open_database()?;
    let normalized_drive = normalize_drive(drive);

    let rows = conn
        .execute(
            r#"
            UPDATE games
            SET play_time_ms = play_time_ms + ?3, updated_at = CURRENT_TIMESTAMP
            WHERE drive = ?1 AND title = ?2
            "#,
            params![normalized_drive.clone(), title, sqlite_u64(delta_ms)],
        )
        .map_err(|e| e.to_string())?;

    if rows == 0 {
        return Ok(None);
    }

    let entry = conn
        .query_row(
            r#"
            SELECT title, install_path, executable, banner, size_gb, play_time_ms
            FROM games
            WHERE drive = ?1 AND title = ?2
            "#,
            params![normalized_drive, title],
            |row| {
                Ok(LibraryEntry {
                    title: row.get(0)?,
                    install_path: row.get(1)?,
                    executable: row.get(2)?,
                    banner: row.get(3)?,
                    size_gb: row.get(4)?,
                    play_time_ms: read_u64(row.get::<_, i64>(5)?),
                })
            },
        )
        .optional()
        .map_err(|e| e.to_string())?;
    Ok(entry)
}

#[tauri::command]
pub fn get_library(drive: String) -> Result<Vec<LibraryEntry>, String> {
    let conn = open_database()?;
    query_games(&conn, &drive)
}

#[tauri::command]
pub fn add_to_library(drive: String, entry: LibraryEntry) -> Result<(), String> {
    let conn = open_database()?;
    let normalized_drive = normalize_drive(&drive);

    conn.execute(
        r#"
        INSERT INTO games (drive, title, install_path, executable, banner, size_gb, play_time_ms, updated_at)
        VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7, CURRENT_TIMESTAMP)
        ON CONFLICT(drive, title) DO UPDATE SET
            install_path = excluded.install_path,
            executable = excluded.executable,
            banner = excluded.banner,
            size_gb = excluded.size_gb,
            play_time_ms = CASE
                WHEN excluded.play_time_ms > 0 THEN excluded.play_time_ms
                ELSE games.play_time_ms
            END,
            updated_at = CURRENT_TIMESTAMP
        "#,
        params![
            normalized_drive,
            entry.title,
            entry.install_path,
            entry.executable,
            entry.banner,
            entry.size_gb,
            sqlite_u64(entry.play_time_ms)
        ],
    )
    .map_err(|e| e.to_string())?;
    Ok(())
}

#[tauri::command]
pub fn remove_from_library(drive: String, title: String) -> Result<(), String> {
    let conn = open_database()?;
    let normalized_drive = normalize_drive(&drive);

    conn.execute(
        "DELETE FROM games WHERE drive = ?1 AND title = ?2",
        params![normalized_drive, title],
    )
    .map_err(|e| e.to_string())?;
    Ok(())
}

#[tauri::command]
pub fn delete_all_games(drive: String) -> Result<(), String> {
    let conn = open_database()?;
    let games = query_games(&conn, &drive)?;

    for game in &games {
        let install_path = PathBuf::from(&game.install_path);
        if install_path.exists() {
            make_writable_recursive(&install_path);
            let _ = fs::remove_dir_all(&install_path);
        }

        #[cfg(target_os = "windows")]
        {
            let programs_dir = std::env::var("APPDATA")
                .ok()
                .map(|appdata| {
                    PathBuf::from(appdata)
                        .join("Microsoft")
                        .join("Windows")
                        .join("Start Menu")
                        .join("Programs")
                });

            if let Some(programs_dir) = programs_dir {
                let shortcut = programs_dir.join(format!("{}.lnk", game.title));
                if shortcut.exists() {
                    let _ = fs::remove_file(shortcut);
                }
            }
        }
    }

    conn.execute(
        "DELETE FROM games WHERE drive = ?1",
        [normalize_drive(&drive)],
    )
    .map_err(|e| e.to_string())?;
    Ok(())
}
