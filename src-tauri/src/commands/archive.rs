use std::path::{Path, PathBuf};
use std::process::{Command, Stdio};
use std::io::{BufRead, BufReader};
use tauri::{AppHandle, Emitter, Manager};

use super::logger::{LogLevel, log, log_tag};

const PASSWORD: &str = "online-fix.me";

async fn ensure_7z(app: &AppHandle) -> Result<PathBuf, String> {
    // 1. Try bundled resources
    if let Ok(resources) = app.path().resolve("bin/7z.exe", tauri::path::BaseDirectory::Resource) {
        if resources.exists() { return Ok(resources); }
    }

    // 2. Fallback: copy to user app_data
    let app_data = app.path().app_data_dir().unwrap();
    let bin_dir = app_data.join("bin");
    let exe7z = bin_dir.join("7z.exe");

    if exe7z.exists() { return Ok(exe7z); }

    // 3. System check
    let system_check = Command::new("7z")
        .arg("i")
        .stdout(Stdio::null())
        .stderr(Stdio::null())
        .spawn();
    if let Ok(mut child) = system_check {
        if child.wait().map(|s| s.success()).unwrap_or(false) {
            return Ok(PathBuf::from("7z.exe"));
        }
    }

    log(LogLevel::WARN, "7z não encontrado como recurso, baixando fallback...");
    // Try known valid 7z versions URLs
    let urls = [
        "https://github.com/ip7z/7zip/releases/download/26.00/7z2600-extra.7z",
        "https://github.com/ip7z/7zip/releases/download/25.00/7z2500-extra.7z",
    ];
    std::fs::create_dir_all(&bin_dir).map_err(|e| e.to_string())?;
    for url in urls {
        let client = reqwest::Client::builder()
            .timeout(std::time::Duration::from_secs(120))
            .build().map_err(|e| e.to_string())?;
        let resp = match client.get(url).send().await {
            Ok(r) if r.status().is_success() => r,
            _ => continue,
        };
        let bytes = resp.bytes().await.map_err(|e| e.to_string())?;
        let temp_7z = bin_dir.join("7z_temp.7z");
        std::fs::write(&temp_7z, &bytes).map_err(|e| e.to_string())?;
        log(LogLevel::INFO, format!("Baixando 7z standalone ({:.1} MB)...", bytes.len() as f64 / 1_048_576.0));
        let _ = sevenz_rust::decompress_file(&temp_7z, &bin_dir);
        let _ = std::fs::remove_file(&temp_7z);
        if exe7z.exists() { return Ok(exe7z); }
    }
    Err("Não foi possível obter 7z.exe. Verifique sua conexão ou instale 7-Zip manualmente.".into())
}

#[tauri::command]
pub async fn extract_game(app: AppHandle, install_path: String) -> Result<(), String> {
    log_tag(LogLevel::SUCCESS, "EXTRACT", format!("Iniciando extração em {}", install_path));
    let root = Path::new(&install_path);

    let sevenz_path = ensure_7z(&app).await.unwrap_or_else(|_| PathBuf::from("7z.exe"));
    log_tag(LogLevel::DEBUG, "EXTRACT", format!("7z em: {:?}", sevenz_path));

    // 1. Find archives
    let rars = find_files_recursive(root, "rar");
    let zips = find_files_recursive(root, "zip");
    let all_archives: Vec<PathBuf> = rars.into_iter().chain(zips).collect();
    if all_archives.is_empty() {
        return Err("No archives found in download directory".into());
    }

    // 2. Separate game from fix
    let mut game_archives: Vec<PathBuf> = Vec::new();
    let mut fix_archives: Vec<PathBuf> = Vec::new();
    for archive in &all_archives {
        let lower = archive.to_string_lossy().to_lowercase();
        if lower.contains(".part")
            && !lower.contains(".part01.rar") && !lower.contains(".part1.rar") && !lower.contains(".part001.rar")
        { continue; }
        if lower.contains("fix") || lower.contains("repair") {
            fix_archives.push(archive.clone());
        } else {
            game_archives.push(archive.clone());
        }
    }
    game_archives.sort();
    fix_archives.sort();

    // Build list of jobs: game first, fix second
    let total_jobs = game_archives.len() + fix_archives.len();
    log_tag(LogLevel::INFO, "EXTRACT", format!("{} arquivo(s) de jogo e {} fix", game_archives.len(), fix_archives.len()));

    // 3. Extract game archives at the directory where they are
    let game_extract_dir = game_archives.first()
        .and_then(|a| a.parent())
        .unwrap_or(root);

    for (i, archive) in game_archives.iter().enumerate() {
        let pct_start = (i as f64 / total_jobs as f64) * 100.0;
        let pct_end = ((i + 1) as f64 / total_jobs as f64) * 100.0;
        let file_name = archive.file_name().unwrap_or_default().to_string_lossy().to_string();
        log_tag(LogLevel::INFO, "EXTRACT", format!("[{}/{}] Jogo: {}", i + 1, total_jobs, file_name));
        run_7z_with_progress(&sevenz_path, archive, game_extract_dir, false, &app,
            pct_start, pct_end, i + 1, total_jobs, "extracting", &file_name)?;
    }

    // 4. Save fix archive to temp (preserve it while we delete Fix Repair dir)
    let fix_tmp_dir = std::env::temp_dir().join("gr_extract_tmp");
    std::fs::create_dir_all(&fix_tmp_dir).map_err(|e| e.to_string())?;
    let mut fix_tmp_paths: Vec<PathBuf> = Vec::new();

    for (i, fix_archive) in fix_archives.iter().enumerate() {
        let dest = fix_tmp_dir.join(format!("fix_{}.rar", i));
        std::fs::copy(fix_archive, &dest)
            .map_err(|e| format!("Não foi possível copiar o fix: {}", e))?;
        log_tag(LogLevel::DEBUG, "EXTRACT", format!("Fix copiado para temp: {:?}", dest));
        fix_tmp_paths.push(dest);
    }

    // Delete Fix Repair dir
    if let Ok(entries) = std::fs::read_dir(game_extract_dir) {
        for entry in entries.flatten() {
            let p = entry.path();
            if p.is_dir() {
                let name = entry.file_name().to_string_lossy().to_lowercase();
                if name.contains("fix") || name.contains("repair") {
                    remove_empty_dirs(&p);
                    let _ = std::fs::remove_dir(&p);
                    let _ = std::fs::remove_dir_all(&p);
                }
            }
        }
    }

    // 5. Flatten duplicate nested dirs (A\A → A)
    log_tag(LogLevel::INFO, "EXTRACT", "Aplicando flattening...");
    while flatten_one_pass(root) > 0 {}

    // 6. Find where the game ended up
    let game_dir = find_deepest_same_name_dir(root);
    log_tag(LogLevel::INFO, "EXTRACT", format!("Pasta do jogo: {:?}", game_dir));

    // 7. Extract fix to game directory
    for (i, fix_tmp_path) in fix_tmp_paths.iter().enumerate() {
        let idx = game_archives.len() + i;
        let pct_start = (idx as f64 / total_jobs as f64) * 100.0;
        let pct_end = ((idx + 1) as f64 / total_jobs as f64) * 100.0;
        let file_name = format!("fix_{}.rar", i);
        log_tag(LogLevel::INFO, "EXTRACT", format!("[{}/{}] Fix: {:?}", idx + 1, total_jobs, fix_tmp_path));
        run_7z_with_progress(&sevenz_path, fix_tmp_path, &game_dir, true, &app,
            pct_start, pct_end, idx + 1, total_jobs, "extracting_fix", &file_name)?;
    }

    // 8. Move everything from deepest nested dir to root
    let deepest = find_deepest_same_name_dir(root);
    if deepest != root && deepest.exists() {
        log_tag(LogLevel::INFO, "EXTRACT", format!("Movendo conteúdo de {:?} para raiz", deepest));
        move_all_to(&deepest, root);
        while flatten_one_pass(root) > 0 {}
    }

    // 9. Remove temp dir
    if fix_tmp_dir.exists() {
        let _ = std::fs::remove_dir_all(&fix_tmp_dir);
    }

    // 10. Clean
    log_tag(LogLevel::INFO, "EXTRACT", "Limpando arquivos e pastas...");
    let _ = app.emit("extract-progress", serde_json::json!({"type": "cleaning"}));
    clean_archives(root);
    remove_empty_dirs(root);

    log_tag(LogLevel::SUCCESS, "EXTRACT", "Extração completa!");
    let _ = app.emit("extract-progress", serde_json::json!({"type": "done"}));
    Ok(())
}

/// Walk down a chain of nested dirs where subdir name matches parent name.
/// root\Chained Wheels\Chained Wheels\Chained Wheels → returns deepest.
fn find_deepest_same_name_dir(start: &Path) -> PathBuf {
    let mut current = start.to_path_buf();
    loop {
        let entries: Vec<_> = match std::fs::read_dir(&current) {
            Ok(e) => e.flat_map(|e| e).collect(),
            Err(_) => break,
        };
        let dirs: Vec<_> = entries.iter().filter(|e| e.path().is_dir()).collect();
        let current_name = match current.file_name() {
            Some(n) => n,
            None => break,
        };
        let same_name = dirs.iter().find(|e| e.file_name() == current_name);
        if let Some(entry) = same_name {
            current = entry.path();
        } else if dirs.len() == 1 && !entries.iter().any(|e| e.path().is_file()) {
            current = dirs[0].path();
        } else {
            break;
        }
    }
    current
}


/// Returns 0 if no progress found
fn extract_pct_from_7z_line(line: &str) -> Option<f64> {
    for token in line.split_whitespace() {
        if let Some(num) = token.strip_suffix('%') {
            if let Ok(v) = num.parse::<f64>() {
                if v >= 0.0 && v <= 100.0 {
                    return Some(v);
                }
            }
        }
    }
    None
}

/// Run 7z with real-time progress from stdout
fn run_7z_with_progress(
    sevenz_exe: &Path, archive: &Path, out_dir: &Path, overwrite: bool,
    app: &AppHandle, pct_start: f64, pct_end: f64,
    current: usize, total: usize, label: &str, file_name: &str,
) -> Result<(), String> {
    #[cfg(target_os = "windows")]
    use std::os::windows::process::CommandExt;

    let mut cmd = Command::new(sevenz_exe);
    cmd.arg("x");
    cmd.arg(archive);
    cmd.arg(format!("-o{}", out_dir.display()));
    cmd.arg("-y");
    cmd.arg(format!("-p{}", PASSWORD));
    if overwrite { cmd.arg("-aoa"); }
    #[cfg(target_os = "windows")]
    cmd.creation_flags(0x08000000);
    cmd.stdout(Stdio::piped());
    cmd.stderr(Stdio::piped());

    let mut child = cmd.spawn().map_err(|e| {
        if e.kind() == std::io::ErrorKind::NotFound {
            format!("7z.exe não encontrado! Erro: {}", e)
        } else { e.to_string() }
    })?;

    let stdout = child.stdout.take();
    if let Some(stdout) = stdout {
        let reader = BufReader::new(stdout);
        for line in reader.lines().flatten() {
            if let Some(pct) = extract_pct_from_7z_line(&line) {
                let global = pct_start + pct * (pct_end - pct_start) / 100.0;
                let _ = app.emit("extract-progress", serde_json::json!({
                    "type": label,
                    "file": file_name,
                    "current": current,
                    "total": total,
                    "global_pct": format!("{:.1}", global)
                }));
            }
        }
    }

    let status = child.wait().map_err(|e| e.to_string())?;
    if !status.success() {
        return Err(format!("Falha ao extrair {} (código {})",
            archive.file_name().unwrap_or_default().to_string_lossy(),
            status.code().unwrap_or(-1)));
    }
    Ok(())
}

/// Top-down flatten: for each dir, if it has only 1 subdir with the SAME name
/// and no files at this level, merge the subdir up. Returns count flattened.
fn flatten_one_pass(root: &Path) -> usize {
    let mut count = 0;

    // Collect all dirs breadth-first
    let mut to_visit = vec![root.to_path_buf()];
    while let Some(dir) = to_visit.pop() {
        if let Ok(entries) = std::fs::read_dir(&dir) {
            for entry in entries.flatten() {
                if entry.path().is_dir() {
                    to_visit.push(entry.path());
                }
            }
        }
    }
    // Process top-down (shorter paths first)
    to_visit.sort_by_key(|p| p.components().count());

    for dir in to_visit {
        let entries: Vec<_> = match std::fs::read_dir(&dir) {
            Ok(e) => e.flat_map(|e| e).collect(),
            Err(_) => continue,
        };
        let dirs: Vec<_> = entries.iter().filter(|e| e.path().is_dir()).collect();
        let has_files = entries.iter().any(|e| e.path().is_file());

        if dirs.len() == 1 && !has_files {
            let inner = dirs[0].path();
            let inner_name = inner.file_name();
            let dir_name = dir.file_name();
            let should_flatten = dir_name == inner_name
                // Also flatten if subdir is the only option left
                || (dirs.len() == 1 && !has_files && !dir.as_os_str().is_empty());

            if should_flatten {
                log_tag(LogLevel::DEBUG, "FLATTEN", format!("{:?}", inner));
                merge_to_parent(&inner);
                count += 1;
            }
        }
    }
    count
}

fn merge_to_parent(inner: &Path) {
    let parent = match inner.parent() {
        Some(p) => p, None => return,
    };
    if let Ok(entries) = std::fs::read_dir(inner) {
        for entry in entries.flatten() {
            let src = entry.path();
            let dst = parent.join(entry.file_name());
            if dst.exists() {
                if src.is_dir() && dst.is_dir() {
                    merge_dirs(&src, &dst);
                } else {
                    let _ = std::fs::remove_file(&dst);
                    let _ = std::fs::rename(&src, &dst);
                }
            } else {
                let _ = std::fs::rename(&src, &dst);
            }
        }
    }
    let _ = std::fs::remove_dir_all(inner);
}


fn merge_dirs(src: &Path, dst: &Path) {
    if let Ok(entries) = std::fs::read_dir(src) {
        for entry in entries.flatten() {
            let src_path = entry.path();
            let dst_path = dst.join(entry.file_name());
            if dst_path.exists() {
                if src_path.is_dir() && dst_path.is_dir() {
                    merge_dirs(&src_path, &dst_path);
                } else {
                    let _ = std::fs::remove_file(&dst_path);
                    let _ = std::fs::rename(&src_path, &dst_path);
                }
            } else {
                let _ = std::fs::rename(&src_path, &dst_path);
            }
        }
    }
    let _ = std::fs::remove_dir(src);
}

/// Move all files and dirs from src into dest, overwriting files and merging dirs.
/// Then removes src.
fn move_all_to(src: &Path, dest: &Path) {
    if !src.is_dir() || !dest.is_dir() { return; }
    if let Ok(entries) = std::fs::read_dir(src) {
        for entry in entries.flatten() {
            let src_path = entry.path();
            let dst_path = dest.join(entry.file_name());
            if dst_path.exists() {
                if src_path.is_dir() && dst_path.is_dir() {
                    merge_dirs(&src_path, &dst_path);
                } else {
                    let _ = std::fs::remove_file(&dst_path);
                    let _ = std::fs::rename(&src_path, &dst_path);
                }
            } else {
                let _ = std::fs::rename(&src_path, &dst_path);
            }
        }
    }
    let _ = std::fs::remove_dir_all(src);
}

fn find_files_recursive(dir: &Path, ext: &str) -> Vec<PathBuf> {
    let mut result = Vec::new();
    if let Ok(entries) = std::fs::read_dir(dir) {
        for entry in entries.flatten() {
            let path = entry.path();
            if path.is_dir() {
                result.extend(find_files_recursive(&path, ext));
            } else if path.extension().and_then(|e| e.to_str()) == Some(ext) {
                result.push(path);
            }
        }
    }
    result
}

fn clean_archives(dir: &Path) {
    if let Ok(entries) = std::fs::read_dir(dir) {
        for entry in entries.flatten() {
            let path = entry.path();
            if path.is_dir() { clean_archives(&path); }
            else {
                let ext = path.extension().and_then(|e| e.to_str()).unwrap_or_default().to_lowercase();
                if ext == "rar" || ext == "zip" || ext == "7z"
                    || ext.starts_with("r0") || ext.starts_with("r1") || ext.starts_with("r2")
                    || ext.starts_with("r3") || ext.starts_with("r4") || ext.starts_with("r5")
                    || ext.starts_with("r6") || ext.starts_with("r7") || ext.starts_with("r8")
                    || ext.starts_with("r9")
                { let _ = std::fs::remove_file(&path); }
            }
        }
    }
}

fn remove_empty_dirs(dir: &Path) {
    if let Ok(entries) = std::fs::read_dir(dir) {
        for entry in entries.flatten() {
            let path = entry.path();
            if path.is_dir() {
                remove_empty_dirs(&path);
                let _ = std::fs::remove_dir(&path);
            }
        }
    }
}

#[tauri::command]
pub fn delete_folder(path: String) -> Result<(), String> {
    log_tag(LogLevel::INFO, "DELETE", format!("Deletando pasta: {}", path));
    let p = Path::new(&path);
    if p.exists() {
        make_writable_recursive(p);
        std::fs::remove_dir_all(p).map_err(|e| {
            log_tag(LogLevel::ERROR, "DELETE", format!("Erro ao deletar: {}", e));
            e.to_string()
        })?;
        log_tag(LogLevel::SUCCESS, "DELETE", format!("Pasta deletada: {}", path));
    }
    Ok(())
}

#[cfg(target_os = "windows")]
fn make_writable_recursive(path: &Path) {
    if path.is_dir() {
        if let Ok(entries) = std::fs::read_dir(path) {
            for entry in entries.flatten() {
                if entry.path().is_dir() {
                    make_writable_recursive(&entry.path());
                }
            }
        }
        if let Ok(meta) = std::fs::metadata(path) {
            let mut perms = meta.permissions();
            if perms.readonly() {
                perms.set_readonly(false);
                let _ = std::fs::set_permissions(path, perms);
            }
        }
    }
}
#[cfg(not(target_os = "windows"))]
fn make_writable_recursive(_path: &Path) {}

#[derive(serde::Serialize)]
pub struct InstallationMetadata {
    pub size_gb: f64,
    pub executable: String,
}

/// Score how well an EXE filename matches keywords from the game title.
/// Higher = better match (full match > partial word match > partial char match).
fn title_match_score(exe_stem: &str, title_words: &[&str]) -> i32 {
    let exe_lower = exe_stem.to_lowercase();
    let mut score = 0;

    for word in title_words {
        let w = word.to_lowercase();
        if w.len() < 3 { continue; } // skip short words like "of", "the", "vs"
        // Exact match (highest priority)
        if exe_lower == w {
            score += 100;
        }
        // Word contained in exe name (case-insensitive)
        else if exe_lower.contains(&w) {
            score += 50;
        }
        // Partial match with at least 3 char substring
        else if w.len() >= 5 && w.split_whitespace().next().map(|s| exe_lower.contains(&s.to_lowercase())).unwrap_or(false) {
            score += 25;
        }
    }

    score
}

#[tauri::command]
pub fn finalize_installation(install_path: String, title: Option<String>) -> Result<InstallationMetadata, String> {
    let root = Path::new(&install_path);
    if !root.exists() { return Err("Path not found".into()); }
    let size_bytes = get_folder_size(root);
    let size_gb = size_bytes as f64 / 1_073_741_824.0;

    let exes = find_files_recursive(root, "exe");
    // Ignored EXEs: redistributables, installers, crash handlers, debug tools
    let ignored = [
        "unins000", "crashreport", "crashhandler", "unitycrashhandler", "unityplayer",
        "dxsetup", "vcredist", "dotnet", "redist", "setup", "installer",
        "repair", "patch", "update", "launcher", "prereq", "cefprocess",
        "shadercache", "mono", "unity"
    ];

    // Short words to ignore in title matching
    let skip_words = ["the", "of", "and", "or", "a", "an", "in", "on", "to", "vs",
                      "do", "da", "e", "em", "de", "para", "com", "por", "sem", "que", "na", "no", "nos", "das", "dos", "se", "seu", "sua", "ele", "ela"];

    // Extract title keywords (non-short, non-skip words, replacing & => and, - => space)
    let safe_title = title.unwrap_or_default()
        .replace('&', " ")
        .replace('-', " ")
        .replace(':', "");
    let title_words: Vec<&str> = safe_title.split_whitespace()
        .filter(|w| w.len() >= 3)
        .filter(|w| !skip_words.contains(&w.to_lowercase().as_str()))
        .collect();

    let mut best_exe = String::new();
    let mut best_score: i32 = i32::MIN;

    for exe in &exes {
        let name = exe.file_name().unwrap_or_default().to_string_lossy().to_lowercase();
        let stem = exe.file_stem().unwrap_or_default().to_string_lossy();

        // Skip known non-game exes
        if ignored.iter().any(|&i| name.contains(i)) { continue; }
        // Skip if exe is tiny (< 100KB) — likely a helper, not the main game
        if let Ok(meta) = exe.metadata() {
            if meta.len() < 100_000 { continue; }
        }

        let depth = exe.components().count() as i32;
        let mut score = 100 - depth * 10;

        // Title keyword matching bonus
        if !title_words.is_empty() {
            let match_score = title_match_score(&stem, &title_words);
            score += match_score;
        }

        // Bonus if parent dir has game indicators
        if let Some(parent) = exe.parent() {
            score += dir_game_bonus(parent);
        }

        if score > best_score {
            best_score = score;
            best_exe = exe.to_string_lossy().into_owned();
        }
    }

    if best_exe.is_empty() {
        log_tag(LogLevel::WARN, "EXE", "Nenhum executável encontrado");
    } else {
        log_tag(LogLevel::SUCCESS, "EXE", format!("{} (score: {})", best_exe, best_score));
    }
    Ok(InstallationMetadata { size_gb, executable: best_exe })
}

fn dir_game_bonus(dir: &Path) -> i32 {
    let mut bonus = 0;
    if let Ok(entries) = std::fs::read_dir(dir) {
        for entry in entries.flatten() {
            let lower = entry.file_name().to_string_lossy().to_lowercase();
            if lower == "steam_api64.dll" || lower == "steam_api.dll" { bonus += 20; }
            if lower == "eos.dll" { bonus += 10; }
            if lower.ends_with("_data") || lower.contains("game") { bonus += 5; }
        }
    }
    bonus
}

fn get_folder_size(dir: &Path) -> u64 {
    let mut size = 0;
    if let Ok(entries) = std::fs::read_dir(dir) {
        for entry in entries.flatten() {
            let path = entry.path();
            if path.is_file() {
                size += std::fs::metadata(&path).map(|m| m.len()).unwrap_or(0);
            } else if path.is_dir() {
                size += get_folder_size(&path);
            }
        }
    }
    size
}
