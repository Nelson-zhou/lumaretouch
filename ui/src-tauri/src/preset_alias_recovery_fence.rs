// SPDX-License-Identifier: GPL-3.0-or-later
//! Narrow pending/unknown mixed-preset fence. AUTHORED / UNRUN.
//! Unknown writes block edit/history/save/export. Receipt queries only read the
//! retained first terminal; they do not retry or resolve it. Verified workspace
//! reopen (or a new engine epoch) is the escape after that immutable unknown.
use serde_json::Value;
use crate::receipt_host::ReceiptKind;
use crate::preset_api::visual::{fields, text};
use crate::original_shadow_transfer_protocol::hex;

fn envelope(value: &Value, required: &[&str], optional: &[&str]) -> bool {
    value.as_object().is_some_and(|map| required.iter().all(|key| map.contains_key(*key))
        && map.keys().all(|key| required.contains(&key.as_str()) || optional.contains(&key.as_str())))
}
fn path(value: &Value) -> bool { value.as_str().is_some_and(|s| !s.trim().is_empty() && s.len() <= 4096 && !s.contains('\0')) }
fn query(value: &Value) -> bool {
    envelope(value, &["cmd", "action"], &["request_id"])
        && value.get("request_id").map_or(true, text)
}
fn recovery(value: &Value) -> bool {
    let common = ["cmd", "action", "request_id", "project_id"];
    if !text(&value["request_id"]) || !text(&value["project_id"])
        || !value.get("area").map_or(true, |area| matches!(area.as_str(), Some("candidates" | "trash"))) { return false; }
    match value["action"].as_str() {
        Some("list" | "status" | "trash_list" | "cancel") => fields(value, &common),
        Some("inspect") => envelope(value, &common, &["candidate_id", "area"]) && text(&value["candidate_id"]),
        Some("restore" | "restore_trash") => envelope(value, &common,
            &["candidate_id", "area", "reviewed_sha256", "destination", "confirmed"])
            && text(&value["candidate_id"]) && hex(&value["reviewed_sha256"], 64)
            && path(&value["destination"]) && value["confirmed"] == true,
        Some("relink") => envelope(value, &common,
            &["candidate_id", "area", "reviewed_sha256", "source_asset_id", "path", "confirmed"])
            && text(&value["candidate_id"]) && text(&value["source_asset_id"])
            && hex(&value["reviewed_sha256"], 64) && path(&value["path"]) && value["confirmed"] == true,
        _ => false,
    }
}

pub(super) fn applies(command: &Value) -> bool {
    command["cmd"] == "preset" && command["action"] == "apply"
        && command["eye_bag_preset_ack"].get("members").is_some()
        && crate::preset_api::eye_bag::command(command).is_ok()
}

pub(super) fn safe_during_pending(command: &Value) -> bool {
    // Do not trust generic action names or suffixes: an exposure command with
    // action=status must not bypass the fence. Use owned read predicates.
    if crate::preset_api::read_only(command) || crate::batch_api::read_only(command)
        || crate::torso_transfer_protocol::read_only_head_preflight(command)
        || crate::people_api::eye_bag::read_only(command) || crate::people_api::face_style::read_only(command)
        || crate::people_api::face_decoration::read_only(command) || crate::people_api::decoration_alias::read_only(command)
        || crate::common_background_readback::read_only(command)
        || crate::torso_length_api::read_only(command) || crate::waist_length_api::read_only(command)
        || crate::head_size_api::read_only(command) || crate::shoulder_shape_api::read_only(command)
        || crate::leg_shape_api::read_only(command) || crate::waist_shape_api::read_only(command)
        || crate::leg_length_api::read_only(command) || crate::neck_shape_api::read_only(command)
        || crate::arm_shape_api::read_only(command) { return true; }
    match command["cmd"].as_str() {
        Some("hello" | "shutdown") => fields(command, &["cmd"]),
        Some("inspection_snapshot") => match command["action"].as_str() {
            Some("status" | "cancel" | "release") => fields(command, &["cmd", "action", "request_id"]) && text(&command["request_id"]),
            Some("start") => fields(command, &["cmd", "action", "request_id", "max_asset_bytes", "render"])
                && text(&command["request_id"]) && command["max_asset_bytes"].is_u64() && command["render"].is_object(),
            _ => false,
        },
        Some("session") => command["action"] == "query" && envelope(command, &["cmd", "action"],
            &["request_id", "query", "session_id", "selected_path", "document_id"]),
        Some("project") => match command["action"].as_str() {
            Some("state") => query(command),
            Some("open") => envelope(command, &["cmd", "action", "path"], &["force", "doc", "document_id"])
                && path(&command["path"]) && command.get("force").map_or(true, Value::is_boolean)
                && command.get("doc").map_or(true, path) && command.get("document_id").map_or(true, text),
            Some("create") => envelope(command, &["cmd", "action", "name", "directory"], &["force"])
                && text(&command["name"]) && path(&command["directory"]) && command.get("force").map_or(true, Value::is_boolean),
            _ => false,
        },
        Some("virtual_copy") => match command["action"].as_str() {
            Some("state") => envelope(command, &["cmd", "action", "request_id"], &["workspace"]) && text(&command["request_id"]),
            Some("query") => fields(command, &["cmd", "action", "request_id", "workspace", "operation_id"])
                && ["request_id", "workspace", "operation_id"].iter().all(|key| text(&command[*key])),
            _ => false,
        },
        Some("managed_import") => matches!(command["action"].as_str(), Some("state" | "query"))
            && envelope(command, &["cmd", "action", "request_id"], &["project_id", "operation_id"])
            && text(&command["request_id"]),
        Some("batch") => command["action"] == "state" && query(command),
        Some("preset") => command["action"] == "list" && query(command),
        Some("project_recovery") => recovery(command),
        _ => false,
    }
}

/// Successful engine workspace events include the actual opened project state.
/// An attempted/failed open, panel dismissal or bare synthetic event is not it.
pub(super) fn reopened(value: &Value) -> bool {
    matches!(value["event"].as_str(), Some("project_opened" | "project_created"))
        && value["open"] == true && path(&value["path"]) && text(&value["project_id"])
        && value["docs"].is_u64() && value["dirty"].is_boolean()
        && value["success"] != false && value["outcome_unknown"] != true
        && value.get("error").is_none() && value["requires_reload"] != true && value["requires_readback"] != true
}

pub(super) fn settled(command: &Value, receipt: &Value) -> bool {
    receipt["outcome_unknown"] == false && matches_request(command, receipt)
}
pub(super) fn matches_request(command: &Value, receipt: &Value) -> bool {
    if !crate::preset_host::PresetKind::valid(receipt, command["document_id"].as_str()) { return false; }
    let Ok(Some(identity)) = crate::preset_api::eye_bag::binding(command) else { return false; };
    identity.as_object().is_some_and(|fields| fields.iter().all(|(key, expected)| receipt.get(key) == Some(expected)))
}

#[cfg(test)]
#[path = "preset_alias_recovery_fence_unrun.rs"]
mod tests;
