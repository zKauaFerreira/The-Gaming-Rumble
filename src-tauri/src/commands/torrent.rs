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
    // 1. Try bundled resources
    if let Ok(resources) = app.path().resolve("bin/aria2c.exe", tauri::path::BaseDirectory::Resource) {
        if resources.exists() { return Ok(resources); }
    }

    // 2. Fallback: copy to user app_data
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

#[tauri::command]
pub async fn start_torrent(app: AppHandle, magnet: String, install_path: String) -> Result<(), String> {
    // Kill any existing aria2c first
    let _ = stop_torrent();
    // Give it a moment to release file handles
    tokio::time::sleep(std::time::Duration::from_millis(500)).await;

    let aria2_exe = ensure_aria2c(&app).await?;

    #[cfg(target_os = "windows")]
    use std::os::windows::process::CommandExt;

    // Clean magnet: remove dn (breaks aria2c with & in names), decode trackers
    let cleaned = clean_magnet(&magnet);

    // Write to temp file so Windows CreateProcess doesn't corrupt the URL
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
        "--bt-stop-timeout=60".into(),
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
                // Console: only important events
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

    // Clean temp file
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
