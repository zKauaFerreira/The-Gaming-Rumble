use std::path::PathBuf;
use std::process::{Command, Stdio};
use std::io::{BufRead, BufReader};
use tauri::{AppHandle, Emitter, Manager};

use super::logger::{LogLevel, log, log_tag};

fn get_trackers() -> String {
    let mut trackers = Vec::new();
    trackers.push("udp://tracker.opentrackr.org:1337/announce");
    trackers.push("udp://open.demonii.com:1337/announce");
    trackers.push("udp://open.tracker.cl:1337/announce");
    trackers.push("udp://open.stealth.si:80/announce");
    trackers.push("udp://exodus.desync.com:6969/announce");
    trackers.push("udp://tracker.torrent.eu.org:451/announce");
    trackers.push("udp://tracker.tiny-vps.com:6969/announce");
    trackers.push("udp://tracker.cyberia.is:6969/announce");
    trackers.push("udp://explodie.org:6969/announce");
    trackers.push("udp://tracker.openbittorrent.org:1337/announce");
    trackers.push("udp://tracker.leech.ie:1337/announce");
    trackers.push("udp://retracker.lanta-net.ru:2710/announce");
    trackers.push("http://tracker.openbittorrent.com:80/announce");
    trackers.push("https://tracker.tamersunion.org:443/announce");
    trackers.push("wss://tracker.btorrent.xyz:443");
    trackers.push("wss://tracker.openwebtorrent.com:443");
    trackers.join(",")
}

async fn ensure_aria2c(app: &AppHandle) -> Result<PathBuf, String> {
    if let Ok(resources) = app.path().resolve("bin/aria2c.exe", tauri::path::BaseDirectory::Resource) {
        if resources.exists() { return Ok(resources); }
    }
    let app_data = app.path().app_data_dir().unwrap();
    let bin_dir = app_data.join("bin");
    let aria2_exe = bin_dir.join("aria2c.exe");
    if aria2_exe.exists() { return Ok(aria2_exe); }
    std::fs::create_dir_all(&bin_dir).map_err(|e| e.to_string())?;
    let url = "https://github.com/aria2/aria2/releases/download/release-1.37.0/aria2-1.37.0-win-64bit-build1.zip";
    log(LogLevel::WARN, "aria2c não encontrado como recurso, baixando fallback...");
    let client = reqwest::Client::new();
    let response = client.get(url).send().await.map_err(|e| e.to_string())?;
    let bytes = response.bytes().await.map_err(|e| e.to_string())?;
    let reader = std::io::Cursor::new(bytes);
    let mut archive = zip::ZipArchive::new(reader).map_err(|e| e.to_string())?;
    for i in 0..archive.len() {
        let mut file = archive.by_index(i).unwrap();
        if file.name().ends_with("aria2c.exe") {
            let mut out = std::fs::File::create(&aria2_exe).map_err(|e| e.to_string())?;
            std::io::copy(&mut file, &mut out).map_err(|e| e.to_string())?;
            return Ok(aria2_exe);
        }
    }
    Err("aria2c.exe não encontrado".into())
}

/// Fetch torrent metadata without downloading any files.
/// Returns the .torrent file path that aria2c saves.
async fn fetch_metadata_only(aria2_exe: &std::path::Path, magnet: &str, dir: &str) -> Result<PathBuf, String> {
    #[cfg(target_os = "windows")]
    use std::os::windows::process::CommandExt;

    let cleaned = clean_magnet(magnet);
    let input_file = std::env::temp_dir().join("gr_meta_fetch.txt");
    std::fs::write(&input_file, format!("{}\n", cleaned)).map_err(|e| e.to_string())?;
    let input_path = input_file.to_string_lossy().replace('\\', "/");

    log_tag(LogLevel::INFO, "DOWNLOAD", "Buscando metadados do torrent...");

    let args = vec![
        format!("--input-file={}", input_path),
        format!("--dir={}", dir),
        "--bt-metadata-only=true".into(),
        "--bt-save-metadata=true".into(),
        "--seed-time=0".into(),
        "--summary-interval=0".into(),
        "--enable-rpc=false".into(),
        "--bt-enable-lpd=true".into(),
        format!("--bt-tracker={}", get_trackers()),
        "--connect-timeout=10".into(),
        "--bt-tracker-connect-timeout=5".into(),
        "--bt-tracker-timeout=5".into(),
        "--timeout=10".into(),
        "--bt-stop-timeout=30".into(),
        "--max-concurrent-downloads=1".into(),
        "--dht-entry-point=router.bittorrent.com:6881".into(),
        "--bt-max-peers=0".into(),
        "--bt-request-peer-speed-limit=15M".into(),
    ];

    let mut cmd = Command::new(aria2_exe);
    cmd.args(&args);
    #[cfg(target_os = "windows")]
    cmd.creation_flags(0x08000000);

    let status = cmd.stdout(Stdio::piped()).stderr(Stdio::piped())
        .spawn().map_err(|e| e.to_string())?
        .wait().map_err(|e| e.to_string())?;

    let _ = std::fs::remove_file(&input_file);

    if !status.success() {
        return Err("Falha ao buscar metadados do torrent.".into());
    }

    let meta_dir = PathBuf::from(dir);
    for entry in std::fs::read_dir(&meta_dir).map_err(|e| e.to_string())? {
        let entry = entry.map_err(|e| e.to_string())?;
        if entry.path().extension().and_then(|e| e.to_str()) == Some("torrent") {
            log_tag(LogLevel::SUCCESS, "DOWNLOAD", "Metadados obtidos.");
            return Ok(entry.path());
        }
    }
    Err("Arquivo .torrent não encontrado após busca de metadados.".into())
}

// --- Minimal bencode parser ---

#[allow(dead_code)]
#[derive(Debug)]
enum BValue {
    Integer(i64),
    Str(Vec<u8>),
    List(Vec<BValue>),
    Dict(std::collections::HashMap<Vec<u8>, BValue>),
}

fn bkey(s: &'static str) -> Vec<u8> {
    s.as_bytes().to_vec()
}

fn dict_get<'a>(dict: &'a std::collections::HashMap<Vec<u8>, BValue>, key: &'static str) -> Option<&'a BValue> {
    dict.get(&bkey(key))
}

fn parse_bencode(bytes: &[u8], pos: usize) -> Result<(usize, BValue), String> {
    if pos >= bytes.len() {
        return Err("EOF".into());
    }
    match bytes[pos] {
        b'i' => {
            let end = bytes[pos + 1..].iter().position(|&b| b == b'e').map(|p| p + pos + 1).ok_or("Unterminated int")?;
            let num_str = std::str::from_utf8(&bytes[pos + 1..end]).map_err(|e| e.to_string())?;
            let val: i64 = num_str.parse::<i64>().map_err(|e: std::num::ParseIntError| e.to_string())?;
            Ok((end + 1, BValue::Integer(val)))
        }
        b'l' => {
            let mut list = Vec::new();
            let mut p = pos + 1;
            while p < bytes.len() && bytes[p] != b'e' {
                let (next, v) = parse_bencode(bytes, p)?;
                list.push(v);
                p = next;
            }
            Ok((p + 1, BValue::List(list)))
        }
        b'd' => {
            let mut dict = std::collections::HashMap::new();
            let mut p = pos + 1;
            while p < bytes.len() && bytes[p] != b'e' {
                let (key_end, key) = parse_bencode_string(bytes, p)?;
                let (val_end, val) = parse_bencode(bytes, key_end)?;
                dict.insert(key, val);
                p = val_end;
            }
            Ok((p + 1, BValue::Dict(dict)))
        }
        b'0'..=b'9' => {
            let (end, s) = parse_bencode_string(bytes, pos)?;
            Ok((end, BValue::Str(s)))
        }
        _ => Err(format!("Unexpected byte in bencode: {:?}", bytes[pos] as char)),
    }
}

fn parse_bencode_string(bytes: &[u8], pos: usize) -> Result<(usize, Vec<u8>), String> {
    let colon = bytes[pos..].iter().position(|&b| b == b':').map(|p| p + pos).ok_or("No colon in bencode string")?;
    let len_str = std::str::from_utf8(&bytes[pos..colon]).map_err(|e| e.to_string())?;
    let len: usize = len_str.parse::<usize>().map_err(|e: std::num::ParseIntError| e.to_string())?;
    let start = colon + 1;
    let content = bytes[start..start + len].to_vec();
    Ok((start + len, content))
}

/// Parse a .torrent file and find the file index of a file matching 'fix' in its name.
fn find_fix_index(torrent_path: &std::path::Path) -> Result<usize, String> {
    let bytes = std::fs::read(torrent_path).map_err(|e| e.to_string())?;
    let (_, outer) = parse_bencode(&bytes, 0).map_err(|e| format!("Erro ao parsear torrent: {}", e))?;

    let BValue::Dict(ref outer_d) = outer else {
        return Err("Torrent root is not a dict".into());
    };
    let Some(BValue::Dict(ref info)) = dict_get(outer_d, "info") else {
        return Err("'info' dict not found in torrent".into());
    };

    if let Some(BValue::List(ref files)) = dict_get(info, "files") {
        for (idx, file) in files.iter().enumerate() {
            if let BValue::Dict(ref fd) = file {
                if let Some(BValue::List(ref path_parts)) = dict_get(fd, "path") {
                    let filename = path_parts.iter()
                        .filter_map(|p| match p {
                            BValue::Str(s) => Some(String::from_utf8_lossy(s).to_string().to_lowercase()),
                            _ => None,
                        })
                        .collect::<Vec<_>>()
                        .join("/")
                        .to_lowercase();
                    eprintln!("[torrent.rs] File[{}] = {}", idx, filename);
                    if filename.contains("fix") {
                        return Ok(idx + 1); // 1-based for aria2c --select-file
                    }
                }
            }
        }
    } else if let Some(BValue::Str(name)) = dict_get(info, "name") {
        let name_lower = String::from_utf8_lossy(name).to_string().to_lowercase();
        if name_lower.contains("fix") {
            return Ok(1); // 1-based for aria2c
        }
    }
    Err("Fix.rar não encontrado nos metadados do torrent.".into())
}

#[tauri::command]
pub async fn start_torrent(app: AppHandle, magnet: String, install_path: String) -> Result<(), String> {
    let _ = stop_torrent();
    tokio::time::sleep(std::time::Duration::from_millis(500)).await;

    let aria2_exe = ensure_aria2c(&app).await?;

    #[cfg(target_os = "windows")]
    use std::os::windows::process::CommandExt;

    let cleaned = clean_magnet(&magnet);
    let input_file = std::env::temp_dir().join("gr_magnet.txt");
    std::fs::write(&input_file, format!("{}\n", cleaned)).map_err(|e| e.to_string())?;
    let input_path = input_file.to_string_lossy().replace('\\', "/");

    log_tag(LogLevel::SUCCESS, "DOWNLOAD", "Transmissão iniciada — aria2c rodando");

    let args = vec![
        format!("--input-file={}", input_path),
        format!("--dir={}", install_path),
        "--bt-metadata-only=false".into(),
        "--bt-save-metadata=false".into(),
        "--seed-time=0".into(),
        "--summary-interval=1".into(),
        "--enable-rpc=false".into(),
        "--bt-enable-lpd=true".into(),
        "--allow-overwrite=true".into(),
        "--auto-file-renaming=false".into(),
        "--file-allocation=none".into(),
        format!("--bt-tracker={}", get_trackers()),
        "--dht-entry-point=router.bittorrent.com:6881".into(),
        "--max-concurrent-downloads=1".into(),
        "--max-connection-per-server=16".into(),
        "--bt-max-peers=0".into(),
        "--bt-request-peer-speed-limit=15M".into(),
        "--bt-tracker-connect-timeout=5".into(),
        "--bt-tracker-timeout=5".into(),
        "--connect-timeout=10".into(),
        "--timeout=10".into(),
        "--max-resume-failure-tries=10".into(),
        "--lowest-speed-limit=10K".into(),
        "--bt-stop-timeout=120".into(),
        "--peer-id-prefix=-GR1000-".into(),
        "--user-agent=GamingRumble/1.0".into(),
    ];

    let mut cmd = Command::new(&aria2_exe);
    cmd.args(&args);
    #[cfg(target_os = "windows")]
    cmd.creation_flags(0x08000000);

    let mut child = cmd
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .spawn()
        .map_err(|e| e.to_string())?;

    let app1 = app.clone();
    let stdout = child.stdout.take().unwrap();
    tokio::spawn(async move {
        let reader = BufReader::new(stdout);
        for line in reader.lines() {
            if let Ok(l) = line {
                let _ = app1.emit("download-log", l.clone());
                if l.contains("NOTICE") || l.contains("ERROR") || l.contains("Exception") || l.contains("errorCode") {
                    let short = l.replace("\x1b[0m", "").replace("\x1b[1m", "");
                    if short.contains("NOTICE") || short.contains("ERROR") {
                        log_tag(LogLevel::INFO, "DOWNLOAD", short);
                    }
                }
            }
        }
    });

    let app2 = app.clone();
    let stderr = child.stderr.take().unwrap();
    tokio::spawn(async move {
        for line in BufReader::new(stderr).lines() {
            if let Ok(l) = line {
                let _ = app2.emit("download-log", format!("ERROR: {}", l));
                log_tag(LogLevel::ERROR, "DOWNLOAD", l);
            }
        }
    });

    tokio::spawn(async move {
        tokio::time::sleep(std::time::Duration::from_secs(3)).await;
        let _ = std::fs::remove_file(&input_file);
    });

    Ok(())
}

#[tauri::command]
pub async fn start_fix_download(app: AppHandle, magnet: String, install_path: String) -> Result<(), String> {
    let _ = stop_torrent();
    tokio::time::sleep(std::time::Duration::from_millis(500)).await;

    let aria2_exe = ensure_aria2c(&app).await?;

    std::fs::create_dir_all(&install_path).map_err(|e| e.to_string())?;
    let meta_path = fetch_metadata_only(&aria2_exe, &magnet, &install_path).await?;

    let fix_idx = find_fix_index(&meta_path)?;
    log_tag(LogLevel::INFO, "DOWNLOAD", format!("Fix.rar encontrado no índice {}.", fix_idx));

    #[cfg(target_os = "windows")]
    use std::os::windows::process::CommandExt;

    let cleaned = clean_magnet(&magnet);
    let input_file = std::env::temp_dir().join("gr_fix.txt");
    std::fs::write(&input_file, format!("{}\n", cleaned)).map_err(|e| e.to_string())?;
    let input_path = input_file.to_string_lossy().replace('\\', "/");

    log_tag(LogLevel::SUCCESS, "DOWNLOAD", format!("Baixando apenas Fix.rar (--select-file={})", fix_idx));

    let mut args = vec![
        format!("--input-file={}", input_path),
        format!("--dir={}", install_path),
        "--bt-metadata-only=false".into(),
        "--bt-save-metadata=false".into(),
        format!("--select-file={}", fix_idx),
        "--seed-time=0".into(),
        "--summary-interval=1".into(),
        "--enable-rpc=false".into(),
        "--bt-enable-lpd=true".into(),
        "--allow-overwrite=true".into(),
        "--auto-file-renaming=false".into(),
        "--file-allocation=none".into(),
        format!("--bt-tracker={}", get_trackers()),
        "--dht-entry-point=router.bittorrent.com:6881".into(),
        "--max-concurrent-downloads=1".into(),
        "--max-connection-per-server=16".into(),
        "--bt-max-peers=0".into(),
        "--bt-request-peer-speed-limit=15M".into(),
        "--bt-tracker-connect-timeout=5".into(),
        "--bt-tracker-timeout=5".into(),
        "--connect-timeout=10".into(),
        "--timeout=10".into(),
        "--max-resume-failure-tries=10".into(),
        "--lowest-speed-limit=10K".into(),
        "--bt-stop-timeout=60".into(),
        "--peer-id-prefix=-GR1000-".into(),
        "--user-agent=GamingRumble/1.0".into(),
    ];

    let meta_clone = meta_path.clone();
    tokio::spawn(async move {
        tokio::time::sleep(std::time::Duration::from_secs(2)).await;
        let _ = std::fs::remove_file(&meta_clone);
    });

    #[cfg(target_os = "windows")]
    { args.push("--enable-color=false".into()); }

    let mut cmd = Command::new(&aria2_exe);
    cmd.args(&args);
    #[cfg(target_os = "windows")]
    cmd.creation_flags(0x08000000);

    let mut child = cmd
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .spawn()
        .map_err(|e| e.to_string())?;

    let app1 = app.clone();
    let stdout = child.stdout.take().unwrap();
    tokio::spawn(async move {
        let reader = BufReader::new(stdout);
        for line in reader.lines() {
            if let Ok(l) = line {
                let _ = app1.emit("download-log", l.clone());
                if l.contains("NOTICE") || l.contains("ERROR") || l.contains("Exception") || l.contains("errorCode") {
                    let short = l.replace("\x1b[0m", "").replace("\x1b[1m", "");
                    if short.contains("NOTICE") || short.contains("ERROR") {
                        log_tag(LogLevel::INFO, "DOWNLOAD", short);
                    }
                }
            }
        }
    });

    let app2 = app.clone();
    let stderr = child.stderr.take().unwrap();
    tokio::spawn(async move {
        for line in BufReader::new(stderr).lines() {
            if let Ok(l) = line {
                let _ = app2.emit("download-log", format!("ERROR: {}", l));
                log_tag(LogLevel::ERROR, "DOWNLOAD", l);
            }
        }
    });

    tokio::spawn(async move {
        tokio::time::sleep(std::time::Duration::from_secs(3)).await;
        let _ = std::fs::remove_file(&input_file);
    });

    Ok(())
}

fn url_decode(input: &str) -> String {
    let bytes = input.as_bytes();
    let mut result = Vec::<u8>::with_capacity(input.len());
    let mut i = 0;
    while i < bytes.len() {
        if bytes[i] == b'%' && i + 2 < bytes.len() {
            if let Some(hex) = hex_byte(bytes[i + 1], bytes[i + 2]) {
                result.push(hex);
                i += 3;
                continue;
            }
        }
        result.push(bytes[i]);
        i += 1;
    }
    String::from_utf8_lossy(&result).to_string()
}

fn hex_byte(h: u8, l: u8) -> Option<u8> {
    let dh = (h as char).to_digit(16)?;
    let dl = (l as char).to_digit(16)?;
    Some((dh * 16 + dl) as u8)
}

fn clean_magnet(magnet: &str) -> String {
    let magnet = magnet.trim();
    if !magnet.starts_with("magnet:?") {
        return String::new();
    }
    let magnet_query = &magnet[8..];
    let mut parts: Vec<(&str, &str)> = Vec::new();
    for segment in magnet_query.split('&') {
        let seg = segment.trim_start_matches('?');
        if let Some(idx) = seg.find('=') {
            parts.push((&seg[..idx], &seg[idx + 1..]));
        } else if !seg.is_empty() && seg != "?" {
            parts.push((seg, ""));
        }
    }
    let mut rebuilt = String::from("magnet:?");
    let mut first = true;
    for (key, val) in &parts {
        if *key == "dn" { continue; }
        if !first { rebuilt.push('&'); }
        first = false;
        if *key == "tr" {
            rebuilt.push_str(&format!("{}={}", key, url_decode(val)));
        } else {
            rebuilt.push_str(&format!("{}={}", key, val));
        }
    }
    rebuilt
}

#[tauri::command]
pub fn stop_torrent() -> Result<(), String> {
    #[cfg(target_os = "windows")]
    {
        use std::os::windows::process::CommandExt;
        let status = Command::new("taskkill")
            .args(["/F", "/IM", "aria2c.exe"])
            .creation_flags(0x08000000)
            .stdout(Stdio::null())
            .stderr(Stdio::null())
            .status()
            .ok();
        if let Some(s) = status {
            if s.success() {
                log_tag(LogLevel::INFO, "DOWNLOAD", "aria2c encerrado");
            }
        }
        Ok(())
    }
    #[cfg(not(target_os = "windows"))]
    Ok(())
}
