// SPDX-License-Identifier: GPL-3.0-or-later
//! Dedicated current-photo hair-volume wire contract. AUTHORED / UNRUN.
//! Geometry here is bounded, user-authored source data, never a segmentation,
//! deformation implementation, source mask from another operation, or quality claim.
use std::io::{self, Write};
use base64::{engine::general_purpose::STANDARD, Engine as _};
use serde_json::Value;
use sha2::{Digest, Sha256};

pub(crate) const OPERATION: &str = "lnx.hair_volume.v1";
pub(crate) const EVENT: &str = "hair_volume_result";
pub(crate) const REQUEST_BYTES: usize = 512 * 1024;
pub(crate) const RESULT_BYTES: usize = 25 * 1024 * 1024;
const IMAGE_URL_BYTES: usize = 8 * 1024 * 1024;
const PNG_BYTES: usize = 4 * 1024 * 1024;
const REGIONS: [&str; 3] = ["crown", "left", "right"];

fn fields(value: &Value, keys: &[&str]) -> bool {
    value.as_object().is_some_and(|map| map.len() == keys.len() && keys.iter().all(|key| map.contains_key(*key)))
}
pub(crate) fn token(value: &Value) -> bool {
    value.as_str().is_some_and(|s| !s.is_empty() && s.len() <= 160 && !s.chars().any(char::is_control))
}
fn hex(value: &Value, length: usize) -> bool {
    value.as_str().is_some_and(|s| s.len() == length && s.bytes().all(|b| b.is_ascii_digit() || (b'a'..=b'f').contains(&b)))
}
fn number(value: &Value, low: f64, high: f64) -> bool {
    value.as_f64().is_some_and(|n| n.is_finite() && (low..=high).contains(&n))
}
fn integer(value: &Value, low: u64, high: u64) -> bool {
    value.as_u64().is_some_and(|n| (low..=high).contains(&n))
}
/// Numeric equality across Python/JSON echoes; never a cross-language hash.
pub(crate) fn same(a: &Value, b: &Value) -> bool {
    match (a, b) {
        (Value::Number(a), Value::Number(b)) => a.as_f64() == b.as_f64(),
        (Value::Array(a), Value::Array(b)) => a.len() == b.len() && a.iter().zip(b).all(|(a,b)| same(a,b)),
        (Value::Object(a), Value::Object(b)) => a.len() == b.len() && a.iter().all(|(key,a)| b.get(key).is_some_and(|b| same(a,b))),
        _ => a == b,
    }
}
fn recipe(value: &Value) -> bool {
    fields(value, &["version", "crown", "sides"]) && value["version"].as_u64() == Some(1)
        && fields(&value["crown"], &["version", "amount"]) && value["crown"]["version"].as_u64() == Some(1)
        && number(&value["crown"]["amount"], -1.0, 1.0)
        && fields(&value["sides"], &["version", "linked", "left", "right"])
        && value["sides"]["version"].as_u64() == Some(1) && value["sides"]["linked"].is_boolean()
        && number(&value["sides"]["left"], -1.0, 1.0) && number(&value["sides"]["right"], -1.0, 1.0)
        && (value["sides"]["linked"] != true || same(&value["sides"]["left"], &value["sides"]["right"]))
}
fn amount<'a>(value: &'a Value, region: &str) -> &'a Value {
    if region == "crown" { &value["crown"]["amount"] } else { &value["sides"][region] }
}
fn active(value: &Value) -> bool { REGIONS.iter().any(|region| amount(value, region).as_f64() != Some(0.0)) }
fn source(value: &Value) -> bool {
    fields(value, &["sha256", "width", "height"]) && hex(&value["sha256"], 64)
        && ["width", "height"].iter().all(|key| integer(&value[*key], 2, 1_000_000))
}
fn point(value: &Value) -> bool {
    value.as_array().is_some_and(|v| v.len() == 2 && v.iter().all(|n| number(n, 0.0, 1.0)))
}
fn bounds(value: &Value) -> bool {
    value.as_array().is_some_and(|v| v.len() == 4 && v.iter().all(|n| number(n, 0.0, 1.0))
        && v[0].as_f64().unwrap() > 0.0 && v[3].as_f64().unwrap() < 1.0
        && v.windows(2).all(|p| p[0].as_f64().unwrap() < p[1].as_f64().unwrap()))
}
fn patch(value: &Value, region: &str) -> bool {
    if !fields(value, &["x", "y", "contour", "hair_samples", "background_samples"])
        || !bounds(&value["x"]) || !bounds(&value["y"]) { return false; }
    let Some(contour) = value["contour"].as_array() else { return false; };
    let Some(hair) = value["hair_samples"].as_array() else { return false; };
    let Some(background) = value["background_samples"].as_array() else { return false; };
    if !(3..=33).contains(&contour.len()) || contour.len() != hair.len() || hair.len() != background.len()
        || !contour.iter().chain(hair).chain(background).all(point) { return false; }
    let tangent = if region == "crown" { 0 } else { 1 };
    let normal = 1 - tangent;
    let direction = if region == "right" { -1.0 } else { 1.0 };
    let in_box = |p: &Value, start: usize, end: usize| ["x", "y"].iter().enumerate().all(|(axis, name)| {
        let n = p[axis].as_f64().unwrap();
        n >= value[*name][start].as_f64().unwrap() && n <= value[*name][end].as_f64().unwrap()
    });
    for (i, ((p, h), b)) in contour.iter().zip(hair).zip(background).enumerate() {
        if !in_box(p, 1, 2) || !in_box(h, 1, 2) || !in_box(b, 0, 3)
            || !same(&h[tangent], &p[tangent]) || !same(&b[tangent], &p[tangent])
            || (i > 0 && p[tangent].as_f64().unwrap() <= contour[i - 1][tangent].as_f64().unwrap())
            || direction * (h[normal].as_f64().unwrap() - p[normal].as_f64().unwrap()) <= 0.0
            || direction * (p[normal].as_f64().unwrap() - b[normal].as_f64().unwrap()) <= 0.0 { return false; }
    }
    true
}
fn protection(value: &Value) -> bool {
    fields(value, &["ears", "neck", "other_people", "visible_anatomy_reviewed", "whole_source_reviewed"])
        && value["visible_anatomy_reviewed"] == true && value["whole_source_reviewed"] == true
        && [("ears", 2), ("neck", 1), ("other_people", 64)].iter().all(|(key, limit)| value[*key].as_array().is_some_and(|boxes|
            boxes.len() <= *limit && boxes.iter().all(|b| b.as_array().is_some_and(|v|
                v.len() == 4 && v.iter().all(|n| number(n, 0.0, 1.0))
                && v[0].as_f64().unwrap() < v[2].as_f64().unwrap()
                && v[1].as_f64().unwrap() < v[3].as_f64().unwrap()))))
}
fn preview_payload(payload: &Value) -> bool {
    if !fields(payload, &["recipe", "regions", "protection", "confirmed", "crown_confirmed", "left_confirmed", "right_confirmed"])
        || !recipe(&payload["recipe"]) || !active(&payload["recipe"]) || payload["confirmed"] != true
        || !protection(&payload["protection"]) || !fields(&payload["regions"], &REGIONS) { return false; }
    REGIONS.iter().all(|region| {
        let confirmation = &payload[format!("{region}_confirmed")];
        let support = &payload["regions"][*region];
        confirmation.is_boolean() && if amount(&payload["recipe"], region).as_f64() == Some(0.0) {
            support.is_null()
        } else { confirmation == &Value::Bool(true) && patch(support, region) }
    })
}
fn review_identity(value: &Value) -> bool { hex(&value["preview_id"], 32) && hex(&value["review_token"], 64) }
fn ack(value: &Value) -> bool {
    review_identity(value) && ["before_sha256", "after_sha256", "support_sha256"].iter().all(|key| hex(&value[*key], 64))
}
pub(crate) fn validate(request: &Value) -> Result<(), String> {
    let payload = &request["payload"];
    let valid = fields(request, &["cmd", "protocol", "operation_id", "request_id", "action", "people_context", "payload"])
        && request["cmd"] == "hair_volume" && request["protocol"].as_u64() == Some(1) && request["operation_id"] == OPERATION
        && token(&request["request_id"]) && crate::people_api::valid_context(&request["people_context"])
        && request["people_context"]["target"]["scope"] == "face"
        && match request["action"].as_str() {
            Some("context" | "clear") => fields(payload, &[]),
            Some("preview") => preview_payload(payload),
            Some("presented") => fields(payload, &["preview_id", "review_token", "before_sha256", "after_sha256", "support_sha256"]) && ack(payload),
            Some("commit") => fields(payload, &["preview_id", "review_token", "confirmed"]) && review_identity(payload) && payload["confirmed"] == true,
            Some("status") => fields(payload, &["original_request_id"]) && token(&payload["original_request_id"]),
            _ => false,
        };
    if !valid { return Err("发量请求需要当前照片独立人物、完整源图轮廓和各项明确确认".into()); }
    size(request, REQUEST_BYTES).map(|_| ())
}
pub(crate) fn mutation(request: &Value) -> bool { matches!(request["action"].as_str(), Some("commit" | "clear")) }
pub(crate) fn read_only(request: &Value) -> bool {
    matches!(request["action"].as_str(), Some("context" | "preview" | "presented" | "status")) && validate(request).is_ok()
}
pub(crate) fn reservation(action: &str) -> usize {
    match action { "preview" | "status" => RESULT_BYTES, "context" => 9 * 1024 * 1024, _ => 8 * 1024 * 1024 }
}
pub(crate) fn size(value: &Value, limit: usize) -> Result<usize, String> {
    struct Count { count: usize, limit: usize }
    impl Write for Count {
        fn write(&mut self, bytes: &[u8]) -> io::Result<usize> {
            self.count = self.count.checked_add(bytes.len()).ok_or_else(|| io::Error::new(io::ErrorKind::InvalidData, "size overflow"))?;
            if self.count > self.limit { return Err(io::Error::new(io::ErrorKind::InvalidData, "size limit")); }
            Ok(bytes.len())
        }
        fn flush(&mut self) -> io::Result<()> { Ok(()) }
    }
    let mut counter = Count { count: 0, limit };
    serde_json::to_writer(&mut counter, value).map_err(|_| "发量数据超过安全大小上限".to_owned())?;
    Ok(counter.count)
}

/// Canonical PNG framing, CRC, dimensions and actual-byte digest. This reuses
/// only the existing transport parser, not that operation's support or renderer.
fn image(value: &Value, url: &str, hash: &str, width: &str, height: &str) -> bool {
    let Some(encoded) = value[url].as_str().filter(|s| s.len() <= IMAGE_URL_BYTES)
        .and_then(|s| s.strip_prefix("data:image/png;base64,")) else { return false; };
    if !hex(&value[hash], 64) || !integer(&value[width], 2, 1024) || !integer(&value[height], 2, 1024) { return false; }
    let Ok(bytes) = STANDARD.decode(encoded) else { return false; };
    bytes.len() <= PNG_BYTES && STANDARD.encode(&bytes) == encoded
        && crate::torso_transfer_protocol::png(&bytes, value[width].as_u64().unwrap() as u32, value[height].as_u64().unwrap() as u32)
        && value[hash] == format!("{:x}", Sha256::digest(&bytes))
}
fn review_image(value: &Value, prefix: &str) -> bool {
    image(value, &format!("{prefix}_png"), &format!("{prefix}_sha256"), &format!("{prefix}_width"), &format!("{prefix}_height"))
}
fn source_binding(payload: &Value, request: &Value) -> bool {
    source(&payload["source"]) && same(&payload["face_ref"], &request["people_context"]["target"]["face_ref"])
        && payload["source"]["sha256"] == request["people_context"]["target"]["face_ref"]["asset_sha256"]
        && payload["source_width"] == payload["source"]["width"] && payload["source_height"] == payload["source"]["height"]
}
fn context_result(payload: &Value, request: &Value) -> bool {
    source_binding(payload, request) && recipe(&payload["recipe"])
        && matches!(payload["source_kind"].as_str(), Some("original" | "derived"))
        && payload["native_available"].is_boolean()
        && payload["notice"].as_str().is_some_and(|s| s.len() <= 4096)
        && payload.get("semantic_evidence_sha256").is_some()
        && (payload["semantic_evidence_sha256"].is_null() || hex(&payload["semantic_evidence_sha256"], 64))
        && image(payload, "source_png", "source_png_sha256", "source_preview_width", "source_preview_height")
}
/// Bounded source-pixel measurements only. The engine still checks source pixels,
/// genuine hair evidence, anatomy, ownership and the deformation's numeric safety.
pub(crate) fn source_geometry(payload: &Value, source: &Value) -> bool {
    if !preview_payload(payload) || !self::source(source) { return false; }
    let extents = [source["width"].as_u64().unwrap() as f64 - 1.0, source["height"].as_u64().unwrap() as f64 - 1.0];
    REGIONS.iter().all(|region| {
        let patch = &payload["regions"][*region];
        if patch.is_null() { return true; }
        for (axis, name) in ["x", "y"].iter().enumerate() {
            let b: Vec<f64> = patch[*name].as_array().unwrap().iter().map(|n| n.as_f64().unwrap()).collect();
            if b[0] * extents[axis] < 1.0 - 1e-8 || (1.0 - b[3]) * extents[axis] < 1.0 - 1e-8
                || (b[1] - b[0]) * extents[axis] < 4.0 - 1e-8 || (b[3] - b[2]) * extents[axis] < 4.0 - 1e-8
                || (b[2] - b[1]) * extents[axis] < 2.0 - 1e-8 { return false; }
        }
        let tangent = if *region == "crown" { 0 } else { 1 };
        let normal = 1 - tangent;
        let contour = patch["contour"].as_array().unwrap();
        let bounds = &patch[if tangent == 0 { "x" } else { "y" }];
        if contour.last().unwrap()[tangent].as_f64().unwrap() - contour[0][tangent].as_f64().unwrap()
            < (bounds[2].as_f64().unwrap() - bounds[1].as_f64().unwrap()) / 2.0 - 1e-12 { return false; }
        contour.iter().enumerate().all(|(i, p)| ["hair_samples", "background_samples"].iter().all(|name|
            (patch[*name][i][normal].as_f64().unwrap() - p[normal].as_f64().unwrap()).abs() * extents[normal] >= 1.0 - 1e-8))
    })
}
fn nonregressing(after: &Value, before: &Value) -> bool {
    after.as_u64().zip(before.as_u64()).is_some_and(|(a,b)| a >= b && a <= 9_007_199_254_740_991)
}
fn publication(value: &Value, request: &Value) -> bool {
    let payload = &value["payload"];
    let context = &request["people_context"];
    let people = &value["doc_state"]["people"];
    let binding = &people["binding"];
    let resolved = &people["resolved"];
    let commit = request["action"] == "commit";
    let expected_kind = if commit { "confirmed" } else { "cleared" };
    payload["kind"] == expected_kind
        && payload["committed"] == true && recipe(&payload["recipe"])
        && (if commit { active(&payload["recipe"]) && hex(&payload["asset_sha256"], 64) } else { !active(&payload["recipe"]) })
        && binding["document_id"] == context["document_id"] && binding["document_epoch"] == context["document_epoch"]
        && binding["asset_sha256"] == context["target"]["face_ref"]["asset_sha256"]
        && nonregressing(&binding["document_revision"], &context["document_revision"])
        && nonregressing(&people["revision"], &context["state_revision"])
        && people["association_revision"] == context["association_revision"]
        && people["selected_face_id"] == context["target"]["target_id"] && same(&people["editing_target"], &context["target"])
        && same(&resolved["face_ref"], &context["target"]["face_ref"])
        && resolved["state_revision"] == people["revision"] && resolved["association_revision"] == people["association_revision"]
        && [("/crown/amount", "crown", "amount"), ("/sides/linked", "sides", "linked"),
            ("/sides/left", "sides", "left"), ("/sides/right", "sides", "right")].iter().all(|(path, group, leaf)|
                same(&resolved["operations"][OPERATION][*path]["value"], &payload["recipe"][*group][*leaf]))
}
pub(crate) fn valid_result(value: &Value, request: &Value) -> bool {
    // Only the native explicit reopen path may create recovery provenance.
    if value.get("workspace_reopened").is_some() || value["event"] != EVENT || value["protocol"].as_u64() != Some(1)
        || value["operation_id"] != OPERATION || value["request_id"] != request["request_id"] || value["action"] != request["action"]
        || value["document_id"] != request["people_context"]["document_id"]
        || !same(&value["people_context"], &request["people_context"]) || !same(&value["request_payload"], &request["payload"])
        || !value["success"].is_boolean() || !value["outcome_unknown"].is_boolean()
        || value.get("frame_emitted").is_some_and(|flag| !flag.is_boolean())
        || value["requires_readback"] == true || value["requires_reload"] == true { return false; }
    if value["success"] == false {
        return value["error"].as_str().is_some_and(|s| !s.trim().is_empty() && s.len() <= 8192);
    }
    if value["outcome_unknown"] != false || !value["payload"].is_object() { return false; }
    let payload = &value["payload"];
    match request["action"].as_str() {
        Some("context") => context_result(payload, request),
        Some("preview") => ack(payload) && hex(&payload["support_asset_sha256"], 64)
            && payload["preview_sha256"] == payload["review_token"] && hex(&payload["semantic_evidence_sha256"], 64)
            && source_binding(payload, request)
            && ["recipe", "regions", "protection"].iter().all(|key| same(&payload[*key], &request["payload"][*key]))
            && source_geometry(&request["payload"], &payload["source"])
            && ["before", "after", "support"].iter().all(|prefix| review_image(payload, prefix))
            && payload["before_width"] == payload["after_width"] && payload["before_height"] == payload["after_height"]
            && payload["before_width"] == payload["support_width"] && payload["before_height"] == payload["support_height"],
        Some("presented") => payload["kind"] == "presented" && payload["presented"] == true
            && ["preview_id", "review_token", "before_sha256", "after_sha256", "support_sha256"].iter()
                .all(|key| payload[*key] == request["payload"][*key]),
        Some("commit" | "clear") => publication(value, request),
        // A status transport reply never settles, redeems, or refreshes another
        // row. UI recovery uses the retained native hair_volume_status mailbox.
        Some("status") => payload["kind"] == "status" && payload["found"].is_boolean()
            && payload["original_request_id"] == request["payload"]["original_request_id"]
            && (if payload["found"] == true {
                payload["result"].is_object() && payload["result"]["event"] == EVENT
                    && payload["result"]["operation_id"] == OPERATION && payload["result"]["protocol"].as_u64() == Some(1)
                    && payload["result"]["request_id"] == request["payload"]["original_request_id"]
            } else { payload["result"].is_null() }),
        _ => false,
    }
}
