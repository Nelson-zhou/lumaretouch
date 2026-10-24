// SPDX-License-Identifier: GPL-3.0-or-later
//! AUTHORED / UNRUN. Native protocol specifications only; no execution or image acceptance.
use super::*;
use crate::receipt_host::{ReceiptHost, ReceiptKind};
use super::super::PeopleKind;
fn request(action: &str, payload: Value) -> Value {
    json!({"cmd":"people", "request_id":"support-request", "action":action, "payload":payload,
        "document_id":"1".repeat(32), "document_epoch":"epoch", "document_revision":7,
        "state_revision":11, "association_revision":3,
        "target":{"scope":"face", "target_id":"face", "face_ref":{"asset_sha256":"a".repeat(64), "face_instance_id":"face", "analysis_revision":2}}})
}
// A generated 2x2 RGB PNG framing fixture, not a portrait or quality claim.
fn image_value() -> Value {
    use base64::{engine::general_purpose::STANDARD, Engine as _};
    use sha2::{Digest, Sha256};
    fn chunk(bytes: &mut Vec<u8>, kind: &[u8], data: &[u8]) {
        bytes.extend_from_slice(&(data.len() as u32).to_be_bytes()); let start = bytes.len();
        bytes.extend_from_slice(kind); bytes.extend_from_slice(data); let mut crc = u32::MAX;
        for byte in &bytes[start..] {
            crc ^= u32::from(*byte);
            for _ in 0..8 { crc = (crc >> 1) ^ ((0u32.wrapping_sub(crc & 1)) & 0xedb8_8320); }
        }
        bytes.extend_from_slice(&(!crc).to_be_bytes());
    }
    let mut bytes = b"\x89PNG\r\n\x1a\n".to_vec();
    chunk(&mut bytes, b"IHDR", &[0,0,0,2,0,0,0,2,8,2,0,0,0]);
    let mut data = vec![0x78,0x01,0x01,14,0,241,255]; data.extend_from_slice(&[0;14]);
    data.extend_from_slice(&[0,14,0,1]); chunk(&mut bytes, b"IDAT", &data); chunk(&mut bytes, b"IEND", &[]);
    json!({"mime":"image/png", "width":2, "height":2, "sha256":format!("{:x}", Sha256::digest(&bytes)), "base64":STANDARD.encode(bytes)})
}
fn proof() -> Value {
    json!({"source":{"sha256":"a".repeat(64), "width":2, "height":2}, "landmark_digest":"b".repeat(64),
        "face_ref":request("", json!({}))["target"]["face_ref"], "preview_sha256":image_value()["sha256"], "reference_request_id":"source-request"})
}
fn region() -> Value {
    json!({"visible":true, "unoccluded":true, "ownership_confirmed":true,
        "recipe":{"version":1, "domain":"source-normalized", "objects":[{"id":"stroke", "name":"Visible source skin",
            "enabled":true, "operation":"add", "kind":"brush", "opacity":1.0, "feather":10.0,
            "points":[[0.4,0.5],[0.6,0.5]], "axes":[[0.02,0],[0,0.02]]}]}})
}
fn preview_request() -> Value { request("face_decoration_support_alias_preview", json!({"region":region(), "reference_proof":proof()})) }
fn review_value() -> Value {
    let c = preview_request();
    let source = json!({"asset_sha256":"a".repeat(64), "original_sha256":"a".repeat(64), "creative_source":null});
    let coverage = json!({"version":1, "support_change":"selected-face-only", "targets":[{
        "face_ref":c["target"]["face_ref"], "before_visibility_sha256":null, "visibility_sha256":"d".repeat(64),
        "before_recipe_sha256":"e".repeat(64), "recipe_sha256":"e".repeat(64)}]});
    let mut rows = Vec::new();
    for (id, rev, path) in [("1".repeat(32), "7", "/source/original"), ("2".repeat(32), "9", "/source/copy")] {
        rows.push(json!({"path":path, "coverage":coverage, "visual":{"version":1, "document_id":id, "revision":rev,
            "source_proof":source, "before_state_sha256":"3".repeat(64), "candidate_state_sha256":"3".repeat(64),
            "before_people_sha256":"4".repeat(64), "candidate_people_sha256":"5".repeat(64), "source_size":[2,2],
            "before_output_size":[2,2], "after_output_size":[2,2], "coverage_sha256":crate::batch_api::collarbone::request_digest(&coverage),
            "before":{"mime":"image/png", "width":2, "height":2, "sha256":"6".repeat(64)},
            "after":{"mime":"image/png", "width":2, "height":2, "sha256":"7".repeat(64)}}}));
    }
    json!({"version":1, "token":"8".repeat(32), "target":"face_decoration_visibility", "owner":{
        "document":{"document_id":c["document_id"], "epoch":c["document_epoch"], "revision":7},
        "people_scope":"project", "state_revision":11, "association_revision":3, "graph_sha256":"4".repeat(64), "source_proof":source},
        "face_ref":c["target"]["face_ref"], "before_support_sha256":null, "support_sha256":"d".repeat(64),
        "reference_proof":proof(), "region":region(), "before_bank_sha256":"9".repeat(64), "candidate_bank_sha256":"f".repeat(64),
        "candidate_state_revision":12, "members":rows, "review_sha256":"b".repeat(64)})
}
fn acknowledgment() -> Value {
    let r = review_value();
    json!({"review_sha256":r["review_sha256"], "members":r["members"].as_array().unwrap().iter().map(|m| {
        let v = &m["visual"]; json!({"document_id":v["document_id"], "revision":v["revision"],
            "before_sha256":v["before"]["sha256"], "after_sha256":v["after"]["sha256"]})
    }).collect::<Vec<_>>()})
}
fn confirm_request() -> Value { request("face_decoration_support_alias_confirm", json!({"token":review_value()["token"], "ack":acknowledgment()})) }
fn receipt_base(c: &Value) -> Value {
    json!({"event":"people_result", "protocol":1, "request_id":c["request_id"], "action":c["action"], "document_id":c["document_id"],
        "success":true, "outcome_unknown":false, "error":null, "created_id":null, "batch_id":null, "frame_emitted":false,
        (REQUEST):binding(c).unwrap().unwrap()[REQUEST]})
}
fn people(c: &Value, changed: bool) -> Value {
    json!({"binding":{"document_id":c["document_id"], "document_epoch":c["document_epoch"], "document_revision":if changed {8} else {7}, "asset_sha256":"a".repeat(64)},
        "revision":if changed {12} else {11}, "association_revision":3, "selected_face_id":"face", "editing_target":c["target"],
        "resolved":{"face_ref":c["target"]["face_ref"], "state_revision":if changed {12} else {11}, "association_revision":3,
            "operations":{"lnx.face_decoration.v1":{"/pattern":{"value":"freckle_dust"}, "/strength":{"value":0.0}}}},
        "face_decoration":{"recipe":{"version":1, "pattern":"freckle_dust", "strength":0.0}, "face_ref":c["target"]["face_ref"],
            "source":proof()["source"], "support_sha256":if changed {json!("d".repeat(64))} else {Value::Null}, "reviewed":changed,
            "support_alias_reason":null, "support_alias_review":if changed {Value::Null} else {review_value()}}})
}
fn preview_result() -> Value {
    let c = preview_request(); let mut v = receipt_base(&c);
    v["payload"] = json!({"kind":c["action"], "review":review_value()}); v["doc_state"] = json!({"people":people(&c, false)}); v
}
fn confirm_result() -> Value {
    let c = confirm_request(); let mut v = receipt_base(&c); let r = review_value(); let a = acknowledgment();
    v["batch_id"] = json!("support-batch"); v["doc_state"] = json!({"people":people(&c, true)});
    v["payload"] = json!({"kind":c["action"], "token":r["token"], "review_sha256":r["review_sha256"], "target":r["target"], "face_ref":r["face_ref"],
        "before_support_sha256":r["before_support_sha256"], "support_sha256":r["support_sha256"], "before_bank_sha256":r["before_bank_sha256"],
        "candidate_bank_sha256":r["candidate_bank_sha256"], "candidate_state_revision":12, "ack":a,
        "history_review_sha256":crate::batch_api::collarbone::request_digest(&a), "alias_members":[
            {"document_id":"1".repeat(32), "expected_revision":"7", "result_revision":"8"},
            {"document_id":"2".repeat(32), "expected_revision":"9", "result_revision":"10"}]});
    v["no_write"] = json!(false); v["module_scope"] = json!(["lnx.people_graph.v1"]);
    v[MARKER] = json!({"version":1, "review_sha256":v["payload"]["history_review_sha256"], "member_count":2});
    v["alias_members"] = v["payload"]["alias_members"].clone(); v
}
fn host() -> ReceiptHost<PeopleKind> {
    let mut h = ReceiptHost::default(); h.reset([176;16]); h.ready([176;16], true); h
}
#[test] fn separate_support_commands_require_exact_reference_and_visible_source_strokes() {
    let c = preview_request(); assert!(command(&c).is_ok()); assert!(read_only(&c));
    let confirm = confirm_request(); assert!(command(&confirm).is_ok()); assert!(!read_only(&confirm)); assert!(applies(&confirm));
    for (path, bad) in [("/payload/reference_proof/source/sha256", json!("f".repeat(64))),
        ("/payload/reference_proof/face_ref/analysis_revision", json!(3)), ("/payload/region/ownership_confirmed", json!(false)),
        ("/payload/region/unoccluded", json!(false)), ("/payload/region/recipe/domain", json!("display-normalized")),
        ("/payload/region/recipe/objects/0/opacity", json!(0)), ("/payload/region/recipe/objects/0/points/0", json!([-0.1,0.5])),
        ("/payload/region/recipe/objects/0/axes", json!([[1,1],[2,2]])), ("/target/scope", json!("person"))] {
        let mut bad_request = c.clone(); *bad_request.pointer_mut(path).unwrap() = bad; assert!(command(&bad_request).is_err(), "{path}");
    }
    for path in ["", "/payload", "/payload/reference_proof", "/payload/region", "/payload/region/recipe/objects/0"] {
        let mut bad = c.clone(); bad.pointer_mut(path).unwrap()["foreign"] = json!(true); assert!(command(&bad).is_err(), "{path}");
    }
    let mut scalar = c.clone(); scalar["action"] = json!("face_decoration_alias_preview"); assert!(super::super::decoration_alias::command(&scalar).is_err());
    let mut copied = c; copied["payload"]["recipe"] = json!({"version":1,"pattern":"mole_pair","strength":0.8}); assert!(command(&copied).is_err());
}
#[test] fn full_member_review_keeps_source_bank_strokes_and_sibling_local_state_exact() {
    let c = preview_request(); let r = review_value(); assert!(review(&r, &c));
    let mut reused_bank = r.clone(); reused_bank["candidate_bank_sha256"] = reused_bank["before_bank_sha256"].clone();
    assert!(review(&reused_bank, &c)); // an already retained record needs no bank append
    let mut no_change = r.clone(); no_change["before_support_sha256"] = no_change["support_sha256"].clone(); assert!(!review(&no_change, &c));
    for (path, bad) in [("/before_bank_sha256", json!("bad")), ("/candidate_bank_sha256", json!(null)), ("/candidate_state_revision", json!(13)),
        ("/region/recipe/objects/0/points/0", json!([0.2,0.3])), ("/reference_proof/landmark_digest", json!("f".repeat(64))),
        ("/members/1/visual/document_id", c["document_id"].clone()), ("/members/1/visual/candidate_state_sha256", json!("8".repeat(64))),
        ("/members/1/visual/after_output_size", json!([1,2])), ("/members/1/visual/source_proof/original_sha256", json!("8".repeat(64))),
        ("/members/1/visual/source_size", json!([4,4])), ("/members/1/coverage/targets/0/visibility_sha256", json!("8".repeat(64))),
        ("/members/1/coverage/targets/0/recipe_sha256", json!("8".repeat(64))), ("/members/1/visual/coverage_sha256", json!("8".repeat(64)))] {
        let mut bad_review = r.clone(); *bad_review.pointer_mut(path).unwrap() = bad; assert!(!review(&bad_review, &c), "{path}");
    }
    let mut derived = r.clone();
    let own = json!({"asset_sha256":"a".repeat(64), "original_sha256":"c".repeat(64),
        "creative_source":{"sha256":"a".repeat(64), "width":2, "height":2}});
    derived["owner"]["source_proof"] = own.clone();
    derived["members"][0]["visual"]["source_proof"] = own.clone();
    derived["members"][1]["visual"]["source_proof"] = own;
    derived["members"][1]["visual"]["source_proof"]["original_sha256"] = json!("f".repeat(64));
    assert!(review(&derived, &c)); // same effective asset, independent retained provenance
    let mut partial = r.clone(); partial["members"].as_array_mut().unwrap().pop(); assert!(!review(&partial, &c));
    let mut donor = r; donor["members"][1]["coverage"]["targets"].as_array_mut().unwrap().push(json!({
        "face_ref":{"asset_sha256":"a".repeat(64), "face_instance_id":"other", "analysis_revision":2},
        "before_visibility_sha256":"a".repeat(64), "visibility_sha256":"d".repeat(64),
        "before_recipe_sha256":"e".repeat(64), "recipe_sha256":"e".repeat(64)}));
    donor["members"][1]["visual"]["coverage_sha256"] = json!(crate::batch_api::collarbone::request_digest(&donor["members"][1]["coverage"]));
    assert!(!review(&donor, &c));
}
#[test] fn preview_envelope_cannot_publish_bank_or_advance_any_revision() {
    let v = preview_result(); assert!(receipt(&v)); assert!(PeopleKind::valid(&v, Some(&"1".repeat(32))));
    for (path, bad) in [("/batch_id", json!("batch")), ("/frame_emitted", json!(true)), ("/error", json!("not really success")),
        ("/doc_state/people/revision", json!(12)), ("/doc_state/people/binding/document_revision", json!(8)),
        ("/doc_state/people/face_decoration/support_sha256", json!("d".repeat(64)))] {
        let mut broken = v.clone(); *broken.pointer_mut(path).unwrap() = bad; assert!(!receipt(&broken), "{path}");
    }
    let mut metadata = v["doc_state"]["people"]["face_decoration"].clone(); assert!(report_metadata(&metadata));
    metadata.as_object_mut().unwrap().remove("support_alias_reason"); assert!(!report_metadata(&metadata));
}
#[test] fn confirmation_requires_exact_complete_ack_and_single_support_publication() {
    let c = confirm_request(); let good = confirm_result(); assert!(receipt(&good)); assert!(matches_request(&c, &good));
    for (path, bad) in [("/payload/history_review_sha256", json!("0".repeat(64))), ("/payload/ack/members/1/revision", json!("10")),
        ("/payload/alias_members/1/result_revision", json!("11")), ("/payload/candidate_state_revision", json!(13)),
        ("/doc_state/people/face_decoration/support_sha256", json!("0".repeat(64))), ("/doc_state/people/association_revision", json!(4))] {
        let mut broken = good.clone(); *broken.pointer_mut(path).unwrap() = bad; assert!(!receipt(&broken), "{path}");
    }
    let mut partial = c.clone(); partial["payload"]["ack"]["members"].as_array_mut().unwrap().pop(); assert!(command(&partial).is_err());
    let mut reordered = c.clone(); reordered["payload"]["ack"]["members"].as_array_mut().unwrap().reverse(); assert!(command(&reordered).is_err());
    let mut markerless = good.clone(); markerless.as_object_mut().unwrap().remove(MARKER); assert!(!receipt(&markerless));
    let mut scalar = good; scalar["face_decoration_alias_request"] = scalar[REQUEST].clone(); assert!(!receipt(&scalar));
}
#[test] fn image_digest_and_review_identity_cannot_be_omitted_or_substituted() {
    let c = request("face_decoration_support_alias_image", json!({"token":"8".repeat(32), "document_id":"2".repeat(32),
        "side":"after", "sha256":"7".repeat(64), "review_sha256":"b".repeat(64)}));
    assert!(command(&c).is_ok()); assert!(read_only(&c));
    let mut no_review = c.clone(); no_review["payload"].as_object_mut().unwrap().remove("review_sha256"); assert!(command(&no_review).is_err());
    let mut released = receipt_base(&c); released["payload_released"] = json!(true); assert!(receipt(&released));
    released["doc_state"] = json!({}); assert!(!receipt(&released));
    let mut h = host(); h.begin_command([176;16], &c).unwrap();
    let mut wrong = receipt_base(&c); wrong[REQUEST]["payload"]["review_sha256"] = json!("0".repeat(64)); wrong["payload_released"] = json!(true);
    h.receive([176;16], &wrong); assert_eq!(h.status("support-request")["result"]["outcome_unknown"], true);
}
#[test] fn image_bytes_are_verified_against_the_exact_member_side_and_frozen_review() {
    let pixels = image_value();
    let c = request("face_decoration_support_alias_image", json!({"token":"8".repeat(32), "document_id":"2".repeat(32),
        "side":"after", "sha256":pixels["sha256"], "review_sha256":"b".repeat(64)}));
    let mut v = receipt_base(&c); v["payload"] = c["payload"].clone();
    v["payload"]["kind"] = c["action"].clone(); v["payload"]["image"] = pixels;
    assert!(receipt(&v));
    for (path, bad) in [("/payload/review_sha256", json!("0".repeat(64))), ("/payload/document_id", json!("1".repeat(32))),
        ("/payload/side", json!("before")), ("/payload/image/sha256", json!("0".repeat(64))),
        ("/payload/image/base64", json!("AAAA")), ("/payload/image/width", json!(3))] {
        let mut broken = v.clone(); *broken.pointer_mut(path).unwrap() = bad; assert!(!receipt(&broken), "{path}");
    }
}
#[test] fn support_preview_requires_original_retained_source_receipt_not_a_scalar_token() {
    let c = preview_request(); let mut read = request("face_decoration_reference", json!({})); read["request_id"] = json!("source-request");
    let mut pixels = image_value();
    for (key, value) in [("source_sha256", json!("a".repeat(64))), ("source_width", json!(2)), ("source_height", json!(2)),
        ("decoded_width", json!(2)), ("decoded_height", json!(2)), ("mapping", json!("normalized_full_frame")),
        ("orientation", json!("exif_normalized_once"))] { pixels[key] = value; }
    let mut report = people(&read, false); report["face_decoration"] = json!({"recipe":{"version":1,"pattern":"freckle_dust","strength":0.0},
        "facts":{}, "source":proof()["source"], "face_ref":proof()["face_ref"], "landmark_digest":proof()["landmark_digest"],
        "reviewed":false, "source_preview":pixels, "reference_proof":proof(), "support_sha256":null,
        "native_available":true, "support_available":true, "support_reason":null, "suspended":null,
        "support_alias_review":null, "support_alias_reason":null});
    let result = json!({"event":"people_result", "protocol":1, "request_id":read["request_id"], "action":read["action"], "document_id":read["document_id"],
        "success":true, "outcome_unknown":false, "error":null, "created_id":null, "batch_id":null, "frame_emitted":false,
        "face_decoration_request":super::super::face_decoration::binding(&read).unwrap().unwrap()["face_decoration_request"],
        "payload":{"kind":"face_decoration_reference", "reference_proof":proof()}, "doc_state":{"people":report}});
    assert!(super::super::face_decoration::receipt(&result));
    let mut h = host(); h.begin_command([176;16], &read).unwrap(); assert!(!reference_matches(&c, &h.status("source-request")));
    h.receive([176;16], &result); assert!(reference_matches(&c, &h.status("source-request")));
    for key in CONTEXT {
        let mut changed = c.clone(); changed[*key] = Value::Null; assert!(!reference_matches(&changed, &h.status("source-request")), "{key}");
    }
    let mut released = h.status("source-request"); released["result"]["payload_released"] = json!(true);
    assert!(!reference_matches(&c, &released));
}
#[test] fn prewrite_rollback_and_unknown_are_not_interchangeable() {
    let c = confirm_request(); let mut v = receipt_base(&c); v["success"] = json!(false); v["error"] = json!("not published");
    assert!(!receipt(&v)); v["no_write"] = json!(true); assert!(receipt(&v));
    v["outcome_unknown"] = json!(true); assert!(!receipt(&v)); v["no_write"] = json!(false); assert!(receipt(&v));
    v["rolled_back"] = json!(true); assert!(!receipt(&v)); v["outcome_unknown"] = json!(false); assert!(receipt(&v));
    v["requires_reload"] = json!(true); assert!(!receipt(&v));
}
#[test] fn unknown_support_write_blocks_edit_save_export_history_and_forged_cancel() {
    let epoch = [177;16]; let c = confirm_request(); crate::project_recovery_fence::issued(epoch, &c).unwrap();
    let mut v = receipt_base(&c); v["success"] = json!(false); v["outcome_unknown"] = json!(true); v["error"] = json!("publication uncertain");
    v["no_write"] = json!(false); crate::project_recovery_fence::observed(epoch, &v);
    for command in [json!({"cmd":"exposure", "request_id":"edit"}), json!({"cmd":"project", "action":"save"}),
        json!({"cmd":"export", "request_id":"export"}), json!({"cmd":"batch", "action":"undo", "batch_id":"batch", "request_id":"undo"}),
        json!({"cmd":"people", "action":"cancel", "request_id":"support-request"})] {
        assert!(crate::project_recovery_fence::issued(epoch, &command).is_err());
    }
    assert!(crate::project_recovery_fence::issued(epoch, &preview_request()).is_err()); // same ID never escapes
    let mut read = preview_request(); read["request_id"] = json!("another-read"); assert!(crate::project_recovery_fence::issued(epoch, &read).is_ok());
    v["action"] = json!("face_decoration_alias_confirm"); v["outcome_unknown"] = json!(false); crate::project_recovery_fence::observed(epoch, &v);
    crate::project_recovery_fence::observed(epoch, &json!({"event":"project_opened"})); assert!(crate::project_recovery_fence::proof(epoch).is_err());
    crate::project_recovery_fence::observed(epoch, &json!({"event":"project_opened", "open":true, "path":"/fixture/project", "project_id":"project", "docs":2, "dirty":false}));
    assert!(crate::project_recovery_fence::proof(epoch).is_ok());
}
#[test] fn reopened_support_history_keeps_distinct_exact_marker_and_complete_restore() {
    let epoch = [178;16]; let marker = json!({"version":1, "review_sha256":crate::batch_api::collarbone::request_digest(&acknowledgment()), "member_count":2});
    crate::project_recovery_fence::observed(epoch, &json!({"event":"session_state", "sync":{"workspace_generation":"support-workspace", "batches":[{
        "batch_id":"support-batch", "module_scope":["lnx.people_graph.v1"], "targets":2, "undone":false, (MARKER):marker}]}}));
    let c = json!({"cmd":"batch", "action":"undo", "request_id":"history", "batch_id":"support-batch"});
    assert_eq!(crate::project_recovery_fence::shared_history_markers(epoch, &c).unwrap(), Some(json!({(MARKER):marker})));
    crate::project_recovery_fence::issued(epoch, &c).unwrap();
    let mut v = json!({"event":"batch_result", "action":"undo", "request_id":"history", "batch_id":"support-batch", "success":true,
        "outcome_unknown":false, "module_scope":["lnx.people_graph.v1"], "restored":[0,1], "conflicts":[], (MARKER):marker});
    assert!(crate::batch_api::history::receipt(&v));
    v["restored"] = json!([0]); assert!(!crate::batch_api::history::receipt(&v)); crate::project_recovery_fence::observed(epoch, &v);
    assert!(crate::project_recovery_fence::proof(epoch).is_err());
    v["restored"] = json!([0,1]); v["face_decoration_alias_review"] = marker.clone(); assert!(!crate::batch_api::history::receipt(&v));
    v.as_object_mut().unwrap().remove("face_decoration_alias_review"); crate::project_recovery_fence::observed(epoch, &v); assert!(crate::project_recovery_fence::proof(epoch).is_ok());
}
#[test] fn scalar_alias_host_binding_is_reachable_without_changing_its_wire_protocol() {
    // people() now calls begin_command for this existing action rather than the
    // old begin_bound path which silently discarded the already-defined binding.
    let c = request("face_decoration_alias_confirm", json!({"token":"8".repeat(32), "ack":acknowledgment()}));
    let mut h = host(); h.begin_command([176;16], &c).unwrap(); assert!(h.guards_review([176;16], "support-request"));
    h.failed("support-request", "transport lost before receipt");
    let result = h.status("support-request")["result"].clone();
    assert_eq!(result["outcome_unknown"], true);
    assert_eq!(result["face_decoration_alias_request"]["payload"], c["payload"]);
    assert!(result.get(REQUEST).is_none());
}

#[test] fn exact_late_support_terminal_reconciles_only_native_unknown_and_never_known_outcome() {
    let epoch = [179;16]; let c = confirm_request(); let good = confirm_result();
    let mut h = ReceiptHost::<PeopleKind>::default(); h.reset(epoch); h.ready(epoch, true);
    h.begin_command(epoch, &c).unwrap(); crate::project_recovery_fence::issued(epoch, &c).unwrap();
    h.failed("support-request", "native transport closed before terminal was observed");
    let pending = h.status("support-request"); assert_eq!(pending["result"]["outcome_unknown"], true);
    assert!(crate::project_recovery_fence::proof(epoch).is_err());
    let mut wrong = good.clone(); wrong[REQUEST]["payload"]["ack"]["members"][1]["after_sha256"] = json!("0".repeat(64));
    h.receive(epoch, &wrong); assert_eq!(h.status("support-request"), pending);
    h.receive([180;16], &good); assert_eq!(h.status("support-request"), pending);
    h.receive(epoch, &good); assert_eq!(h.status("support-request")["result"], good);
    assert!(crate::project_recovery_fence::proof(epoch).is_ok());
    h.receive(epoch, &wrong); h.failed("support-request", "late duplicate failure");
    assert_eq!(h.status("support-request")["result"], good); // known terminals are immutable

    let mut engine_unknown = receipt_base(&c); engine_unknown["success"] = json!(false);
    engine_unknown["outcome_unknown"] = json!(true); engine_unknown["no_write"] = json!(false);
    engine_unknown["error"] = json!("engine could not prove publication outcome");
    let mut h = host(); h.begin_command([176;16], &c).unwrap(); h.receive([176;16], &engine_unknown);
    let retained = h.status("support-request"); h.receive([176;16], &good); assert_eq!(h.status("support-request"), retained);
    let mut h = host(); h.begin_command([176;16], &c).unwrap(); h.failed("support-request", "native lost terminal");
    h.failed("support-request", "duplicate native failure cannot change provenance");
    h.receive([176;16], &engine_unknown); let retained = h.status("support-request");
    h.receive([176;16], &good); assert_eq!(h.status("support-request"), retained);
}

fn support_history_summary(workspace: &str, marker_key: &str) -> Value {
    json!({"event":"session_state", "sync":{"workspace_generation":workspace, "batches":[{
        "batch_id":"support-history", "module_scope":["lnx.people_graph.v1"], "targets":2, "undone":false,
        (marker_key):{"version":1,"review_sha256":"e".repeat(64),"member_count":2}}]}})
}
fn support_history_command(action: &str) -> Value {
    json!({"cmd":"batch", "action":action, "request_id":"support-history-request", "batch_id":"support-history"})
}
fn support_history_result(action: &str, marker_key: &str) -> Value {
    json!({"event":"batch_result", "action":action, "request_id":"support-history-request", "batch_id":"support-history",
        "success":true, "outcome_unknown":false, "no_write":false, "module_scope":["lnx.people_graph.v1"],
        "restored":[0,1], "conflicts":[], (marker_key):{"version":1,"review_sha256":"e".repeat(64),"member_count":2}})
}
fn support_history_host(epoch: [u8;16], action: &str, marker_key: &str) -> crate::batch_host::BatchHost {
    crate::project_recovery_fence::observed(epoch, &support_history_summary("original-workspace", marker_key));
    let mut h = crate::batch_host::BatchHost::default(); h.reset(epoch); h.ready(epoch, true);
    h.begin_command(epoch, &support_history_command(action)).unwrap(); h
}
#[test] fn support_undo_redo_transport_unknown_needs_same_workspace_marker_and_complete_restore() {
    for (action, epoch) in [("undo", [181;16]), ("redo", [182;16])] {
        let c = support_history_command(action); let good = support_history_result(action, MARKER);
        let mut h = support_history_host(epoch, action, MARKER); crate::project_recovery_fence::issued(epoch, &c).unwrap();
        h.failed("support-history-request", "native transport lost history terminal");
        let retained = h.status("support-history-request"); assert_eq!(retained["result"]["outcome_unknown"], true);
        for (path, bad) in [("/batch_id", json!("another-batch")), ("/restored", json!([0])), ("/module_scope", json!(["lnx.exposure.v1"])),
            ("/request_id", json!("another-request")), ("/action", json!("commit")),
            ("/face_decoration_support_alias_review/review_sha256", json!("f".repeat(64)))] {
            let mut wrong = good.clone(); *wrong.pointer_mut(path).unwrap() = bad;
            h.receive(epoch, &wrong); assert_eq!(h.status("support-history-request"), retained, "{path}");
        }
        h.receive([180;16], &good); assert_eq!(h.status("support-history-request"), retained);
        assert!(crate::project_recovery_fence::proof(epoch).is_err());
        h.receive(epoch, &good); assert_eq!(h.status("support-history-request")["result"], good);
        assert!(crate::project_recovery_fence::proof(epoch).is_ok());
        h.failed("support-history-request", "late transport failure");
        let mut contradicted = good.clone(); contradicted["restored"] = json!([0]); h.receive(epoch, &contradicted);
        assert_eq!(h.status("support-history-request")["result"], good);
    }
}
#[test] fn support_history_engine_unknown_and_changed_workspace_cannot_be_laundered_by_late_success() {
    let good = support_history_result("undo", MARKER);
    let mut engine_unknown = good.clone(); engine_unknown["success"] = json!(false); engine_unknown["outcome_unknown"] = json!(true);
    engine_unknown["error"] = json!("engine could not establish restored graph and bank"); engine_unknown.as_object_mut().unwrap().remove("restored");
    assert!(crate::batch_api::history::receipt(&engine_unknown));
    let epoch = [183;16]; let mut h = support_history_host(epoch, "undo", MARKER);
    h.failed("support-history-request", "native transport unknown"); h.receive(epoch, &engine_unknown);
    let retained = h.status("support-history-request"); h.receive(epoch, &good); assert_eq!(h.status("support-history-request"), retained);

    let epoch = [184;16]; let mut h = support_history_host(epoch, "undo", MARKER); h.failed("support-history-request", "transport unknown");
    let retained = h.status("support-history-request");
    crate::project_recovery_fence::observed(epoch, &support_history_summary("different-workspace", MARKER));
    h.receive(epoch, &good); assert_eq!(h.status("support-history-request"), retained);

    let epoch = [185;16]; let mut h = support_history_host(epoch, "undo", MARKER); h.failed("support-history-request", "transport unknown");
    let retained = h.status("support-history-request"); let mut changed = support_history_summary("original-workspace", MARKER);
    changed["sync"]["batches"][0][MARKER]["review_sha256"] = json!("f".repeat(64));
    crate::project_recovery_fence::observed(epoch, &changed); h.receive(epoch, &good);
    assert_eq!(h.status("support-history-request"), retained);
}
#[test] fn scalar_alias_history_does_not_gain_support_late_terminal_authority() {
    let epoch = [186;16]; let key = "face_decoration_alias_review";
    let mut h = support_history_host(epoch, "undo", key); h.failed("support-history-request", "scalar native transport unknown");
    let retained = h.status("support-history-request"); h.receive(epoch, &support_history_result("undo", key));
    assert_eq!(h.status("support-history-request"), retained);
}
