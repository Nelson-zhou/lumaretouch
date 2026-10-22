//! Native edit-command boundary: validation and dispatch, no engine state ownership.
//! Image algorithms remain in their dedicated cores; AppState owns transport.
use std::sync::Arc;
use serde_json::{json, Value};
use tauri::State;
use crate::AppState;

/// 曝光/白平衡（P0 注册表 lnx.exposure / lnx.white_balance）。量程不在这里写：
/// 引擎随事件报 exposure_limits，宿主抄一份数就是第二个会漂的地方。
#[tauri::command]
pub(crate) fn exposure(
    state: State<'_, Arc<AppState>>,
    action: String,
    ev: Option<f64>,
    temperature_shift: Option<f64>,
    tint_shift: Option<f64>,
    reference_k: Option<f64>,
    // 影调四项与 EV 同一层（原创扩展）：宿主少接一个参数，面板上那个滑块
    // 就是“拖了、画面不动，而命令回执正常”——上一版这四格根本不在签名里。
    contrast: Option<f64>,
    highlights: Option<f64>,
    shadows: Option<f64>,
    saturation: Option<f64>,
    interactive: Option<bool>,
) -> Result<Value, String> {
    const ACTIONS: [&str; 2] = ["set", "clear"];
    if !ACTIONS.contains(&action.as_str()) {
        return Err(format!("exposure 不认识动作 {action}（可用：{}）", ACTIONS.join("/")));
    }
    let mut cmd = json!({"cmd": "exposure", "action": action});
    for (k, v) in [
        ("ev", ev.map(Value::from)),
        ("temperature_shift", temperature_shift.map(Value::from)),
        ("tint_shift", tint_shift.map(Value::from)),
        ("reference_k", reference_k.map(Value::from)),
        ("contrast", contrast.map(Value::from)),
        ("highlights", highlights.map(Value::from)),
        ("shadows", shadows.map(Value::from)),
        ("saturation", saturation.map(Value::from)),
    ] {
        if let Some(v) = v {
            cmd[k] = v;
        }
    }
    if interactive == Some(true) && action == "set" {
        let fields:Vec<_>=cmd.as_object().unwrap().keys().cloned().collect();
        let target=cmd.get("band").cloned().unwrap_or(Value::Null);
        state.send_interactive(format!("exposure:{target}:{fields:?}"),cmd)?;
    } else {state.send_to_engine(cmd)?;}
    Ok(json!({"requested": true}))
}

/// 八色 HSL（原创扩展）：band 0…7，dh/ds/dl 是这一段的三格。
/// 与 exposure 同一个形状：动作名单、参数白名单都在这里，量程由引擎随事件报。
#[tauri::command]
pub(crate) fn hsl(
    state: State<'_, Arc<AppState>>,
    action: String,
    band: Option<i64>,
    dh: Option<f64>,
    ds: Option<f64>,
    dl: Option<f64>,
    interactive: Option<bool>,
) -> Result<Value, String> {
    const ACTIONS: [&str; 2] = ["set", "clear"];
    if !ACTIONS.contains(&action.as_str()) {
        return Err(format!("hsl 不认识动作 {action}（可用：{}）", ACTIONS.join("/")));
    }
    let mut cmd = json!({"cmd": "hsl", "action": action});
    for (k, v) in [
        ("band", band.map(Value::from)),
        ("dh", dh.map(Value::from)),
        ("ds", ds.map(Value::from)),
        ("dl", dl.map(Value::from)),
    ] {
        if let Some(v) = v {
            cmd[k] = v;
        }
    }
    if interactive == Some(true) && action == "set" {
        let fields:Vec<_>=cmd.as_object().unwrap().keys().cloned().collect();
        let target=cmd.get("band").cloned().unwrap_or(Value::Null);
        state.send_interactive(format!("hsl:{target}:{fields:?}"),cmd)?;
    } else {state.send_to_engine(cmd)?;}
    Ok(json!({"requested": true}))
}

/// 裁剪/旋转（P0 注册表 lnx.crop.v1）。rect 是归一化的 [左,上,右,下]，
/// 正角顺时针——两个口径的出处都在引擎 ops/geometry.py，宿主不另定一套。
#[tauri::command]
pub(crate) fn crop(
    state: State<'_, Arc<AppState>>,
    action: String,
    rect: Option<Vec<f64>>,
    rotation_degrees: Option<f64>,
) -> Result<Value, String> {
    const ACTIONS: [&str; 2] = ["set", "clear"];
    if !ACTIONS.contains(&action.as_str()) {
        return Err(format!("crop 不认识动作 {action}（可用：{}）", ACTIONS.join("/")));
    }
    let mut cmd = json!({"cmd": "crop", "action": action});
    if let Some(v) = rect {
        cmd["rect"] = json!(v);
    }
    if let Some(v) = rotation_degrees {
        cmd["rotation_degrees"] = json!(v);
    }
    state.send_to_engine(cmd)?;
    Ok(json!({"requested": true}))
}

/// Compile the same Rust point curves used by headless recipe replay.
#[tauri::command]
pub(crate) fn curve_preview(spec: Value) -> Result<Value, String> {crate::curve_api::preview(&spec)}

#[tauri::command]
pub(crate) fn curves(state: State<'_, Arc<AppState>>, action: String, spec: Option<Value>,
          gesture_id: Option<String>, request_id: Option<String>, interactive: Option<bool>,
          document_id: Option<String>) -> Result<Value,String> {
    if action != "set" && action != "clear" {return Err("unknown curves action".into());}
    let mut command = json!({"cmd":"curves", "action":action});
    if action == "set" {
        let value=spec.ok_or("curves set requires spec")?;
        curve_preview(value.clone())?;
        if value["version"]==3 && !state.ready_caps.lock().map_err(|_|"capability lock poisoned")?["curve_recipe_versions"]
            .as_array().is_some_and(|versions|versions.iter().any(|v|v.as_u64()==Some(3))){return Err("engine does not support curve recipe v3".into());}
        command["spec"]=value;
    }
    if let Some(document) = document_id {
        if document.is_empty() || document.len() > 64 {return Err("invalid curve document id".into());}
        command["document_id"]=json!(document);
    }
    let gesture=gesture_id.unwrap_or_default();
    if gesture.chars().count()>128 {return Err("curve gesture id too long".into());}
    command["gesture_id"]=json!(gesture.clone());
    let request=request_id.unwrap_or_default();
    if request.chars().count()>128 {return Err("curve request id too long".into());}
    command["request_id"]=json!(request);
    if interactive==Some(true) && action=="set" {
        state.send_interactive(format!("curves:{gesture}"),command)?;
    } else {state.send_to_engine(command)?;}
    Ok(json!({"requested":true}))
}


#[cfg(test)]
mod tests {
    use super::*;
    fn neutral()->Value {json!({"version":1,"space":"srgb-display","interpolation":"pchip",
        "boundary":"linear","enabled":true,"master":[[0,0],[1,1]],"red":[[0,0],[1,1]],
        "green":[[0,0],[1,1]],"blue":[[0,0],[1,1]]})}
    #[test] fn old_rgb_recipe_keeps_four_native_sample_channels() {
        let result=curve_preview(neutral()).unwrap();
        assert_eq!(result.as_object().unwrap().len(),4);
        assert_eq!(result["master"][128],json!(0.5));
    }
    #[test] fn luminance_requires_explicit_domain_and_uses_same_compiler() {
        let mut value=neutral();value["version"]=json!(2);
        assert!(curve_preview(value.clone()).is_err());
        value["luminance_space"]=json!("linear-srgb-y-ratio");
        value["luminance"]=json!([[0,0.1],[1,0.9]]);
        let result=curve_preview(value.clone()).unwrap();
        assert_eq!(result.as_object().unwrap().len(),5);
        assert!((result["luminance"][128].as_f64().unwrap()-0.5).abs()<1e-12);
        value["luminance_space"]=json!("lab-l");assert!(curve_preview(value).is_err());
    }
}
