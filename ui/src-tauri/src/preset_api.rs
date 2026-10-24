//! Preset command surface. Querying a receipt never resubmits a mutation.
use std::sync::Arc;
use serde_json::{json, Value};
use tauri::State;
use crate::{AppState, engine::EngineHandle};
#[path="preset_visual_protocol.rs"]
pub(crate) mod visual;
#[path="eye_bag_preset_protocol.rs"]
pub(crate) mod eye_bag;
#[path="collarbone_preset_protocol.rs"]
pub(crate) mod collarbone;
pub(crate) fn read_only(value:&Value)->bool {eye_bag::read_only(value)||collarbone::read_only(value)}
fn require_xmp_support(state: &AppState, command: &Value) -> Result<(), String> {
    if (command["action"] == "xmp_inspect" || command.get("xmp_ack").is_some() || command.get("xmp_review_ack").is_some())
        && state.ready_caps.lock().map_err(|_| "capability lock poisoned")?["xmp_import_protocol"] != 1 {
        return Err("current engine does not support reviewed XMP parameter adaptation".into());
    }
    Ok(())
}
pub(crate) fn enqueue(state: &AppState, handle: &EngineHandle, command: Value) -> Result<(), String> {
    eye_bag::command(&command)?;
    collarbone::command(&command)?;
    crate::spill_transfer_protocol::command(&command)?;
    crate::original_shadow_transfer_protocol::command(&command)?;
    crate::torso_transfer_protocol::command(&command)?;
    crate::waist_transfer_protocol::command(&command)?;
    crate::torso_transfer_protocol::head_command(&command)?;
    crate::preset_host::xmp_protocol::command(&command)?;
    require_xmp_support(state, &command)?;
    let Some(id) = command["request_id"].as_str().map(str::to_owned) else { return handle.send(command) };
    let mut host = state.preset_results.lock().map_err(|_| "preset receipt lock poisoned")?;
    host.begin_command(handle.epoch(), &command)?;
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
    local_mask_transfer: Option<Value>,
    preflight_token: Option<String>,
    xmp_ack: Option<Value>,
    xmp_review_ack: Option<Value>,
    spill_review_ack: Option<Value>,
    shadow_review_ack: Option<Value>,
    torso_review_ack: Option<Value>,
    waist_review_ack: Option<Value>,
    head_review_ack: Option<Value>,
    collarbone_preset_ack: Option<Value>,
    eye_bag_preset_ack: Option<Value>,
    eye_bag_replace_legacy: Option<bool>,
    revision: Option<String>,
    side: Option<String>,
    sha256: Option<String>,
) -> Result<Value, String> {
    const ACTIONS: [&str; 9] = ["list", "preflight", "apply", "save", "import", "delete", "xmp_inspect", "collarbone_visual", "eye_bag_visual"];
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
        ("local_mask_transfer", local_mask_transfer),
        ("preflight_token", preflight_token.map(Value::from)),
        ("xmp_ack", xmp_ack),
        ("xmp_review_ack", xmp_review_ack),
        ("spill_review_ack", spill_review_ack),
        ("shadow_review_ack", shadow_review_ack),
        ("torso_review_ack", torso_review_ack),
        ("waist_review_ack", waist_review_ack),
        ("head_review_ack", head_review_ack),
        ("collarbone_preset_ack", collarbone_preset_ack),
        ("eye_bag_preset_ack", eye_bag_preset_ack),
        ("eye_bag_replace_legacy", eye_bag_replace_legacy.map(Value::from)),
        ("revision", revision.map(Value::from)),
        ("side", side.map(Value::from)),
        ("sha256", sha256.map(Value::from)),
    ] {
        if let Some(v) = v {
            cmd[k] = v;
        }
    }
    if let Some(v) = module_scope {
        cmd["module_scope"] = json!(v);
    }
    eye_bag::command(&cmd)?;
    collarbone::command(&cmd)?;
    crate::spill_transfer_protocol::command(&cmd)?;
    crate::original_shadow_transfer_protocol::command(&cmd)?;
    crate::torso_transfer_protocol::command(&cmd)?;
    crate::waist_transfer_protocol::command(&cmd)?;
    crate::torso_transfer_protocol::head_command(&cmd)?;
    crate::preset_host::xmp_protocol::command(&cmd)?;
    require_xmp_support(&state, &cmd)?;
    state.send_to_engine(cmd)?;
    Ok(json!({"requested": true}))
}

#[tauri::command]
pub(crate) fn preset_result(state: State<'_, Arc<AppState>>, request_id: String) -> Result<Value, String> {
    if request_id.is_empty() || request_id.len() > 128 { return Err("invalid preset request ID".into()); }
    Ok(state.preset_results.lock().map_err(|_| "preset receipt lock poisoned")?.status(&request_id))
}
