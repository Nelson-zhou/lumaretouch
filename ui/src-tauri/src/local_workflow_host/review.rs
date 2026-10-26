//! Strict handoff boundary. A display DTO is never authority to apply a preset.
use lrt_local_workflow::ports::{Command, CommandKind};
use serde_json::Value;
use super::wire;

pub fn exact(value: &Value, keys: &[&str]) -> bool {
    value.as_object().is_some_and(|map| map.len() == keys.len() && keys.iter().all(|key| map.contains_key(*key)))
}
pub fn hash(value: &Value) -> bool { value.as_str().is_some_and(|s| s.len() == 64 && s.bytes().all(|b| b.is_ascii_digit() || (b'a'..=b'f').contains(&b))) }
fn token(value: &Value) -> bool { value.as_str().is_some_and(wire::identity) }
fn bounded(value: &Value, max: usize) -> bool { value.as_str().is_some_and(|s| s.len() <= max && !s.chars().any(char::is_control)) }
pub fn target(value: &Value) -> bool {
    exact(value, &["document_id", "load_id", "revision"]) && token(&value["document_id"]) && token(&value["load_id"])
        && value["revision"].as_str().is_some_and(|s| !s.is_empty() && s.len() <= 20 && s.bytes().all(|b| b.is_ascii_digit())
            && (s == "0" || !s.starts_with('0')) && s.parse::<u64>().is_ok())
}
pub fn image(value: &Value) -> bool {
    exact(value, &["mime", "width", "height", "sha256", "byte_length", "page_count"])
        && value["mime"] == "image/png" && hash(&value["sha256"])
        && value["width"].as_u64().is_some_and(|n| (1..=4096).contains(&n))
        && value["height"].as_u64().is_some_and(|n| (1..=4096).contains(&n))
        && value["byte_length"].as_u64().is_some_and(|n| (33..=4 * 1024 * 1024).contains(&n)
            && value["page_count"].as_u64() == Some(n.div_ceil(65536)))
}
pub fn report(value: &Value) -> bool {
    exact(value, &["schema", "review_id", "target", "preset_id", "preset_sha256", "module_ids", "before", "after",
        "source_proof", "source_size", "output_size", "before_state_sha256", "candidate_state_sha256", "people_sha256",
        "repair_sha256", "before_render_sha256", "candidate_render_sha256", "page_bytes", "ttl_seconds", "approval_only", "runtime_verified", "review_sha256"])
        && value["schema"] == "lrt.workflow-preset-review.v1" && token(&value["review_id"]) && target(&value["target"])
        && token(&value["preset_id"]) && hash(&value["preset_sha256"]) && hash(&value["review_sha256"])
        && image(&value["before"]) && image(&value["after"]) && value["before"]["width"] == value["after"]["width"]
        && value["before"]["height"] == value["after"]["height"] && value["page_bytes"] == 65536
        && value["ttl_seconds"] == 900 && value["approval_only"] == true && value["runtime_verified"] == false
        && ["before_state_sha256", "candidate_state_sha256", "people_sha256", "repair_sha256", "before_render_sha256", "candidate_render_sha256"].iter().all(|key| hash(&value[*key]))
        && value["module_ids"].as_array().is_some_and(|ids| !ids.is_empty() && ids.len() <= 3
            && ids.iter().all(|id| matches!(id.as_str(), Some("lnx.exposure.v1" | "lnx.white_balance.v1" | "lnx.skin.v1")))
            && ids.iter().enumerate().all(|(index, id)| !ids[..index].contains(id)))
        && ["source_size", "output_size"].iter().all(|key| value[*key].as_array().is_some_and(|size| size.len() == 2
            && size.iter().all(|n| n.as_u64().is_some_and(|n| n > 0 && n <= 32_000_000))
            && size[0].as_u64().unwrap() * size[1].as_u64().unwrap() <= 32_000_000))
        && value["source_proof"].is_object() && value.to_string().len() <= 256 * 1024
}
pub fn handoff(value: &Value, command: &Command) -> bool {
    let (document, preset_id, preset_sha256) = match &command.operation {
        CommandKind::PreflightPreset { document, preset_id, preset_sha256, .. } => (document, preset_id, preset_sha256),
        CommandKind::ApplyPreset { document, preset_id, assessment } => (document, preset_id, &assessment.preset_sha256),
        _ => return false,
    };
    if let CommandKind::ApplyPreset { assessment, .. } = &command.operation {
        if (value["mode"] == "automatic") == assessment.requires_review { return false; }
    }
    if value["mode"] == "automatic" {
        return exact(value, &["version", "operation_id", "document_id", "preset_id", "preset_sha256", "phase", "review", "message", "mode"])
            && value["version"] == 1 && value["operation_id"] == command.identity.operation_id
            && value["document_id"] == document.document_id && value["preset_id"] == *preset_id && value["preset_sha256"] == *preset_sha256
            && matches!(value["phase"].as_str(), Some("authorized" | "unknown"))
            && value["review"].is_null() && bounded(&value["message"], 8192);
    }
    exact(value, &["version", "operation_id", "document_id", "preset_id", "preset_sha256", "phase", "review", "message"])
        && value["version"] == 1 && value["operation_id"] == command.identity.operation_id
        && value["document_id"] == document.document_id && value["preset_id"] == *preset_id && value["preset_sha256"] == *preset_sha256
        && matches!(value["phase"].as_str(), Some("awaiting_open" | "awaiting_preparation" | "reviewing" | "authorized" | "awaiting_save" | "awaiting_return" | "unknown"))
        && bounded(&value["message"], 8192)
        && (value["review"].is_null() || (report(&value["review"]) && value["review"]["target"]["document_id"] == document.document_id
            && value["review"]["preset_id"] == *preset_id && value["review"]["preset_sha256"] == *preset_sha256))
        && (value["phase"] != "reviewing" || !value["review"].is_null())
}
pub fn step_allowed(handoff: &Value, step: &str, payload: &Value) -> bool {
    if handoff["mode"] == "automatic" { return false; }
    match step {
        "open_target" => handoff["phase"] == "awaiting_open" && exact(payload, &[]),
        "prepare_skin" => handoff["phase"] == "awaiting_preparation" && exact(payload, &[]),
        "save_project" => handoff["phase"] == "awaiting_save" && exact(payload, &[]),
        "return_target" => matches!(handoff["phase"].as_str(), Some("awaiting_open" | "awaiting_preparation" | "reviewing" | "awaiting_return")) && exact(payload, &[]),
        "approve" => {
            let review = &handoff["review"];
            handoff["phase"] == "reviewing" && report(review)
                && exact(payload, &["review_id", "review_sha256", "target", "preset_id", "preset_sha256", "before_sha256", "after_sha256", "accepted"])
                && ["review_id", "review_sha256", "target", "preset_id", "preset_sha256"].iter().all(|key| payload[*key] == review[*key])
                && payload["before_sha256"] == review["before"]["sha256"] && payload["after_sha256"] == review["after"]["sha256"] && payload["accepted"] == true
        }
        _ => false,
    }
}
pub fn image_request(input: &wire::ReviewImageInput, handoff: &Value) -> bool {
    let report = &handoff["review"];
    input.port_version == 1 && handoff["operation_id"] == input.operation_id && handoff["phase"] == "reviewing" && self::report(report)
        && report["review_id"] == input.review_id && report["review_sha256"] == input.review_sha256
        && matches!(input.side.as_str(), "before" | "after") && report[&input.side]["sha256"] == input.sha256
        && report[&input.side]["page_count"].as_u64().is_some_and(|count| input.page < count)
}
pub fn image_page(value: &Value, request: &Value, handoff: &Value) -> bool {
    use base64::Engine;
    use sha2::{Digest, Sha256};
    let Some(side) = request["side"].as_str() else { return false; };
    let metadata = &handoff["review"][side];
    if !matches!(side, "before" | "after") || !report(&handoff["review"]) || !image(metadata) { return false; }
    if !exact(value, &["review_id", "review_sha256", "target", "side", "mime", "width", "height", "sha256", "byte_length", "page_count",
        "page", "page_bytes", "offset", "page_byte_length", "page_sha256", "base64"])
        || !["review_id", "review_sha256", "side", "sha256", "page"].iter().all(|key| value[*key] == request[*key])
        || value["target"] != handoff["review"]["target"] || value["page_bytes"] != 65536
        || !["mime", "width", "height", "sha256", "byte_length", "page_count"].iter().all(|key| value[*key] == metadata[*key]) { return false; }
    let Some(page) = value["page"].as_u64() else { return false; };
    let Some(total) = metadata["byte_length"].as_u64() else { return false; };
    if page >= metadata["page_count"].as_u64().unwrap_or(0) || value["offset"].as_u64() != Some(page * 65536) { return false; }
    let Some(encoded) = value["base64"].as_str().filter(|s| s.len() <= 87384) else { return false; };
    let Ok(bytes) = base64::engine::general_purpose::STANDARD.decode(encoded) else { return false; };
    let length = (total - page * 65536).min(65536);
    bytes.len() as u64 == length && value["page_byte_length"].as_u64() == Some(length)
        && base64::engine::general_purpose::STANDARD.encode(&bytes) == encoded
        && value["page_sha256"].as_str() == Some(format!("{:x}", Sha256::digest(&bytes)).as_str())
}
