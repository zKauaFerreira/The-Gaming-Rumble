use std::sync::Mutex;
use std::time::Duration;

use serde::Serialize;
use tauri::{AppHandle, Emitter, State};
use tauri_plugin_updater::{Update, UpdaterExt};
use reqwest::Url;

const DEFAULT_UPDATE_ENDPOINT: &str =
    "https://github.com/zKauaFerreira/The-Gaming-Rumble/releases/latest/download/latest.json";
const UPDATER_PUBKEY: &str =
    "dW50cnVzdGVkIGNvbW1lbnQ6IG1pbmlzaWduIHB1YmxpYyBrZXk6IDRCMEU4MzlDMDgwQzI4RUYKUldUdktBd0luSU1PU3lhbUxwOUZFczZQekFoampRVnZ1SUVBSEc1ZlJiMjRIWlA3ZzlaQ0hOOFAK";

pub struct PendingUpdate(pub Mutex<Option<Update>>);

#[derive(Serialize)]
#[serde(rename_all = "camelCase")]
pub struct UpdateCheckResponse {
    pub configured: bool,
    pub available: bool,
    pub current_version: String,
    pub version: Option<String>,
    pub notes: Option<String>,
    pub pub_date: Option<String>,
    pub error: Option<String>,
}

#[derive(Clone, Serialize)]
#[serde(tag = "event", content = "data")]
pub enum UpdateEvent {
    #[serde(rename_all = "camelCase")]
    Started {
        content_length: Option<u64>,
        version: String,
    },
    #[serde(rename_all = "camelCase")]
    Progress {
        downloaded: u64,
        chunk_length: usize,
        content_length: Option<u64>,
    },
    FinishedDownload,
    Installing,
    #[serde(rename_all = "camelCase")]
    Failed {
        message: String,
    },
}

fn updater_configured() -> bool {
    !UPDATER_PUBKEY.trim().is_empty()
}

fn build_updater(app: &AppHandle) -> Result<tauri_plugin_updater::Updater, String> {
    let endpoint = Url::parse(DEFAULT_UPDATE_ENDPOINT).map_err(|e| e.to_string())?;
    app.updater_builder()
        .pubkey(UPDATER_PUBKEY.to_string())
        .endpoints(vec![endpoint])
        .map_err(|e| e.to_string())?
        .timeout(Duration::from_secs(30))
        .build()
        .map_err(|e| e.to_string())
}

#[tauri::command]
pub async fn check_for_app_update(
    app: AppHandle,
    pending: State<'_, PendingUpdate>,
) -> Result<UpdateCheckResponse, String> {
    let current_version = app.package_info().version.to_string();

    if !updater_configured() {
        *pending.0.lock().map_err(|e| e.to_string())? = None;
        return Ok(UpdateCheckResponse {
            configured: false,
            available: false,
            current_version,
            version: None,
            notes: None,
            pub_date: None,
            error: None,
        });
    }

    let updater = build_updater(&app)?;
    match updater.check().await {
        Ok(Some(update)) => {
            let response = UpdateCheckResponse {
                configured: true,
                available: true,
                current_version,
                version: Some(update.version.clone()),
                notes: update.body.clone(),
                pub_date: update.date.map(|d| d.to_string()),
                error: None,
            };
            *pending.0.lock().map_err(|e| e.to_string())? = Some(update);
            Ok(response)
        }
        Ok(None) => {
            *pending.0.lock().map_err(|e| e.to_string())? = None;
            Ok(UpdateCheckResponse {
                configured: true,
                available: false,
                current_version,
                version: None,
                notes: None,
                pub_date: None,
                error: None,
            })
        }
        Err(err) => {
            *pending.0.lock().map_err(|e| e.to_string())? = None;
            Ok(UpdateCheckResponse {
                configured: true,
                available: false,
                current_version,
                version: None,
                notes: None,
                pub_date: None,
                error: Some(err.to_string()),
            })
        }
    }
}

#[tauri::command]
pub async fn install_app_update(
    app: AppHandle,
    pending: State<'_, PendingUpdate>,
) -> Result<(), String> {
    let update = pending
        .0
        .lock()
        .map_err(|e| e.to_string())?
        .take()
        .ok_or_else(|| "Nenhuma atualizacao pendente encontrada.".to_string())?;

    let mut downloaded = 0u64;
    let version = update.version.clone();
    let mut started = false;

    let bytes = match update
        .download(
            |chunk_length, content_length| {
                downloaded += chunk_length as u64;
                if !started {
                    started = true;
                    let _ = app.emit(
                        "app-update",
                        UpdateEvent::Started {
                            content_length,
                            version: version.clone(),
                        },
                    );
                }

                let _ = app.emit(
                    "app-update",
                    UpdateEvent::Progress {
                        downloaded,
                        chunk_length,
                        content_length,
                    },
                );
            },
            || {
                let _ = app.emit("app-update", UpdateEvent::FinishedDownload);
            },
        )
        .await
    {
        Ok(bytes) => bytes,
        Err(e) => {
            let message = e.to_string();
            if let Ok(mut guard) = pending.0.lock() {
                *guard = Some(update);
            }
            let _ = app.emit(
                "app-update",
                UpdateEvent::Failed {
                    message: message.clone(),
                },
            );
            return Err(message);
        }
    };

    let _ = app.emit("app-update", UpdateEvent::Installing);
    if let Err(e) = update.install(bytes) {
        let message = e.to_string();
        if let Ok(mut guard) = pending.0.lock() {
            *guard = Some(update);
        }
        let _ = app.emit(
            "app-update",
            UpdateEvent::Failed {
                message: message.clone(),
            },
        );
        return Err(message);
    }

    #[cfg(not(target_os = "windows"))]
    {
        app.restart();
    }

    Ok(())
}
