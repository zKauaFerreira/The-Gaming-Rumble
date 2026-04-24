use std::path::{Path, PathBuf};
use std::process::{Command, Stdio};
use std::io::{BufReader, Read};
#[cfg(target_os = "windows")]
use std::os::windows::process::CommandExt;
use std::cmp::Ordering;
use sevenz_rust::{decompress_file_with_password, Password};
use std::sync::Mutex;
use tauri::{AppHandle, Emitter, Manager};

use super::logger::{LogLevel, log_tag};

fn dbg(msg: &str) {
    eprintln!("[7z dbg] {}", msg);
}

const PASSWORD: &str = "online-fix.me";

static SEVENZ_PATH: Mutex<Option<PathBuf>> = Mutex::new(None);

#[derive(Debug, Clone, Eq, PartialEq)]
struct ArchiveSortKey {
    kind_rank: u8,
    group_name: String,
    part_number: Option<u32>,
    file_name: String,
}

async fn ensure_7z(app: &AppHandle) -> Option<PathBuf> {
    dbg("ensure_7z called");
    let cached = SEVENZ_PATH.lock().unwrap().clone();
    if let Some(ref p) = cached {
        dbg(&format!("cached path: {:?}, exists: {}", p, p.exists()));
        if p.exists() { return cached; }
    }
    drop(cached);

    // 1. System installed
    for c in &["C:\\Program Files\\7-Zip\\7z.exe", "C:\\Program Files (x86)\\7-Zip\\7z.exe"] {
        let p = PathBuf::from(c);
        if p.exists() {
            dbg(&format!("found system 7z: {:?}", p));
            *SEVENZ_PATH.lock().unwrap() = Some(p.clone());
            return Some(p);
        }
    }

    // 2. Bundled with app resources
    if let Ok(res) = app.path().resolve("7-ZIP/7z.exe", tauri::path::BaseDirectory::Resource) {
        dbg(&format!("resolve path: {:?}", res));
        let sevenz_path: PathBuf = res;
        if sevenz_path.exists() {
            dbg(&format!("bundled 7z found: {:?}", sevenz_path));
            *SEVENZ_PATH.lock().unwrap() = Some(sevenz_path.clone());
            return Some(sevenz_path);
        }
    }

    dbg("7z not available");
    None
}

#[tauri::command]
pub async fn extract_game(app: AppHandle, install_path: String) -> Result<(), String> {
    log_tag(LogLevel::SUCCESS, "EXTRACT", format!("Iniciando extracao em {}", install_path));
    let root = Path::new(&install_path);

    // 1. Find archives
    let rars = find_files_recursive(root, "rar");
    let zips = find_files_recursive(root, "zip");
    let all_archives: Vec<PathBuf> = rars.into_iter().chain(zips).collect();
    if all_archives.is_empty() {
        return Err("Nenhum arquivo encontrado no diretorio de download".into());
    }

    // 2. Separate game from fix
    let mut game_archives: Vec<PathBuf> = Vec::new();
    let mut fix_archives: Vec<PathBuf> = Vec::new();
    for archive in &all_archives {
        let lower = archive.to_string_lossy().to_lowercase();
        if lower.contains("fix") || lower.contains("repair") {
            fix_archives.push(archive.clone());
        } else {
            game_archives.push(archive.clone());
        }
    }
    game_archives.sort_by(compare_archives);
    fix_archives.sort_by(compare_archives);

    let total_jobs = game_archives.len() + fix_archives.len();
    log_tag(LogLevel::INFO, "EXTRACT", format!("{} arquivo(s) de jogo e {} fix", game_archives.len(), fix_archives.len()));

    // 3. Extract game archives
    let game_extract_dir = game_archives.first()
        .and_then(|a| a.parent())
        .unwrap_or(root);

    for (i, archive) in game_archives.iter().enumerate() {
        let pct_start = (i as f64 / total_jobs as f64) * 100.0;
        let pct_end = ((i + 1) as f64 / total_jobs as f64) * 100.0;
        let file_name = archive.file_name().unwrap_or_default().to_string_lossy().to_string();
        log_tag(LogLevel::INFO, "EXTRACT", format!("[{}/{}] Jogo: {}", i + 1, total_jobs, file_name));
        run_extract_with_progress(archive, game_extract_dir, &app,
            pct_start, pct_end, i + 1, total_jobs, "extracting", &file_name).await?;
    }

    // 4. Save fix archive to temp (preserve while we delete Fix Repair dir)
    let fix_tmp_dir = std::env::temp_dir().join("gr_extract_tmp");
    std::fs::create_dir_all(&fix_tmp_dir).map_err(|e| e.to_string())?;
    let mut fix_tmp_paths: Vec<PathBuf> = Vec::new();

    for (i, fix_archive) in fix_archives.iter().enumerate() {
        let dest = fix_tmp_dir.join(format!("fix_{}.rar", i));
        std::fs::copy(fix_archive, &dest)
            .map_err(|e| format!("Nao foi possivel copiar o fix: {}", e))?;
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

    // 5. Flatten duplicate nested dirs
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
        run_extract_with_progress(fix_tmp_path, &game_dir, &app,
            pct_start, pct_end, idx + 1, total_jobs, "extracting_fix", &file_name).await?;
    }

    // 8. Move everything from deepest nested dir to root
    let deepest = find_deepest_same_name_dir(root);
    if deepest != root && deepest.exists() {
        log_tag(LogLevel::INFO, "EXTRACT", format!("Movendo conteudo de {:?} para raiz", deepest));
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

    log_tag(LogLevel::SUCCESS, "EXTRACT", "Extracao completa!");
    let _ = app.emit("extract-progress", serde_json::json!({"type": "done"}));
    Ok(())
}

fn compare_archives(a: &PathBuf, b: &PathBuf) -> Ordering {
    let a_key = archive_sort_key(a);
    let b_key = archive_sort_key(b);

    a_key.kind_rank.cmp(&b_key.kind_rank)
        .then_with(|| a_key.group_name.cmp(&b_key.group_name))
        .then_with(|| a_key.part_number.unwrap_or(0).cmp(&b_key.part_number.unwrap_or(0)))
        .then_with(|| a_key.file_name.cmp(&b_key.file_name))
}

fn archive_sort_key(path: &Path) -> ArchiveSortKey {
    let file_name = path.file_name()
        .map(|name| name.to_string_lossy().to_string())
        .unwrap_or_default();
    let lower_name = file_name.to_lowercase();

    if let Some((group_name, part_number)) = parse_multi_part_info(&lower_name) {
        return ArchiveSortKey {
            kind_rank: 0,
            group_name,
            part_number: Some(part_number),
            file_name: lower_name,
        };
    }

    ArchiveSortKey {
        kind_rank: 1,
        group_name: lower_name.clone(),
        part_number: None,
        file_name: lower_name,
    }
}

fn parse_multi_part_info(file_name: &str) -> Option<(String, u32)> {
    let lower = file_name.to_lowercase();
    let dot_part = lower.find(".part")?;
    let part_digits_start = dot_part + 5;
    let digits: String = lower[part_digits_start..]
        .chars()
        .take_while(|ch| ch.is_ascii_digit())
        .collect();

    if digits.is_empty() {
        return None;
    }

    let part_number = digits.parse::<u32>().ok()?;
    let group_name = format!(
        "{}{}",
        &lower[..dot_part],
        &lower[part_digits_start + digits.len()..]
    );

    Some((group_name, part_number))
}

/// Try system 7z first, fallback to sevenz-rust
async fn extract_rust_or_7z(app: &AppHandle, archive: &Path, out_dir: &str) -> Result<(), String> {
    if let Some(sevenz) = ensure_7z(app).await {
        log_tag(LogLevel::SUCCESS, "EXTRACT", format!("Usando 7-Zip para {}",
            archive.file_name().unwrap_or_default().to_string_lossy()));

        let output = Command::new(&sevenz)
            .args(&[
                "x",
                &archive.to_string_lossy(),
                &format!("-o{}", out_dir),
                &format!("-p{}", PASSWORD),
                "-y",
                "-bb1",
                "-bso1",
                "-bsp1",
            ])
            .creation_flags(0x08000000)
            .stdout(Stdio::piped())
            .stderr(Stdio::null())
            .spawn();

        if let Ok(mut child) = output {
            let mut progress_output = String::new();
            if let Some(stdout) = child.stdout.take() {
                let mut reader = BufReader::new(stdout);
                let _ = reader.read_to_string(&mut progress_output);
            }

            let status = child.wait().map_err(|e| e.to_string())?;

            if status.success() {
                return Ok(());
            }

            log_tag(
                LogLevel::INFO,
                "EXTRACT",
                format!("7-Zip falhou (exit {}), tentando sevenz-rust", status.code().unwrap_or(-1))
            );
            if !progress_output.trim().is_empty() {
                log_tag(LogLevel::DEBUG, "EXTRACT", progress_output);
            }
        }
    }

    decompress_file_with_password(archive, out_dir, Password::from(PASSWORD))
        .map_err(|e| format!("Falha ao extrair {} (erro: {})", archive.file_name().unwrap_or_default().to_string_lossy(), e))?;

    Ok(())
}

/// Extract archive using system 7z with sevenz-rust fallback
async fn run_extract_with_progress(
    archive: &Path, out_dir: &Path,
    app: &AppHandle, pct_start: f64, pct_end: f64,
    current: usize, total: usize, label: &str, file_name: &str,
) -> Result<(), String> {
    let _ = app.emit("extract-progress", serde_json::json!({
        "type": label,
        "file": file_name,
        "current": current,
        "total": total,
        "global_pct": format!("{:.1}", pct_start)
    }));

    std::fs::create_dir_all(out_dir).map_err(|e| e.to_string())?;

    if let Some(sevenz) = ensure_7z(app).await {
        extract_with_7z_progress(
            &sevenz,
            archive,
            out_dir,
            app,
            pct_start,
            pct_end,
            current,
            total,
            label,
            file_name,
        ).await.map_err(|e| format!("Falha ao extrair {} (erro: {})", file_name, e))?;
    } else {
        extract_rust_or_7z(app, archive, &out_dir.to_string_lossy())
            .await
            .map_err(|e| format!("Falha ao extrair {} (erro: {})", file_name, e))?;
    }

    let _ = app.emit("extract-progress", serde_json::json!({
        "type": label,
        "file": file_name,
        "current": current,
        "total": total,
        "archive_pct": 100.0,
        "global_pct": format!("{:.1}", pct_end)
    }));

    Ok(())
}

async fn extract_with_7z_progress(
    sevenz: &Path,
    archive: &Path,
    out_dir: &Path,
    app: &AppHandle,
    pct_start: f64,
    pct_end: f64,
    current: usize,
    total: usize,
    label: &str,
    file_name: &str,
) -> Result<(), String> {
    let mut cmd = Command::new(sevenz);
    cmd.args(&[
        "x",
        &archive.to_string_lossy(),
        &format!("-o{}", out_dir.to_string_lossy()),
        &format!("-p{}", PASSWORD),
        "-y",
        "-bb1",
        "-bso1",
        "-bsp1",
    ]);
    #[cfg(target_os = "windows")]
    cmd.creation_flags(0x08000000);

    let mut child = cmd
        .stdout(Stdio::piped())
        .stderr(Stdio::null())
        .spawn()
        .map_err(|e| e.to_string())?;

    if let Some(stdout) = child.stdout.take() {
        let mut reader = BufReader::new(stdout);
        let mut buffer = [0u8; 1024];
        let mut pending = String::new();
        let mut last_percent = 0.0f64;

        loop {
            let read = reader.read(&mut buffer).map_err(|e| e.to_string())?;
            if read == 0 {
                break;
            }

            pending.push_str(&String::from_utf8_lossy(&buffer[..read]));

            while let Some(split_idx) = pending.find(['\r', '\n']) {
                let line = pending[..split_idx].trim().to_string();
                let delimiter_len = pending[split_idx..]
                    .chars()
                    .take_while(|ch| *ch == '\r' || *ch == '\n')
                    .count();
                pending.drain(..split_idx + delimiter_len);

                if let Some(percent) = parse_7z_percent(&line) {
                    last_percent = percent;
                    emit_extract_progress(app, label, file_name, current, total, pct_start, pct_end, percent);
                }
            }
        }

        let trailing = pending.trim();
        if let Some(percent) = parse_7z_percent(trailing) {
            last_percent = percent;
        }

        if last_percent < 100.0 {
            emit_extract_progress(app, label, file_name, current, total, pct_start, pct_end, last_percent);
        }
    }

    let status = child.wait().map_err(|e| e.to_string())?;
    if !status.success() {
        return Err(format!("7-Zip retornou codigo {}", status.code().unwrap_or(-1)));
    }

    Ok(())
}

fn emit_extract_progress(
    app: &AppHandle,
    label: &str,
    file_name: &str,
    current: usize,
    total: usize,
    pct_start: f64,
    pct_end: f64,
    archive_pct: f64,
) {
    let clamped_pct = archive_pct.clamp(0.0, 100.0);
    let global_pct = pct_start + ((pct_end - pct_start) * (clamped_pct / 100.0));

    let _ = app.emit("extract-progress", serde_json::json!({
        "type": label,
        "file": file_name,
        "current": current,
        "total": total,
        "archive_pct": clamped_pct,
        "global_pct": format!("{:.1}", global_pct)
    }));
}

fn parse_7z_percent(line: &str) -> Option<f64> {
    let trimmed = line.trim_start();
    let digits: String = trimmed.chars()
        .take_while(|ch| ch.is_ascii_digit())
        .collect();

    if digits.is_empty() {
        return None;
    }

    let remainder = &trimmed[digits.len()..];
    if !remainder.starts_with('%') {
        return None;
    }

    digits.parse::<f64>().ok()
}

/// Walk down a chain of nested dirs where subdir name matches parent name.
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

/// Top-down flatten: for each dir, if it has only 1 subdir with the SAME name
/// and no files at this level, merge the subdir up. Returns count flattened.
fn flatten_one_pass(root: &Path) -> usize {
    let mut count = 0;
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
fn title_match_score(exe_stem: &str, title_words: &[&str]) -> i32 {
    let exe_lower = exe_stem.to_lowercase();
    let mut score = 0;
    for word in title_words {
        let w = word.to_lowercase();
        if w.len() < 3 { continue; }
        if exe_lower == w {
            score += 100;
        } else if exe_lower.contains(&w) {
            score += 50;
        } else if w.len() >= 5 && w.split_whitespace().next().map(|s| exe_lower.contains(&s.to_lowercase())).unwrap_or(false) {
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
    let ignored = [
        "unins000", "crashreport", "crashhandler", "unitycrashhandler", "unityplayer",
        "dxsetup", "vcredist", "dotnet", "redist", "setup", "launcher", "prereq", "cefprocess",
        "shadercache", "mono", "unity"
    ];
    let skip_words = ["the", "of", "and", "or", "a", "an", "in", "on", "to", "vs",
                      "do", "da", "e", "em", "de", "para", "com", "por", "sem", "que", "na", "no", "nos", "das", "dos", "se", "seu", "sua", "ele", "ela"];
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
        if ignored.iter().any(|&i| name.contains(i)) { continue; }
        if let Ok(meta) = exe.metadata() {
            if meta.len() < 100_000 { continue; }
        }
        let depth = exe.components().count() as i32;
        let mut score = 100 - depth * 10;
        if !title_words.is_empty() {
            score += title_match_score(&stem, &title_words);
        }
        if let Some(parent) = exe.parent() {
            score += dir_game_bonus(parent);
        }
        if score > best_score {
            best_score = score;
            best_exe = exe.to_string_lossy().into_owned();
        }
    }

    if best_exe.is_empty() {
        log_tag(LogLevel::WARN, "EXE", "Nenhum executavel encontrado");
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
