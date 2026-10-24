// SPDX-License-Identifier: GPL-3.0-or-later
//! AUTHORED / UNRUN. Transport contracts, not inference or photo acceptance.
use super::*;
use crate::receipt_host::{ReceiptHost, ReceiptKind};
use super::super::PeopleKind;

fn request(action: &str, payload: Value) -> Value {
    json!({"cmd":"people", "request_id":if action == "eye_makeup_enhance_reference" {"makeup-source"} else {"makeup-review"},
        "action":action, "payload":payload, "document_id":"photo", "document_epoch":"epoch",
        "document_revision":7, "state_revision":11, "association_revision":3,
        "target":{"scope":"face", "target_id":"face", "face_ref":{"asset_sha256":"a".repeat(64),
            "face_instance_id":"face", "analysis_revision":2}}})
}
fn neutral() -> Value {
    let mut value = json!({"version":1});
    for key in CONTROLS { value[*key] = json!({"linked":true,"left":0.0,"right":0.0}); }
    value
}
fn eye() -> Value {
    json!({"makeup":[[0.40,0.30],[0.45,0.30],[0.45,0.34],[0.40,0.34]], "exclusions":[],
        "reference_a":[[0.35,0.35],[0.38,0.35],[0.38,0.37],[0.35,0.37]],
        "reference_b":[[0.47,0.35],[0.49,0.35],[0.49,0.37],[0.47,0.37]],
        "reference_confirmed":true,"visible_makeup":true,"unoccluded":true,
        "ownership_confirmed":true,"globe_lashes_brows_excluded":true})
}
// Synthetic black RGB PNG framing fixture, explicitly not a portrait or result.
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
    chunk(&mut bytes, b"IHDR", &[0,0,0,128,0,0,0,96,8,2,0,0,0]);
    let length: u16 = 96 * (128 * 3 + 1);
    let mut pixels = vec![0x78,0x01,0x01];
    pixels.extend_from_slice(&length.to_le_bytes()); pixels.extend_from_slice(&(!length).to_le_bytes());
    pixels.extend(std::iter::repeat(0).take(usize::from(length)));
    pixels.extend_from_slice(&((u32::from(length) << 16) | 1).to_be_bytes());
    chunk(&mut bytes, b"IDAT", &pixels); chunk(&mut bytes, b"IEND", &[]);
    json!({"mime":"image/png","base64":STANDARD.encode(&bytes),"sha256":format!("{:x}",Sha256::digest(&bytes)),
        "source":{"sha256":"a".repeat(64),"width":1024,"height":768},"width":128,"height":96,
        "view_box":[119.5,179.5,128.0,96.0],"mapping":"source_pixel_centre_periocular_crop","minimum_eye_width":40.0})
}
fn proof() -> Value {
    json!({"source":preview()["source"],"face_ref":request("eye_makeup_enhance_reference",json!({}))["target"]["face_ref"],
        "landmark_digest":"b".repeat(64),"preview_sha256":preview()["sha256"],"reference_request_id":"makeup-source"})
}
fn review_request() -> Value {
    request("eye_makeup_enhance_review",json!({"eyes":{"left":eye()},"reference_proof":proof()}))
}
fn result(command: &Value) -> Value {
    let changed = command["action"] == "eye_makeup_enhance_review";
    let payload = if changed {json!({"kind":"eye_makeup_enhance_review","reference_proof":proof(),"support_sha256":"c".repeat(64)})}
        else {json!({"kind":"eye_makeup_enhance_reference","reference_proof":proof()})};
    let mut operation = json!({});
    for key in CONTROLS {
        operation[format!("/{key}/linked")] = json!({"value":true});
        for side in SIDES { operation[format!("/{key}/{side}")] = json!({"value":0.0}); }
    }
    let report = json!({"recipe":neutral(),"facts":{},"source":proof()["source"],"face_ref":proof()["face_ref"],
        "landmark_digest":"b".repeat(64),"reviewed":changed,"support_sha256":if changed {json!("c".repeat(64))} else {Value::Null},
        "sides":if changed {json!({"left":{"reviewed":true,"reference_reviewed":true}})} else {json!({})},
        "source_preview":if changed {Value::Null} else {preview()},"reference_proof":if changed {Value::Null} else {proof()},
        "native_available":false,"support_available":changed,"support_reason":if changed {Value::Null} else {json!("Source-only fixture")},"suspended":null});
    json!({"event":"people_result","protocol":1,"request_id":command["request_id"],"action":command["action"],
        "document_id":command["document_id"],"success":true,"outcome_unknown":false,"error":null,
        "created_id":null,"batch_id":null,"frame_emitted":changed,
        "eye_makeup_enhance_request":binding(command).unwrap().unwrap()["eye_makeup_enhance_request"],"payload":payload,
        "doc_state":{"people":{"binding":{"document_id":"photo","document_epoch":"epoch",
            "document_revision":if changed {8} else {7},"asset_sha256":"a".repeat(64)},
            "revision":if changed {12} else {11},"association_revision":3,"selected_face_id":"face","editing_target":command["target"],
            "resolved":{"face_ref":proof()["face_ref"],"state_revision":if changed {12} else {11},"association_revision":3,
                "operations":{"lnx.eye_makeup_enhance.v1":operation}},"eye_makeup_enhance":report}}})
}
fn host() -> ReceiptHost<PeopleKind> {
    let mut host = ReceiptHost::default(); host.reset([183;16]); host.ready([183;16],true); host
}
fn released() -> Value {
    let mut value = result(&request("eye_makeup_enhance_reference",json!({})));
    value.as_object_mut().unwrap().remove("payload"); value.as_object_mut().unwrap().remove("doc_state");
    value["payload_released"] = json!(true); value
}

#[test] fn commands_require_own_face_source_and_independent_eye_review() {
    let read = request("eye_makeup_enhance_reference",json!({})); let review = review_request();
    assert!(command(&read).is_ok()); assert!(read_only(&read)); assert!(command(&review).is_ok()); assert!(!read_only(&review));
    assert!(fields(&binding(&review).unwrap().unwrap(), &["eye_makeup_enhance_request"]));
    for (path,bad) in [("/target/scope",json!("person")),("/payload/eyes/left/visible_makeup",json!(false)),
        ("/payload/eyes/left/unoccluded",json!(false)),("/payload/eyes/left/ownership_confirmed",json!(1)),
        ("/payload/eyes/left/globe_lashes_brows_excluded",json!(false)),("/payload/reference_proof/source/width",json!(1)),
        ("/payload/reference_proof/source/sha256",json!("f".repeat(64))),
        ("/payload/reference_proof/face_ref/analysis_revision",json!(3)),("/payload/reference_proof/reference_request_id",json!(" "))] {
        let mut value = review.clone(); *value.pointer_mut(path).unwrap() = bad; assert!(command(&value).is_err(),"{path}");
    }
}
#[test] fn bilateral_signed_controls_link_only_within_their_own_control() {
    let mut value = neutral(); assert!(recipe(&value));
    for key in CONTROLS {
        value[*key] = json!({"linked":false,"left":-1.0,"right":1.0}); assert!(recipe(&value));
        value[*key]["linked"] = json!(true); assert!(!recipe(&value)); value[*key]["right"] = json!(-1.0); assert!(recipe(&value));
        for bad in [json!(-1.01),json!(1.01),json!(true),json!("0"),Value::Null] {
            let mut invalid = value.clone(); invalid[*key]["left"] = bad; assert!(!recipe(&invalid));
        }
    }
    for key in ["palette","iris","eyeliner","highlight","shadow","reference_proof","linked"] {
        let mut invalid = value.clone(); invalid[key] = json!(true); assert!(!recipe(&invalid));
    }
    value["version"] = json!(1.0); assert!(!recipe(&value));
}
#[test] fn simple_source_polygons_reject_duplicate_crossing_touching_and_degenerate_edges() {
    assert!(polygon(&eye()["makeup"]));
    for bad in [json!([]),json!([[0,0],[1,1]]),json!([[0,0],[0.5,0.5],[1,1]]),
        json!([[0,0],[1,0],[1,1],[0,0]]),json!([[0,0],[1,1],[0,1],[1,0]]),
        json!([[0,0],[1,0],[1,1],[0.5,0],[0,1]]),json!([[0,0],[1,0],[1,1],[-0.1,1]]),
        json!([[0,0],[true,0],[1,1]]),json!(vec![[0.5,0.5];97])] { assert!(!polygon(&bad)); }
}
#[test] fn paired_skin_references_are_optional_but_never_partial_or_implicitly_confirmed() {
    let mut value = json!({"left":eye()}); assert!(eyes(&value));
    value["left"]["reference_a"] = Value::Null; assert!(!eyes(&value));
    value["left"]["reference_b"] = Value::Null; assert!(!eyes(&value));
    value["left"]["reference_confirmed"] = json!(false); assert!(eyes(&value));
    value["right"] = eye(); assert!(eyes(&value));
    value["right"]["reference_confirmed"] = json!(false); assert!(!eyes(&value));
    assert!(!eyes(&json!({}))); assert!(!eyes(&json!({"image_left":eye()})));
    value = json!({"left":eye()}); value["left"]["exclusions"] = json!(vec![eye()["makeup"].clone();13]); assert!(!eyes(&value));
}
#[test] fn exact_fields_reject_other_operations_support_aliases_and_unknown_authority() {
    let review = review_request();
    for path in ["","/payload","/payload/eyes/left","/payload/reference_proof","/payload/reference_proof/source"] {
        let mut value = review.clone(); value.pointer_mut(path).unwrap()["foreign"] = json!(true); assert!(command(&value).is_err(),"{path}");
    }
    for key in ["alias_members","alias_review","support_alias_review","region","palette","mask","source_preview"] {
        let mut value = review.clone(); value["payload"][key] = json!({}); assert!(command(&value).is_err(),"{key}");
    }
    for name in ["eye_makeup_enhance_alias_confirm","eye_makeup_enhance_image","iris_reference","eye_light_reference","facial_sculpt_reference"] {
        let value = request(name,json!({})); assert!(!action(&value)); assert!(!read_only(&value)); assert!(binding(&value).unwrap().is_none());
    }
}
#[test] fn readonly_classification_uses_the_original_validated_people_command() {
    let read = request("eye_makeup_enhance_reference",json!({}));
    for (key,bad) in [("cmd",json!("batch")),("request_id",json!("")),("request_id",json!("bad\0id")),
        ("host_epoch",json!("wrong")),("commit",json!(true)),("payload",json!({"eyes":{"left":eye()}}))] {
        let mut value = read.clone(); value[key] = bad; assert!(!read_only(&value),"{key}");
    }
    let mut value = read; value["host_epoch"] = json!("a".repeat(32)); assert!(read_only(&value));
    value.as_object_mut().unwrap().remove("request_id"); assert!(!read_only(&value));
}
#[test] fn source_crop_receipt_binds_own_mapping_and_rejects_full_frame_schema() {
    let good = result(&request("eye_makeup_enhance_reference",json!({})));
    assert!(receipt(&good)); assert!(PeopleKind::valid(&good,Some("photo")));
    for (path,bad) in [("/doc_state/people/eye_makeup_enhance/source_preview/base64",json!("AAAA")),
        ("/doc_state/people/eye_makeup_enhance/source_preview/mapping",json!("normalized_full_frame")),
        ("/doc_state/people/eye_makeup_enhance/source_preview/source/width",json!(1025)),
        ("/doc_state/people/eye_makeup_enhance/source_preview/view_box",json!([0,0,-1,1])),
        ("/doc_state/people/eye_makeup_enhance/source_preview/view_box",json!([1000000,0,1,1])),
        ("/doc_state/people/eye_makeup_enhance/source_preview/minimum_eye_width",json!(39.999)),
        ("/doc_state/people/eye_makeup_enhance/source_preview/width",json!(127)),
        ("/payload/reference_proof/preview_sha256",json!("f".repeat(64))),
        ("/payload/reference_proof/reference_request_id",json!("other-read")),("/frame_emitted",json!(true))] {
        let mut value = good.clone(); *value.pointer_mut(path).unwrap() = bad; assert!(!receipt(&value),"{path}");
    }
    for key in ["source_sha256","source_width","decoded_width","orientation","foreign"] {
        let mut value = good.clone(); value["doc_state"]["people"]["eye_makeup_enhance"]["source_preview"][key] = json!(true);
        assert!(!receipt(&value),"{key}");
    }
}
#[test] fn producer_half_pixel_proxy_border_is_not_mistaken_for_full_frame_coordinates() {
    let mut image = preview(); image["view_box"] = json!([-1.0,-1.0,1025.0,769.0]);
    assert!(source_preview(&image,&proof()));
    image["view_box"] = json!([-1000.0,0.0,128.0,96.0]); assert!(!source_preview(&image,&proof()));
}
#[test] fn png_framing_crc_and_canonical_base64_are_checked_without_claiming_a_portrait() {
    use base64::{engine::general_purpose::STANDARD, Engine as _};
    use sha2::{Digest, Sha256};
    let good = preview(); assert!(source_preview(&good,&proof()));
    let original = STANDARD.decode(good["base64"].as_str().unwrap()).unwrap();
    let mut corrupted = original.clone(); corrupted[29] ^= 1;
    let mut trailing = original; trailing.push(0);
    for bytes in [corrupted,trailing] {
        let mut image = good.clone(); let mut claim = proof(); image["base64"] = json!(STANDARD.encode(&bytes));
        image["sha256"] = json!(format!("{:x}",Sha256::digest(&bytes))); claim["preview_sha256"] = image["sha256"].clone();
        assert!(!source_preview(&image,&claim));
    }
    let mut image = good; image["base64"] = json!(format!("{}\n",image["base64"].as_str().unwrap()));
    assert!(!source_preview(&image,&proof()));
}
#[test] fn review_requires_exactly_one_commit_and_matching_twelve_resolved_leaves() {
    let good = result(&review_request()); assert!(receipt(&good)); assert!(PeopleKind::valid(&good,Some("photo")));
    for (path,bad) in [("/doc_state/people/binding/document_revision",json!(7)),("/doc_state/people/revision",json!(13)),
        ("/doc_state/people/association_revision",json!(4)),("/doc_state/people/selected_face_id",json!("other")),
        ("/doc_state/people/eye_makeup_enhance/support_sha256",json!("f".repeat(64))),
        ("/doc_state/people/eye_makeup_enhance/source_preview",preview()),("/doc_state/people/eye_makeup_enhance/reference_proof",proof()),
        ("/doc_state/people/eye_makeup_enhance/sides/left/reference_reviewed",json!(false)),
        ("/payload/reference_proof/landmark_digest",json!("f".repeat(64))),
        ("/batch_id",json!("unreviewed-alias-batch")),("/outcome_unknown",json!(true))] {
        let mut value = good.clone(); *value.pointer_mut(path).unwrap() = bad; assert!(!receipt(&value),"{path}");
    }
    for key in CONTROLS { for leaf in ["linked","left","right"] {
        let mut value = good.clone(); let path = format!("/{key}/{leaf}");
        value["doc_state"]["people"]["resolved"]["operations"][OPERATION][path.as_str()]["value"] = Value::Null;
        assert!(!receipt(&value),"{path}");
    }}
}
#[test] fn unavailable_analysis_does_not_invent_per_eye_visibility_or_reference_acceptance() {
    let mut good = result(&review_request());
    good["doc_state"]["people"]["eye_makeup_enhance"]["support_available"] = json!(false);
    good["doc_state"]["people"]["eye_makeup_enhance"]["support_reason"] = json!("Actual face skin analysis unavailable");
    good["doc_state"]["people"]["eye_makeup_enhance"]["sides"] = json!({}); assert!(receipt(&good));
    for key in ["automatic_visibility","cosmetic_segmentation","alias_review","support_alias_review"] {
        let mut value = good.clone(); value["doc_state"]["people"]["eye_makeup_enhance"][key] = json!(true); assert!(!receipt(&value));
    }
    good["doc_state"]["people"]["eye_makeup_enhance"]["support_available"] = json!(true); assert!(!receipt(&good));
}
#[test] fn original_successful_terminal_read_binds_all_six_context_fences() {
    let read = request("eye_makeup_enhance_reference",json!({})); let review = review_request(); let mut ledger = host();
    ledger.begin_command([183;16],&read).unwrap(); assert!(!reference_matches(&review,&ledger.status("makeup-source")));
    ledger.receive([183;16],&result(&read)); let status = ledger.status("makeup-source"); assert!(reference_matches(&review,&status));
    for key in CONTEXT {
        let mut value = review.clone(); value[*key] = Value::Null; assert!(!reference_matches(&value,&status),"{key}");
    }
    let mut changed = review.clone(); changed["payload"]["eyes"]["left"]["visible_makeup"] = json!(false);
    assert!(!reference_matches(&changed,&status)); ledger.reset([184;16]); assert!(!reference_matches(&review,&ledger.status("makeup-source")));
}
#[test] fn substituted_review_echo_becomes_guarded_unknown_not_late_success() {
    let review = review_request(); let mut ledger = host(); ledger.begin_command([183;16],&review).unwrap();
    let mut changed = result(&review); changed["eye_makeup_enhance_request"]["payload"]["eyes"]["left"]["makeup"] = json!([[0.4,0.3],[0.46,0.3],[0.46,0.35]]);
    ledger.receive([183;16],&changed); let unknown = ledger.status("makeup-review"); assert_eq!(unknown["result"]["outcome_unknown"],true);
    assert_eq!(unknown["result"]["eye_makeup_enhance_request"],binding(&review).unwrap().unwrap()["eye_makeup_enhance_request"]);
    ledger.receive([183;16],&result(&review)); assert_eq!(ledger.status("makeup-review"),unknown);
    assert!(ledger.guards_review([183;16],"makeup-review")); assert!(ledger.begin_command([183;16],&review).is_err());
}
#[test] fn failure_retains_its_exact_family_binding_and_excludes_other_authority() {
    let review = review_request(); let mut failure = result(&review);
    failure.as_object_mut().unwrap().remove("payload"); failure.as_object_mut().unwrap().remove("doc_state");
    failure["success"] = json!(false); failure["frame_emitted"] = json!(false); failure["error"] = json!("No change was made");
    assert!(receipt(&failure));
    let mut ledger = host(); ledger.begin_command([183;16],&review).unwrap(); ledger.receive([183;16],&failure);
    assert_eq!(ledger.status("makeup-review")["result"],failure);
    for (key,bad) in [("error",json!("")),("batch_id",json!("alias-batch")),("eye_makeup_enhance_request",json!({})),("facial_sculpt_request",json!({}))] {
        let mut value = failure.clone(); value[key] = bad; assert!(!receipt(&value),"{key}");
    }
}
#[test] fn released_read_is_bounded_terminal_outcome_without_image_or_reusable_proof() {
    let good = released(); assert!(released_reference(&good)); assert!(receipt(&good)); assert!(PeopleKind::valid(&good,Some("photo")));
    let read = request("eye_makeup_enhance_reference",json!({})); let mut ledger = host(); ledger.begin_command([183;16],&read).unwrap();
    ledger.receive([183;16],&good); assert_eq!(ledger.status("makeup-source")["result"],good);
    assert!(!reference_matches(&review_request(),&ledger.status("makeup-source")));
    for (key,bad) in [("success",json!(false)),("outcome_unknown",json!(true)),("frame_emitted",json!(true)),
        ("payload_released",json!(false)),("payload",json!({})),("doc_state",json!({})),("foreign",json!(true))] {
        let mut value = good.clone(); value[key] = bad; assert!(!released_reference(&value)); assert!(!receipt(&value));
    }
    let mut review = result(&review_request()); review.as_object_mut().unwrap().remove("payload");
    review.as_object_mut().unwrap().remove("doc_state"); review["payload_released"] = json!(true); assert!(!receipt(&review));
}
#[test] fn source_read_cannot_release_a_pending_review_with_the_same_request_id() {
    let epoch = [185;16]; let review = review_request(); crate::project_recovery_fence::issued(epoch,&review).unwrap();
    let mut read = request("eye_makeup_enhance_reference",json!({})); read["request_id"] = review["request_id"].clone();
    assert!(crate::project_recovery_fence::issued(epoch,&read).is_err());
    crate::project_recovery_fence::observed(epoch,&json!({"event":"people_result","action":"eye_makeup_enhance_reference",
        "request_id":"makeup-review","success":true,"outcome_unknown":false}));
    assert!(crate::project_recovery_fence::proof(epoch).is_err());
    crate::project_recovery_fence::observed(epoch,&json!({"event":"project_opened"}));
    crate::project_recovery_fence::issued(epoch,&read).unwrap(); assert!(crate::project_recovery_fence::proof(epoch).is_ok());
}
#[test] fn safe_integer_revision_limits_cannot_masquerade_as_one_commit() {
    let mut request = review_request(); request["document_revision"] = json!(MAX_REVISION); request["state_revision"] = json!(MAX_REVISION);
    assert!(command(&request).is_ok()); let mut value = result(&request);
    value["doc_state"]["people"]["binding"]["document_revision"] = json!(MAX_REVISION+1);
    value["doc_state"]["people"]["revision"] = json!(MAX_REVISION+1);
    value["doc_state"]["people"]["resolved"]["state_revision"] = json!(MAX_REVISION+1); assert!(!receipt(&value));
    request["document_revision"] = json!(7.0); assert!(command(&request).is_err());
}
fn active_report() -> Value {
    let mut recipe = neutral(); recipe["brightness"] = json!({"linked":false,"left":0.25,"right":0.0});
    json!({"recipe":recipe,"source":proof()["source"],"face_ref":proof()["face_ref"],"landmark_digest":"b".repeat(64),"support_sha256":"c".repeat(64),
        "facts":{"recipe":recipe,"review_sha256":"c".repeat(64),"face_ref":proof()["face_ref"],"landmark_digest":"b".repeat(64),
            "sides":{"left":{"reviewed_makeup_pixels":100,"permitted_makeup_pixels":80,"reference_pixels":[0,0],"measured_eye_width":80.0,
                "radius":1,"controls":{"amount":0.0,"saturation":0.0,"brightness":0.25,"structure":0.0},"changed_pixels":75,"reason":null}},
            "face_skin_observation":{"contract":"mediapipe-face-skin-edit-weight-v1","source_sha256":"a".repeat(64),
                "semantic_model_sha256":"e".repeat(64),"producer_width":512,"producer_height":384},
            "changed_pixels":75,"native_solver":"rust-eye-makeup-enhance-v1","source_dimensions":[1024,768],"render_dimensions":[512,384],
            "protected_face_boxes":1,"limitations":["user-reviewed-visible-makeup-not-cosmetic-segmentation",
                "paired-nearby-skin-reference-not-known-underlying-skin","bounded-appearance-fading-not-makeup-removal",
                "no-pigment-pattern-generation-or-hidden-anatomy","authored-unrun-no-photo-quality-acceptance"]}})
}
#[test] fn eye_specific_facts_are_bounded_side_consistent_and_not_quality_acceptance() {
    let good = active_report(); assert!(facts(&good["facts"],&good));
    for (path,bad) in [("/facts/changed_pixels",json!(74)),("/facts/review_sha256",json!("f".repeat(64))),
        ("/facts/source_dimensions/0",json!(1025)),("/facts/face_skin_observation/source_sha256",json!("f".repeat(64))),
        ("/facts/sides/left/radius",json!(65)),("/facts/sides/left/permitted_makeup_pixels",json!(69)),
        ("/facts/sides/left/reference_pixels",json!([16,16])),("/facts/sides/left/controls/brightness",json!(0.1)),
        ("/facts/sides/left/reason",json!("accepted-photo")),("/facts/limitations",json!([])),("/facts/native_solver",json!("eye-light"))] {
        let mut value = good.clone(); *value.pointer_mut(path).unwrap() = bad; assert!(!facts(&value["facts"],&value),"{path}");
    }
    let mut value = good.clone(); value["facts"]["sides"]["right"] = value["facts"]["sides"]["left"].clone(); assert!(!facts(&value["facts"],&value));
    value = good; value["facts"]["sides"]["left"]["changed_pixels"] = json!(0); value["facts"]["changed_pixels"] = json!(0);
    value["facts"]["sides"]["left"]["reason"] = json!("no_measurable_change"); assert!(facts(&value["facts"],&value));
}
