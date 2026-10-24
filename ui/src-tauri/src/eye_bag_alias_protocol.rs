// SPDX-License-Identifier: GPL-3.0-or-later
//! Shared-source direct-editor alias evidence. AUTHORED / UNRUN.
//! One source-owned painted ridge, not donor-support transfer or preset intent.
use serde_json::Value;
use super::{fields, text};
use crate::original_shadow_transfer_protocol::hex;
const MAX_MEMBERS: usize = 16;
const MAX_SAFE_REVISION: u64 = 9_007_199_254_740_991;

pub(super) fn revision(v: &Value) -> Option<u64> {
    let s = v.as_str()?;
    if s.is_empty() || s.len() > 16 || !s.bytes().all(|b| b.is_ascii_digit()) { return None; }
    let n = s.parse::<u64>().ok()?;
    (n <= MAX_SAFE_REVISION && n.to_string() == s).then_some(n)
}
pub(super) fn ack(v: &Value) -> bool {
    let Some(rows) = v["members"].as_array() else { return false; };
    let mut seen = std::collections::BTreeSet::new();
    fields(v, &["review_sha256", "support_overlay_sha256", "members"])
        && hex(&v["review_sha256"], 64) && hex(&v["support_overlay_sha256"], 64)
        && (2..=MAX_MEMBERS).contains(&rows.len()) && rows.iter().all(|row|
            fields(row, &["document_id", "revision", "before_sha256", "after_sha256"])
                && text(&row["document_id"]) && revision(&row["revision"]).is_some()
                && hex(&row["before_sha256"], 64) && hex(&row["after_sha256"], 64)
                && seen.insert(row["document_id"].as_str().unwrap()))
}
pub(super) fn members(v: &Value) -> bool {
    let Some(rows) = v["members"].as_array() else { return false; };
    let mut seen = std::collections::BTreeSet::new();
    (2..=MAX_MEMBERS).contains(&rows.len()) && rows[0]["visual"] == v["visual"]
        && rows.iter().all(|row| {
            let visual = &row["visual"];
            fields(row, &["path", "visual"])
                && row["path"].as_str().is_some_and(|s| !s.trim().is_empty() && s.len() <= 4096 && !s.contains('\0'))
                && text(&visual["document_id"]) && revision(&visual["revision"]).is_some()
                && crate::people_api::face_style::visual_shape(visual)
                && visual["source_proof"]["asset_sha256"] == v["face_ref"]["asset_sha256"]
                && visual["source_size"] == v["visual"]["source_size"]
                // Per-member repairs, crops, graph/render fingerprints and
                // original/creative provenance stay independent and frozen.
                && seen.insert(visual["document_id"].as_str().unwrap())
        })
}
pub(super) fn confirmation(v: &Value, request: &Value) -> bool {
    let Some(expected) = request["payload"]["ack"]["members"].as_array() else { return false; };
    let Some(actual) = v["payload"]["alias_members"].as_array() else { return false; };
    text(&v["batch_id"]) && actual.len() == expected.len()
        && actual.iter().zip(expected).all(|(actual, expected)|
            fields(actual, &["document_id", "expected_revision", "result_revision"])
                && actual["document_id"] == expected["document_id"]
                && actual["expected_revision"] == expected["revision"]
                && revision(&expected["revision"]).is_some_and(|before|
                    before < MAX_SAFE_REVISION && revision(&actual["result_revision"]) == Some(before + 1)))
}
