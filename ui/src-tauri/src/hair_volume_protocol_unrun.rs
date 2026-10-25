// SPDX-License-Identifier: GPL-3.0-or-later
//! AUTHORED / UNRUN. Synthetic transport fixtures only, not image-quality proof.
use super::*;
use base64::{engine::general_purpose::STANDARD, Engine as _};
use sha2::{Digest, Sha256};

const EPOCH: [u8; 16] = [79; 16];
fn context() -> Value {
    json!({"document_id":"doc", "document_epoch":"workspace", "document_revision":2,
        "state_revision":3, "association_revision":4, "target":{"scope":"face", "target_id":"face",
            "face_ref":{"asset_sha256":"a".repeat(64), "face_instance_id":"face", "analysis_revision":5}}})
}
fn request(id: &str, action: &str, payload: Value) -> Value {
    json!({"cmd":"hair_volume", "protocol":1, "operation_id":OPERATION, "request_id":id,
        "action":action, "people_context":context(), "payload":payload})
}
fn recipe(amount: f64) -> Value {
    json!({"version":1, "crown":{"version":1, "amount":amount},
        "sides":{"version":1, "linked":true, "left":0, "right":0}})
}
fn source() -> Value { json!({"sha256":"a".repeat(64), "width":100, "height":100}) }
fn patch() -> Value {
    json!({"x":[0.1,0.2,0.8,0.9], "y":[0.1,0.2,0.7,0.9],
        "contour":[[0.3,0.4],[0.5,0.4],[0.7,0.4]], "hair_samples":[[0.3,0.5],[0.5,0.5],[0.7,0.5]],
        "background_samples":[[0.3,0.3],[0.5,0.3],[0.7,0.3]]})
}
fn preview_request(id: &str) -> Value {
    request(id, "preview", json!({"recipe":recipe(0.3), "regions":{"crown":patch(), "left":null, "right":null},
        "protection":{"ears":[], "neck":[], "other_people":[], "visible_anatomy_reviewed":true, "whole_source_reviewed":true},
        "confirmed":true, "crown_confirmed":true, "left_confirmed":false, "right_confirmed":false}))
}
fn host() -> Mailbox { Mailbox { epoch:EPOCH, supported:true, native_available:true, ..Default::default() } }
fn admit(host: &mut Mailbox, request: &Value) {
    host.begin(EPOCH, request).unwrap(); host.rows.back_mut().unwrap().dispatched = true;
}
fn result(request: &Value, payload: Value) -> Value {
    let mut value = failure(request, "fixture");
    value.as_object_mut().unwrap().remove("error");
    value["success"] = json!(true); value["outcome_unknown"] = json!(false); value["payload"] = payload;
    value
}
/// A two-by-two black RGB8 PNG, built only when explicitly running fixtures.
/// Its uncompressed zlib stream describes two scanlines, not a portrait output.
fn image() -> Value {
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
    let mut zlib = vec![0x78,0x01,0x01,14,0,0xf1,0xff];
    zlib.extend_from_slice(&[0; 14]); zlib.extend_from_slice(&[0,14,0,1]);
    chunk(&mut bytes, b"IDAT", &zlib); chunk(&mut bytes, b"IEND", &[]);
    json!({"png":format!("data:image/png;base64,{}", STANDARD.encode(&bytes)),
        "sha256":format!("{:x}", Sha256::digest(&bytes)), "width":2, "height":2})
}
fn context_result(request: &Value) -> Value {
    let image = image();
    result(request, json!({"kind":"context", "source":source(), "face_ref":context()["target"]["face_ref"],
        "recipe":recipe(0.0), "source_kind":"original", "semantic_evidence_sha256":"e".repeat(64),
        "source_png":image["png"], "source_png_sha256":image["sha256"], "source_width":100, "source_height":100,
        "source_preview_width":2, "source_preview_height":2, "native_available":true, "notice":"UNRUN fixture"}))
}
fn retain_context(host: &mut Mailbox) {
    let request = request("context", "context", json!({})); admit(host, &request);
    assert!(host.observe(EPOCH, &context_result(&request)).is_none()); assert!(host.rows.back().unwrap().settled);
}
fn preview_result(request: &Value) -> Value {
    let mut payload = json!({"kind":"preview", "preview_id":"1".repeat(32), "review_token":"2".repeat(64),
        "preview_sha256":"2".repeat(64), "support_asset_sha256":"b".repeat(64),
        "semantic_evidence_sha256":"e".repeat(64), "source":source(), "source_width":100, "source_height":100,
        "face_ref":context()["target"]["face_ref"], "recipe":request["payload"]["recipe"],
        "regions":request["payload"]["regions"], "protection":request["payload"]["protection"]});
    let image = image();
    for prefix in ["before", "after", "support"] {
        for key in ["png", "sha256", "width", "height"] { payload[format!("{prefix}_{key}")] = image[key].clone(); }
    }
    result(request, payload)
}
fn ack(preview: &Value) -> Value {
    let mut payload = json!({});
    for key in ["preview_id", "review_token", "before_sha256", "after_sha256", "support_sha256"] {
        payload[key] = preview["payload"][key].clone();
    }
    payload
}
fn commit_request() -> Value {
    request("commit", "commit", json!({"preview_id":"1".repeat(32), "review_token":"2".repeat(64), "confirmed":true}))
}
fn publication(request: &Value) -> Value {
    let is_commit = request["action"] == "commit";
    let recipe = recipe(if is_commit { 0.3 } else { 0.0 });
    let mut value = result(request, json!({"kind":if is_commit { "confirmed" } else { "cleared" },
        "committed":true, "recipe":recipe, "asset_sha256":if is_commit { json!("b".repeat(64)) } else { Value::Null }}));
    value["doc_state"] = json!({"people":{"revision":4, "association_revision":4,
        "binding":{"document_id":"doc", "document_epoch":"workspace", "document_revision":3, "asset_sha256":"a".repeat(64)},
        "selected_face_id":"face", "editing_target":context()["target"],
        "resolved":{"face_ref":context()["target"]["face_ref"], "state_revision":4, "association_revision":4,
            "operations":{OPERATION:{"/crown/amount":{"value":recipe["crown"]["amount"]},
                "/sides/linked":{"value":true}, "/sides/left":{"value":0}, "/sides/right":{"value":0}}}}}});
    value
}
fn retain_presented(host: &mut Mailbox) -> Value {
    retain_context(host);
    let preview = preview_request("preview"); admit(host, &preview);
    let rendered = preview_result(&preview); host.observe(EPOCH, &rendered);
    assert!(host.rows.back().unwrap().settled);
    let presented = request("presented", "presented", ack(&rendered)); admit(host, &presented);
    let mut payload = presented["payload"].clone(); payload["kind"] = json!("presented"); payload["presented"] = json!(true);
    host.observe(EPOCH, &result(&presented, payload)); assert!(host.rows.back().unwrap().settled);
    rendered
}

#[test]
fn exact_family_target_and_independent_source_contours() {
    let valid = preview_request("preview"); assert!(validate(&valid).is_ok());
    for path in ["/cmd", "/protocol", "/operation_id", "/people_context/target/scope", "/payload/regions/crown/x",
        "/payload/confirmed", "/payload/crown_confirmed", "/payload/protection/whole_source_reviewed"] {
        let mut value = valid.clone(); *value.pointer_mut(path).unwrap() = json!("foreign"); assert!(validate(&value).is_err(), "{path}");
    }
    for (path, replacement) in [("/payload/regions/crown/contour/1/0", 0.3),
        ("/payload/regions/crown/hair_samples/0/1", 0.4), ("/payload/regions/crown/background_samples/0/1", 0.4)] {
        let mut value = valid.clone(); *value.pointer_mut(path).unwrap() = json!(replacement); assert!(validate(&value).is_err(), "{path}");
    }
    let mut value = valid.clone(); value["payload"]["recipe"]["sides"]["left"] = json!(0.2); assert!(validate(&value).is_err());
    let mut value = valid.clone(); value["payload"]["regions"]["left"] = patch(); assert!(validate(&value).is_err());
    let mut value = valid.clone(); value["payload"]["recipe"] = recipe(0.0); assert!(validate(&value).is_err());
    let mut value = valid; value["payload"]["source_mask"] = json!({}); assert!(validate(&value).is_err());
}
#[test]
fn own_confirmation_and_protection_bounds_are_not_shared_masks() {
    let valid = preview_request("preview");
    for (field, maximum) in [("ears", 2), ("neck", 1), ("other_people", 64)] {
        let mut value = valid.clone(); value["payload"]["protection"][field] = json!(vec![[0.1,0.1,0.2,0.2]; maximum]);
        assert!(validate(&value).is_ok());
        value["payload"]["protection"][field].as_array_mut().unwrap().push(json!([0.1,0.1,0.2,0.2]));
        assert!(validate(&value).is_err());
    }
    let mut host = host(); assert!(host.begin(EPOCH, &valid).is_err()); assert!(host.rows.is_empty());
    retain_context(&mut host); assert!(host.begin(EPOCH, &valid).is_ok());
}
#[test]
fn source_pixel_geometry_is_bound_to_retained_reference() {
    let valid = preview_request("preview"); assert!(protocol::source_geometry(&valid["payload"], &source()));
    let mut small = source(); small["width"] = json!(10); assert!(!protocol::source_geometry(&valid["payload"], &small));
    let mut value = valid.clone(); value["payload"]["regions"]["crown"]["x"] = json!([0.1,0.11,0.8,0.9]);
    assert!(validate(&value).is_ok()); assert!(!protocol::source_geometry(&value["payload"], &source()));
    let mut host = host(); retain_context(&mut host);
    host.rows[0].result.as_mut().unwrap()["payload"]["semantic_evidence_sha256"] = Value::Null;
    assert!(host.begin(EPOCH, &valid).is_err());
}
#[test]
fn context_and_full_review_validate_real_png_framing_hashes_and_dimensions() {
    let context = request("context", "context", json!({})); let reference = context_result(&context);
    let preview = preview_request("preview"); let rendered = preview_result(&preview);
    assert!(valid_result(&reference, &context)); assert!(valid_result(&rendered, &preview));
    for field in ["before_sha256", "after_sha256", "support_sha256", "preview_sha256"] {
        let mut value = rendered.clone(); value["payload"][field] = json!("c".repeat(64)); assert!(!valid_result(&value, &preview));
    }
    let mut value = rendered.clone(); value["payload"]["support_width"] = json!(3); assert!(!valid_result(&value, &preview));
    let mut value = reference.clone(); value["payload"]["source_png_sha256"] = json!("c".repeat(64)); assert!(!valid_result(&value, &context));
    let mut value = reference; value["payload"]["source_kind"] = json!("guessed"); assert!(!valid_result(&value, &context));
    let mut value = rendered; let url = value["payload"]["before_png"].as_str().unwrap();
    let mut bytes = STANDARD.decode(url.strip_prefix("data:image/png;base64,").unwrap()).unwrap();
    bytes[29] ^= 1;
    value["payload"]["before_png"] = json!(format!("data:image/png;base64,{}", STANDARD.encode(&bytes)));
    value["payload"]["before_sha256"] = json!(format!("{:x}", Sha256::digest(&bytes)));
    assert!(!valid_result(&value, &preview));
}
#[test]
fn preview_cannot_exchange_source_or_semantic_evidence_after_context() {
    let mut host = host(); retain_context(&mut host); let request = preview_request("preview"); admit(&mut host, &request);
    let mut value = preview_result(&request); value["payload"]["semantic_evidence_sha256"] = json!("f".repeat(64));
    assert!(valid_result(&value, &request)); assert!(host.observe(EPOCH, &value).is_none());
    assert!(!host.rows.back().unwrap().settled);
    host.observe(EPOCH, &preview_result(&request)); assert!(host.rows.back().unwrap().settled);
}
#[test]
fn exact_presented_tuple_is_required_before_single_commit() {
    let mut host = host(); retain_context(&mut host); let preview = preview_request("preview"); admit(&mut host, &preview);
    let rendered = preview_result(&preview); host.observe(EPOCH, &rendered);
    assert!(host.begin(EPOCH, &commit_request()).is_err());
    let mut presented = request("presented", "presented", ack(&rendered));
    presented["payload"]["support_sha256"] = json!("f".repeat(64)); assert!(host.begin(EPOCH, &presented).is_err());
    let mut host = self::host(); retain_presented(&mut host); let commit = commit_request(); admit(&mut host, &commit);
    let mut wrong = publication(&commit); wrong["payload"]["asset_sha256"] = json!("c".repeat(64));
    assert!(host.observe(EPOCH, &wrong).is_none()); assert!(!host.rows.back().unwrap().settled);
    assert!(host.observe(EPOCH, &publication(&commit)).is_some());
    let mut second = commit; second["request_id"] = json!("second-commit"); assert!(host.begin(EPOCH, &second).is_err());
}
#[test]
fn publication_requires_current_photo_face_and_all_four_canonical_leaves() {
    let request = request("clear", "clear", json!({})); let value = publication(&request); assert!(valid_result(&value, &request));
    for path in ["/doc_state/people/binding/document_epoch", "/doc_state/people/binding/asset_sha256",
        "/doc_state/people/selected_face_id", "/doc_state/people/editing_target", "/doc_state/people/resolved/face_ref",
        "/doc_state/people/resolved/operations/lnx.hair_volume.v1/~1crown~1amount/value",
        "/doc_state/people/resolved/operations/lnx.hair_volume.v1/~1sides~1linked/value",
        "/doc_state/people/resolved/operations/lnx.hair_volume.v1/~1sides~1left/value",
        "/doc_state/people/resolved/operations/lnx.hair_volume.v1/~1sides~1right/value"] {
        let mut wrong = value.clone(); *wrong.pointer_mut(path).unwrap() = Value::Null;
        assert!(!valid_result(&wrong, &request), "{path}");
    }
    let mut wrong = value; wrong["doc_state"]["people"]["binding"]["document_revision"] = json!(1);
    assert!(!valid_result(&wrong, &request));
}
#[test]
fn strict_epoch_context_request_and_first_terminal_ownership() {
    let request = request("clear", "clear", json!({})); let done = publication(&request);
    for path in ["/event", "/operation_id", "/action", "/document_id", "/people_context/document_revision", "/request_payload"] {
        let mut host = host(); admit(&mut host, &request); let mut wrong = done.clone();
        *wrong.pointer_mut(path).unwrap() = json!("foreign");
        assert!(host.observe(EPOCH, &wrong).is_none()); assert!(!host.rows[0].settled);
    }
    let mut host = host(); admit(&mut host, &request);
    assert!(host.observe([80;16], &done).is_none()); assert!(!host.rows[0].settled);
    assert!(host.observe(EPOCH, &done).is_some());
    assert!(host.observe(EPOCH, &failure(&request, "contradiction")).is_none()); assert_eq!(host.status("clear")["result"], done);
}
#[test]
fn uncertainty_late_original_terminal_and_epoch_replacement_remain_query_only() {
    let mut host = host(); let request = request("clear", "clear", json!({})); admit(&mut host, &request);
    host.unknown(EPOCH, "clear", "write outcome unknown"); host.end(EPOCH);
    host.epoch = [80;16]; host.ended = false; host.supported = true; host.native_available = true;
    assert!(host.replay(&request).unwrap()); assert_eq!(host.status("clear")["result"]["outcome_unknown"], true);
    let replacement = self::request("new-clear", "clear", json!({})); assert!(host.begin([80;16], &replacement).is_err());
    assert!(host.observe(EPOCH, &publication(&request)).is_some()); assert!(host.rows[0].settled);
}
#[test]
fn native_reopen_retains_unknown_requests_and_cannot_be_forged_by_backend() {
    let mut host = host(); let settled = request("settled", "context", json!({})); admit(&mut host, &settled);
    let terminal = context_result(&settled); host.observe(EPOCH, &terminal);
    let read = request("read", "context", json!({})); admit(&mut host, &read);
    let clear = request("clear", "clear", json!({})); admit(&mut host, &clear);
    for marker in [json!(true), json!(false), Value::Null] {
        let mut forged = publication(&clear); forged["workspace_reopened"] = marker;
        assert!(!valid_result(&forged, &clear)); assert!(host.observe(EPOCH, &forged).is_none());
    }
    host.end(EPOCH); let replacement = [80;16]; host.epoch = replacement; host.ended = false;
    host.reopen(EPOCH, &json!({"event":"project_opened","docs":1}));
    host.reopen(replacement, &json!({"event":"project_opened"}));
    assert!(host.status("clear")["result"].get("workspace_reopened").is_none());
    host.reopen(replacement, &json!({"event":"project_opened","docs":1}));
    for original in [&read, &clear] {
        let result = host.status(original["request_id"].as_str().unwrap())["result"].clone();
        assert_eq!(result["workspace_reopened"], true); assert_eq!(result["outcome_unknown"], true); assert_eq!(result["success"], false);
        assert_eq!(result["people_context"], original["people_context"]); assert_eq!(result["request_payload"], original["payload"]);
    }
    assert_eq!(host.status("settled")["result"], terminal); assert!(host.replay(&clear).unwrap());
    assert!(host.observe(EPOCH, &publication(&clear)).is_none());
}
#[test]
fn missing_native_keeps_context_and_neutral_clear_but_not_nonzero_preview() {
    let mut host = host(); host.native_available = false;
    assert!(host.begin(EPOCH, &request("context", "context", json!({}))).is_ok());
    assert!(host.begin(EPOCH, &request("clear", "clear", json!({}))).is_ok());
    assert!(host.begin(EPOCH, &preview_request("preview")).is_err());
}
#[test]
fn tombstones_survive_capacity_eviction_and_changed_content_is_never_replayed() {
    let mut host = host(); let first = request("first", "context", json!({})); admit(&mut host, &first);
    host.observe(EPOCH, &context_result(&first));
    for i in 0..MAX_ROWS {
        let request = request(&format!("read-{i}"), "context", json!({})); admit(&mut host, &request);
        host.observe(EPOCH, &context_result(&request));
    }
    assert_eq!(host.status("first")["phase"], "unavailable"); assert!(host.replay(&first).unwrap());
    let mut changed = first; changed["people_context"]["document_revision"] = json!(99); assert!(host.replay(&changed).is_err());
    let mut host = self::host(); host.tombstone_bytes = TOMBSTONE_BYTES;
    assert!(host.begin(EPOCH, &request("new", "context", json!({}))).is_err()); assert!(host.rows.is_empty());
}
#[test]
fn live_pending_budget_never_evicts_a_possible_mutation() {
    let mut host = host(); let clear = request("clear", "clear", json!({})); admit(&mut host, &clear);
    for i in 0..3 {
        let query = request(&format!("status-{i}"), "status", json!({"original_request_id":"clear"})); admit(&mut host, &query);
    }
    let fourth = request("status-overflow", "status", json!({"original_request_id":"clear"}));
    assert!(host.begin(EPOCH, &fourth).is_err()); assert_eq!(host.rows.len(), 4);
    assert_eq!(host.rows[0].request["request_id"], "clear"); assert!(!host.rows[0].settled); assert!(!host.rows[0].retired);
    assert!(!host.seen.contains_key("status-overflow"));
}
#[test]
fn status_read_has_no_original_mutation_settlement_authority() {
    let mut host = host(); let clear = request("clear", "clear", json!({})); admit(&mut host, &clear);
    let query = request("query", "status", json!({"original_request_id":"clear"})); admit(&mut host, &query);
    let reply = result(&query, json!({"kind":"status", "original_request_id":"clear", "found":true, "result":publication(&clear)}));
    assert!(valid_result(&reply, &query)); assert!(host.observe(EPOCH, &reply).is_none());
    assert!(!host.rows[0].settled); assert!(host.rows[1].settled);
}
#[test]
fn malformed_json_duplicates_nonfinite_and_trailing_content_are_rejected() {
    for raw in [r#"{"event":"hair_volume_result","event":"other"}"#,
        r#"{"payload":{"crown":{"amount":0.1,"amount":0.2}}}"#, "{} {}", "{\"number\":1e999}"] {
        assert!(unique_json(raw).is_none());
    }
    assert!(unique_json("{}").is_some()); assert!(same(&json!({"point":[1,0.5]}), &json!({"point":[1.0,0.5]})));
    assert!(!same(&json!({"point":[1,0.5]}), &json!({"point":[1.0,0.6]})));
}
