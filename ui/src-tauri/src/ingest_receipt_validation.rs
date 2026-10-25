//! Pure protocol-1 ingestion receipt checks. No epoch, storage, IO or mutation.
//!
//! Callers must supply only previously accepted, same-epoch ownership evidence.
//! A receipt must pass this boundary before storage AND recovery-fence settlement.
use std::collections::HashSet;
use serde_json::Value;

const MAX_BYTES: usize = 4 * 1024 * 1024;
const MAX_FILES: usize = 512;
const MAX_FILE_BYTES: u64 = 2 * 1024 * 1024 * 1024;
const MAX_SOURCE_BYTES: u64 = 16 * 1024 * 1024 * 1024;

#[derive(Default)]
pub(crate) struct ValidationContext<'a> {
    pub arm_request: Option<&'a Value>,
    pub arm_receipt: Option<&'a Value>,
    pub original_import_request: Option<&'a Value>,
    pub original_import_prior: Option<&'a Value>,
}

fn fields(value: &Value, required: &[&str], optional: &[&str]) -> bool {
    value.as_object().is_some_and(|object| {
        required.iter().all(|key| object.contains_key(*key))
            && object.keys().all(|key| required.contains(&key.as_str()) || optional.contains(&key.as_str()))
    })
}

fn uuid(value: &Value) -> bool {
    value.as_str().is_some_and(|value| {
        value.len() == 36 && value.bytes().enumerate().all(|(index, byte)| {
            if matches!(index, 8 | 13 | 18 | 23) { byte == b'-' }
            else { byte.is_ascii_digit() || (b'a'..=b'f').contains(&byte) }
        })
    })
}

fn token(value: &Value) -> bool {
    value.as_str().is_some_and(|value| !value.is_empty() && value.len() <= 128
        && !value.chars().any(|character| character < ' ' || character == '\u{7f}'))
}

fn text(value: &Value) -> bool { value.as_str().is_some_and(|value| !value.is_empty()) }
fn nullable_text(value: &Value) -> bool { value.is_null() || text(value) }
fn digest(value: &Value) -> bool {
    value.as_str().is_some_and(|value| value.len() == 64
        && value.bytes().all(|byte| byte.is_ascii_digit() || (b'a'..=b'f').contains(&byte)))
}

fn path(value: &Value) -> bool {
    value.as_str().is_some_and(|value| value.starts_with('/') && !value.contains('\0')
        && value.chars().count() <= 4096
        && (value == "/" || value[1..].split('/').all(|part| !matches!(part, "" | "." | ".."))))
}

fn decimal(value: &Value) -> bool {
    value.as_str().is_some_and(|value| !value.is_empty() && value.len() <= 20
        && value.bytes().all(|byte| byte.is_ascii_digit())
        && (value == "0" || !value.starts_with('0')))
}

fn root_identity(value: &Value) -> bool {
    value.as_array().is_some_and(|identity| identity.len() == 2 && identity.iter().all(|part|
        decimal(part) && part.as_str().and_then(|part| part.parse::<u64>().ok()).is_some()))
}

fn binding(value: &Value) -> bool {
    fields(value, &["project_id", "path", "workspace", "disk_sha256"], &[])
        && token(&value["project_id"]) && path(&value["path"])
        && token(&value["workspace"]) && digest(&value["disk_sha256"])
}

fn same_project(left: &Value, right: &Value) -> bool {
    binding(left) && binding(right)
        && ["project_id", "path", "workspace"].iter().all(|key| left[*key] == right[*key])
}

fn sources(request: &Value) -> bool {
    let (Some(paths), Some(proofs)) = (request["paths"].as_array(), request["completed_sources"].as_array()) else { return false; };
    if paths.is_empty() || paths.len() > MAX_FILES || paths.len() != proofs.len() { return false; }
    let mut seen_paths = HashSet::new();
    let mut seen_occurrences = HashSet::new();
    let mut total = 0u64;
    for (selected, proof) in paths.iter().zip(proofs) {
        if !fields(proof, &["path", "sha256", "size", "stat", "occurrence_id", "completion"], &[])
            || !path(selected) || proof["path"] != *selected || !digest(&proof["sha256"])
            || !token(&proof["occurrence_id"])
            || !seen_paths.insert(selected.as_str().unwrap())
            || !seen_occurrences.insert(proof["occurrence_id"].as_str().unwrap())
            || !matches!(proof["completion"].as_str(), Some("stable_read" | "completed_transfer")) { return false; }
        let Some(size) = proof["size"].as_u64().filter(|size| (1..=MAX_FILE_BYTES).contains(size)) else { return false; };
        let Some(stat) = proof["stat"].as_array().filter(|stat| stat.len() == 5) else { return false; };
        if !stat.iter().all(decimal) || stat[2].as_str().and_then(|part| part.parse::<u64>().ok()) != Some(size) { return false; }
        total += size;
    }
    total <= MAX_SOURCE_BYTES
}

/// Also suitable for native admission: exact Python protocol-1 command schema.
pub(crate) fn valid_request(request: &Value) -> bool {
    if request.to_string().len() > MAX_BYTES || request["cmd"] != "ingest_session" || !uuid(&request["request_id"]) { return false; }
    let base = ["cmd", "action", "request_id"];
    match request["action"].as_str() {
        Some("state") => fields(request, &base, &[]),
        Some("arm") => fields(request, &["cmd", "action", "request_id", "owner", "expected", "max_operations"], &[])
            && matches!(request["owner"].as_str(), Some("workflow" | "tether"))
            && binding(&request["expected"])
            && request["max_operations"].as_u64().is_some_and(|count| (1..=64).contains(&count)),
        Some("import") => fields(request, &["cmd", "action", "request_id", "session_id", "paths", "root", "root_identity", "completed_sources"], &[])
            && uuid(&request["session_id"]) && path(&request["root"])
            && root_identity(&request["root_identity"]) && sources(request),
        Some("query" | "cancel") => fields(request, &["cmd", "action", "request_id", "session_id", "operation_id"], &[])
            && uuid(&request["session_id"]) && uuid(&request["operation_id"]),
        Some("release") => fields(request, &["cmd", "action", "request_id", "session_id"], &[])
            && uuid(&request["session_id"]),
        _ => false,
    }
}

fn session(value: &Value) -> bool {
    if !fields(value, &["session_id", "owner", "phase", "binding", "max_operations", "used_operations",
        "remaining_operations", "operation_id", "stop_reason", "requires_readback", "rotation_supported", "runtime_verified"], &[])
        || !uuid(&value["session_id"]) || !binding(&value["binding"])
        || !matches!(value["owner"].as_str(), Some("workflow" | "tether"))
        || !(value["operation_id"].is_null() || uuid(&value["operation_id"]))
        || !nullable_text(&value["stop_reason"])
        || value["rotation_supported"] != false || value["runtime_verified"] != false { return false; }
    let (Some(maximum), Some(used), Some(remaining)) = (value["max_operations"].as_u64(),
        value["used_operations"].as_u64(), value["remaining_operations"].as_u64()) else { return false; };
    if !(1..=64).contains(&maximum) || used > maximum || remaining != maximum - used { return false; }
    match value["phase"].as_str() {
        Some("unknown") => uuid(&value["operation_id"]) && used > 0 && value["requires_readback"] == true,
        Some("pending") => uuid(&value["operation_id"]) && used > 0 && value["requires_readback"] == false,
        Some("stopped") => value["operation_id"].is_null() && value["requires_readback"] == false && text(&value["stop_reason"]),
        Some("exhausted") => value["operation_id"].is_null() && value["requires_readback"] == false
            && value["stop_reason"].is_null() && used == maximum,
        Some("armed") => value["operation_id"].is_null() && value["requires_readback"] == false
            && value["stop_reason"].is_null() && used < maximum,
        _ => false,
    }
}

fn envelope(request: &Value, value: &Value) -> bool {
    fields(value, &["event", "protocol", "request_id", "action", "status", "session"],
        &["state", "operation", "released_session", "error", "dispatch_rejected"])
        && value.to_string().len() <= MAX_BYTES && value["event"] == "ingest_session_result"
        && value["protocol"].as_u64() == Some(1) && value["request_id"] == request["request_id"]
        && value["action"] == request["action"]
        && matches!(value["status"].as_str(), Some("pending" | "readback" | "succeeded" | "failed" | "unknown"))
        && (value["session"].is_null() || session(&value["session"]))
}

fn event_fields(value: &Value, extra: &[&str]) -> bool {
    fields(value, &["event", "protocol", "request_id", "action", "status", "session"], extra)
        && extra.iter().all(|key| value.get(*key).is_some())
}

fn arm_success(request: &Value, event: &Value) -> bool {
    event_fields(event, &[]) && event["status"] == "succeeded" && session(&event["session"])
        && event["session"]["owner"] == request["owner"]
        && event["session"]["binding"] == request["expected"]
        && event["session"]["max_operations"] == request["max_operations"]
        && event["session"]["used_operations"].as_u64() == Some(0)
        && event["session"]["phase"] == "armed"
}

fn owned_session(request: &Value, value: &Value, context: &ValidationContext<'_>) -> bool {
    let (Some(arm), Some(receipt)) = (context.arm_request, context.arm_receipt) else { return false; };
    valid_request(arm) && arm["action"] == "arm" && envelope(arm, receipt) && arm_success(arm, receipt)
        && session(value) && value["session_id"] == request["session_id"]
        && value["session_id"] == receipt["session"]["session_id"]
        && value["owner"] == arm["owner"] && value["max_operations"] == arm["max_operations"]
        && same_project(&value["binding"], &arm["expected"])
        && (value["used_operations"].as_u64() != Some(0) || value["binding"] == arm["expected"])
}

fn state_readback(event: &Value) -> bool {
    let value = &event["state"];
    event_fields(event, &["state"]) && event["status"] == "readback"
        && fields(value, &["current_binding", "available", "reason", "receipt_capacity", "max_operations", "rotation_supported", "runtime_verified"], &[])
        && (value["current_binding"].is_null() || binding(&value["current_binding"]))
        && value["available"].is_boolean() && nullable_text(&value["reason"])
        && value["receipt_capacity"].as_u64().is_some_and(|count| count <= 256)
        && value["max_operations"].as_u64() == Some(64)
        && value["rotation_supported"] == false && value["runtime_verified"] == false
        && (value["available"] != true || (event["session"].is_null()
            && value["reason"].is_null() && binding(&value["current_binding"])))
}

fn managed_receipt(receipt: &Value, operation_id: &Value, count: usize) -> bool {
    if !fields(receipt, &["event", "request_id", "status"], &["progress", "imported", "mode", "replayed", "reconciled",
        "error", "requires_readback", "verified_copies", "notice"])
        || receipt["event"] != "managed_import_result" || receipt["request_id"] != *operation_id
        || !matches!(receipt["status"].as_str(), Some("pending" | "succeeded" | "failed" | "cancelled" | "unknown")) { return false; }
    for key in ["replayed", "reconciled", "requires_readback"] {
        if receipt.get(key).is_some_and(|value| !value.is_boolean()) { return false; }
    }
    if receipt.get("mode").is_some_and(|value| value != "copy")
        || receipt.get("error").is_some_and(|value| !nullable_text(value))
        || receipt.get("notice").is_some_and(|value| !text(value))
        || receipt.get("verified_copies").is_some_and(|value| !value.as_array().is_some_and(|rows| rows.len() <= count && rows.iter().all(path))) { return false; }
    if let Some(progress) = receipt.get("progress") {
        if !fields(progress, &["phase", "bytes", "total"], &[]) || !token(&progress["phase"])
            || progress["bytes"].as_u64().is_none() || progress["total"].as_u64().is_none() { return false; }
    }
    match receipt["status"].as_str() {
        Some("succeeded") => fields(receipt, &["event", "request_id", "status", "imported"], &["mode", "replayed", "reconciled"])
            && receipt["imported"].as_u64() == Some(count as u64)
            && receipt.get("error").is_none() && receipt.get("progress").is_none()
            && receipt["requires_readback"] != true && receipt.get("verified_copies").is_none()
            && ["replayed", "reconciled"].iter().all(|key| receipt.get(*key).map_or(true, |value| value == true)),
        Some("failed" | "cancelled") => fields(receipt, &["event", "request_id", "status", "error"], &["verified_copies", "notice"])
            && text(&receipt["error"]) && receipt.get("imported").is_none()
            && receipt.get("progress").is_none() && receipt["requires_readback"] != true,
        Some("pending") => fields(receipt, &["event", "request_id", "status", "progress"], &[])
            && receipt.get("progress").is_some() && receipt.get("imported").is_none()
            && receipt.get("error").is_none() && receipt["requires_readback"] != true,
        Some("unknown") => fields(receipt, &["event", "request_id", "status"], &["error", "requires_readback", "verified_copies", "notice"])
            && receipt.get("imported").is_none()
            && receipt.get("requires_readback").map_or(true, |value| value == true),
        _ => false,
    }
}

fn managed_target(request: &Value, operation_id: &str, original: &str) -> String {
    // Python os.path.splitext treats leading dots as part of the basename.
    let name = original.rsplit('/').next().unwrap_or("");
    let extension = name.rfind('.').filter(|index| name[..*index].chars().any(|character| character != '.'))
        .map(|index| name[index..].to_lowercase()).unwrap_or_default();
    let root = request["root"].as_str().unwrap_or("").trim_end_matches('/');
    format!("{root}/{}{extension}", uuid_v5_name(operation_id, original))
}

fn documents(request: &Value, operation: &Value) -> bool {
    let (Some(documents), Some(proofs), Some(operation_id)) = (operation["documents"].as_array(),
        request["completed_sources"].as_array(), operation["operation_id"].as_str()) else { return false; };
    if documents.len() != proofs.len() { return false; }
    let mut seen_documents = HashSet::new();
    let mut seen_sources = HashSet::new();
    let mut seen_paths = HashSet::new();
    for document in documents {
        if !fields(document, &["document_id", "revision", "source_asset_id", "recipe_version_id", "path", "original_path", "filename",
            "source_sha256", "size", "stat", "occurrence_id", "completion", "import_receipt_id"], &[])
            || !token(&document["document_id"]) || !decimal(&document["revision"])
            || document["revision"].as_str().and_then(|revision| revision.parse::<u64>().ok()).is_none()
            || !token(&document["source_asset_id"]) || !token(&document["recipe_version_id"])
            || !path(&document["original_path"]) || !path(&document["path"])
            || !seen_documents.insert(document["document_id"].as_str().unwrap())
            || !seen_sources.insert(document["original_path"].as_str().unwrap())
            || !seen_paths.insert(document["path"].as_str().unwrap()) { return false; }
        let Some(proof) = proofs.iter().find(|proof| proof["path"] == document["original_path"]) else { return false; };
        let original = proof["path"].as_str().unwrap();
        if document["source_sha256"] != proof["sha256"] || document["size"] != proof["size"]
            || document["stat"] != proof["stat"] || document["occurrence_id"] != proof["occurrence_id"]
            || document["completion"] != proof["completion"] || document["import_receipt_id"] != operation["operation_id"]
            || document["filename"].as_str() != original.rsplit('/').next()
            || document["path"].as_str() != Some(managed_target(request, operation_id, original).as_str()) { return false; }
    }
    true
}

fn terminal_operation(operation: &Value) -> bool {
    matches!(operation["status"].as_str(), Some("succeeded" | "failed" | "cancelled"))
}

fn operation(request: &Value, value: &Value) -> bool {
    if !fields(value, &["operation_id", "request_id", "status", "documents", "receipt"], &[])
        || !uuid(&value["operation_id"]) || value["request_id"] != request["request_id"]
        || value["operation_id"].as_str() != Some(uuid_v5_name(request["session_id"].as_str().unwrap_or(""),
            request["request_id"].as_str().unwrap_or("")).as_str()) { return false; }
    let Some(rows) = value["documents"].as_array() else { return false; };
    let count = request["completed_sources"].as_array().map_or(0, |proofs| proofs.len());
    if !value["receipt"].is_null() && !managed_receipt(&value["receipt"], &value["operation_id"], count) { return false; }
    if let Some(copies) = value["receipt"]["verified_copies"].as_array() {
        let expected: HashSet<String> = request["completed_sources"].as_array().unwrap().iter().map(|proof|
            managed_target(request, value["operation_id"].as_str().unwrap(), proof["path"].as_str().unwrap())).collect();
        let mut seen = HashSet::new();
        for copy in copies {
            let Some(copy_path) = copy.as_str() else { return false; };
            if !seen.insert(copy_path) || !expected.contains(copy_path) { return false; }
        }
    }
    match value["status"].as_str() {
        Some("succeeded") => value["receipt"]["status"] == "succeeded" && documents(request, value),
        Some("failed" | "cancelled") => rows.is_empty() && value["receipt"]["status"] == value["status"],
        Some("pending") => rows.is_empty() && value["receipt"]["status"] != "unknown",
        Some("unknown") => rows.is_empty(),
        _ => false,
    }
}

fn pinned_operation(request: &Value, prior: &Value, value: &Value) -> bool {
    let previous = &prior["operation"];
    operation(request, previous) && operation(request, value)
        && previous["operation_id"] == value["operation_id"] && previous["request_id"] == value["request_id"]
        && (!terminal_operation(previous) || previous == value)
        && !(previous["status"] == "unknown" && value["status"] == "pending")
}

fn import_event(request: &Value, prior: Option<&Value>, event: &Value, context: &ValidationContext<'_>) -> bool {
    if !event_fields(event, &["operation"]) || !owned_session(request, &event["session"], context)
        || !operation(request, &event["operation"]) { return false; }
    let current = &event["session"];
    let operation = &event["operation"];
    if current["used_operations"].as_u64().unwrap_or(0) == 0 { return false; }
    let completion = if current["owner"] == "tether" { "completed_transfer" } else { "stable_read" };
    if request["completed_sources"].as_array().unwrap().iter().any(|proof| proof["completion"] != completion) { return false; }
    // Pin the first observed pending identity and enforce it thereafter. If the
    // pending event itself was lost, a fully proven original terminal can still
    // reconcile: the derived ID plus retained request/arm and actual managed
    // receipt/document evidence bind the operation, not the outer status alone.
    if let Some(previous) = prior {
        if !pinned_operation(request, previous, operation) || !session(&previous["session"])
            || current["session_id"] != previous["session"]["session_id"]
            || current["used_operations"] != previous["session"]["used_operations"]
            || current["max_operations"] != previous["session"]["max_operations"]
            || !same_project(&current["binding"], &previous["session"]["binding"])
            || (operation["status"] != "succeeded" && current["binding"] != previous["session"]["binding"]) { return false; }
    }
    match event["status"].as_str() {
        Some("pending") => operation["status"] == "pending" && current["phase"] == "pending"
            && current["operation_id"] == operation["operation_id"],
        Some("unknown") => operation["status"] == "unknown" && current["phase"] == "unknown"
            && current["operation_id"] == operation["operation_id"],
        Some("succeeded") => operation["status"] == "succeeded" && current["operation_id"].is_null()
            && current["requires_readback"] == false,
        Some("failed") => matches!(operation["status"].as_str(), Some("failed" | "cancelled"))
            && current["phase"] == "stopped" && current["operation_id"].is_null(),
        _ => false,
    }
}

fn operation_readback(request: &Value, event: &Value, context: &ValidationContext<'_>) -> bool {
    let Some(original) = context.original_import_request else { return false; };
    if !valid_request(original) || original["action"] != "import" || original["session_id"] != request["session_id"]
        || !event_fields(event, &["operation"]) || event["status"] != "readback"
        || !owned_session(request, &event["session"], context)
        || event["operation"]["operation_id"] != request["operation_id"]
        || !operation(original, &event["operation"])
        || event["session"]["used_operations"].as_u64().unwrap_or(0) == 0 { return false; }
    let completion = if event["session"]["owner"] == "tether" { "completed_transfer" } else { "stable_read" };
    if original["completed_sources"].as_array().unwrap().iter().any(|proof| proof["completion"] != completion) { return false; }
    if let Some(previous) = context.original_import_prior {
        if !envelope(original, previous) || !owned_session(original, &previous["session"], context)
            || !pinned_operation(original, previous, &event["operation"])
            || event["session"]["used_operations"].as_u64() < previous["session"]["used_operations"].as_u64() { return false; }
        if event["operation"]["status"] != "succeeded"
            && event["session"]["used_operations"] == previous["session"]["used_operations"]
            && event["session"]["binding"] != previous["session"]["binding"] { return false; }
    }
    let status = event["operation"]["status"].as_str();
    if matches!(status, Some("pending" | "unknown")) {
        event["session"]["operation_id"] == request["operation_id"]
            && event["session"]["phase"] == event["operation"]["status"]
            && context.original_import_prior.map_or(true, |previous|
                event["session"]["binding"] == previous["session"]["binding"]
                    && event["session"]["used_operations"] == previous["session"]["used_operations"])
    } else {
        // A query for an older completed operation may coexist with a newer
        // current operation. It still cannot rewrite that older operation.
        event["session"]["operation_id"] != request["operation_id"]
    }
}

fn original_owner(request: &Value, context: &ValidationContext<'_>) -> bool {
    let Some(original) = context.original_import_request else { return false; };
    if !valid_request(original) || original["action"] != "import" || original["session_id"] != request["session_id"]
        || request["operation_id"].as_str() != Some(uuid_v5_name(original["session_id"].as_str().unwrap(),
            original["request_id"].as_str().unwrap()).as_str()) { return false; }
    context.original_import_prior.map_or(true, |previous| envelope(original, previous)
        && owned_session(original, &previous["session"], context) && operation(original, &previous["operation"])
        && previous["operation"]["operation_id"] == request["operation_id"])
}

fn terminal(event: &Value) -> bool {
    matches!(event["status"].as_str(), Some("succeeded" | "failed" | "readback"))
}

/// Fail-closed convenience entry point. Session-owned actions need context.
pub(crate) fn accept(request: &Value, prior: Option<&Value>, event: &Value) -> bool {
    accept_with_context(request, prior, event, &ValidationContext::default())
}

pub(crate) fn accept_with_context(request: &Value, prior: Option<&Value>, event: &Value, context: &ValidationContext<'_>) -> bool {
    if !valid_request(request) || !envelope(request, event) { return false; }
    if let Some(previous) = prior {
        if !envelope(request, previous) { return false; }
        // No late error, different successful document set, or fresh state
        // snapshot can rewrite the first terminal receipt under this identity.
        if terminal(previous) { return previous == event; }
        if previous["status"] == "unknown" && event["status"] == "pending" { return false; }
    }
    if event.get("dispatch_rejected").is_some() {
        return prior.is_none() && event_fields(event, &["error", "dispatch_rejected"])
            && event["status"] == "failed" && event["session"].is_null()
            && event["dispatch_rejected"] == true && text(&event["error"]);
    }
    let action = request["action"].as_str().unwrap();
    if event.get("error").is_some() {
        if !event_fields(event, &["error"]) || !text(&event["error"])
            || !matches!(event["status"].as_str(), Some("failed" | "unknown")) { return false; }
        // Errors without operation proof cannot settle or replace an admitted
        // original import. In particular a dispatcher rejection is not rollback.
        if prior.is_some() { return false; }
        if matches!(action, "state" | "arm") { return true; }
        return owned_session(request, &event["session"], context)
            && (!matches!(action, "query" | "cancel") || original_owner(request, context))
            && !(action == "import" && event["session"]["operation_id"].as_str()
                == Some(uuid_v5_name(request["session_id"].as_str().unwrap(), request["request_id"].as_str().unwrap()).as_str()));
    }
    let accepted = match action {
        "state" => state_readback(event),
        "arm" => arm_success(request, event),
        "import" => import_event(request, prior, event, context),
        "query" | "cancel" => operation_readback(request, event, context),
        "release" => event_fields(event, &["released_session"]) && event["status"] == "succeeded"
            && event["session"].is_null() && owned_session(request, &event["released_session"], context)
            && event["released_session"]["operation_id"].is_null()
            && event["released_session"]["requires_readback"] == false,
        _ => false,
    };
    // Unknown is not a general overwrite permission. Only the original managed
    // operation's validated proof can reconcile it; arm/release/state cannot.
    accepted && !(prior.is_some_and(|previous| previous["status"] == "unknown")
        && terminal(event) && !matches!(action, "import" | "query" | "cancel"))
}

/// Derive a protocol UUIDv5 name/address. This does not authorize replay.
pub(crate) fn uuid_v5(namespace: &str, name: &str) -> Result<String, String> {
    if !uuid(&Value::String(namespace.to_owned())) {
        return Err("UUIDv5 namespace must be a canonical UUID".into());
    }
    if name.len() > MAX_BYTES { return Err("UUIDv5 name exceeds ingestion budget".into()); }
    Ok(uuid_v5_name(namespace, name))
}

/// Stable recovery address for an already admitted original import request.
pub(crate) fn operation_id(session_id: &str, request_id: &str) -> Result<String, String> {
    if !uuid(&Value::String(request_id.to_owned())) {
        return Err("Ingestion request identity must be a canonical UUID".into());
    }
    uuid_v5(session_id, request_id)
}

/// UUIDv5 is a protocol name/address, NOT an authentication or content hash.
/// Keeping this private avoids adding a runtime dependency for name derivation.
fn uuid_v5_name(namespace: &str, name: &str) -> String {
    let compact: String = namespace.chars().filter(|character| *character != '-').collect();
    if compact.len() != 32 || !compact.bytes().all(|byte| byte.is_ascii_hexdigit()) { return String::new(); }
    let mut bytes = Vec::with_capacity(16 + name.len() + 72);
    for index in (0..32).step_by(2) {
        let Ok(byte) = u8::from_str_radix(&compact[index..index + 2], 16) else { return String::new(); };
        bytes.push(byte);
    }
    bytes.extend_from_slice(name.as_bytes());
    let bit_length = (bytes.len() as u64) * 8;
    bytes.push(0x80);
    while bytes.len() % 64 != 56 { bytes.push(0); }
    bytes.extend_from_slice(&bit_length.to_be_bytes());
    let mut hash = [0x67452301u32, 0xefcdab89, 0x98badcfe, 0x10325476, 0xc3d2e1f0];
    for chunk in bytes.chunks_exact(64) {
        let mut words = [0u32; 80];
        for (index, word) in chunk.chunks_exact(4).enumerate() {
            words[index] = u32::from_be_bytes([word[0], word[1], word[2], word[3]]);
        }
        for index in 16..80 { words[index] = (words[index - 3] ^ words[index - 8] ^ words[index - 14] ^ words[index - 16]).rotate_left(1); }
        let [mut a, mut b, mut c, mut d, mut e] = hash;
        for (index, word) in words.iter().enumerate() {
            let (function, constant) = match index {
                0..=19 => ((b & c) | ((!b) & d), 0x5a827999u32),
                20..=39 => (b ^ c ^ d, 0x6ed9eba1),
                40..=59 => ((b & c) | (b & d) | (c & d), 0x8f1bbcdc),
                _ => (b ^ c ^ d, 0xca62c1d6),
            };
            let next = a.rotate_left(5).wrapping_add(function).wrapping_add(e).wrapping_add(constant).wrapping_add(*word);
            e = d; d = c; c = b.rotate_left(30); b = a; a = next;
        }
        for (value, addition) in hash.iter_mut().zip([a, b, c, d, e]) { *value = value.wrapping_add(addition); }
    }
    let mut result = [0u8; 16];
    for (index, word) in hash[..4].iter().enumerate() { result[index * 4..index * 4 + 4].copy_from_slice(&word.to_be_bytes()); }
    result[6] = (result[6] & 0x0f) | 0x50;
    result[8] = (result[8] & 0x3f) | 0x80;
    let hex: String = result.iter().map(|byte| format!("{byte:02x}")).collect();
    format!("{}-{}-{}-{}-{}", &hex[..8], &hex[8..12], &hex[12..16], &hex[16..20], &hex[20..])
}

// AUTHORED / UNRUN. These fixtures describe a pure JSON boundary, not an actual
// import, successful build, filesystem check, camera test or product acceptance.
#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    const ARM: &str = "11111111-1111-4111-8111-111111111111";
    const SESSION: &str = "22222222-2222-4222-8222-222222222222";
    const IMPORT: &str = "33333333-3333-4333-8333-333333333333";
    const READ: &str = "44444444-4444-4444-8444-444444444444";
    const OTHER: &str = "55555555-5555-4555-8555-555555555555";

    struct Fixture { arm: Value, armed: Value, request: Value, pending: Value, success: Value }
    impl Fixture {
        fn context(&self) -> ValidationContext<'_> {
            ValidationContext { arm_request: Some(&self.arm), arm_receipt: Some(&self.armed), ..ValidationContext::default() }
        }
        fn query(&self, action: &str) -> Value {
            json!({"cmd":"ingest_session", "action":action, "request_id":READ,
                "session_id":SESSION, "operation_id":self.pending["operation"]["operation_id"]})
        }
        fn readback(&self, command: &Value, original: &Value) -> Value {
            json!({"event":"ingest_session_result", "protocol":1, "action":command["action"],
                "request_id":command["request_id"], "status":"readback", "session":original["session"],
                "operation":original["operation"]})
        }
        fn unknown(&self) -> Value {
            let mut value = self.pending.clone();
            value["status"] = json!("unknown");
            value["session"]["phase"] = json!("unknown");
            value["session"]["requires_readback"] = json!(true);
            value["operation"]["status"] = json!("unknown");
            value["operation"]["receipt"] = json!({"event":"managed_import_result", "request_id":self.pending["operation"]["operation_id"],
                "status":"unknown", "error":"post-replace publication not yet reconciled", "requires_readback":true});
            value
        }
        fn failure(&self, cancelled: bool) -> Value {
            let status = if cancelled { "cancelled" } else { "failed" };
            let mut value = self.pending.clone();
            value["status"] = json!("failed");
            value["session"]["phase"] = json!("stopped");
            value["session"]["operation_id"] = Value::Null;
            value["session"]["stop_reason"] = json!("Original import stopped; inspect retained copies");
            value["operation"]["status"] = json!(status);
            value["operation"]["receipt"] = json!({"event":"managed_import_result", "request_id":self.pending["operation"]["operation_id"],
                "status":status, "error":"Original managed operation did not register documents", "verified_copies":[]});
            value
        }
    }

    fn fixture() -> Fixture {
        let binding = json!({"project_id":"project-original", "path":"/project/current.lrt", "workspace":"workspace-original", "disk_sha256":"a".repeat(64)});
        let arm = json!({"cmd":"ingest_session", "action":"arm", "request_id":ARM,
            "owner":"workflow", "max_operations":2, "expected":binding});
        let armed = json!({"event":"ingest_session_result", "protocol":1, "action":"arm", "request_id":ARM, "status":"succeeded",
            "session":{"session_id":SESSION, "owner":"workflow", "phase":"armed", "binding":binding, "max_operations":2,
                "used_operations":0, "remaining_operations":2, "operation_id":null, "stop_reason":null,
                "requires_readback":false, "rotation_supported":false, "runtime_verified":false}});
        let proofs = json!([
            {"path":"/incoming/first.CR3", "sha256":"c".repeat(64), "size":7,
                "stat":["12", "9007199254740993", "7", "1800000000000000001", "1800000000000000002"],
                "occurrence_id":"capture-first", "completion":"stable_read"},
            {"path":"/incoming/second.CR3", "sha256":"c".repeat(64), "size":7,
                "stat":["12", "9007199254740995", "7", "1800000000000000003", "1800000000000000004"],
                "occurrence_id":"capture-second", "completion":"stable_read"}
        ]);
        let request = json!({"cmd":"ingest_session", "action":"import", "request_id":IMPORT,
            "session_id":SESSION, "root":"/managed", "root_identity":["12", "9007199254740997"],
            "paths":["/incoming/first.CR3", "/incoming/second.CR3"], "completed_sources":proofs});
        let operation_id = uuid_v5_name(SESSION, IMPORT);
        let mut pending_session = armed["session"].clone();
        pending_session["phase"] = json!("pending"); pending_session["used_operations"] = json!(1);
        pending_session["remaining_operations"] = json!(1); pending_session["operation_id"] = json!(operation_id);
        let pending = json!({"event":"ingest_session_result", "protocol":1, "action":"import", "request_id":IMPORT, "status":"pending",
            "session":pending_session, "operation":{"operation_id":operation_id, "request_id":IMPORT, "status":"pending", "documents":[], "receipt":null}});
        let documents: Vec<Value> = proofs.as_array().unwrap().iter().enumerate().map(|(index, proof)| {
            let original = proof["path"].as_str().unwrap();
            json!({"document_id":format!("document-{index}"), "revision":"0", "source_asset_id":format!("source-{index}"),
                "recipe_version_id":format!("recipe-{index}"), "path":managed_target(&request, &operation_id, original),
                "original_path":original, "filename":original.rsplit('/').next().unwrap(), "source_sha256":proof["sha256"],
                "size":proof["size"], "stat":proof["stat"], "occurrence_id":proof["occurrence_id"],
                "completion":proof["completion"], "import_receipt_id":operation_id})
        }).collect();
        let mut success = pending.clone();
        success["status"] = json!("succeeded"); success["session"]["phase"] = json!("armed");
        success["session"]["operation_id"] = Value::Null; success["session"]["binding"]["disk_sha256"] = json!("b".repeat(64));
        success["operation"]["status"] = json!("succeeded"); success["operation"]["documents"] = json!(documents);
        success["operation"]["receipt"] = json!({"event":"managed_import_result", "request_id":operation_id, "status":"succeeded", "imported":2, "mode":"copy"});
        Fixture { arm, armed, request, pending, success }
    }

    #[test]
    fn uuid_name_address_matches_rfc_vector_and_python_target_rules() {
        assert_eq!(uuid_v5_name("6ba7b810-9dad-11d1-80b4-00c04fd430c8", "www.widgets.com"), "21f7f8de-8051-5b89-8680-0195ef798b6a");
        assert_eq!(operation_id(SESSION, IMPORT).unwrap(), uuid_v5(SESSION, IMPORT).unwrap());
        assert!(operation_id(SESSION, "not-a-request-uuid").is_err());
        assert!(uuid_v5("not-a-namespace-uuid", "/incoming/first.CR3").is_err());
        let request = json!({"root":"/"});
        assert_eq!(managed_target(&request, SESSION, "/incoming/a.CR3"), format!("/{}.cr3", uuid_v5_name(SESSION, "/incoming/a.CR3")));
        assert_eq!(managed_target(&request, SESSION, "/incoming/.hidden"), format!("/{}", uuid_v5_name(SESSION, "/incoming/.hidden")));
    }

    #[test]
    fn strict_command_schema_preserves_exact_stat_and_occurrences() {
        let fixture = fixture();
        assert!(valid_request(&fixture.request));
        for (pointer, replacement) in [
            ("/request_id", json!("not-a-canonical-uuid")), ("/completed_sources/0/stat/1", json!(9007199254740993u64)),
            ("/completed_sources/0/stat/2", json!("8")), ("/completed_sources/0/size", json!(7.0)),
            ("/completed_sources/1/occurrence_id", json!("capture-first")), ("/completed_sources/0/completion", json!("camera-certified")),
            ("/root", json!("/managed/../elsewhere")), ("/completed_sources/0/sha256", json!("C".repeat(64))),
        ] {
            let mut changed = fixture.request.clone(); *changed.pointer_mut(pointer).unwrap() = replacement;
            assert!(!valid_request(&changed), "{pointer}");
        }
        let mut changed = fixture.request.clone(); changed["trusted_precommit"] = json!(true);
        assert!(!valid_request(&changed));
    }

    #[test]
    fn import_requires_original_root_device_and_inode_as_exact_u64_strings() {
        let fixture = fixture();
        assert!(valid_request(&fixture.request));
        let mut missing = fixture.request.clone(); missing.as_object_mut().unwrap().remove("root_identity");
        assert!(!valid_request(&missing));
        assert!(!accept_with_context(&missing, None, &fixture.success, &fixture.context()));
        for invalid in [Value::Null, json!([]), json!(["12"]), json!(["12", "34", "56"]),
            json!([12, "34"]), json!(["12", 34.0]), json!(["-1", "34"]), json!(["+1", "34"]),
            json!(["01", "34"]), json!(["12", "00"]), json!(["12", " 34"]), json!(["12", "34 "]),
            json!(["12", "18446744073709551616"]), json!(["18446744073709551616", "34"]),
            json!({"dev":"12", "ino":"34"})] {
            let mut changed = fixture.request.clone(); changed["root_identity"] = invalid;
            assert!(!valid_request(&changed), "{}", changed["root_identity"]);
            assert!(!accept_with_context(&changed, None, &fixture.success, &fixture.context()));
        }
        let mut boundary = fixture.request.clone(); boundary["root_identity"] = json!(["0", "18446744073709551615"]);
        assert!(valid_request(&boundary));
        // Receipt schemas deliberately do not invent a root identity echo. The
        // engine checks the retained request's pin against its actual root FD.
        assert!(fixture.success.get("root_identity").is_none());
        assert!(accept_with_context(&fixture.request, None, &fixture.success, &fixture.context()));
    }

    #[test]
    fn arm_requires_exact_expected_binding_and_immutable_first_terminal() {
        let fixture = fixture();
        assert!(accept(&fixture.arm, None, &fixture.armed));
        assert!(accept(&fixture.arm, Some(&fixture.armed), &fixture.armed));
        for pointer in ["/session/binding/project_id", "/session/binding/path", "/session/binding/workspace", "/session/binding/disk_sha256", "/session/owner"] {
            let mut changed = fixture.armed.clone(); *changed.pointer_mut(pointer).unwrap() = json!("different");
            assert!(!accept(&fixture.arm, None, &changed));
            assert!(!accept(&fixture.arm, Some(&fixture.armed), &changed));
        }
    }

    #[test]
    fn owned_import_pins_pending_and_accepts_only_exact_original_success() {
        let fixture = fixture(); let context = fixture.context();
        assert!(!accept(&fixture.request, None, &fixture.pending));
        assert!(accept_with_context(&fixture.request, None, &fixture.pending, &context));
        assert!(accept_with_context(&fixture.request, None, &fixture.success, &context));
        assert!(accept_with_context(&fixture.request, Some(&fixture.pending), &fixture.success, &context));
        let mut reversed = fixture.success.clone(); reversed["operation"]["documents"].as_array_mut().unwrap().reverse();
        assert!(accept_with_context(&fixture.request, Some(&fixture.pending), &reversed, &context));
        // Equal bytes still represent two distinct selected source occurrences.
        assert_eq!(fixture.success["operation"]["documents"].as_array().unwrap().len(), 2);
    }

    #[test]
    fn identity_or_document_substitution_never_settles_original_import() {
        let fixture = fixture(); let context = fixture.context();
        for (pointer, replacement) in [
            ("/protocol", json!(2)), ("/action", json!("query")), ("/request_id", json!(OTHER)),
            ("/session/session_id", json!(OTHER)), ("/session/binding/project_id", json!("different-project")),
            ("/session/binding/path", json!("/different.lrt")), ("/session/binding/workspace", json!("different-workspace")),
            ("/operation/request_id", json!(OTHER)), ("/operation/operation_id", json!(OTHER)),
            ("/operation/receipt/request_id", json!(OTHER)), ("/operation/receipt/imported", json!(1)),
            ("/operation/documents/0/source_sha256", json!("d".repeat(64))), ("/operation/documents/0/size", json!(8)),
            ("/operation/documents/0/stat/1", json!("9007199254740992")), ("/operation/documents/0/occurrence_id", json!("different-occurrence")),
            ("/operation/documents/0/completion", json!("completed_transfer")), ("/operation/documents/0/import_receipt_id", json!(OTHER)),
            ("/operation/documents/0/filename", json!("renamed.CR3")), ("/operation/documents/0/original_path", json!("/incoming/unselected.CR3")),
            ("/operation/documents/0/path", json!(format!("/managed/{OTHER}.cr3"))),
            ("/operation/documents/0/revision", json!("18446744073709551616")),
            ("/operation/documents/1/document_id", json!("document-0")),
        ] {
            let mut changed = fixture.success.clone(); *changed.pointer_mut(pointer).unwrap() = replacement;
            assert!(!accept_with_context(&fixture.request, Some(&fixture.pending), &changed, &context), "{pointer}");
        }
        let mut changed = fixture.success.clone(); changed["operation"]["documents"].as_array_mut().unwrap().pop();
        assert!(!accept_with_context(&fixture.request, Some(&fixture.pending), &changed, &context));
        let mut changed = fixture.pending.clone(); changed["session"]["operation_id"] = json!(OTHER); changed["operation"]["operation_id"] = json!(OTHER);
        assert!(!accept_with_context(&fixture.request, None, &changed, &context));
    }

    #[test]
    fn terminal_success_failure_and_readback_are_exact_repeat_only() {
        let fixture = fixture(); let context = fixture.context();
        let failure = fixture.failure(false);
        for terminal in [&fixture.success, &failure] {
            assert!(accept_with_context(&fixture.request, Some(terminal), terminal, &context));
            assert!(!accept_with_context(&fixture.request, Some(terminal), &fixture.pending, &context));
            let mut changed = terminal.clone(); changed["session"]["binding"]["disk_sha256"] = json!("e".repeat(64));
            assert!(!accept_with_context(&fixture.request, Some(terminal), &changed, &context));
        }
        assert!(!accept_with_context(&fixture.request, Some(&fixture.success), &failure, &context));
        assert!(!accept_with_context(&fixture.request, Some(&failure), &fixture.success, &context));
        let query = fixture.query("query"); let readback = fixture.readback(&query, &fixture.pending);
        let changed = fixture.readback(&query, &fixture.success);
        assert!(accept_with_context(&query, Some(&readback), &readback, &context));
        assert!(!accept_with_context(&query, Some(&readback), &changed, &context));
    }

    #[test]
    fn unknown_reconciles_only_with_exact_original_managed_terminal_proof() {
        let fixture = fixture(); let context = fixture.context(); let unknown = fixture.unknown();
        assert!(accept_with_context(&fixture.request, Some(&fixture.pending), &unknown, &context));
        assert!(!accept_with_context(&fixture.request, Some(&unknown), &fixture.pending, &context));
        assert!(accept_with_context(&fixture.request, Some(&unknown), &fixture.success, &context));
        assert!(accept_with_context(&fixture.request, Some(&unknown), &fixture.failure(false), &context));
        assert!(accept_with_context(&fixture.request, Some(&unknown), &fixture.failure(true), &context));
        let mut arbitrary = fixture.success.clone(); arbitrary["operation"]["receipt"] = Value::Null;
        assert!(!accept_with_context(&fixture.request, Some(&unknown), &arbitrary, &context));
        let mut arbitrary = fixture.success.clone(); arbitrary["operation"]["receipt"]["requires_readback"] = json!(true);
        assert!(!accept_with_context(&fixture.request, Some(&unknown), &arbitrary, &context));
        let mut no_proof = fixture.failure(false); no_proof.as_object_mut().unwrap().remove("operation"); no_proof["error"] = json!("Generic late error is not rollback");
        assert!(!accept_with_context(&fixture.request, Some(&unknown), &no_proof, &context));
    }

    #[test]
    fn pending_may_advance_but_cannot_change_project_digest_before_success() {
        let fixture = fixture(); let context = fixture.context();
        let mut progress = fixture.pending.clone();
        progress["operation"]["receipt"] = json!({"event":"managed_import_result", "request_id":fixture.pending["operation"]["operation_id"],
            "status":"pending", "progress":{"phase":"copying", "bytes":7, "total":14}});
        assert!(accept_with_context(&fixture.request, Some(&fixture.pending), &progress, &context));
        progress["session"]["binding"]["disk_sha256"] = json!("b".repeat(64));
        assert!(!accept_with_context(&fixture.request, Some(&fixture.pending), &progress, &context));
    }

    #[test]
    fn query_and_cancel_need_retained_original_import_and_never_replace_it() {
        let fixture = fixture(); let mut context = fixture.context();
        for action in ["query", "cancel"] {
            let request = fixture.query(action); let readback = fixture.readback(&request, &fixture.success);
            assert!(!accept_with_context(&request, None, &readback, &context));
            context.original_import_request = Some(&fixture.request);
            context.original_import_prior = Some(&fixture.pending);
            assert!(accept_with_context(&request, None, &readback, &context));
            assert!(!accept_with_context(&fixture.request, Some(&fixture.pending), &readback, &context));
            let mut changed = readback.clone(); changed["operation"]["request_id"] = json!(OTHER);
            assert!(!accept_with_context(&request, None, &changed, &context));
            let mut changed_request = request.clone(); changed_request["operation_id"] = json!(OTHER);
            assert!(!accept_with_context(&changed_request, None, &readback, &context));
            context.original_import_request = None; context.original_import_prior = None;
        }
    }

    #[test]
    fn lost_pending_recovers_from_full_proof_but_contradictory_pending_does_not() {
        let fixture = fixture(); let mut context = fixture.context();
        let query = fixture.query("query"); let readback = fixture.readback(&query, &fixture.success);
        context.original_import_request = Some(&fixture.request);
        assert!(accept_with_context(&query, None, &readback, &context));
        assert!(accept_with_context(&fixture.request, None, &fixture.success, &context));
        let mut substituted = readback.clone(); substituted["operation"]["documents"][0]["occurrence_id"] = json!("not-original");
        assert!(!accept_with_context(&query, None, &substituted, &context));
        let mut contradictory = fixture.pending.clone();
        contradictory["operation"]["operation_id"] = json!(OTHER); contradictory["session"]["operation_id"] = json!(OTHER);
        context.original_import_prior = Some(&contradictory);
        assert!(!accept_with_context(&query, None, &readback, &context));
        assert!(!accept_with_context(&fixture.request, Some(&contradictory), &fixture.success, &context));
        let mut status_only = fixture.success.clone(); status_only.as_object_mut().unwrap().remove("operation");
        assert!(!accept_with_context(&fixture.request, None, &status_only, &context));
    }

    #[test]
    fn session_owner_completion_and_first_pending_binding_are_checked() {
        let fixture = fixture(); let context = fixture.context();
        let mut changed = fixture.pending.clone(); changed["session"]["owner"] = json!("tether");
        assert!(!accept_with_context(&fixture.request, None, &changed, &context));
        let mut request = fixture.request.clone();
        for proof in request["completed_sources"].as_array_mut().unwrap() { proof["completion"] = json!("completed_transfer"); }
        assert!(!accept_with_context(&request, None, &fixture.pending, &context));
        let mut changed = fixture.pending.clone(); changed["session"]["binding"]["workspace"] = json!("another");
        assert!(!accept_with_context(&fixture.request, None, &changed, &context));
    }

    #[test]
    fn release_is_owned_idle_and_cannot_clear_prior_unknown() {
        let fixture = fixture(); let context = fixture.context();
        let request = json!({"cmd":"ingest_session", "action":"release", "request_id":READ, "session_id":SESSION});
        let released = json!({"event":"ingest_session_result", "protocol":1, "action":"release", "request_id":READ,
            "status":"succeeded", "session":null, "released_session":fixture.success["session"]});
        assert!(!accept(&request, None, &released));
        assert!(accept_with_context(&request, None, &released, &context));
        let mut pending = released.clone(); pending["released_session"] = fixture.pending["session"].clone();
        assert!(!accept_with_context(&request, None, &pending, &context));
        let unknown = json!({"event":"ingest_session_result", "protocol":1, "action":"release", "request_id":READ,
            "status":"unknown", "session":fixture.unknown()["session"], "error":"Original operation still unknown"});
        assert!(accept_with_context(&request, None, &unknown, &context));
        assert!(!accept_with_context(&request, Some(&unknown), &released, &context));
    }

    #[test]
    fn correlated_dispatch_rejection_is_first_receipt_only_not_rollback() {
        let fixture = fixture(); let context = fixture.context();
        let rejected = json!({"event":"ingest_session_result", "protocol":1, "action":"import", "request_id":IMPORT,
            "status":"failed", "session":null, "error":"Rejected by guard before handler dispatch", "dispatch_rejected":true});
        assert!(accept_with_context(&fixture.request, None, &rejected, &context));
        assert!(accept_with_context(&fixture.request, Some(&rejected), &rejected, &context));
        for previous in [&fixture.pending, &fixture.unknown(), &fixture.success] {
            assert!(!accept_with_context(&fixture.request, Some(previous), &rejected, &context));
        }
        let mut changed = rejected.clone(); changed["dispatch_rejected"] = json!(false);
        assert!(!accept_with_context(&fixture.request, None, &changed, &context));
        let mut changed = rejected; changed["operation"] = fixture.success["operation"].clone();
        assert!(!accept_with_context(&fixture.request, None, &changed, &context));
    }

    #[test]
    fn readback_schema_and_terminal_snapshot_are_not_generic_success() {
        let fixture = fixture();
        let request = json!({"cmd":"ingest_session", "action":"state", "request_id":READ});
        let readback = json!({"event":"ingest_session_result", "protocol":1, "action":"state", "request_id":READ, "status":"readback", "session":null,
            "state":{"current_binding":fixture.arm["expected"], "available":true, "reason":null, "receipt_capacity":250,
                "max_operations":64, "rotation_supported":false, "runtime_verified":false}});
        assert!(accept(&request, None, &readback));
        let mut changed = readback.clone(); changed["session"] = fixture.pending["session"].clone();
        assert!(!accept(&request, None, &changed));
        let mut changed = readback.clone(); changed["state"]["receipt_capacity"] = json!(249);
        assert!(!accept(&request, Some(&readback), &changed));
        let mut changed = readback; changed["status"] = json!("succeeded");
        assert!(!accept(&request, None, &changed));
    }
}
