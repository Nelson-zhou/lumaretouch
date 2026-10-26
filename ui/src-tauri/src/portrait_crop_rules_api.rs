// SPDX-License-Identifier: GPL-3.0-or-later
//! Local catalogue only; never dispatches to the engine or changes a photo.
use serde_json::{json, Value};
use crate::portrait_crop_rules_core::Request;
#[cfg(target_os = "linux")]
#[path = "portrait_crop_rules_store.rs"]
mod storage;

fn rejected(message: String) -> Value { json!({"status":"rejected","no_change":true,"message":message}) }
#[tauri::command]
pub(crate) async fn portrait_crop_rules(app: tauri::AppHandle, request: Value) -> Result<Value, String> {
    // Parsing failure precedes opening any catalogue; unknown fields cannot leak
    // source state into persistence. No schema coercion and no ordinary-crop import.
    let request = match serde_json::to_vec(&request) {
        Ok(bytes) if bytes.len() <= 8192 => match Request::parse(&bytes) {
            Ok(request) => request,
            Err(_) => return Ok(rejected("构图预设请求包含未知字段、版本或无效数值；未修改目录".into())),
        },
        _ => return Ok(rejected("构图预设请求超出大小上限；未修改目录".into())),
    };
    #[cfg(target_os = "linux")]
    {
        use tauri::Manager;
        let path = match app.path().app_local_data_dir() { Ok(path) => path, Err(error) => return Ok(rejected(error.to_string())) };
        // Keep fsync off the UI thread. Lost IPC/join receipts remain unknown to
        // the client, which must read the catalogue rather than retry a mutation.
        tauri::async_runtime::spawn_blocking(move || storage::perform(&path, request)).await.map_err(|error| error.to_string())
    }
    #[cfg(not(target_os = "linux"))]
    { let _ = (app, request); Ok(rejected("构图规则预设本地存储目前仅支持 Linux；未修改目录".into())) }
}
