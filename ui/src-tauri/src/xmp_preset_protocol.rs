//! Public XMP report boundary. XML parsing and original byte storage stay in the
//! engine. This host does not parse XML or claim Adobe rendering compatibility.
use serde_json::Value;

const MAX_SOURCE_BYTES: u64 = 1024 * 1024;
const MAX_REPORT_BYTES: usize = 4 * 1024 * 1024;
const MAX_PREVIEW_BYTES: usize = 1024 * 1024;
const MODE: &str = "native-parameter-adaptation-v1";
fn fields(value: &Value, names: &[&str]) -> bool {
    value.as_object().is_some_and(|map| map.len() == names.len() && names.iter().all(|name| map.contains_key(*name)))
}
fn text(value: &Value, max: usize) -> bool { value.as_str().is_some_and(|s| s.chars().count() <= max) }
fn nonempty(value: &Value, max: usize) -> bool { text(value, max) && value.as_str().is_some_and(|s| !s.is_empty()) }
fn hash(value: &Value) -> bool {
    value.as_str().is_some_and(|s| s.len() == 64 && s.bytes().all(|b| b.is_ascii_digit() || (b'a'..=b'f').contains(&b)))
}
fn module(id: &str) -> Option<&'static str> {
    match id { "exposure" => Some("lnx.exposure.v1"), "point_curves" => Some("lnx.curves.v1"), _ => None }
}
fn selected(value: &Value) -> bool {
    value.as_array().is_some_and(|a| !a.is_empty() && a.len() <= 2
        && a.iter().all(|v| v.as_str().and_then(module).is_some())
        && a.iter().filter_map(Value::as_str).collect::<std::collections::BTreeSet<_>>().len() == a.len())
}
fn bounded_json(value: &Value, depth: usize) -> bool {
    if depth > 32 { return false; }
    match value {
        Value::Null | Value::Bool(_) => true,
        Value::Number(n) => n.as_f64().is_some_and(f64::is_finite),
        Value::String(s) => s.chars().count() <= 65536,
        Value::Array(a) => a.len() <= 4096 && a.iter().all(|v| bounded_json(v, depth + 1)),
        Value::Object(m) => m.len() <= 4096 && m.iter().all(|(k, v)| k.chars().count() <= 1026 && bounded_json(v, depth + 1)),
    }
}
pub(crate) fn report(value: &Value) -> bool {
    if !fields(value, &["version", "source_sha256", "report_sha256", "filename", "byte_length", "process_version",
        "camera_raw_version", "properties", "adaptations", "warnings", "can_import"])
        || value["version"] != 1 || !hash(&value["source_sha256"]) || !hash(&value["report_sha256"])
        || !nonempty(&value["filename"], 255) || value["filename"].as_str().is_some_and(|s| s.contains(['/', '\\', '\0']))
        || !value["byte_length"].as_u64().is_some_and(|n| (1..=MAX_SOURCE_BYTES).contains(&n))
        || !value["can_import"].is_boolean() || value.to_string().len() > MAX_REPORT_BYTES
        || !["process_version", "camera_raw_version"].iter().all(|key| value[*key].is_null() || text(&value[*key], 65536)) { return false; }
    let (Some(properties), Some(adaptations), Some(warnings)) = (value["properties"].as_array(), value["adaptations"].as_array(), value["warnings"].as_array()) else { return false; };
    if properties.len() > 512 || adaptations.len() > 2 || warnings.len() > 256 || !warnings.iter().all(|v| text(v, 1048576))
        || !properties.iter().all(|p| fields(p, &["name", "status", "value", "reason"]) && nonempty(&p["name"], 1026)
            && matches!(p["status"].as_str(), Some("adaptable" | "unsupported" | "metadata" | "invalid"))
            && text(&p["reason"], 131072) && bounded_json(&p["value"], 0)) { return false; }
    let mut seen = std::collections::BTreeSet::new();
    for adaptation in adaptations {
        let Some(id) = adaptation["id"].as_str() else { return false; };
        if !fields(adaptation, &["id", "title", "module", "reason"]) || module(id).is_none()
            || module(id) != adaptation["module"].as_str() || !seen.insert(id)
            || !nonempty(&adaptation["title"], 512) || !text(&adaptation["reason"], 131072) { return false; }
    }
    value["can_import"] != true || (value["process_version"] == "11.0" && !adaptations.is_empty())
}
pub(crate) fn import_ack(value: &Value) -> bool {
    fields(value, &["source_sha256", "report_sha256", "mode", "selected"]) && value["mode"] == MODE
        && hash(&value["source_sha256"]) && hash(&value["report_sha256"]) && selected(&value["selected"])
}
pub(crate) fn review_ack(value: &Value) -> bool {
    fields(value, &["source_sha256", "report_sha256", "before_sha256", "after_sha256"])
        && ["source_sha256", "report_sha256", "before_sha256", "after_sha256"].iter().all(|k| hash(&value[*k]))
}
fn point_curve(value: &Value) -> bool {
    let Some(points) = value.as_array() else { return false; };
    if !(2..=64).contains(&points.len()) { return false; }
    let mut previous = -1.;
    for point in points {
        let Some(pair) = point.as_array() else { return false; };
        if pair.len() != 2 || !pair.iter().all(|n| n.as_f64().is_some_and(|n| n.is_finite() && (0.0..=1.0).contains(&n))) { return false; }
        let Some(x) = pair[0].as_f64() else { return false; };
        if x <= previous { return false; } previous = x;
    }
    points[0][0].as_f64() == Some(0.) && points[points.len() - 1][0].as_f64() == Some(1.)
}
pub(crate) fn adapted_modules(value: &Value, report_value: &Value) -> bool {
    if !report(report_value) || report_value["can_import"] != true { return false; }
    let (Some(map), Some(adaptations)) = (value.as_object(), report_value["adaptations"].as_array()) else { return false; };
    if map.is_empty() || map.len() > 2 { return false; }
    map.iter().all(|(op, params)| {
        if !adaptations.iter().any(|a| a["module"].as_str() == Some(op.as_str())) { return false; }
        match op.as_str() {
            "lnx.exposure.v1" => fields(params, &["ev"]) && params["ev"].as_f64().is_some_and(|n| n.is_finite() && (-5.0..=5.0).contains(&n)),
            "lnx.curves.v1" => {
                let recipe = &params["recipe"];
                fields(params, &["recipe"]) && fields(recipe, &["version", "space", "interpolation", "boundary", "enabled", "master", "red", "green", "blue"])
                    && recipe["version"] == 1 && recipe["space"] == "srgb-display" && recipe["interpolation"] == "pchip"
                    && recipe["boundary"] == "linear" && recipe["enabled"] == true
                    && ["master", "red", "green", "blue"].iter().all(|key| point_curve(&recipe[*key]))
            },
            _ => false,
        }
    })
}
pub(crate) fn summary(value: &Value, modules: &Value) -> bool {
    if !fields(value, &["version", "source_sha256", "filename", "selected", "report", "read_only_summary"])
        || value["version"] != 1 || value["read_only_summary"] != true || !report(&value["report"])
        || value["report"]["can_import"] != true || value["source_sha256"] != value["report"]["source_sha256"]
        || value["filename"] != value["report"]["filename"] || !selected(&value["selected"]) { return false; }
    let (Some(choices), Some(map), Some(adaptations)) = (value["selected"].as_array(), modules.as_object(), value["report"]["adaptations"].as_array()) else { return false; };
    adapted_modules(modules, &value["report"]) && choices.len() == map.len() && choices.iter().all(|choice| {
        choice.as_str().and_then(module).is_some_and(|op| map.get(op).is_some_and(Value::is_object))
            && adaptations.iter().any(|a| a["id"] == *choice)
    })
}
fn size(value: &Value) -> Option<(u64, u64)> {
    let a = value.as_array()?;
    if a.len() != 2 { return None; }
    let (w, h) = (a[0].as_u64()?, a[1].as_u64()?);
    (w > 0 && h > 0 && w <= 9007199254740991 && h <= 9007199254740991).then_some((w, h))
}
fn source_proof(value: &Value, dimensions: (u64, u64)) -> bool {
    if !fields(value, &["asset_sha256", "original_sha256", "creative_source"])
        || !hash(&value["asset_sha256"]) || !hash(&value["original_sha256"]) { return false; }
    let creative = &value["creative_source"];
    if creative.is_null() { return value["asset_sha256"] == value["original_sha256"]; }
    fields(creative, &["sha256", "width", "height"]) && creative["sha256"] == value["asset_sha256"]
        && creative["width"].as_u64() == Some(dimensions.0) && creative["height"].as_u64() == Some(dimensions.1)
}
/// Bounded standard base64 only, with canonical padding. The browser separately
/// decodes both images, verifies SHA-256 and natural dimensions before review.
fn png_header(encoded: &str) -> Option<(usize, [u8; 24])> {
    if encoded.is_empty() || encoded.len() > 1398104 || encoded.len() % 4 != 0 { return None; }
    let mut length = 0usize; let mut header = [0u8; 24];
    fn digit(byte: u8) -> Option<u8> { match byte {
        b'A'..=b'Z' => Some(byte - b'A'), b'a'..=b'z' => Some(byte - b'a' + 26),
        b'0'..=b'9' => Some(byte - b'0' + 52), b'+' => Some(62), b'/' => Some(63), _ => None,
    } }
    for (index, chunk) in encoded.as_bytes().chunks_exact(4).enumerate() {
        let last = (index + 1) * 4 == encoded.len();
        let (a, b) = (digit(chunk[0])?, digit(chunk[1])?);
        let (c, d, count) = if chunk[2] == b'=' { if !last || chunk[3] != b'=' || b & 15 != 0 { return None; } (0, 0, 1) }
            else if chunk[3] == b'=' { let c = digit(chunk[2])?; if !last || c & 3 != 0 { return None; } (c, 0, 2) }
            else { (digit(chunk[2])?, digit(chunk[3])?, 3) };
        for byte in [a << 2 | b >> 4, b << 4 | c >> 2, c << 6 | d].into_iter().take(count) {
            if length < header.len() { header[length] = byte; } length += 1;
        }
        if length > MAX_PREVIEW_BYTES { return None; }
    }
    if length < 33 || header[..8] != [137, 80, 78, 71, 13, 10, 26, 10]
        || header[8..12] != [0, 0, 0, 13] || header[12..16] != *b"IHDR" { return None; }
    Some((length, header))
}
fn preview(value: &Value, output: (u64, u64)) -> bool {
    if !fields(value, &["mime", "width", "height", "sha256", "base64"]) || value["mime"] != "image/png" || !hash(&value["sha256"]) { return false; }
    let (Some(width), Some(height), Some(encoded)) = (value["width"].as_u64(), value["height"].as_u64(), value["base64"].as_str()) else { return false; };
    if !(1..=640).contains(&width) || !(1..=640).contains(&height) || width > output.0 || height > output.1
        || (width as u128 * output.1 as u128).abs_diff(height as u128 * output.0 as u128) > output.0.max(output.1) as u128 { return false; }
    let Some((_, header)) = png_header(encoded) else { return false; };
    u32::from_be_bytes([header[16], header[17], header[18], header[19]]) as u64 == width
        && u32::from_be_bytes([header[20], header[21], header[22], header[23]]) as u64 == height
}
pub(crate) fn transfer(value: &Value, document: &Value, revision: &Value, report_value: &Value) -> bool {
    if !fields(value, &["version", "document_id", "revision", "xmp_sha256", "source_proof", "before_sha256", "candidate_sha256",
        "before_people_sha256", "candidate_people_sha256", "source_size", "before_output_size", "after_output_size", "before", "after"])
        || value["version"] != 1 || &value["document_id"] != document || !nonempty(document, 128)
        || &value["revision"] != revision || !revision.as_str().is_some_and(|s| !s.is_empty() && s.len() <= 20 && s.bytes().all(|b| b.is_ascii_digit()) && s.parse::<u64>().is_ok())
        || !report(report_value) || !hash(&value["xmp_sha256"]) || value["xmp_sha256"] != report_value["source_sha256"]
        || !["before_sha256", "candidate_sha256", "before_people_sha256", "candidate_people_sha256"].iter().all(|k| hash(&value[*k])) { return false; }
    let (Some(source), Some(before), Some(after)) = (size(&value["source_size"]), size(&value["before_output_size"]), size(&value["after_output_size"])) else { return false; };
    source_proof(&value["source_proof"], source) && preview(&value["before"], before) && preview(&value["after"], after)
}
pub(crate) fn command(value: &Value) -> Result<(), String> {
    let action = value["action"].as_str().unwrap_or("");
    if action == "xmp_inspect" && (!nonempty(&value["path"], 32768) || !nonempty(&value["request_id"], 128) || !value["document_id"].is_null()) {
        return Err("XMP inspection needs a correlated request and file path, not a loaded photo".into());
    }
    if let Some(ack) = value.get("xmp_ack") {
        if action != "import" || !import_ack(ack) || !nonempty(&value["path"], 32768) || !nonempty(&value["request_id"], 128) || value["force"] == true {
            return Err("invalid explicit XMP compatibility acknowledgment".into());
        }
    }
    if action == "import" && value["path"].as_str().is_some_and(|s| s.to_ascii_lowercase().ends_with(".xmp")) && value.get("xmp_ack").is_none() {
        return Err("inspect XMP and explicitly choose native adaptations before import".into());
    }
    if let Some(ack) = value.get("xmp_review_ack") {
        if action != "apply" || !review_ack(ack) || !nonempty(&value["document_id"], 128) || !nonempty(&value["request_id"], 128)
            || !value["preflight_token"].as_str().is_some_and(|s| s.len() == 32 && s.bytes().all(|b| b.is_ascii_digit() || (b'a'..=b'f').contains(&b))) {
            return Err("XMP application needs the exact frozen photo review and PNG hashes".into());
        }
    }
    Ok(())
}

#[cfg(test)]
#[path = "xmp_preset_protocol_tests.rs"]
mod tests;
