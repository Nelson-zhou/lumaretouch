// SPDX-License-Identifier: GPL-3.0-or-later
//! Source-owned full-cohort evidence and atomic outcome structure. AUTHORED / UNRUN.
use super::*;
fn index(v: &Value) -> bool { v.as_u64().is_some_and(|n| n <= 9_007_199_254_740_991) }
fn bounded(v: &Value, limit: usize) -> bool {
    v.as_str().is_some_and(|s| !s.trim().is_empty() && s.len() <= limit && !s.chars().any(char::is_control))
}
fn state(v: &Value) -> bool {
    fields(v, &["scope", "ridge_sha256", "sides"]) && match v["scope"].as_str() {
        Some("neutral-no-effect") => v["ridge_sha256"].is_null() && v["sides"] == json!([]),
        Some("target-reviewed-ridge") => hex(&v["ridge_sha256"], 64)
            && [json!(["left"]), json!(["right"]), json!(["left", "right"])].contains(&v["sides"]),
        _ => false,
    }
}
fn coverage(v: &Value, reference: &Value, choice: &Value) -> bool {
    fields(v, &["version", "support_transfer", "replace_legacy", "face_ref", "before", "after"])
        && v["version"].as_u64() == Some(1) && v["support_transfer"] == "none"
        && v["replace_legacy"] == choice["replace_legacy"] && v["replace_legacy"].is_boolean()
        && &v["face_ref"] == reference && state(&v["before"]) && state(&v["after"])
}
fn intent(v: &Value) -> bool {
    portrait::review(v) && v["intent"].as_array().unwrap().iter().all(|leaf| {
        let op = leaf["op"].as_str().unwrap();
        if UNSUPPORTED.contains(&op) { return false; }
        op != eye_bag::OP || (matches!(leaf["path"].as_str(), Some("/amount" | "/preserve"))
            && leaf["value"].as_f64().is_some_and(|n| n.is_finite() && (0.0..=1.0).contains(&n)))
    })
}
fn families(v: &Value) -> bool {
    let intent = &v["persistent_association"]["intent"];
    (v["portrait_cohort"] == true) == portrait::complete_intent(intent)
        && (!intent.as_array().is_some_and(|leaves| leaves.iter().any(|leaf| leaf["op"] == collarbone::OP))
            || v["collarbone_cohort"] == true)
        && ["portrait_cohort", "collarbone_cohort"].iter().all(|key|
            v.get(*key).map_or(true, |marker| marker == true))
}
fn pair(a: &Value, b: &Value, other_hash: &str) -> bool {
    a.as_object().is_some_and(|a| a.iter().all(|(key, value)|
        key == "coverage_sha256" || b.get(key) == Some(value)))
        && b.as_object().is_some_and(|b| b.keys().all(|key| key != "coverage_sha256" || other_hash == "coverage_sha256"))
}
pub(super) fn preflight(v: &Value) -> bool {
    let applies = &v["applies"]; let common = &v["persistent_association"];
    if v["people_transfer"] != true || v.get("outcome_unknown").is_some_and(|unknown| unknown != false)
        || !intent(common) || !families(v)
        || common["operation"] != applies["operation"] || common["association_id"] != applies["association_id"]
        || v["blocked"].as_u64() != Some(0) || !hex(&v["preflight_token"], 32) || v.to_string().len() > 7 * 1024 * 1024
        || v["rejected_docs"].as_array().map_or(true, |rows| !rows.is_empty()) { return false; }
    let Some(targets) = v["targets"].as_array() else { return false; };
    let requested = applies["targets"].as_array().unwrap(); let members = common["members"].as_array().unwrap();
    let choices = applies[KEY]["members"].as_array().unwrap();
    if targets.len() != requested.len() || members.len() != targets.len() + 1
        || v["ok"].as_u64() != Some(targets.len() as u64) { return false; }
    let source = &v["association_source"]; let snapshot = &v["source_snapshot"];
    if ["document_id", "revision", "path"].iter().any(|k| snapshot[*k] != source[*k]) { return false; }
    let mut ids = std::collections::BTreeSet::new(); let mut indices = std::collections::BTreeSet::new();
    let leaves = common["intent"].as_array().unwrap();
    for (position, row) in std::iter::once(source).chain(targets.iter()).enumerate() {
        let (owner, reference) = if position == 0 { (&applies["source"], &applies["source_ref"]) }
            else { (&requested[position - 1]["target"], &requested[position - 1]["target_refs"][0]) };
        let association = &row["association"]; let proof = &association[VISUAL]; let support = &association[KEY];
        let mut names = vec!["owner", "ref", "candidate_sha256", "person_id", KEY, VISUAL];
        if v["portrait_cohort"] == true { names.push("portrait_visual"); }
        if v["collarbone_cohort"] == true { names.extend(["collarbone_coverage", "collarbone_visual"]); }
        if !fields(association, &names) || &association["owner"] != owner || &association["ref"] != reference
            || !hex(&association["candidate_sha256"], 64) || !text(&association["person_id"])
            || row["document_id"] != owner["document"]["document_id"]
            || row["revision"].as_str() != owner["document"]["revision"].as_u64().map(|n| n.to_string()).as_deref()
            || !row["blocked"].is_null() || !index(&row["index"]) || !bounded(&row["path"], 4096)
            || !ids.insert(row["document_id"].as_str().unwrap()) || !indices.insert(row["index"].as_u64().unwrap())
            || !members.iter().any(|m| m["document_id"] == row["document_id"] && m["scope_id"] == owner["people_scope"]
                && m["original_sha256"] == owner["source_proof"]["original_sha256"] && &m["ref"] == reference)
            || !coverage(support, reference, &choices[position])
            || !visual(proof, &row["document_id"], &row["revision"], &owner["source_proof"])
            || proof["coverage_sha256"].as_str() != Some(collarbone::request_digest(support).as_str()) { return false; }
        // Capsule intent is not the effective per-face recipe: explicit local
        // overrides win. Actual before/after activity comes only from each
        // member's independently frozen full graph and owned support evidence.
        let selected_legacy = applies["operation"] != "unlink" && applies["selection"]["lnx.enhance.v1"]
            .as_array().is_some_and(|paths| paths.iter().any(|path| path == "/eye_bags"));
        if selected_legacy && leaves.iter().any(|leaf| leaf["op"] == "lnx.enhance.v1" && leaf["path"] == "/eye_bags"
            && leaf["value"].as_f64().is_some_and(|n| n > 0.0)) && support["after"]["scope"] != "neutral-no-effect" { return false; }
        if v["portrait_cohort"] == true && !pair(proof, &association["portrait_visual"], "cohort_sha256") { return false; }
        if v["collarbone_cohort"] == true && (!eye_bag::collarbone_coverage(&association["collarbone_coverage"], &json!([reference]))
            || !visual(&association["collarbone_visual"], &row["document_id"], &row["revision"], &owner["source_proof"])
            || association["collarbone_visual"]["coverage_sha256"].as_str()
                != Some(collarbone::request_digest(&association["collarbone_coverage"]).as_str())
            || !pair(proof, &association["collarbone_visual"], "coverage_sha256")) { return false; }
    }
    if applies["operation"] == "create" && leaves.len() != applies["selection"].as_object().unwrap().values()
        .map(|paths| paths.as_array().unwrap().len()).sum::<usize>() { return false; }
    if applies["operation"] != "unlink" && !applies["selection"].as_object().unwrap().iter().all(|(op, paths)|
        paths.as_array().unwrap().iter().all(|path| leaves.iter().any(|leaf|
            leaf["op"].as_str() == Some(op.as_str()) && &leaf["path"] == path))) { return false; }
    v["portrait_cohort"] != true || portrait::receipt(v)
}
pub(super) fn commit(v: &Value) -> bool {
    let (Some(targets), Some(acks), Some(applied), Some(skipped)) = (v["target_outcomes"].as_array(), v[ACK].as_array(),
        v["applied"].as_array(), v["skipped"].as_array()) else { return false; };
    let common = &v["persistent_association"]; let source = &v["source_outcome"]; let snapshot = &v["source_snapshot"];
    if v["people_transfer"] != true || !intent(common) || !families(v)
        || targets.len() + 1 != acks.len() || applied.len() != acks.len() || !skipped.is_empty()
        || common["members"].as_array().unwrap().len() != acks.len() || !text(&v["batch_id"])
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
    v["portrait_cohort"] != true || portrait::receipt(v)
}
