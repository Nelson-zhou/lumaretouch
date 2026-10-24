// SPDX-License-Identifier: GPL-3.0-or-later
//! AUTHORED / UNRUN. Transport fixture specifications, not runtime acceptance.
use super::*;
use crate::receipt_host::{ReceiptHost, ReceiptKind};
use super::super::PeopleKind;

fn request(action: &str, payload: Value) -> Value {
    json!({"cmd":"people", "request_id":if action == "facial_sculpt_reference" {"sculpt-source"} else {"sculpt-review"},
        "action":action, "payload":payload, "document_id":"photo", "document_epoch":"epoch",
        "document_revision":7, "state_revision":11, "association_revision":3,
        "target":{"scope":"face", "target_id":"face", "face_ref":{"asset_sha256":"a".repeat(64),
            "face_instance_id":"face", "analysis_revision":2}}})
}
fn brush_region() -> Value {
    json!({"recipe":{"version":1, "domain":"source-normalized", "objects":[{
        "id":"sculpt-stroke", "name":"Visible facial structure skin", "enabled":true, "operation":"add", "kind":"brush",
        "opacity":1.0, "feather":8.0, "points":[[0.4,0.5],[0.6,0.5]], "axes":[[0.02,0],[0,0.02]]}]},
        "visible":true, "unoccluded":true, "ownership_confirmed":true})
}
// Authored 2x2 black RGB framing sample. It is not a portrait or a solver output.
fn preview() -> Value {
    use base64::{engine::general_purpose::STANDARD, Engine as _};
    use sha2::{Digest, Sha256};
    fn chunk(bytes: &mut Vec<u8>, kind: &[u8], data: &[u8]) {
        bytes.extend_from_slice(&(data.len() as u32).to_be_bytes());
        let start = bytes.len(); bytes.extend_from_slice(kind); bytes.extend_from_slice(data);
        let mut crc = u32::MAX;
        for byte in &bytes[start..] {
            crc ^= u32::from(*byte);
            for _ in 0..8 { crc = (crc >> 1) ^ ((0u32.wrapping_sub(crc & 1)) & 0xedb8_8320); }
        }
        bytes.extend_from_slice(&(!crc).to_be_bytes());
    }
    let mut bytes = b"\x89PNG\r\n\x1a\n".to_vec();
    chunk(&mut bytes, b"IHDR", &[0,0,0,2,0,0,0,2,8,2,0,0,0]);
    let mut pixels = vec![0x78,0x01,0x01,14,0,241,255];
    pixels.extend_from_slice(&[0;14]); pixels.extend_from_slice(&[0,14,0,1]);
    chunk(&mut bytes, b"IDAT", &pixels); chunk(&mut bytes, b"IEND", &[]);
    json!({"mime":"image/png", "width":2, "height":2, "sha256":format!("{:x}", Sha256::digest(&bytes)),
        "base64":STANDARD.encode(bytes), "source_sha256":"a".repeat(64), "source_width":2, "source_height":2,
        "decoded_width":2, "decoded_height":2, "mapping":"normalized_full_frame", "orientation":"exif_normalized_once"})
}
fn proof() -> Value {
    json!({"source":{"sha256":"a".repeat(64), "width":2, "height":2},
        "face_ref":request("facial_sculpt_reference",json!({}))["target"]["face_ref"],
        "landmark_digest":"b".repeat(64), "preview_sha256":preview()["sha256"], "reference_request_id":"sculpt-source"})
}
fn review_request() -> Value {
    request("facial_sculpt_review",json!({"region":brush_region(), "reference_proof":proof()}))
}
fn result(command: &Value) -> Value {
    let changed = command["action"] == "facial_sculpt_review";
    let payload = if changed {json!({"kind":"facial_sculpt_review", "reference_proof":proof(), "support_sha256":"c".repeat(64)})}
        else {json!({"kind":"facial_sculpt_reference", "reference_proof":proof()})};
    let report = json!({"recipe":{"version":1, "highlight":0.0, "shadow":0.0}, "facts":{},
        "source":proof()["source"], "face_ref":proof()["face_ref"], "landmark_digest":proof()["landmark_digest"], "reviewed":changed,
        "source_preview":if changed {Value::Null} else {preview()}, "reference_proof":if changed {Value::Null} else {proof()},
        "support_sha256":if changed {json!("c".repeat(64))} else {Value::Null}, "native_available":false,
        "support_available":false, "support_reason":"Source-only fixture", "suspended":null,
        "alias_required":false, "alias_reason":null});
    json!({"event":"people_result", "protocol":1, "request_id":command["request_id"], "action":command["action"],
        "document_id":command["document_id"], "success":true, "outcome_unknown":false, "error":null,
        "created_id":null, "batch_id":null, "frame_emitted":changed,
        "facial_sculpt_request":binding(command).unwrap().unwrap()["facial_sculpt_request"], "payload":payload,
        "doc_state":{"people":{"binding":{"document_id":"photo", "document_epoch":"epoch",
            "document_revision":if changed {8} else {7}, "asset_sha256":"a".repeat(64)},
            "revision":if changed {12} else {11}, "association_revision":3, "selected_face_id":"face", "editing_target":command["target"],
            "resolved":{"face_ref":proof()["face_ref"], "state_revision":if changed {12} else {11}, "association_revision":3,
                "operations":{"lnx.facial_sculpt.v1":{"/highlight":{"value":0.0}, "/shadow":{"value":0.0}}}},
            "facial_sculpt":report}}})
}
fn host() -> ReceiptHost<PeopleKind> {
    let mut host = ReceiptHost::default(); host.reset([179;16]); host.ready([179;16],true); host
}
fn released() -> Value {
    let mut value = result(&request("facial_sculpt_reference",json!({})));
    value.as_object_mut().unwrap().remove("payload"); value.as_object_mut().unwrap().remove("doc_state");
    value["payload_released"] = json!(true); value
}

#[test] fn exact_source_read_and_separate_visible_brush_consent_are_admitted() {
    let read = request("facial_sculpt_reference",json!({})); let review = review_request();
    assert!(command(&read).is_ok()); assert!(read_only(&read));
    assert!(command(&review).is_ok()); assert!(!read_only(&review));
    let bound = binding(&review).unwrap().unwrap();
    assert!(fields(&bound, &["facial_sculpt_request"]));
    assert!(fields(&bound["facial_sculpt_request"], REQUEST_FIELDS));
    for (path, bad) in [("/target/scope",json!("person")), ("/payload/region/visible",json!(false)),
        ("/payload/region/unoccluded",json!(false)), ("/payload/region/ownership_confirmed",json!(1)),
        ("/payload/region/recipe/version",json!(2)), ("/payload/region/recipe/domain",json!("display-normalized")),
        ("/payload/region/recipe/objects/0/kind",json!("full")), ("/payload/region/recipe/objects/0/operation",json!("intersect")),
        ("/payload/region/recipe/objects/0/enabled",json!(false)), ("/payload/region/recipe/objects/0/opacity",json!(0)),
        ("/payload/region/recipe/objects/0/points/0/0",json!(-0.01)),
        ("/payload/region/recipe/objects/0/axes",json!([[1,1],[2,2]])),
        ("/payload/reference_proof/source/sha256",json!("f".repeat(64))), ("/payload/reference_proof/source/width",json!(1)),
        ("/payload/reference_proof/face_ref/analysis_revision",json!(3)), ("/payload/reference_proof/reference_request_id",json!(" "))] {
        let mut changed = review.clone(); *changed.pointer_mut(path).unwrap() = bad;
        assert!(command(&changed).is_err(),"{path}");
    }
}

#[test] fn unknown_fields_and_foreign_authority_are_not_a_second_protocol() {
    let review = review_request();
    for path in ["", "/payload", "/payload/reference_proof", "/payload/reference_proof/source", "/payload/region",
        "/payload/region/recipe", "/payload/region/recipe/objects/0"] {
        let mut changed = review.clone(); changed.pointer_mut(path).unwrap()["foreign"] = json!(true);
        assert!(command(&changed).is_err(),"{path}");
    }
    for key in ["face_decoration_request", "alias_members", "alias_review", "support_alias_review", "pattern", "strength"] {
        let mut changed = review.clone(); changed["payload"][key] = json!({}); assert!(command(&changed).is_err(),"{key}");
    }
    for name in ["facial_sculpt_alias_confirm", "facial_sculpt_image", "face_decoration_reference", "facial_sculpt_reference_extra"] {
        let other = request(name,json!({})); assert!(!action(&other)); assert!(!read_only(&other)); assert!(binding(&other).unwrap().is_none());
    }
}

#[test] fn brush_stack_is_unique_bounded_and_requires_an_enabled_add() {
    let good = brush_region();
    let mut value = good.clone(); let object = value["recipe"]["objects"][0].clone();
    value["recipe"]["objects"].as_array_mut().unwrap().push(object); assert!(!region(&value));
    value = good.clone(); value["recipe"]["objects"][0]["points"] = json!(vec![[0.5,0.5];1025]); assert!(!region(&value));
    value = good.clone(); value["recipe"]["objects"][0]["operation"] = json!("subtract"); assert!(!region(&value));
    value = good.clone(); value["recipe"]["objects"][0]["axes"] = json!([[0,0],[0,0]]); assert!(!region(&value));
    let mut objects = Vec::new();
    for index in 0..9 {
        let mut object = good["recipe"]["objects"][0].clone(); object["id"] = json!(format!("stroke-{index}"));
        object["points"] = json!(vec![[0.5,0.5];1024]); objects.push(object);
    }
    value = good.clone(); value["recipe"]["objects"] = json!(&objects[..8]); assert!(region(&value));
    value["recipe"]["objects"] = json!(objects); assert!(!region(&value));
    value = good.clone(); value["recipe"]["objects"] = json!([]); assert!(!region(&value));
}

#[test] fn recipe_is_only_version_highlight_and_shadow_not_cosmetic_materials() {
    for highlight in [0.0,0.25,1.0] { for shadow in [0.0,0.75,1.0] {
        assert!(recipe(&json!({"version":1,"highlight":highlight,"shadow":shadow})));
    }}
    for key in ["highlight", "shadow"] { for bad in [json!(true),json!(-0.01),json!(1.01),json!("0.5"),Value::Null] {
        let mut value = json!({"version":1,"highlight":0.5,"shadow":0.5}); value[key] = bad; assert!(!recipe(&value));
    }}
    assert!(!recipe(&json!({"version":1,"pattern":"freckle_dust","strength":0.5})));
    assert!(!recipe(&json!({"version":1,"highlight":0.5,"shadow":0.5,"support_sha256":"a".repeat(64)})));
    assert!(!recipe(&json!({"version":1.0,"highlight":0.5,"shadow":0.5})));
}

#[test] fn readonly_classification_rejects_unknown_envelopes_and_write_payloads() {
    let read = request("facial_sculpt_reference",json!({}));
    for (key,bad) in [("cmd",json!("batch")),("request_id",json!("")),("request_id",json!("bad\0id")),
        ("host_epoch",json!("wrong")),("commit",json!(true)),("payload",json!({"region":brush_region()}))] {
        let mut value = read.clone(); value[key] = bad; assert!(!read_only(&value),"{key}");
    }
    let mut exact = read.clone(); exact["host_epoch"] = json!("a".repeat(32)); assert!(read_only(&exact));
    exact.as_object_mut().unwrap().remove("request_id"); assert!(!read_only(&exact));
}

#[test] fn reference_receipt_binds_png_bytes_full_frame_mapping_and_source_echo() {
    let good = result(&request("facial_sculpt_reference",json!({})));
    assert!(receipt(&good)); assert!(PeopleKind::valid(&good,Some("photo")));
    for (path,bad) in [("/doc_state/people/facial_sculpt/source_preview/base64",json!("AAAA")),
        ("/doc_state/people/facial_sculpt/source_preview/mapping",json!("crop")),
        ("/doc_state/people/facial_sculpt/source_preview/orientation",json!("raw_exif")),
        ("/doc_state/people/facial_sculpt/source_preview/source_width",json!(3)),
        ("/doc_state/people/facial_sculpt/source_preview/decoded_width",json!(1)),
        ("/doc_state/people/facial_sculpt/source_preview/width",json!(3)),
        ("/payload/reference_proof/preview_sha256",json!("f".repeat(64))),
        ("/payload/reference_proof/reference_request_id",json!("another-read")),
        ("/doc_state/people/binding/document_revision",json!(8)),
        ("/doc_state/people/facial_sculpt/landmark_digest",json!("f".repeat(64))),
        ("/doc_state/people/facial_sculpt/recipe/highlight",json!(2)), ("/frame_emitted",json!(true))] {
        let mut value = good.clone(); *value.pointer_mut(path).unwrap() = bad; assert!(!receipt(&value),"{path}");
    }
    let mut value = good; value["doc_state"]["people"]["facial_sculpt"]["source_preview"]["foreign"] = json!(true);
    assert!(!receipt(&value));
}

#[test] fn original_terminal_read_is_required_and_all_six_context_fences_remain_exact() {
    let read = request("facial_sculpt_reference",json!({})); let review = review_request(); let mut h = host();
    h.begin_command([179;16],&read).unwrap(); assert!(!reference_matches(&review,&h.status("sculpt-source")));
    h.receive([179;16],&result(&read)); let status = h.status("sculpt-source"); assert!(reference_matches(&review,&status));
    for key in CONTEXT {
        let mut value = review.clone(); value[*key] = Value::Null; assert!(!reference_matches(&value,&status),"{key}");
    }
    let mut value = review.clone(); value["payload"]["reference_proof"]["preview_sha256"] = json!("f".repeat(64));
    assert!(!reference_matches(&value,&status)); h.reset([180;16]); assert!(!reference_matches(&review,&h.status("sculpt-source")));
}

#[test] fn successful_review_advances_exactly_once_and_cannot_claim_alias_authority() {
    let good = result(&review_request()); assert!(receipt(&good)); assert!(PeopleKind::valid(&good,Some("photo")));
    for (path,bad) in [("/doc_state/people/binding/document_revision",json!(7)), ("/doc_state/people/revision",json!(13)),
        ("/doc_state/people/association_revision",json!(4)), ("/doc_state/people/selected_face_id",json!("other")),
        ("/doc_state/people/facial_sculpt/support_sha256",json!("f".repeat(64))),
        ("/doc_state/people/facial_sculpt/reference_proof",proof()),
        ("/doc_state/people/facial_sculpt/source_preview",preview()),
        ("/doc_state/people/facial_sculpt/alias_required",json!(true)),
        ("/payload/reference_proof/landmark_digest",json!("f".repeat(64))),
        ("/batch_id",json!("unreviewed-alias-batch")), ("/outcome_unknown",json!(true))] {
        let mut value = good.clone(); *value.pointer_mut(path).unwrap() = bad; assert!(!receipt(&value),"{path}");
    }
    let mut value = good; value["doc_state"]["people"]["resolved"]["operations"][OPERATION]["/highlight"]["value"] = json!(0.1);
    assert!(!receipt(&value));
}

#[test] fn alias_refusal_can_be_displayed_but_never_claims_alias_review_authority() {
    let mut value = result(&request("facial_sculpt_reference",json!({})));
    value["doc_state"]["people"]["facial_sculpt"]["alias_required"] = json!(true);
    value["doc_state"]["people"]["facial_sculpt"]["alias_reason"] = json!("Shared source needs an independent copy");
    assert!(receipt(&value));
    for key in ["alias_review", "support_alias_review", "alias_member_count", "alias_members", "face_decoration_request"] {
        let mut changed = value.clone(); changed["doc_state"]["people"]["facial_sculpt"][key] = json!({});
        assert!(!receipt(&changed),"{key}");
    }
    let mut review = result(&review_request());
    review["doc_state"]["people"]["facial_sculpt"]["alias_required"] = json!(true);
    review["doc_state"]["people"]["facial_sculpt"]["alias_reason"] = json!("Shared source"); assert!(!receipt(&review));
}

#[test] fn substituted_echo_becomes_guarded_unknown_and_late_success_never_reopens_it() {
    let review = review_request(); let mut h = host(); h.begin_command([179;16],&review).unwrap();
    let mut substituted = result(&review);
    substituted["facial_sculpt_request"]["payload"]["region"]["recipe"]["objects"][0]["points"] = json!([[0.1,0.1]]);
    h.receive([179;16],&substituted); let unknown = h.status("sculpt-review");
    assert_eq!(unknown["result"]["outcome_unknown"],true);
    assert_eq!(unknown["result"]["facial_sculpt_request"],binding(&review).unwrap().unwrap()["facial_sculpt_request"]);
    h.receive([179;16],&result(&review)); assert_eq!(h.status("sculpt-review"),unknown);
    assert!(h.guards_review([179;16],"sculpt-review")); assert!(h.begin_command([179;16],&review).is_err());
}

#[test] fn failure_retains_the_original_family_binding_and_never_carries_an_alias_batch() {
    let review = review_request(); let mut failure = result(&review);
    failure.as_object_mut().unwrap().remove("payload"); failure.as_object_mut().unwrap().remove("doc_state");
    failure["success"] = json!(false); failure["frame_emitted"] = json!(false); failure["error"] = json!("No change was made");
    assert!(receipt(&failure));
    let mut h = host(); h.begin_command([179;16],&review).unwrap(); h.receive([179;16],&failure);
    assert_eq!(h.status("sculpt-review")["result"],failure);
    for (key,bad) in [("error",json!("")),("batch_id",json!("alias-batch")),("facial_sculpt_request",json!({})),
        ("face_decoration_request",json!({}))] {
        let mut value = failure.clone(); value[key] = bad; assert!(!receipt(&value),"{key}");
    }
}

#[test] fn released_read_keeps_only_known_outcome_never_document_or_reusable_proof() {
    let value = released(); assert!(released_reference(&value)); assert!(receipt(&value));
    assert!(PeopleKind::valid(&value,Some("photo")));
    let read = request("facial_sculpt_reference",json!({})); let mut h = host(); h.begin_command([179;16],&read).unwrap();
    h.receive([179;16],&value); assert_eq!(h.status("sculpt-source")["result"],value);
    assert!(!reference_matches(&review_request(),&h.status("sculpt-source")));
    for (key,bad) in [("success",json!(false)),("outcome_unknown",json!(true)),("error",json!("uncertain")),
        ("created_id",json!("new-face")),("batch_id",json!("alias-batch")),("frame_emitted",json!(true)),
        ("payload_released",json!(false)),("payload",json!({})),("doc_state",json!({})),("foreign",json!(true))] {
        let mut changed = value.clone(); changed[key] = bad;
        assert!(!released_reference(&changed),"{key}"); assert!(!receipt(&changed),"{key}");
    }
    let mut write = result(&review_request()); write.as_object_mut().unwrap().remove("payload");
    write.as_object_mut().unwrap().remove("doc_state"); write["payload_released"] = json!(true); write["frame_emitted"] = json!(false);
    assert!(!released_reference(&write)); assert!(!receipt(&write));
}

#[test] fn pending_mutation_is_not_released_by_a_source_read_with_reused_identity() {
    let epoch = [178;16]; let review = review_request(); crate::project_recovery_fence::issued(epoch,&review).unwrap();
    let mut read = request("facial_sculpt_reference",json!({})); read["request_id"] = review["request_id"].clone();
    assert!(crate::project_recovery_fence::issued(epoch,&read).is_err());
    crate::project_recovery_fence::observed(epoch,&json!({"event":"people_result","action":"facial_sculpt_reference",
        "request_id":"sculpt-review","success":true,"outcome_unknown":false}));
    assert!(crate::project_recovery_fence::proof(epoch).is_err());
    crate::project_recovery_fence::observed(epoch,&json!({"event":"project_opened"}));
    crate::project_recovery_fence::issued(epoch,&read).unwrap(); assert!(crate::project_recovery_fence::proof(epoch).is_ok());
}

#[test] fn uncertain_reads_can_age_out_but_unknown_review_mutations_stay_fenced() {
    let mut reads = host();
    for index in 0..crate::receipt_host::MAX_RECORDS {
        let mut read = request("facial_sculpt_reference",json!({})); read["request_id"] = json!(format!("read-{index}"));
        reads.begin_command([179;16],&read).unwrap(); reads.failed(read["request_id"].as_str().unwrap(),"Source read unavailable");
    }
    assert!(reads.begin_command([179;16],&request("facial_sculpt_reference",json!({}))).is_ok());
    let mut writes = host();
    for index in 0..crate::receipt_host::MAX_RECORDS {
        let mut review = review_request(); review["request_id"] = json!(format!("review-{index}"));
        writes.begin_command([179;16],&review).unwrap(); writes.failed(review["request_id"].as_str().unwrap(),"Review outcome unknown");
    }
    assert!(writes.begin_command([179;16],&review_request()).is_err());
    assert!(writes.guards_review([179;16],"review-0"));
    writes.reset([180;16]); writes.ready([180;16],true);
    assert!(!writes.guards_review([179;16],"review-0")); assert!(writes.begin_command([180;16],&review_request()).is_ok());
}

#[test] fn png_transport_rejects_crc_mutation_trailing_bytes_and_noncanonical_base64() {
    use base64::{engine::general_purpose::STANDARD, Engine as _};
    use sha2::{Digest, Sha256};
    let good = preview(); assert!(source_preview(&good,&proof()));
    let original = STANDARD.decode(good["base64"].as_str().unwrap()).unwrap();
    let mut bad_crc = original.clone(); bad_crc[29] ^= 1;
    let mut trailing = original; trailing.push(0);
    for bytes in [bad_crc,trailing] {
        let mut image = good.clone(); let mut claimed = proof();
        let digest = format!("{:x}",Sha256::digest(&bytes));
        image["base64"] = json!(STANDARD.encode(bytes)); image["sha256"] = json!(digest);
        claimed["preview_sha256"] = image["sha256"].clone(); assert!(!source_preview(&image,&claimed));
    }
    let mut image = good; image["base64"] = json!(format!("{}\n",image["base64"].as_str().unwrap()));
    assert!(!source_preview(&image,&proof()));
}

#[test] fn revision_overflow_and_noninteger_revisions_cannot_look_like_one_commit() {
    let mut review = review_request(); review["document_revision"] = json!(MAX_REVISION);
    review["state_revision"] = json!(MAX_REVISION); assert!(command(&review).is_ok());
    let mut value = result(&review);
    value["doc_state"]["people"]["binding"]["document_revision"] = json!(MAX_REVISION+1);
    value["doc_state"]["people"]["revision"] = json!(MAX_REVISION+1);
    value["doc_state"]["people"]["resolved"]["state_revision"] = json!(MAX_REVISION+1); assert!(!receipt(&value));
    review["document_revision"] = json!(7.0); assert!(command(&review).is_err());
}

fn active_report() -> Value {
    // Facts-only schema fixture. Not an image, inference run or numeric result.
    let recipe = json!({"version":1,"highlight":0.5,"shadow":0.25});
    json!({"recipe":recipe,"source":{"sha256":"a".repeat(64),"width":800,"height":1000},
        "face_ref":proof()["face_ref"],"landmark_digest":"b".repeat(64),
        "facts":{"zones":{"forehead_center":180,"nose_bridge":100,"nose_tip":90,"midface_left":150,"midface_right":140,"chin":100},
            "measured_face_width":400.0,"radius":10,"protected_face_boxes":1,"recipe":recipe,"face_ref":proof()["face_ref"],
            "landmark_digest":"b".repeat(64),"semantic_model_sha256":"e".repeat(64),
            "skin_observation":{"contract":"mediapipe-face-skin-edit-weight-v1","source_sha256":"a".repeat(64),
                "semantic_model_sha256":"e".repeat(64),"producer_width":400,"producer_height":500},
            "source_dimensions":[800,1000],"render_dimensions":[400,500],"positive_structure_pixels":200,
            "negative_structure_pixels":100,"changed_pixels":300,"reason":null,
            "native_solver":"rust-facial-two-scale-log-structure-v1","policy":"reviewed-source-two-scale-facial-log-structure-v1",
            "composition":"source-log-gain-common-linear-rgb-gamut-bound",
            "limitations":["not-3d-relighting-or-highlight-recovery","not-specular-gloss-or-skin-smoothing",
                "review-is-not-complete-occlusion-segmentation","photo-and-numeric-acceptance-unrun"]}})
}

#[test] fn renderer_facts_are_sculpt_specific_bounded_and_do_not_claim_runtime_acceptance() {
    let report = active_report(); assert!(facts(&report["facts"],&report));
    for (path,bad) in [("/facts/changed_pixels",json!(301)),("/facts/negative_structure_pixels",json!(4_000_001)),
        ("/facts/measured_face_width",json!(95)),("/facts/radius",json!(129)),("/facts/protected_face_boxes",json!(4097)),
        ("/facts/zones/nose_bridge",json!(-1)),("/facts/source_dimensions/0",json!(801)),
        ("/facts/skin_observation/source_sha256",json!("f".repeat(64))),
        ("/facts/skin_observation/semantic_model_sha256",json!("f".repeat(64))),
        ("/facts/skin_observation/contract",json!("merged-skin")),
        ("/facts/native_solver",json!("face-decoration")),("/facts/composition",json!("independent-channel-clipping")),
        ("/facts/limitations",json!([])),("/facts/reason",json!("accepted-photo"))] {
        let mut value = report.clone(); *value.pointer_mut(path).unwrap() = bad; assert!(!facts(&value["facts"],&value),"{path}");
    }
    for key in ["catalogue_sha256","pattern","rasterizer","alias_review","unknown_diagnostic"] {
        let mut value = report.clone(); value["facts"][key] = json!(true); assert!(!facts(&value["facts"],&value),"{key}");
    }
    let mut zero = report; zero["facts"]["positive_structure_pixels"] = json!(0);
    zero["facts"]["negative_structure_pixels"] = json!(0); zero["facts"]["changed_pixels"] = json!(0);
    zero["facts"]["reason"] = json!("no_measurable_broad_structure"); assert!(facts(&zero["facts"],&zero));
}
