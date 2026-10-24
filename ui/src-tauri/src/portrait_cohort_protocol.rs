//! Persistent portrait cohort review transport. AUTHORED / UNRUN.
//! The existing association controller owns intent, atomic publication and history.
//! Cohort/generation digests are opaque Python commitments, never Rust JSON hashes.
use serde_json::{json, Value};
use crate::batch_api::{collarbone, face_style};
use crate::original_shadow_transfer_protocol::{hex, revision, source_proof};

pub(crate) const ACK: &str = "portrait_cohort_ack";
pub(crate) const MAX_MEMBERS: usize = 16;
const FOREIGN: &[&str] = &["face_style_review_ack", "torso_review_ack", "waist_review_ack",
    "head_review_ack", "spill_review_ack", "shadow_review_ack", "local_mask_transfer", "reference_color"];
fn fields(v: &Value, names: &[&str]) -> bool {
    v.as_object().is_some_and(|m| m.len() == names.len() && names.iter().all(|k| m.contains_key(*k)))
}
fn bounded(v: &Value, limit: usize) -> bool {
    v.as_str().is_some_and(|s| !s.trim().is_empty() && s.len() <= limit && !s.chars().any(char::is_control))
}
fn token(v: &Value) -> bool {
    bounded(v, 128) && v.as_str().unwrap().bytes().all(|b| b.is_ascii_alphanumeric() || b"_.:-".contains(&b))
}
fn index(v: &Value) -> bool { v.as_u64().is_some_and(|n| n <= 9_007_199_254_740_991) }
fn path(v: &Value) -> bool { bounded(v, 512) && v.as_str().unwrap().starts_with('/') }
pub(crate) fn scope(v: &Value) -> bool {
    v.as_array().is_some_and(|ops| ops.len() <= 256 && ops.iter().all(token)
        && ops.iter().enumerate().all(|(i, op)| !ops[..i].contains(op)))
}
fn selection(v: &Value, unlink: bool) -> bool {
    let Some(ops) = v.as_object() else { return false; };
    if unlink { return ops.is_empty(); }
    if ops.is_empty() || ops.len() > 256 { return false; }
    let mut count = 0;
    ops.iter().all(|(op, value)| {
        let Some(paths) = value.as_array() else { return false; };
        count += paths.len();
        token(&json!(op)) && !paths.is_empty() && count <= 256 && paths.iter().all(path)
            && paths.iter().enumerate().all(|(i, p)| !paths[..i].contains(p))
    })
}
pub(crate) fn request(v: &Value) -> bool {
    let mut names = vec!["target_policy", "operation", "association_id", "source_ref", "selection", "source", "targets"];
    if v.get("face_style").is_some() { names.push("face_style"); }
    if v.get("eye_bag_cohort").is_some() { names.push("eye_bag_cohort"); }
    if !fields(v, &names) || v["target_policy"] != "persistent_association"
        || !matches!(v["operation"].as_str(), Some("create" | "patch" | "unlink"))
        || !token(&v["association_id"]) || !face_style::endpoint(&v["source"])
        || !face_style::face(&v["source_ref"], &v["source"]["source_proof"]["asset_sha256"])
        || !selection(&v["selection"], v["operation"] == "unlink") { return false; }
    if v.get("eye_bag_cohort").is_some() && !crate::batch_api::eye_cohort::policy(v) { return false; }
    if let Some(recipe) = v.get("face_style") {
        if v["operation"] == "unlink" || !face_style::recipe(recipe) || !face_style::selection(&v["selection"]) { return false; }
    }
    let Some(targets) = v["targets"].as_array() else { return false; };
    let mut documents = std::collections::BTreeSet::from([v["source"]["document"]["document_id"].as_str().unwrap()]);
    let mut scopes = std::collections::BTreeSet::from([v["source"]["people_scope"].as_str().unwrap()]);
    !targets.is_empty() && targets.len() < MAX_MEMBERS && targets.iter().all(|row| {
        let owner = &row["target"];
        fields(row, &["target", "target_refs"]) && face_style::endpoint(owner)
            && row["target_refs"].as_array().is_some_and(|refs| refs.len() == 1
                && face_style::face(&refs[0], &owner["source_proof"]["asset_sha256"]))
            && owner["document"]["epoch"] == v["source"]["document"]["epoch"]
            && documents.insert(owner["document"]["document_id"].as_str().unwrap())
            && scopes.insert(owner["people_scope"].as_str().unwrap())
    })
}
pub(crate) fn request_scope(ops: &Value, applies: &Value) -> bool {
    if !scope(ops) { return false; }
    if applies.get("face_style").is_some() { return ops == &json!(face_style::OPS); }
    let (Some(ops), Some(selected)) = (ops.as_array(), applies["selection"].as_object()) else { return false; };
    ops.len() == selected.len() && ops.iter().all(|op| selected.contains_key(op.as_str().unwrap()))
}
fn preflight_request(v: &Value) -> bool {
    let Some(map) = v.as_object() else { return false; };
    let names = ["cmd", "action", "request_id", "docs", "module_scope", "people_transfer"];
    if !names.iter().all(|k| map.contains_key(*k))
        || !map.keys().all(|k| names.contains(&k.as_str()) || k == "conflict_policy")
        || v["cmd"] != "batch" || v["action"] != "preflight" || !bounded(&v["request_id"], 128)
        || !v.get("conflict_policy").map_or(true, |p| p == "recheck")
        || !request(&v["people_transfer"]) || !request_scope(&v["module_scope"], &v["people_transfer"]) { return false; }
    let Some(docs) = v["docs"].as_array() else { return false; };
    let targets = v["people_transfer"]["targets"].as_array().unwrap();
    docs.len() == targets.len() && targets.iter().all(|row|
        docs.iter().filter(|id| *id == &row["target"]["document"]["document_id"]).count() == 1)
}
pub(crate) fn acknowledgments(v: &Value) -> bool {
    let Some(rows) = v.as_array() else { return false; };
    let mut seen = std::collections::BTreeSet::new();
    (2..=MAX_MEMBERS).contains(&rows.len()) && rows.iter().all(|row|
        fields(row, &["document_id", "revision", "before_sha256", "after_sha256", "cohort_sha256"])
        && hex(&row["document_id"], 32) && revision(&row["revision"])
        && ["before_sha256", "after_sha256", "cohort_sha256"].iter().all(|k| hex(&row[*k], 64))
        && row["cohort_sha256"] == rows[0]["cohort_sha256"]
        && seen.insert(row["document_id"].as_str().unwrap()))
}
fn paired_acknowledgments(v: &Value) -> bool {
    let Some(other) = v.get(collarbone::ACK) else { return true; };
    if !collarbone::acknowledgments(other) { return false; }
    let (Some(portrait), Some(collarbone)) = (v[ACK].as_array(), other.as_array()) else { return false; };
    portrait.len() == collarbone.len() && portrait.iter().zip(collarbone).all(|(a, b)|
        ["document_id", "revision", "before_sha256", "after_sha256"].iter().all(|k| a[*k] == b[*k]))
}
fn image_request(v: &Value) -> bool {
    fields(v, &["cmd", "action", "request_id", "preflight_token", "document_id", "revision", "side", "sha256"])
        && v["cmd"] == "batch" && v["action"] == "portrait_cohort_visual" && bounded(&v["request_id"], 128)
        && hex(&v["preflight_token"], 32) && hex(&v["document_id"], 32) && revision(&v["revision"])
        && matches!(v["side"].as_str(), Some("before" | "after")) && hex(&v["sha256"], 64)
}
pub(crate) fn command(v: &Value) -> Result<(), String> {
    if v["action"]==crate::batch_api::decoration_cohort::IMAGE||v.get(crate::batch_api::decoration_cohort::ACK).is_some() {return crate::batch_api::decoration_cohort::command(v);}
    if crate::batch_api::eye_cohort::routed(v) { return crate::batch_api::eye_cohort::command(v); }
    if v["action"] == "portrait_cohort_visual" {
        return if image_request(v) { Ok(()) } else { Err("Portrait cohort image read needs exact frozen coordinates".into()) };
    }
    if v.get("portrait_cohort").is_some() { return Err("Portrait cohort classification comes only from the frozen engine plan".into()); }
    if v["people_transfer"]["target_policy"] == "persistent_association" && !preflight_request(v) {
        return Err("Persistent portrait association needs exact independent members, scope and optional thirty-leaf local style".into());
    }
    if let Some(ack) = v.get(ACK) {
        let mut names = vec!["cmd", "action", "request_id", "preflight_token", "module_scope", ACK];
        if v.get(collarbone::ACK).is_some() { names.push(collarbone::ACK); }
        if !fields(v, &names) || v["cmd"] != "batch" || v["action"] != "commit"
            || !bounded(&v["request_id"], 128) || !hex(&v["preflight_token"], 32)
            || !scope(&v["module_scope"]) || !acknowledgments(ack) || !paired_acknowledgments(v)
            || (collarbone::selected(v) && v.get(collarbone::ACK).is_none()) {
            return Err("Portrait cohort commit needs its exact scope and ordered source-first image acknowledgments".into());
        }
    }
    Ok(())
}
pub(crate) fn read_only(v: &Value) -> bool { image_request(v) || preflight_request(v) }
pub(crate) fn binding(v: &Value) -> Result<Option<Value>, String> {
    command(v)?;
    if image_request(v) {
        return Ok(Some(json!({"preflight_token":v["preflight_token"], "document_id":v["document_id"],
            "revision":v["revision"], "side":v["side"], "sha256":v["sha256"]})));
    }
    if let Some(ack) = v.get(ACK) {
        let mut binding = json!({"preflight_token":v["preflight_token"], "module_scope":v["module_scope"],
            "portrait_cohort":true, (ACK):ack});
        if let Some(other) = v.get(collarbone::ACK) {
            binding[collarbone::ACK] = other.clone(); binding["collarbone_cohort"] = json!(true);
        }
        return Ok(Some(binding));
    }
    if preflight_request(v) {
        return Ok(Some(json!({"module_scope":v["module_scope"], "policy":"recheck",
            "portrait_applies_sha256":face_style::request_digest(&v["people_transfer"])})));
    }
    Ok(None)
}
pub(crate) fn complete_intent(v: &Value) -> bool {
    v.as_array().is_some_and(|leaves| face_style::LEAVES.iter().all(|(op, paths)| paths.iter().all(|path|
        leaves.iter().any(|leaf| leaf["op"] == *op && leaf["path"] == *path))))
}
pub(crate) fn review(v: &Value) -> bool {
    if !fields(v, &["version", "operation", "association_id", "generation", "members", "intent"])
        || v["version"].as_u64() != Some(1) || !token(&v["association_id"]) || !hex(&v["generation"], 64)
        || !matches!(v["operation"].as_str(), Some("create" | "patch" | "unlink")) { return false; }
    let (Some(members), Some(intent)) = (v["members"].as_array(), v["intent"].as_array()) else { return false; };
    let mut ids = std::collections::BTreeSet::new(); let mut scopes = std::collections::BTreeSet::new();
    let mut leaves = std::collections::BTreeSet::new();
    (2..=MAX_MEMBERS).contains(&members.len()) && (1..=256).contains(&intent.len())
        && members.iter().all(|m| fields(m, &["document_id", "scope_id", "original_sha256", "ref"])
            && hex(&m["document_id"], 32) && (m["scope_id"] == "project" || m["scope_id"] == m["document_id"])
            && hex(&m["original_sha256"], 64) && face_style::face(&m["ref"], &m["ref"]["asset_sha256"])
            && ids.insert(m["document_id"].as_str().unwrap()) && scopes.insert(m["scope_id"].as_str().unwrap()))
        && intent.iter().all(|leaf| fields(leaf, &["op", "path", "value"]) && token(&leaf["op"]) && path(&leaf["path"])
            && (leaf["value"].is_boolean() || leaf["value"].is_string() || leaf["value"].as_f64().is_some_and(f64::is_finite))
            && leaves.insert((leaf["op"].as_str().unwrap(), leaf["path"].as_str().unwrap())))
}
fn visual(v: &Value, row: &Value) -> bool {
    if !fields(v, &["version", "document_id", "revision", "source_proof", "before_state_sha256", "candidate_state_sha256",
        "before_people_sha256", "candidate_people_sha256", "source_size", "before_output_size", "after_output_size", "before", "after", "cohort_sha256"])
        || v["version"].as_u64() != Some(1) || v["document_id"] != row["document_id"] || v["revision"] != row["revision"]
        || !source_proof(&v["source_proof"]) || v["source_proof"] != row["association"]["owner"]["source_proof"]
        || ["before_state_sha256", "candidate_state_sha256", "before_people_sha256", "candidate_people_sha256", "cohort_sha256"]
            .iter().any(|k| !hex(&v[*k], 64)) { return false; }
    let (Some(source), Some(before), Some(after)) = (collarbone::size(&v["source_size"]),
        collarbone::size(&v["before_output_size"]), collarbone::size(&v["after_output_size"])) else { return false; };
    let derived = &v["source_proof"]["creative_source"];
    (derived.is_null() || (derived["width"].as_u64() == Some(source.0) && derived["height"].as_u64() == Some(source.1)))
        && collarbone::compact_image(&v["before"], before) && collarbone::compact_image(&v["after"], after)
}
fn preflight(v: &Value) -> bool {
    let applies = &v["applies"]; let common = &v["persistent_association"];
    if v["people_transfer"] != true || !request(applies) || !request_scope(&v["module_scope"], applies)
        || !review(common) || !complete_intent(&common["intent"]) || v["policy"] != "recheck"
        || common["operation"] != applies["operation"] || common["association_id"] != applies["association_id"]
        || v["blocked"].as_u64() != Some(0) || !hex(&v["preflight_token"], 32) || v.to_string().len() > 7 * 1024 * 1024
        || v["rejected_docs"].as_array().map_or(true, |rows| !rows.is_empty()) { return false; }
    let Some(targets) = v["targets"].as_array() else { return false; };
    let requested = applies["targets"].as_array().unwrap(); let members = common["members"].as_array().unwrap();
    if targets.len() != requested.len() || members.len() != targets.len() + 1
        || v["ok"].as_u64() != Some(targets.len() as u64) { return false; }
    let source = &v["association_source"]; let snapshot = &v["source_snapshot"];
    if snapshot["document_id"] != source["document_id"] || snapshot["revision"] != source["revision"]
        || snapshot["path"] != source["path"] { return false; }
    let mut ids = std::collections::BTreeSet::new(); let mut indices = std::collections::BTreeSet::new();
    for (position, row) in std::iter::once(source).chain(targets.iter()).enumerate() {
        let (owner, reference) = if position == 0 { (&applies["source"], &applies["source_ref"]) }
            else { (&requested[position - 1]["target"], &requested[position - 1]["target_refs"][0]) };
        let association = &row["association"];
        let mut names = vec!["owner", "ref", "candidate_sha256", "person_id", "portrait_visual"];
        if v["collarbone_cohort"] == true { names.extend(["collarbone_coverage", "collarbone_visual"]); }
        if v["eye_bag_cohort"] == true { names.extend(["eye_bag_cohort", "eye_bag_cohort_visual"]); }
        if !fields(association, &names) || &association["owner"] != owner || &association["ref"] != reference
            || !hex(&association["candidate_sha256"], 64) || !token(&association["person_id"])
            || row["document_id"] != owner["document"]["document_id"]
            || row["revision"].as_str() != owner["document"]["revision"].as_u64().map(|n| n.to_string()).as_deref()
            || !row["blocked"].is_null() || !index(&row["index"]) || !bounded(&row["path"], 4096)
            || !ids.insert(row["document_id"].as_str().unwrap()) || !indices.insert(row["index"].as_u64().unwrap())
            || !members.iter().any(|m| m["document_id"] == row["document_id"] && m["scope_id"] == owner["people_scope"]
                && m["original_sha256"] == owner["source_proof"]["original_sha256"] && &m["ref"] == reference)
            || !visual(&association["portrait_visual"], row)
            || association["portrait_visual"]["cohort_sha256"] != source["association"]["portrait_visual"]["cohort_sha256"] { return false; }
        // Dual reviews reuse the same exact full-source before/after pair.
        // Their coverage/cohort commitments remain distinct and independently bound.
        if v["collarbone_cohort"] == true && !association["portrait_visual"].as_object().unwrap().iter()
            .all(|(key, value)| key == "cohort_sha256" || association["collarbone_visual"].get(key) == Some(value)) { return false; }
    }
    let intent = common["intent"].as_array().unwrap();
    if applies["operation"] == "create" && intent.len() != applies["selection"].as_object().unwrap().values()
        .map(|paths| paths.as_array().unwrap().len()).sum::<usize>() { return false; }
    if applies["operation"] != "unlink" && !applies["selection"].as_object().unwrap().iter().all(|(op, paths)|
        paths.as_array().unwrap().iter().all(|path| intent.iter().any(|leaf|
            leaf["op"].as_str() == Some(op.as_str()) && &leaf["path"] == path))) { return false; }
    if let Some(recipe) = applies.get("face_style") {
        let parameters: Vec<Value> = intent.iter().filter(|leaf| face_style::LEAVES.iter().any(|(op, paths)|
            leaf["op"] == *op && paths.iter().any(|path| leaf["path"] == *path)))
            .map(|leaf| json!({"operation_id":leaf["op"], "parameter_path":leaf["path"], "value":leaf["value"]})).collect();
        if !face_style::parameters(&json!(parameters), recipe) { return false; }
    }
    true
}
fn image_receipt(v: &Value) -> bool {
    let Some(map) = v.as_object() else { return false; };
    let mut names = vec!["action", "success", "request_id", "preflight_token", "document_id", "revision", "side", "sha256"];
    if v["success"] == true { names.extend(["compact", "image"]); }
    else if v["success"] == false { names.push("error"); } else { return false; }
    if !names.iter().all(|k| map.contains_key(*k))
        || !map.keys().all(|k| names.contains(&k.as_str()) || k == "event" || k == "outcome_unknown")
        || !v.get("event").map_or(true, |event| event == "batch_result")
        || !bounded(&v["request_id"], 128) || !hex(&v["preflight_token"], 32) || !hex(&v["document_id"], 32)
        || !revision(&v["revision"]) || !matches!(v["side"].as_str(), Some("before" | "after")) || !hex(&v["sha256"], 64)
        || !v.get("outcome_unknown").map_or(true, Value::is_boolean) { return false; }
    if v["success"] == false { return bounded(&v["error"], 8000); }
    let image = &v["image"]; let compact = &v["compact"];
    let (Some(w), Some(h)) = (image["width"].as_u64(), image["height"].as_u64()) else { return false; };
    v["outcome_unknown"] != true && image["sha256"] == v["sha256"] && collarbone::image(image, (w, h))
        && collarbone::compact_image(compact, (w, h))
        && ["mime", "width", "height", "sha256"].iter().all(|k| compact[*k] == image[*k])
}
fn commit(v: &Value) -> bool {
    if v["success"] != true { return true; }
    let (Some(targets), Some(acks), Some(applied), Some(skipped)) = (v["target_outcomes"].as_array(), v[ACK].as_array(),
        v["applied"].as_array(), v["skipped"].as_array()) else { return false; };
    let common = &v["persistent_association"]; let source = &v["source_outcome"]; let snapshot = &v["source_snapshot"];
    if v["people_transfer"] != true || !review(common) || !complete_intent(&common["intent"])
        || targets.len() + 1 != acks.len() || applied.len() != acks.len() || !skipped.is_empty()
        || common["members"].as_array().unwrap().len() != acks.len() || !bounded(&v["batch_id"], 128)
        || source["document_id"] != snapshot["document_id"] || source["expected_revision"] != snapshot["revision"]
        || source["path"] != snapshot["path"] || v["source_changed_since_preflight"] != false || v["source_missing"] != false
        || (common["operation"] == "unlink" && v["module_scope"] != json!([])) { return false; }
    let mut ids = std::collections::BTreeSet::new(); let mut indices = std::collections::BTreeSet::new();
    for ((row, ack), applied_index) in std::iter::once(source).chain(targets.iter()).zip(acks).zip(applied) {
        if !fields(row, &["index", "path", "document_id", "expected_revision", "result_revision", "outcome", "blocked"])
            || row["document_id"] != ack["document_id"] || row["expected_revision"] != ack["revision"]
            || !revision(&row["result_revision"]) || row["result_revision"].as_str().unwrap().parse::<u64>().unwrap()
                <= ack["revision"].as_str().unwrap().parse::<u64>().unwrap()
            || row["outcome"] != "applied" || !row["blocked"].is_null() || !bounded(&row["path"], 4096)
            || !index(&row["index"]) || &row["index"] != applied_index
            || !ids.insert(row["document_id"].as_str().unwrap()) || !indices.insert(row["index"].as_u64().unwrap())
            || !common["members"].as_array().unwrap().iter().any(|m| m["document_id"] == row["document_id"]) { return false; }
    }
    true
}
pub(crate) fn receipt(v: &Value) -> bool {
    // A dedicated cohort failure still needs its exact echoed identity.
    if crate::batch_api::eye_cohort::evidence(v) && v["success"] != true {
        return crate::batch_api::eye_cohort::receipt(v);
    }
    if v["action"] == "portrait_cohort_visual" { return image_receipt(v); }
    let evidence = v["association_source"]["association"].get("portrait_visual").is_some()
        || v["targets"].as_array().is_some_and(|rows| rows.iter().any(|row| row["association"].get("portrait_visual").is_some()));
    let inherited = v["applies"]["target_policy"] == "persistent_association"
        && (v["applies"].get("face_style").is_some() || complete_intent(&v["persistent_association"]["intent"]));
    if v.get("portrait_cohort").is_some() && v["portrait_cohort"] != true { return false; }
    if v["action"] == "preflight" && (inherited || evidence || v["portrait_cohort"] == true) {
        return v["success"] == true && v["portrait_cohort"] == true && v.get(ACK).is_none()
            && !FOREIGN.iter().any(|k| v.get(*k).is_some()) && v.get(collarbone::ACK).is_none() && preflight(v);
    }
    if evidence { return false; }
    let Some(ack) = v.get(ACK) else {
        return v["portrait_cohort"] != true
            && !(v["action"] == "commit" && complete_intent(&v["persistent_association"]["intent"])
                && (v["success"] == true || v["outcome_unknown"] == true));
    };
    v["action"] == "commit" && v["portrait_cohort"] == true && scope(&v["module_scope"])
        && hex(&v["preflight_token"], 32) && acknowledgments(ack) && paired_acknowledgments(v)
        && !FOREIGN.iter().any(|k| v.get(*k).is_some())
        && (v.get(collarbone::ACK).is_some() == (v["collarbone_cohort"] == true))
        && (!(collarbone::selected(v) || v["persistent_association"]["intent"].as_array()
            .is_some_and(|leaves| leaves.iter().any(|leaf| leaf["op"] == collarbone::OP))) || v["collarbone_cohort"] == true)
        && (if v["success"] == true { v["outcome_unknown"] == false }
            else { v["success"] == false && v["outcome_unknown"].is_boolean() && bounded(&v["error"], 8000) })
        && commit(v)
}

#[cfg(test)]
#[path = "portrait_cohort_protocol_tests.rs"]
mod tests;
