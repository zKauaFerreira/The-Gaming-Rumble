use std::process::{Command, Stdio};
use std::path::PathBuf;

#[tauri::command]
pub fn check_is_admin() -> bool {
    #[cfg(target_os = "windows")]
    {
        let output = Command::new("net")
            .arg("session")
            .output();
        output.map(|o| o.status.success()).unwrap_or(false)
    }
    #[cfg(not(target_os = "windows"))]
    true
}

#[tauri::command]
pub async fn create_gaming_rumble_folder(drive: String) -> Result<(), String> {
    let path = PathBuf::from(&drive).join("Gaming Rumble");
    std::fs::create_dir_all(&path).map_err(|e| e.to_string())?;
    Ok(())
}

#[tauri::command]
pub fn add_defender_exclusion(path: String) -> Result<(), String> {
    #[cfg(target_os = "windows")]
    {
        use std::os::windows::process::CommandExt;
        let status = Command::new("powershell")
            .args(["-Command", &format!("Add-MpPreference -ExclusionPath '{}'", path)])
            .creation_flags(0x08000000)
            .status()
            .map_err(|e| e.to_string())?;

        if !status.success() {
            return Err("Falha ao adicionar exclusão (provavelmente falta Admin)".into());
        }
    }
    Ok(())
}

#[tauri::command]
pub fn play_game(executable: String) -> Result<(), String> {
    std::process::Command::new(&executable)
        .spawn()
        .map_err(|e| e.to_string())?;
    Ok(())
}

#[tauri::command]
pub fn open_path(_path: String, select_file: String) -> Result<(), String> {
    #[cfg(target_os = "windows")]
    {
        use std::os::windows::process::CommandExt;
        Command::new("explorer")
            .arg("/select,")
            .arg(&select_file)
            .creation_flags(0x08000000)
            .stdout(std::process::Stdio::null())
            .stderr(std::process::Stdio::null())
            .spawn()
            .map_err(|e| format!("Falha ao abrir pasta: {}", e))?;
    }
    Ok(())
}

#[tauri::command]
pub fn show_exe_picker(default_path: String) -> Result<Option<String>, String> {
    #[cfg(target_os = "windows")]
    {
        use std::os::windows::process::CommandExt;

        // Create a PowerShell script to show a file picker dialog
        let ps_script = r#"
Add-Type -AssemblyName System.Windows.Forms
$dialog = New-Object System.Windows.Forms.OpenFileDialog
$dialog.InitialDirectory = '{default_path}'
$dialog.Filter = "Executables (*.exe)|*.exe|All files (*.*)|*.*"
$dialog.Title = "Selecionar Executável"
$result = $dialog.ShowDialog()
if ($result -eq [System.Windows.Forms.DialogResult]::OK) {
    Write-Output $dialog.FileName
} else {
    Write-Output "CANCELLED"
}
        "#.replace("{default_path}", &default_path).replace('/', "\\");

        // Write ps temp file
        let temp_ps = std::env::temp_dir().join("gr_picker.ps1");
        std::fs::write(&temp_ps, &ps_script).ok();
        let ps_path = temp_ps.to_string_lossy().replace('/', "\\");

        let mut cmd = Command::new("powershell");
        cmd.arg("-NoProfile")
           .arg("-WindowStyle")
           .arg("Hidden")
           .arg("-File")
           .arg(&ps_path)
           .creation_flags(0x08000000)
           .stdout(std::process::Stdio::piped())
           .stderr(std::process::Stdio::null());

        let output = cmd.output().map_err(|e| e.to_string())?;
        let result = String::from_utf8_lossy(&output.stdout).trim().to_string();
        let _ = std::fs::remove_file(&temp_ps);

        if result == "CANCELLED" || result.is_empty() {
            return Ok(None);
        }

        Ok(Some(result.trim().trim_end_matches('\r').to_string()))
    }

    #[cfg(not(target_os = "windows"))]
    {
        Ok(None)
    }
}

#[tauri::command]
pub fn update_executable(title: String, executable: String) -> Result<(), String> {
    use std::fs;

    let drives = ['D', 'C', 'E', 'F', 'G'];
    for drive in drives {
        let lib_path = format!("{}:\\Gaming Rumble\\library.json", drive);
        if fs::metadata(&lib_path).is_ok() {
            let content = fs::read_to_string(&lib_path).map_err(|e| e.to_string())?;
            let mut config: serde_json::Value = serde_json::from_str(&content).map_err(|e| e.to_string())?;

            if let Some(games) = config.get_mut("games").and_then(|v| v.as_array_mut()) {
                for game in games.iter_mut() {
                    if game.get("title").and_then(|v| v.as_str()) == Some(&title) {
                        game["executable"] = serde_json::json!(executable);
                        let updated = serde_json::to_string_pretty(&config).map_err(|e| e.to_string())?;
                        fs::write(&lib_path, updated).map_err(|e| e.to_string())?;
                        return Ok(());
                    }
                }
            }
            if let Some(downloads) = config.get_mut("downloads").and_then(|v| v.as_array_mut()) {
                for game in downloads.iter_mut() {
                    if game.get("title").and_then(|v| v.as_str()) == Some(&title) {
                        game["executable"] = serde_json::json!(executable);
                        let updated = serde_json::to_string_pretty(&config).map_err(|e| e.to_string())?;
                        fs::write(&lib_path, updated).map_err(|e| e.to_string())?;
                        return Ok(());
                    }
                }
            }
            return Err("Jogo não encontrado na biblioteca".into());
        }
    }
    Err("Biblioteca não encontrada".into())
}

/// Create a .lnk shortcut in the Start Menu Programs folder for a game
#[tauri::command]
pub fn create_shortcut(title: String, executable: String, icon: Option<String>) -> Result<(), String> {
    #[cfg(target_os = "windows")]
    {
        use std::os::windows::process::CommandExt;

        // Get the Start Menu Programs path via PowerShell
        let ps_path_script = r#"
$path = [Environment]::GetFolderPath([Environment+SpecialFolder]::Programs)
Write-Output $path
        "#;

        let programs_path = Command::new("powershell")
            .args(["-NoProfile", "-WindowStyle", "Hidden", "-Command", ps_path_script])
            .creation_flags(0x08000000)
            .stdout(Stdio::piped())
            .stderr(Stdio::null())
            .output()
            .map_err(|e| e.to_string())?;

        let programs_dir = String::from_utf8_lossy(&programs_path.stdout)
            .trim()
            .trim_end_matches('\r')
            .to_string();

        if programs_dir.is_empty() {
            return Err("Não foi possível encontrar a pasta do Menu Iniciar".into());
        }

        // Create shortcut via WScript.Shell
        let safe_title = title.replace('\'', "''");
        let safe_exe = executable.replace('\'', "''");
        let icon_path = icon.as_deref().unwrap_or(&executable).replace('\'', "''");

        let ps_shortcut = format!(r#"
$shell = New-Object -ComObject WScript.Shell
$shortcut = $shell.CreateShortcut('{programs_dir}\{safe_title}.lnk')
$shortcut.TargetPath = '{safe_exe}'
$shortcut.WorkingDirectory = Split-Path '{safe_exe}'
$shortcut.IconLocation = '{icon_path}'
$shortcut.Save()
        "#, programs_dir = programs_dir, safe_title = safe_title, safe_exe = safe_exe, icon_path = icon_path);

        let temp_ps = std::env::temp_dir().join("gr_shortcut.ps1");
        std::fs::write(&temp_ps, &ps_shortcut).ok();
        let ps_cmd = temp_ps.to_string_lossy().replace('/', "\\");

        let result = Command::new("powershell")
            .args(["-NoProfile", "-WindowStyle", "Hidden", "-File", &ps_cmd])
            .creation_flags(0x08000000)
            .stdout(Stdio::null())
            .stderr(Stdio::null())
            .status()
            .map_err(|e| e.to_string())?;

        let _ = std::fs::remove_file(&temp_ps);

        if !result.success() {
            return Err("Falha ao criar atalho no Menu Iniciar".into());
        }

        Ok(())
    }
    #[cfg(not(target_os = "windows"))]
    {
        let _ = title;
        let _ = executable;
        let _ = icon;
        Ok(())
    }
}

/// Remove a .lnk shortcut from the Start Menu Programs folder
#[tauri::command]
pub fn remove_shortcut(title: String) -> Result<(), String> {
    #[cfg(target_os = "windows")]
    {
        use std::os::windows::process::CommandExt;

        let safe_title = title.replace('\'', "''");
        let ps_script = format!(r#"
$programs = [Environment]::GetFolderPath([Environment+SpecialFolder]::Programs)
$lnk = Join-Path $programs '{safe_title}.lnk'
if (Test-Path $lnk) {{
    Remove-Item $lnk -Force
}}
        "#, safe_title = safe_title);

        let temp_ps = std::env::temp_dir().join("gr_remove_shortcut.ps1");
        std::fs::write(&temp_ps, &ps_script).ok();
        let ps_cmd = temp_ps.to_string_lossy().replace('/', "\\");

        Command::new("powershell")
            .args(["-NoProfile", "-WindowStyle", "Hidden", "-File", &ps_cmd])
            .creation_flags(0x08000000)
            .stdout(Stdio::null())
            .stderr(Stdio::null())
            .status()
            .map_err(|e| e.to_string())?;

        let _ = std::fs::remove_file(&temp_ps);
        Ok(())
    }
    #[cfg(not(target_os = "windows"))]
    {
        let _ = title;
        Ok(())
    }
}
