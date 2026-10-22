//! Preset command surface. Querying a receipt never resubmits a mutation.
use std::sync::Arc;
use serde_json::{json, Value};
use tauri::State;
use crate::{AppState, engine::EngineHandle};
pub(crate) fn enqueue(state: &AppState, handle: &EngineHandle, command: Value) -> Result<(), String> {
    let Some(id) = command["request_id"].as_str().map(str::to_owned) else { return handle.send(command) };
    let action = command["action"].as_str().ok_or("missing preset action")?.to_owned();
    let mut host = state.preset_results.lock().map_err(|_| "preset receipt lock poisoned")?;
    host.begin_bound(handle.epoch(), &id, &action, command["document_id"].as_str())?;
    let result = handle.send(command);
    if let Err(error) = &result { host.failed(&id, error); }
    result
}
/// 模块预设（LNX-P0-PRESET / PRESET-001、002）：清单/应用/保存/导入/删除一条命令。
/// “哪些参数属于哪个模块”“这个预设文件能不能接”全在引擎的 scope.py + preset_store.py：
/// 宿主抄一份模块名单或量程就是第二个会漂的地方（与 exposure/crop 同一条理由）。
/// 清单随 session_state 的 `presets` 上来，这里不开“拿清单”的口子给前端自己扫目录。
#[tauri::command]
pub(crate) fn preset(
    state: State<'_, Arc<AppState>>,
    action: String,
    id: Option<String>,
    name: Option<String>,
    path: Option<String>,
    kind: Option<String>,
    note: Option<String>,
    force: Option<bool>,
    module_scope: Option<Vec<String>>,
    request_id: Option<String>,
    document_id: Option<String>,
) -> Result<Value, String> {
    const ACTIONS: [&str; 5] = ["list", "apply", "save", "import", "delete"];
    if !ACTIONS.contains(&action.as_str()) {
        return Err(format!("preset 不认识动作 {action}（可用：{}）", ACTIONS.join("/")));
    }
    if request_id.is_some() && state.ready_caps.lock().map_err(|_| "capability lock poisoned")?["preset_result_protocol"] != 1 {
        return Err("current engine does not support correlated preset receipts".into());
    }
    let mut cmd = json!({"cmd": "preset", "action": action});
    for (k, v) in [
        ("id", id.map(Value::from)),
        ("name", name.map(Value::from)),
        ("path", path.map(Value::from)),
        ("kind", kind.map(Value::from)),
        ("note", note.map(Value::from)),
        ("force", force.map(Value::from)),
        ("request_id", request_id.map(Value::from)),
        ("document_id", document_id.map(Value::from)),
    ] {
        if let Some(v) = v {
            cmd[k] = v;
        }
    }
    if let Some(v) = module_scope {
        cmd["module_scope"] = json!(v);
    }
    state.send_to_engine(cmd)?;
    Ok(json!({"requested": true}))
}

#[tauri::command]
pub(crate) fn preset_result(state: State<'_, Arc<AppState>>, request_id: String) -> Result<Value, String> {
    if request_id.is_empty() || request_id.len() > 128 { return Err("invalid preset request ID".into()); }
    Ok(state.preset_results.lock().map_err(|_| "preset receipt lock poisoned")?.status(&request_id))
}
