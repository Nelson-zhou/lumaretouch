// SPDX-License-Identifier: GPL-3.0-or-later
//! Existing portrait transports, with captured people scope/revision fences.
use serde_json::{json, Value};
use std::sync::Arc;
use tauri::State;
use crate::AppState;

#[tauri::command]
pub(crate) fn deform(
    state: State<'_, Arc<AppState>>,
    action: String,
    amounts: Option<Value>,
    scope: Option<String>,
    people_context: Option<Value>,
) -> Result<Value, String> {
    let mut cmd = json!({"cmd": "deform", "action": action});
    // 与 light 同一条规矩：给了才附。宿主写默认值等于替引擎做决定，
    // 生产默认值一改这条通路就会静默漂开。
    if let Some(v) = amounts {
        cmd["amounts"] = v;
    }
    // 作用层（LNX-PORTRAIT-004）：all=改全人物默认 / person=只覆盖当前选定那一张。
    // 同样"给了才附"——引擎那边的默认值才是唯一出处，这里再刻一份就是双出处。
    if let Some(v) = scope {
        cmd["scope"] = json!(v);
    }
    crate::people_api::add_context(&mut cmd, people_context)?;
    state.send_to_engine(cmd)?;
    Ok(json!({"requested": true}))
}

#[tauri::command]
pub(crate) fn enhance(
    state: State<'_, Arc<AppState>>,
    action: String,
    sclera: Option<f64>,
    iris: Option<f64>,
    teeth: Option<f64>,
    dark_circles: Option<f64>,
    eye_bags: Option<f64>,
    veins: Option<f64>,
    catchlight_left: Option<f64>,
    catchlight_right: Option<f64>,
    wrinkles: Option<Value>,
    people_context: Option<Value>,
) -> Result<Value, String> {
    let mut cmd = crate::facial_wrinkle_api::enhance_command(&action,
        [sclera, iris, teeth, dark_circles, eye_bags, veins, catchlight_left, catchlight_right], wrinkles)?;
    crate::people_api::add_context(&mut cmd, people_context)?;
    state.send_to_engine(cmd)?;
    Ok(json!({"requested": true}))
}
