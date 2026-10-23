//! Creative document requests use bounded, engine-epoch-bound receipts.
//! This bridge does not invent document state, image bytes, history or success.
use std::{collections::HashMap, sync::{Arc, Mutex, OnceLock}};
use serde_json::{json, Value};
use tauri::State;
use crate::AppState;

const MAX_REVISION: u64 = 9_007_199_254_740_991;
const MAX_FILE_BYTES: usize = 128 * 1024 * 1024;
const MAX_RESULT_BYTES: usize = 32 * 1024 * 1024;
const MAX_STORE_BYTES: usize = 64 * 1024 * 1024;
const MAX_ROWS: usize = 256;
struct Row { epoch: [u8; 16], identity: Value, read: bool, result: Option<Value>, sequence: u64, bytes: usize }
#[derive(Default)]
struct Store { rows: HashMap<String, Row>, sequence: u64 }
fn mailbox() -> &'static Mutex<Store> {
    static STORE: OnceLock<Mutex<Store>> = OnceLock::new();
    STORE.get_or_init(|| Mutex::new(Store::default()))
}
fn identity(value: &Value) -> bool {
    value.as_str().is_some_and(|text| !text.is_empty() && text.len() <= 512 && !text.chars().any(char::is_control))
}
fn validate(request: &Value) -> Result<bool, String> {
    if !request.is_object() || request["cmd"] != "creative_document" || !identity(&request["request_id"]) || !identity(&request["source_uid"]) {
        return Err("创意文档请求缺少有效命令或来源身份".into());
    }
    let action = request["action"].as_str().ok_or("缺少创意文档动作")?;
    let read = matches!(action, "open" | "state");
    if !read && (!identity(&request["document_id"]) || !identity(&request["ownership_token"])
        || !request["expected_revision"].as_u64().is_some_and(|r| r <= MAX_REVISION)) {
        return Err("创意文档修改缺少所有权或修订栅栏".into());
    }
    match action {
        "open" | "state" => {},
        "command" if request["command"].is_object() => {},
        "import_image" | "attach_mask" => {
            match (request.get("bytes_base64"), request.get("path")) {
                (Some(bytes), None) => {
                    let bytes = bytes.as_str().ok_or("无效图片文件字节")?;
                    if bytes.is_empty() || bytes.len() > ((MAX_FILE_BYTES + 2) / 3) * 4 { return Err("图片文件为空或超过 128 MiB 安全上限".into()); }
                },
                (None, Some(path)) if action == "import_image" => {
                    let path = path.as_str().filter(|p| p.len() <= 4096).ok_or("无效拖入文件路径")?;
                    let path = std::path::Path::new(path);
                    if !path.is_absolute() { return Err("拖入文件必须是原生绝对路径".into()); }
                    let metadata = std::fs::metadata(path).map_err(|error| format!("无法读取拖入文件：{error}"))?;
                    if !metadata.is_file() || metadata.len() == 0 || metadata.len() > MAX_FILE_BYTES as u64 { return Err("拖入文件不是普通图片文件或超过 128 MiB 上限".into()); }
                },
                _ => return Err("请提供唯一的真实图片文件字节或原生拖入路径".into()),
            }
            if action == "attach_mask" && !identity(&request["layer_id"]) { return Err("缺少蒙版目标图层".into()); }
            if !request["filename"].as_str().is_some_and(|name| !name.is_empty() && name.len() <= 4096) {
                return Err("缺少图片文件名".into());
            }
        },
        "remove_mask" if identity(&request["layer_id"]) => {},
        "history" if matches!(request["direction"].as_str(), Some("undo" | "redo")) => {},
        "return" if matches!(request["mode"].as_str(), Some("new" | "update")) && identity(&request["render_id"]) => {},
        _ => return Err("未知或不完整的创意文档动作".into()),
    }
    if !matches!(action, "import_image" | "attach_mask") && request.to_string().len() > 1024 * 1024 {
        return Err("创意文档命令超过安全大小上限".into());
    }
    Ok(read)
}
fn trim_completed(store: &mut Store, reserve_row: bool) -> Result<(), String> {
    while store.rows.len() + usize::from(reserve_row) > MAX_ROWS || store.rows.values().map(|row| row.bytes).sum::<usize>() > MAX_STORE_BYTES {
        let oldest = store.rows.iter().filter(|(_, row)| row.result.is_some())
            .min_by_key(|(_, row)| row.sequence).map(|(id, _)| id.clone());
        if let Some(id) = oldest { store.rows.remove(&id); }
        else { return Err("创意文档待确认请求已满，请先核对原操作".into()); }
    }
    Ok(())
}
pub(crate) fn receive(epoch: [u8; 16], value: &Value) {
    if !matches!(value["event"].as_str(), Some("creative_document_state" | "creative_document_result")) { return; }
    let Some(id) = value["request_id"].as_str() else { return; };
    let Ok(mut store) = mailbox().lock() else { return; };
    let Some(row) = store.rows.get_mut(id) else { return; };
    if row.epoch != epoch || row.result.is_some() || value["source_uid"] != row.identity["source_uid"] { return; }
    if !row.read && ["document_id", "ownership_token", "expected_revision"].iter().any(|key| value[*key] != row.identity[*key]) { return; }
    let mut result = value.clone();
    if let Some(object) = result.as_object_mut() { object.remove("doc_state"); }
    let bytes = result.to_string().len();
    if bytes > MAX_RESULT_BYTES {
        result = row.identity.clone();
        result["event"] = json!(if row.read { "creative_document_state" } else { "creative_document_result" });
        result["status"] = json!("unknown"); result["message"] = json!("创意文档回执超过安全上限，操作结果需要核对");
    }
    row.bytes = result.to_string().len(); row.result = Some(result);
    let _ = trim_completed(&mut store, false);
}

#[tauri::command]
pub(crate) fn creative_document_request(state: State<'_, Arc<AppState>>, request: Value) -> Result<Value, String> {
    let read = match validate(&request) {
        Ok(read) => read,
        Err(message) => return Ok(json!({"requested":false,"request_id":request["request_id"],"status":"rejected","message":message})),
    };
    let id = request["request_id"].as_str().ok_or("缺少请求身份")?.to_owned();
    let guard = state.engine.lock().map_err(|_| "引擎锁不可用")?;
    let epoch = guard.as_ref().filter(|engine| engine.is_alive()).ok_or("引擎未启动")?.epoch();
    {
        let mut store = mailbox().lock().map_err(|_| "创意文档回执锁不可用")?;
        store.rows.retain(|_, row| row.epoch == epoch);
        if store.rows.contains_key(&id) { return Err("创意文档请求身份已存在；请查询原请求，不会重复发送".into()); }
        trim_completed(&mut store, true)?;
        store.sequence = store.sequence.checked_add(1).ok_or("创意文档回执序号耗尽")?;
        let sequence = store.sequence;
        let mut bound = json!({"request_id":id,"source_uid":request["source_uid"]});
        if !read { for key in ["document_id", "ownership_token", "expected_revision"] { bound[key] = request[key].clone(); } }
        // Never retain original large file bytes in the receipt mailbox.
        store.rows.insert(id.clone(), Row { epoch, identity: bound, read, result: None, sequence, bytes: 0 });
    }
    if read {
        guard.as_ref().ok_or("引擎未启动")?.send(request).map_err(|error| format!("创意文档读取发送状态待确认：{error}"))?;
    } else {
        drop(guard);
        state.send_to_engine(request).map_err(|error| format!("创意文档发送结果待确认：{error}；请查询原请求"))?;
    }
    Ok(json!({"requested":true,"request_id":id}))
}
#[tauri::command]
pub(crate) fn creative_document_status(state: State<'_, Arc<AppState>>, request_id: String) -> Result<Value, String> {
    if !identity(&Value::String(request_id.clone())) { return Err("无效创意文档请求身份".into()); }
    let engine = state.engine.lock().map_err(|_| "引擎锁不可用")?;
    let epoch = engine.as_ref().filter(|handle| handle.is_alive()).map(|handle| handle.epoch());
    let store = mailbox().lock().map_err(|_| "创意文档回执锁不可用")?;
    let Some(row) = store.rows.get(&request_id).filter(|row| Some(row.epoch) == epoch) else {
        return Ok(json!({"phase":"unknown","result":null}));
    };
    Ok(json!({"phase":if row.result.is_some() {"done"} else {"pending"},"result":row.result}))
}
