// SPDX-License-Identifier: GPL-3.0-or-later
//! Engine-observed shared-graph history classification, never replay authority.
//! Preset and recovery markers stay distinct while sharing bounded ownership.
use std::{collections::{BTreeSet, HashMap, VecDeque}, sync::{Mutex, OnceLock}};
use serde_json::{json, Value};
use crate::preset_api::visual::{fields, text};
const MARKER: &str = "eye_bag_preset_alias_review";
const RECOVERY: &str = "eye_bag_recovery_alias_review";
fn valid_marker(key: &str, value: &Value) -> bool {
    match key {
        MARKER => crate::batch_api::history::preset_alias_summary(value),
        RECOVERY => crate::effect_recovery_host::alias::summary(value),
        _ => false,
    }
}
const MAX_BATCHES: usize = 4096;
const MAX_SUMMARY_ROWS: usize = 10_000;
const MAX_BYTES: usize = 4 * 1024 * 1024;
#[derive(Default)]
struct Snapshot { workspace: Option<String>, ids: BTreeSet<String>, markers: HashMap<String, Value>, blocked: BTreeSet<String>, invalid: bool }
fn registry() -> &'static Mutex<VecDeque<([u8;16], Snapshot)>> {
    static VALUE: OnceLock<Mutex<VecDeque<([u8;16], Snapshot)>>> = OnceLock::new();
    VALUE.get_or_init(|| Mutex::new(VecDeque::new()))
}
fn replace(epoch: [u8;16], mut snapshot: Snapshot) {
    let Ok(mut registry) = registry().lock() else { return; };
    if let Some((_, prior)) = registry.iter().find(|(key, _)| *key == epoch) {
        if snapshot.workspace.is_some() && prior.workspace == snapshot.workspace {
            // A second incomplete status cannot launder a previously rejected
            // composite ID into the ordinary-history route in this workspace.
            for id in &prior.blocked {
                if snapshot.ids.contains(id) { snapshot.blocked.insert(id.clone()); }
            }
            for (id, marker) in &prior.markers {
                if snapshot.ids.contains(id) && snapshot.markers.get(id) != Some(marker) { snapshot.blocked.insert(id.clone()); }
            }
        }
    }
    registry.retain(|(key, _)| *key != epoch);
    registry.push_back((epoch, snapshot));
    while registry.len() > 8 { registry.pop_front(); }
}
pub(super) fn clear(epoch: [u8;16]) { if let Ok(mut registry) = registry().lock() { registry.retain(|(key, _)| *key != epoch); } }

pub(super) fn observe_session(epoch: [u8;16], event: &Value) {
    if event["event"] != "session_state" || event.get("sync").is_none() { return; }
    let sync = &event["sync"];
    let mut snapshot = Snapshot::default();
    if !text(&sync["workspace_generation"]) {
        snapshot.invalid = true; replace(epoch, snapshot); return;
    }
    snapshot.workspace = sync["workspace_generation"].as_str().map(str::to_owned);
    let Some(rows) = sync["batches"].as_array() else { snapshot.invalid = true; replace(epoch, snapshot); return; };
    if rows.len() > MAX_SUMMARY_ROWS { snapshot.invalid = true; replace(epoch, snapshot); return; }
    let mut seen = BTreeSet::new();
    let mut retained_bytes = 0;
    for row in rows {
        if !text(&row["batch_id"]) || !seen.insert(row["batch_id"].as_str().unwrap()) { snapshot.invalid = true; break; }
        snapshot.ids.insert(row["batch_id"].as_str().unwrap().to_owned());
        let keys: Vec<_> = [MARKER, RECOVERY].into_iter().filter(|key| row.get(*key).is_some()).collect();
        if keys.is_empty() { continue; }
        if keys.len() != 1 { snapshot.blocked.insert(row["batch_id"].as_str().unwrap().to_owned()); continue; }
        let key = keys[0]; let marker = &row[key];
        if !fields(row, &["batch_id", "module_scope", "targets", "undone", key])
            || row["module_scope"] != json!(["lnx.people_graph.v1"]) || !row["undone"].is_boolean()
            || !valid_marker(key, marker) || row["targets"] != marker["member_count"] {
            snapshot.blocked.insert(row["batch_id"].as_str().unwrap().to_owned()); continue;
        }
        retained_bytes += marker.to_string().len();
        if snapshot.markers.len() >= MAX_BATCHES || retained_bytes > MAX_BYTES {
            snapshot.blocked.insert(row["batch_id"].as_str().unwrap().to_owned()); continue;
        }
        snapshot.markers.insert(row["batch_id"].as_str().unwrap().to_owned(), json!({(key):marker}));
    }
    replace(epoch, snapshot);
}

/// Called only with a validated original preset/recovery receipt and matching ACK.
pub(super) fn observe_publication(epoch: [u8;16], value: &Value) {
    let keys: Vec<_> = [MARKER, RECOVERY].into_iter().filter(|key| value.get(*key).is_some()).collect();
    if !text(&value["batch_id"]) || keys.len() != 1 || !valid_marker(keys[0], &value[keys[0]]) { return; }
    let marker = json!({(keys[0]):value[keys[0]]});
    let Ok(mut registry) = registry().lock() else { return; };
    if !registry.iter().any(|(key, _)| *key == epoch) { registry.push_back((epoch, Snapshot::default())); }
    while registry.len() > 8 { registry.pop_front(); }
    let snapshot = &mut registry.iter_mut().find(|(key, _)| *key == epoch).unwrap().1;
    let id = value["batch_id"].as_str().unwrap();
    if !snapshot.ids.contains(id) && snapshot.ids.len() >= MAX_SUMMARY_ROWS { snapshot.invalid = true; return; }
    snapshot.ids.insert(id.to_owned());
    let existing = snapshot.markers.get(id);
    if existing.is_some_and(|old| old != &marker) || (existing.is_none() && snapshot.markers.len() >= MAX_BATCHES)
        || snapshot.markers.values().map(|v| v.to_string().len()).sum::<usize>()
            - existing.map_or(0, |v| v.to_string().len()) + marker.to_string().len() > MAX_BYTES {
        snapshot.blocked.insert(id.to_owned()); return;
    }
    snapshot.markers.insert(id.to_owned(), marker.clone());
}

pub(super) fn marker(epoch: [u8;16], command: &Value) -> Result<Option<Value>, String> {
    Ok(markers(epoch, command)?.and_then(|markers| markers.get(MARKER).cloned()))
}
pub(super) fn markers(epoch: [u8;16], command: &Value) -> Result<Option<Value>, String> {
    if command["cmd"] != "batch" || !matches!(command["action"].as_str(), Some("undo" | "redo")) { return Ok(None); }
    let registry = registry().lock().map_err(|_| "多照片效果历史身份表不可用")?;
    let Some((_, snapshot)) = registry.iter().find(|(key, _)| *key == epoch) else { return Ok(None); };
    if snapshot.invalid { return Err("工程批次身份不完整或冲突；请重新读取工程状态后再操作历史".into()); }
    if command["batch_id"].as_str().is_some_and(|id|snapshot.blocked.contains(id)) {
        return Err("此多照片效果批次标记缺失、冲突或超过身份缓存容量，未提交历史操作".into());
    }
    Ok(command["batch_id"].as_str().and_then(|id| snapshot.markers.get(id)).cloned())
}

pub(super) fn settled_markers(command: &Value, markers: &Value, receipt: &Value) -> bool {
    crate::batch_api::history::command(command).is_ok()
        && crate::batch_api::history::receipt(receipt) && receipt["outcome_unknown"] == false
        && receipt["batch_id"] == command["batch_id"]
        && markers.as_object().is_some_and(|map| map.len() == 1 && map.iter().all(|(key, marker)|
            valid_marker(key, marker) && receipt.get(key) == Some(marker)))
}
pub(super) fn settled(command: &Value, marker: &Value, receipt: &Value) -> bool {
    crate::batch_api::history::command(command).is_ok()
        && crate::batch_api::history::receipt(receipt) && receipt["outcome_unknown"] == false
        && receipt["batch_id"] == command["batch_id"] && receipt[MARKER] == *marker
}

#[cfg(test)]
#[path = "preset_alias_history_fence_unrun.rs"]
mod tests;
