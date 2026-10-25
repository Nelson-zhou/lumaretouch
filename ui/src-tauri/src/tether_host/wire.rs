//! UI v1 envelopes. No camera or engine side effects.
use serde::{Deserialize, Serialize};
use serde_json::{json, Value};

pub const PROTOCOL: u32 = 1;
pub const MAX_REQUESTS: usize = 192;
pub const MAX_TRANSFERS: usize = 64;
pub const MAX_BYTES: u64 = 4 * 1024 * 1024 * 1024;
pub const MAX_SAFE: u64 = 9_007_199_254_740_991;

#[derive(Clone, Debug, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct Destination { pub destination_id: String, pub display_path: String }
#[derive(Clone, Debug, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct Target { pub project_id: String, pub path: String }
#[derive(Clone, Debug, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct Naming { pub mode: String, pub custom_name: String, pub counter_start: u64 }
#[derive(Clone, Debug, Deserialize, Serialize)]
#[serde(tag = "action", rename_all = "snake_case")]
pub enum Action {
    ProbeDevice { device_id: String },
    Start { device_id: String, ingestion_target: Target, destination: Destination,
        naming: Naming, import_format: String, preview_mode: String },
    Stop,
    RetryTransfer { transfer_id: String },
    SetPreviewMode { preview_mode: String },
    StartLiveView,
    StopLiveView,
    Capture,
}
impl Action {
    pub fn name(&self) -> &'static str {
        match self { Self::ProbeDevice { .. } => "probe_device", Self::Start { .. } => "start",
            Self::Stop => "stop", Self::RetryTransfer { .. } => "retry_transfer",
            Self::SetPreviewMode { .. } => "set_preview_mode", Self::StartLiveView => "start_live_view",
            Self::StopLiveView => "stop_live_view", Self::Capture => "capture" }
    }
}
#[derive(Clone, Debug, Deserialize, Serialize)]
pub struct Request {
    pub protocol_version: u32,
    pub host_id: String,
    pub request_id: String,
    pub expected_revision: u64,
    pub expected_session_id: Option<String>,
    pub expected_generation: Option<u64>,
    #[serde(flatten)] pub action: Action,
    #[serde(skip)] pub admitted_binding: Option<Value>,
}
impl Request {
    pub fn parse(value: Value) -> Result<Self, String> {
        if value.to_string().len() > 16 * 1024 { return Err("联机请求超过长度限制".into()); }
        let request: Self = serde_json::from_value(value.clone()).map_err(|e| e.to_string())?;
        if serde_json::to_value(&request).map_err(|e| e.to_string())? != value {
            return Err("联机请求包含未知、缺失或非规范字段".into());
        }
        if request.protocol_version != PROTOCOL || request.request_id.is_empty()
            || request.request_id.len() > 128 || request.request_id.chars().any(char::is_control)
            || request.expected_revision > MAX_SAFE {
            return Err("联机请求身份无效".into());
        }
        Ok(request)
    }
    pub fn pending(&self) -> Value {
        json!({"request_id":self.request_id,"action":self.action.name(),
            "expected_session_id":self.expected_session_id,"expected_generation":self.expected_generation})
    }
    pub fn receipt(&self, done: bool, unknown: bool, success: bool, error: Option<&str>) -> Value {
        let mut value = self.pending();
        value["protocol_version"] = json!(PROTOCOL);
        value["host_id"] = json!(self.host_id);
        value["phase"] = json!(if done { "done" } else { "pending" });
        value["outcome_unknown"] = json!(unknown);
        if done && !unknown { value["success"] = json!(success); }
        if let Some(error) = error { value["error"] = json!(error); }
        value
    }
}
pub fn preview_mode(value: &str) -> Result<(), String> {
    if matches!(value, "follow_latest" | "keep_current") { Ok(()) } else { Err("未知预览模式".into()) }
}
pub fn component(value: &str) -> Result<(), String> {
    if value.is_empty() || value.len() > 255 || matches!(value, "." | "..")
        || value.chars().any(|c| c.is_control() || matches!(c, '/' | '\\' | '<' | '>' | ':' | '"' | '|' | '?' | '*'))
        || value.ends_with('.') || value.ends_with(' ') {
        return Err("文件名须为安全 UTF-8 单一分量，最多 255 字节；不会静默改名或截断".into());
    }
    let stem = value.split('.').next().unwrap_or("").to_ascii_uppercase();
    if matches!(stem.as_str(), "CON" | "PRN" | "AUX" | "NUL")
        || (stem.len() == 4 && (stem.starts_with("COM") || stem.starts_with("LPT"))
            && matches!(stem.as_bytes()[3], b'1'..=b'9')) {
        return Err("文件名是保留名称".into());
    }
    Ok(())
}
pub fn validate_naming(naming: &Naming) -> Result<(), String> {
    if !matches!(naming.mode.as_str(), "custom_counter" | "custom_filename" | "date_counter" | "date_filename" | "original") {
        return Err("未知命名方式".into());
    }
    if naming.mode.starts_with("custom_") {
        component(&naming.custom_name)?;
        if naming.custom_name.chars().count() > 80 || naming.custom_name.trim().is_empty() { return Err("自定义名称须为 1–80 字符".into()); }
    }
    if naming.counter_start == 0 || naming.counter_start > 999_999_999 { return Err("计数起点须为 1–999999999".into()); }
    Ok(())
}
pub fn local_name(naming: &Naming, original: &str, utc_date: &str, ordinal: u64) -> Result<String, String> {
    component(original)?;
    let (stem, extension) = original.rsplit_once('.').ok_or("相机文件没有已知扩展名")?;
    let counter = naming.counter_start.checked_add(ordinal).filter(|v| *v <= 999_999_999).ok_or("命名计数已耗尽")?;
    let stem = match naming.mode.as_str() {
        "custom_counter" => format!("{}-{counter:06}", naming.custom_name),
        "custom_filename" => format!("{}-{stem}", naming.custom_name),
        "date_counter" => format!("{utc_date}-{counter:06}"),
        "date_filename" => format!("{utc_date}-{stem}"),
        "original" => stem.to_owned(),
        _ => return Err("未知命名方式".into()),
    };
    let result = format!("{stem}.{extension}");
    component(&result)?;
    Ok(result)
}
pub fn format(name: &str) -> &'static str {
    match name.rsplit('.').next().unwrap_or("").to_ascii_lowercase().as_str() {
        "jpg" | "jpeg" => "jpeg",
        "arw" | "cr2" | "cr3" | "nef" | "raf" | "orf" | "rw2" | "dng" => "raw",
        _ => "other",
    }
}
/// JPEG SOF dimensions, without allocating or decoding untrusted pixel data.
pub fn jpeg_dimensions(bytes: &[u8]) -> Option<(u32, u32)> {
    if !bytes.starts_with(&[0xff, 0xd8]) { return None; }
    let mut at = 2;
    while at + 1 < bytes.len() {
        if bytes[at] != 0xff { return None; }
        while at < bytes.len() && bytes[at] == 0xff { at += 1; }
        let marker = *bytes.get(at)?; at += 1;
        if matches!(marker, 0xd9 | 0xda | 0x00) { return None; }
        if marker == 0x01 || (0xd0..=0xd7).contains(&marker) { continue; }
        let length = u16::from_be_bytes([*bytes.get(at)?, *bytes.get(at + 1)?]) as usize;
        if length < 2 || at.checked_add(length)? > bytes.len() { return None; }
        if matches!(marker, 0xc0..=0xc3 | 0xc5..=0xc7 | 0xc9..=0xcb | 0xcd..=0xcf) {
            if length < 8 { return None; }
            let h = u16::from_be_bytes([bytes[at + 3], bytes[at + 4]]) as u32;
            let w = u16::from_be_bytes([bytes[at + 5], bytes[at + 6]]) as u32;
            return (w > 0 && h > 0 && w <= 16384 && h <= 16384
                && u64::from(w) * u64::from(h) <= 16 * 1024 * 1024).then_some((w, h));
        }
        at += length;
    }
    None
}
