use sysinfo::Disks;

#[derive(serde::Serialize)]
pub struct DriveInfo {
    pub name: String,
    pub label: String,
    pub free_gb: f64,
    pub total_gb: f64,
}

#[tauri::command]
pub fn list_drives() -> Vec<DriveInfo> {
    let mut disks = Disks::new();
    disks.refresh(true);
    disks.iter().map(|d| {
        let name = d.mount_point().to_string_lossy().to_string();
        let label = d.name().to_string_lossy().to_string();
        let free = d.available_space() as f64 / 1_073_741_824.0;
        let total = d.total_space() as f64 / 1_073_741_824.0;
        DriveInfo { name, label, free_gb: free, total_gb: total }
    }).collect()
}

#[tauri::command]
pub fn get_disk_space(path: String) -> String {
    let mut disks = Disks::new();
    disks.refresh(true);
    let p = std::path::Path::new(&path);
    for disk in disks.iter() {
        if p.starts_with(disk.mount_point()) {
            let free = disk.available_space() as f64 / 1_073_741_824.0;
            return format!("{:.1} GB", free);
        }
    }
    "N/A".to_string()
}
