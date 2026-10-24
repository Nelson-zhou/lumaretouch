// SPDX-License-Identifier: GPL-3.0-or-later
//! AUTHORED / UNRUN. Synthetic source fixtures, not photographic acceptance.
use super::*;
use crate::source_patch_capture_host::Proof;
const PREVIEW: &str = "11111111111111111111111111111111";
const CAPTURE: &str = "22222222222222222222222222222222";
const DOCUMENT: &str = "33333333333333333333333333333333";
const SIBLING: &str = "44444444444444444444444444444444";
fn epoch(tag: u8) -> [u8;16] { let mut value = [249;16]; value[15] = tag; value }
fn proof(epoch: [u8;16]) -> Proof {
    Proof { identity: crate::capture_wire::Identity { epoch, instance:[4;16], capture:[0x22;16], seq:1,
        generation:5, document:6, ticket:7, width:1, height:1, presentation_width:1, presentation_height:1 },
        recipe_document_id:DOCUMENT.into(), recipe_revision:"8".into(),
        descriptor:json!({"domain":"source-input","full_source":[1,1],"projection":{"version":"fixture"}}) }
}
/// Existing original one-pixel RGB transport fixture, not generated render evidence.
fn png() -> Value {
    use base64::{engine::general_purpose::STANDARD, Engine as _}; use sha2::{Digest, Sha256};
    fn chunk(bytes: &mut Vec<u8>, kind: &[u8], data: &[u8]) {
        bytes.extend_from_slice(&(data.len() as u32).to_be_bytes()); let start = bytes.len();
        bytes.extend_from_slice(kind); bytes.extend_from_slice(data); let mut crc = 0xffff_ffffu32;
        for byte in &bytes[start..] { crc ^= u32::from(*byte); for _ in 0..8 { crc = (crc >> 1) ^ ((0u32.wrapping_sub(crc & 1)) & 0xedb8_8320); } }
        bytes.extend_from_slice(&(!crc).to_be_bytes());
    }
    let mut bytes = b"\x89PNG\r\n\x1a\n".to_vec();
    chunk(&mut bytes, b"IHDR", &[0,0,0,1,0,0,0,1,8,2,0,0,0]);
    chunk(&mut bytes, b"IDAT", &[0x78,0x01,0x01,4,0,0xfb,0xff,0,32,64,96,0x01,0x44,0x00,0xc1]);
    chunk(&mut bytes, b"IEND", &[]);
    json!({"mime":"image/png","width":1,"height":1,"sha256":format!("{:x}",Sha256::digest(&bytes)),"base64":STANDARD.encode(bytes)})
}
fn rehash(value: &mut Value) {
    value.as_object_mut().unwrap().remove("review_sha256");
    value["review_sha256"] = json!(crate::batch_api::collarbone::request_digest(value));
}
fn review() -> Value {
    let mut metadata = png(); metadata.as_object_mut().unwrap().remove("base64");
    let active = json!({"version":1,"document_id":DOCUMENT,"revision":"8",
        "source_proof":{"asset_sha256":"a".repeat(64),"original_sha256":"a".repeat(64),"creative_source":null},
        "before_state_sha256":"b".repeat(64),"candidate_state_sha256":"b".repeat(64),
        "before_people_sha256":"c".repeat(64),"candidate_people_sha256":"d".repeat(64),
        "source_size":[1,1],"before_output_size":[1,1],"after_output_size":[1,1],"before":metadata,"after":metadata});
    let mut sibling = active.clone(); sibling["document_id"] = json!(SIBLING); sibling["revision"] = json!("11");
    sibling["source_proof"] = json!({"asset_sha256":"a".repeat(64),"original_sha256":"e".repeat(64),
        "creative_source":{"sha256":"a".repeat(64),"width":1,"height":1}});
    let mut review = json!({"version":2,"token":"f".repeat(32),"target":"eye_bag_preserve",
        "face_ref":{"asset_sha256":"a".repeat(64),"face_instance_id":"face","analysis_revision":1},
        "before_recovery_sha256":null,"recovery_sha256":"1".repeat(64),"visual":active,
        "members":[{"path":"/source.raw","visual":active},{"path":"/source.raw","visual":sibling}]});
    rehash(&mut review); review
}
fn base() -> Value {
    json!({"protocol":2,"preview_id":PREVIEW,"capture_id":CAPTURE,"ticket":"7","document_id":"6",
        "generation":"5","recipe_document_id":DOCUMENT,"recipe_revision":"8"})
}
fn ready(review: &Value) -> Value {
    let mut value = base(); value["state"] = json!("ready"); value["success"] = json!(true);
    value["target"] = json!("eye_bag_preserve");
    value["result"] = json!({"domain":"production-output","quality":"full-source-render-srgb8","review":review}); value
}
fn preview_host(epoch: [u8;16], viewing: bool) -> RecoveryPreviewHost {
    let mut host = RecoveryPreviewHost::default(); host.reset(epoch);
    host.begin(epoch, PREVIEW, CAPTURE, "7", "6", &json!("eye_bag_preserve")).unwrap();
    host.bind_capture(&proof(epoch), viewing); host.receive(epoch, &ready(&review())); host
}
fn image_command(review: &Value, index: usize, side: &str) -> Value {
    let mut command = base(); let own = &review["members"][index]["visual"];
    command["cmd"] = json!("effect_recovery_preview"); command["action"] = json!("image");
    command["request_id"] = json!(format!("image-{index}-{side}")); command["review_sha256"] = review["review_sha256"].clone();
    command["member_document_id"] = own["document_id"].clone(); command["member_revision"] = own["revision"].clone();
    command["side"] = json!(side); command["sha256"] = own[side]["sha256"].clone(); command
}
fn image_result(command: &Value) -> Value {
    let mut value = command.clone(); value.as_object_mut().unwrap().remove("cmd"); value.as_object_mut().unwrap().remove("action");
    value["state"] = json!("image"); value["success"] = json!(true); value["image"] = png(); value
}
fn deliver(host: &mut RecoveryPreviewHost, epoch: [u8;16]) {
    assert_eq!(host.status(epoch, PREVIEW)["state"], "ready");
    for member in 0..2 { for side in ["before", "after"] {
        let command = image_command(&review(), member, side); host.begin_image(&command).unwrap();
        host.receive(epoch, &image_result(&command));
        assert_eq!(host.image_status(epoch, PREVIEW, command["request_id"].as_str().unwrap())["state"], "image");
    } }
}
#[test] fn metadata_only_partial_or_unpresented_alias_review_cannot_redeem() {
    let epoch = epoch(1); let ack = alias::expected_ack(&review()); let mut host = preview_host(epoch, false);
    assert!(host.allow_presented_aliases(&ack).is_err()); host.status(epoch, PREVIEW);
    assert!(host.allow_presented_aliases(&ack).is_err()); assert!(host.allow_presented().is_err()); assert!(host.redeem().is_err());
    deliver(&mut host, epoch); assert!(host.redeem_aliases(&ack).is_err());
    let mut reversed = ack.clone(); reversed["members"].as_array_mut().unwrap().reverse();
    assert!(host.allow_presented_aliases(&reversed).is_err()); host.allow_presented_aliases(&ack).unwrap();
    assert!(host.redeem_aliases(&ack).is_err());
    let mut shown = base(); shown["state"] = json!("presented"); shown["success"] = json!(true);
    shown["review_sha256"] = ack["review_sha256"].clone(); host.receive(epoch, &shown);
    assert_eq!(host.status(epoch, PREVIEW)["review_sha256"], ack["review_sha256"]);
    host.redeem_aliases(&ack).unwrap(); assert!(host.redeem_aliases(&ack).is_err());
}
#[test] fn image_bytes_hash_member_revision_and_first_terminal_are_not_metadata() {
    for (path, replacement) in [("/image/base64", json!("AAAA")), ("/member_revision", json!("12")),
        ("/member_document_id", json!(DOCUMENT)), ("/side", json!("after")), ("/sha256", json!("e".repeat(64))),
        ("/image/width", json!(2)), ("/review_sha256", json!("e".repeat(64)))] {
        let epoch = epoch(2); let mut host = preview_host(epoch, false); host.status(epoch, PREVIEW);
        let command = image_command(&review(), 1, "before"); host.begin_image(&command).unwrap();
        let mut bad = image_result(&command); *bad.pointer_mut(path).unwrap() = replacement; host.receive(epoch, &bad);
        let id = command["request_id"].as_str().unwrap(); let retained = host.image_status(epoch, PREVIEW, id);
        assert_eq!(retained["state"], "failed", "{path}"); host.receive(epoch, &image_result(&command));
        assert_eq!(host.image_status(epoch, PREVIEW, id), retained); assert!(host.allow_presented_aliases(&alias::expected_ack(&review())).is_err());
    }
}
#[test] fn capture_frame_epoch_mapping_and_view_only_keep_their_separate_fences() {
    let epoch = epoch(3); let mut host = preview_host(epoch, true); let original = proof(epoch);
    assert!(host.matches_capture(&original)); let mut changed = original.clone(); changed.identity.instance = [9;16];
    assert!(!host.matches_capture(&changed)); changed = original.clone(); changed.descriptor["projection"]["version"] = json!("other");
    assert!(!host.matches_capture(&changed)); changed = original; changed.recipe_revision = "9".into(); assert!(!host.matches_capture(&changed));
    deliver(&mut host, epoch); let ack = alias::expected_ack(&review()); host.allow_presented_aliases(&ack).unwrap();
    let mut shown = base(); shown["state"] = json!("presented"); shown["success"] = json!(true); shown["review_sha256"] = ack["review_sha256"].clone();
    host.receive([8;16], &shown); assert!(host.redeem_aliases(&ack).is_err()); host.receive(epoch, &shown);
    assert!(host.redeem_aliases(&ack).is_err()); host.ended(epoch); assert_eq!(host.status(epoch, PREVIEW)["state"], "stale");
}
#[test] fn exact_cancellation_clears_alias_images_without_inventing_a_failure() {
    let epoch = epoch(4); let mut host = preview_host(epoch, false); host.status(epoch, PREVIEW);
    let mut cancel = base(); cancel["state"] = json!("cancelled"); cancel["success"] = json!(true); host.receive(epoch, &cancel);
    assert_eq!(host.status(epoch, PREVIEW)["state"], "cancelled");
    assert!(host.begin_image(&image_command(&review(), 0, "before")).is_err()); assert!(host.redeem_aliases(&alias::expected_ack(&review())).is_err());
}
fn apply() -> Value {
    let mut value = base(); value["cmd"] = json!("effect_recovery"); value["action"] = json!("apply");
    value["request_id"] = json!("recovery-original"); value["ack"] = alias::expected_ack(&review()); value
}
fn applied(command: &Value) -> Value {
    let mut value = command.clone(); value.as_object_mut().unwrap().remove("cmd");
    value["success"] = json!(true); value["outcome_unknown"] = json!(false); value["requires_reload"] = json!(false); value["no_change"] = json!(false); value["no_write"] = json!(false);
    value["batch_id"] = json!("recovery-batch"); value["module_scope"] = json!(["lnx.people_graph.v1"]);
    value[alias::MARKER] = json!({"version":1,"review_sha256":command["ack"]["review_sha256"],"member_count":2});
    value["alias_members"] = json!([{ "document_id":DOCUMENT,"expected_revision":"8","result_revision":"9" },
        { "document_id":SIBLING,"expected_revision":"11","result_revision":"12" }]);
    value["doc_state"] = json!({"document_id":"6","people":{"binding":{"document_id":DOCUMENT,"document_revision":9}}});
    value["history"] = json!({"undo_steps":0,"redo_steps":0}); value
}
fn receipt_host(epoch: [u8;16], command: &Value) -> RecoveryHost {
    let mut host = RecoveryHost::default(); host.reset(epoch); host.ready(epoch, true);
    host.begin_bound_command(epoch, command, Some(&binding("6", CAPTURE, "7", PREVIEW).unwrap())).unwrap(); host
}
fn opened() -> Value { json!({"event":"project_opened","open":true,"path":"/actual/project.lrt","project_id":"project","docs":2,"dirty":false}) }
#[test] fn original_alias_receipt_binds_all_members_source_generation_and_publication() {
    let command = apply(); let good = applied(&command); assert!(alias::receipt(&good));
    for (path, changed) in [("/protocol",json!(1)),("/generation",json!("9")),("/recipe_revision",json!("9")),
        ("/ack/members/1/before_sha256",json!("e".repeat(64))),("/alias_members/1/result_revision",json!("13")),
        ("/eye_bag_recovery_alias_review/review_sha256",json!("e".repeat(64))),("/doc_state/people/binding/document_revision",json!(8)),
        ("/module_scope",json!(["lnx.eye_bags.v2"])),("/no_change",json!(true))] {
        let epoch = epoch(5); let mut host = receipt_host(epoch, &command);
        let mut wrong = good.clone(); *wrong.pointer_mut(path).unwrap() = changed; host.receive(epoch, &wrong);
        let retained = host.status("recovery-original"); assert_eq!(retained["result"]["outcome_unknown"], true, "{path}");
        assert_eq!(retained["result"]["ack"], command["ack"]); assert_eq!(retained["result"]["generation"], command["generation"]);
        host.receive(epoch, &good); assert_eq!(host.status("recovery-original"), retained);
    }
}
#[test] fn unknown_alias_receipt_is_query_only_until_actual_workspace_reopen() {
    let epoch = epoch(6); let command = apply(); let mut host = receipt_host(epoch, &command);
    crate::project_recovery_fence::issued(epoch, &command).unwrap(); host.failed("recovery-original", "Transport outcome unknown");
    let retained = host.status("recovery-original"); assert_eq!(retained["result"]["protocol"], 2);
    for command in [json!({"cmd":"exposure","action":"status","exposure":1}),json!({"cmd":"project","action":"save"}),
        json!({"cmd":"export","path":"/output.png"}),json!({"cmd":"batch","action":"undo","batch_id":"recovery-batch","request_id":"new"})] {
        assert!(crate::project_recovery_fence::issued(epoch, &command).is_err());
    }
    host.receive(epoch, &applied(&command)); assert_eq!(host.status("recovery-original"), retained);
    crate::project_recovery_fence::observed(epoch, &json!({"event":"project_opened"})); assert!(crate::project_recovery_fence::proof(epoch).is_err());
    crate::project_recovery_fence::observed(epoch, &opened()); assert!(crate::project_recovery_fence::proof(epoch).is_ok());
}
#[test] fn raw_engine_events_are_guarded_before_native_recovery_fence_observation() {
    let source = include_str!("engine.rs");
    let guard = source.find("st.effect_recovery.lock().map(|h|h.guards_review(inspection_epoch,id))").unwrap();
    let observation = source.find("if !scalar_review").unwrap(); assert!(guard < observation);
    let source = include_str!("receipt_host.rs");
    assert!(source.find("!review.matches(value)").unwrap() < source.find("crate::project_recovery_fence::observed(epoch, &observed)").unwrap());
}

#[test] fn cancellation_never_reanimates_from_late_pages_or_ready_events() {
    let epoch = epoch(7); let mut host = preview_host(epoch, false); host.status(epoch, PREVIEW);
    let command = image_command(&review(), 0, "before"); host.begin_image(&command).unwrap();
    let mut cancelled = base(); cancelled["state"] = json!("cancelled"); cancelled["success"] = json!(true);
    host.receive(epoch, &cancelled); host.receive(epoch, &image_result(&command)); host.receive(epoch, &ready(&review()));
    assert_eq!(host.status(epoch, PREVIEW)["state"], "cancelled");
    assert_eq!(host.image_status(epoch, PREVIEW, command["request_id"].as_str().unwrap())["state"], "stale");
}
#[test] fn recovery_review_rejects_wrong_hash_member_set_source_and_recipe_mutation() {
    let original = review(); let proof = proof(epoch(8)); assert!(alias::review(&original, &proof));
    for (path, changed) in [("/members/1/visual/document_id",json!(DOCUMENT)),("/members/1/visual/revision",json!("011")),
        ("/members/1/visual/candidate_state_sha256",json!("e".repeat(64))),
        ("/members/1/visual/candidate_people_sha256",json!("e".repeat(64))),
        ("/members/1/visual/source_size",json!([2,1])),("/members/1/visual/after/width",json!(2)),
        ("/target",json!("skin_smoothing")),("/visual/revision",json!("9"))] {
        let mut changed_review = original.clone(); *changed_review.pointer_mut(path).unwrap() = changed; rehash(&mut changed_review);
        assert!(!alias::review(&changed_review, &proof), "{path}");
    }
    let mut wrong_hash = original; wrong_hash["review_sha256"] = json!("e".repeat(64)); assert!(!alias::review(&wrong_hash, &proof));
}
#[test] fn strict_known_no_write_or_compensation_does_not_claim_a_batch() {
    let command = apply(); let epoch = epoch(9); let mut failed = command.clone(); failed.as_object_mut().unwrap().remove("cmd");
    failed["success"] = json!(false); failed["outcome_unknown"] = json!(false); failed["requires_reload"] = json!(false);
    failed["error"] = json!("Source changed before claim"); failed["no_write"] = json!(true);
    assert!(alias::receipt(&failed));
    let mut host = receipt_host(epoch, &command); crate::project_recovery_fence::issued(epoch, &command).unwrap();
    host.receive(epoch, &failed); assert!(crate::project_recovery_fence::proof(epoch).is_ok());
    failed["no_write"] = json!(false); assert!(!alias::receipt(&failed));
    failed["rolled_back"] = json!(true); assert!(alias::receipt(&failed));
    failed["batch_id"] = json!("unproven-batch"); assert!(!alias::receipt(&failed));
    failed["outcome_unknown"] = json!(true); failed["requires_reload"] = json!(true); assert!(alias::receipt(&failed));
}
#[test] fn uncertain_publication_retains_only_validated_bounded_batch_diagnostics() {
    let command = apply(); let epoch = epoch(10); let mut value = applied(&command);
    value["success"] = json!(false); value["outcome_unknown"] = json!(true); value["requires_reload"] = json!(true);
    value["error"] = json!("Readback failed after publication"); value["large_extension"] = json!("x".repeat(100_000));
    let mut host = receipt_host(epoch, &command); host.receive(epoch, &value); let retained = host.status("recovery-original")["result"].clone();
    assert_eq!(retained[alias::MARKER], value[alias::MARKER]); assert_eq!(retained["alias_members"], value["alias_members"]);
    assert!(retained.get("large_extension").is_none()); assert!(retained.get("doc_state").is_none());
    let epoch = self::epoch(11); for key in ["alias_members", alias::MARKER] { value.as_object_mut().unwrap().remove(key); }
    let mut host = receipt_host(epoch, &command); host.receive(epoch, &value);
    assert_eq!(host.status("recovery-original")["result"]["batch_id"], "recovery-batch");
    assert!(host.status("recovery-original")["result"].get(alias::MARKER).is_none());
}

#[test] fn another_eye_review_family_cannot_be_smuggled_into_recovery_publication() {
    let command = apply(); let value = applied(&command);
    for key in ["eye_bag_preset_alias_review", "eye_bag_alias_review", "eye_bag_batch_review", "eye_bag_cohort_review", "eye_bag_preset_ack", "eye_bag_request"] {
        let mut mixed = value.clone(); mixed[key] = json!({}); assert!(!alias::receipt(&mixed));
    }
}
