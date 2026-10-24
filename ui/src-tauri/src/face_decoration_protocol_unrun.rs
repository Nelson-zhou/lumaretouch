//! AUTHORED / UNRUN. Static fixture specifications only; never executed here.
use super::*;
use crate::receipt_host::{ReceiptHost, ReceiptKind};
use super::super::PeopleKind;

fn request(action: &str, payload: Value) -> Value {
    json!({"cmd":"people","request_id":if action == "face_decoration_reference" {"reference-request"} else {"review-request"},
        "action":action,"payload":payload,"document_id":"document","document_epoch":"epoch",
        "document_revision":7,"state_revision":11,"association_revision":3,
        "target":{"scope":"face","target_id":"face","face_ref":{"asset_sha256":"a".repeat(64),
            "face_instance_id":"face","analysis_revision":2}}})
}
fn brush_region() -> Value {
    json!({"recipe":{"version":1,"domain":"source-normalized","objects":[{
        "id":"stroke","name":"Visible decoration skin","enabled":true,"operation":"add","kind":"brush",
        "opacity":1.0,"feather":10.0,"points":[[0.4,0.5],[0.6,0.5]],"axes":[[0.02,0],[0,0.02]]}]},
        "visible":true,"unoccluded":true,"ownership_confirmed":true})
}
// Original 2x2 black RGB PNG framing fixture, not evidence of a portrait render.
fn preview() -> Value {
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
    json!({"mime":"image/png","width":2,"height":2,"sha256":format!("{:x}", Sha256::digest(&bytes)),
        "base64":STANDARD.encode(bytes),"source_sha256":"a".repeat(64),"source_width":2,"source_height":2,
        "decoded_width":2,"decoded_height":2,"mapping":"normalized_full_frame","orientation":"exif_normalized_once"})
}
fn proof() -> Value {
    json!({"source":{"sha256":"a".repeat(64),"width":2,"height":2},
        "face_ref":request("face_decoration_reference",json!({}))["target"]["face_ref"],
        "landmark_digest":"b".repeat(64),"preview_sha256":preview()["sha256"],"reference_request_id":"reference-request"})
}
fn review_request() -> Value {
    request("face_decoration_review",json!({"reference_proof":proof(),"region":brush_region()}))
}
fn result(c: &Value) -> Value {
    let changed = c["action"] == "face_decoration_review";
    let p = if changed { json!({"kind":"face_decoration_review","reference_proof":proof(),"support_sha256":"c".repeat(64)}) }
        else { json!({"kind":"face_decoration_reference","reference_proof":proof()}) };
    let report = json!({"recipe":{"version":1,"pattern":"freckle_dust","strength":0.0},"facts":{},
        "source":proof()["source"],"face_ref":proof()["face_ref"],"landmark_digest":proof()["landmark_digest"],"reviewed":changed,
        "source_preview":if changed {Value::Null} else {preview()},"reference_proof":if changed {Value::Null} else {proof()},
        "support_sha256":if changed {json!("c".repeat(64))} else {Value::Null},"native_available":false,
        "support_available":false,"support_reason":"Source-only fixture","suspended":null});
    json!({"event":"people_result","protocol":1,"request_id":c["request_id"],"action":c["action"],"document_id":c["document_id"],
        "success":true,"outcome_unknown":false,"error":null,"created_id":null,"batch_id":null,"frame_emitted":changed,
        "face_decoration_request":binding(c).unwrap().unwrap()["face_decoration_request"],"payload":p,
        "doc_state":{"people":{"binding":{"document_id":"document","document_epoch":"epoch","document_revision":if changed {8} else {7},
            "asset_sha256":"a".repeat(64)},"revision":if changed {12} else {11},"association_revision":3,
            "selected_face_id":"face","editing_target":c["target"],
            "resolved":{"face_ref":proof()["face_ref"],"state_revision":if changed {12} else {11},"association_revision":3,
                "operations":{"lnx.face_decoration.v1":{"/pattern":{"value":"freckle_dust"},"/strength":{"value":0.0}}}},
            "face_decoration":report}}})
}
fn host() -> ReceiptHost<PeopleKind> {
    let mut host = ReceiptHost::default(); host.reset([173;16]); host.ready([173;16],true); host
}

#[test] fn exact_reference_and_only_explicit_visible_brushes_are_admitted() {
    let read = request("face_decoration_reference",json!({})); let review = review_request();
    assert!(command(&read).is_ok()); assert!(read_only(&read));
    assert!(command(&review).is_ok()); assert!(!read_only(&review));
    for (path,bad) in [("/target/scope",json!("person")),("/payload/region/visible",json!(false)),
        ("/payload/region/ownership_confirmed",json!(1)),("/payload/region/recipe/version",json!(2)),
        ("/payload/region/recipe/domain",json!("display-normalized")),("/payload/region/recipe/objects/0/kind",json!("full")),
        ("/payload/region/recipe/objects/0/operation",json!("intersect")),("/payload/region/recipe/objects/0/opacity",json!(0)),
        ("/payload/region/recipe/objects/0/points/0/0",json!(-0.01)),("/payload/region/recipe/objects/0/axes",json!([[1,1],[2,2]])),
        ("/payload/reference_proof/source/sha256",json!("f".repeat(64))),("/payload/reference_proof/face_ref/analysis_revision",json!(3))] {
        let mut changed = review.clone(); *changed.pointer_mut(path).unwrap() = bad;
        assert!(command(&changed).is_err(),"{path}");
    }
    for path in ["", "/payload", "/payload/reference_proof", "/payload/region", "/payload/region/recipe", "/payload/region/recipe/objects/0"] {
        let mut changed = review.clone(); changed.pointer_mut(path).unwrap()["foreign"] = json!(true);
        assert!(command(&changed).is_err(),"{path}");
    }
    let mut changed = read; changed["commit"] = json!(true); assert!(!read_only(&changed));
}

#[test] fn recipe_contains_exactly_five_freckles_and_three_moles() {
    assert_eq!(PATTERNS.len(),8);
    assert_eq!(PATTERNS.iter().filter(|name| name.starts_with("freckle_")).count(),5);
    for pattern in PATTERNS { assert!(recipe(&json!({"version":1,"pattern":pattern,"strength":0.5}))); }
    for bad in [json!(true),json!(-0.01),json!(1.01),json!("0.5")] {
        assert!(!recipe(&json!({"version":1,"pattern":"freckle_dust","strength":bad})));
    }
    assert!(!recipe(&json!({"version":1,"pattern":"vendor_pattern","strength":0.5})));
    assert!(!recipe(&json!({"version":1,"pattern":"freckle_dust","strength":0.5,"source":"foreign"})));
}

#[test] fn source_preview_digest_mapping_dimensions_and_report_are_exact() {
    let c = request("face_decoration_reference",json!({})); let good = result(&c);
    assert!(receipt(&good)); assert!(PeopleKind::valid(&good,Some("document")));
    for (path,bad) in [("/doc_state/people/face_decoration/source_preview/base64",json!("AAAA")),("/doc_state/people/face_decoration/source_preview/mapping",json!("crop")),
        ("/payload/reference_proof/preview_sha256",json!("f".repeat(64))), ("/payload/reference_proof/reference_request_id",json!("other")),
        ("/doc_state/people/binding/document_revision",json!(8)),("/doc_state/people/face_decoration/landmark_digest",json!("f".repeat(64))),
        ("/doc_state/people/face_decoration/recipe/pattern",json!("unknown"))] {
        let mut changed = good.clone(); *changed.pointer_mut(path).unwrap() = bad; assert!(!receipt(&changed),"{path}");
    }
    let mut changed = good; changed["doc_state"]["people"]["face_decoration"]["source_preview"]["foreign"] = json!(true); assert!(!receipt(&changed));
}

#[test] fn review_requires_retained_successful_reference_with_all_original_fences() {
    let read = request("face_decoration_reference",json!({})); let review = review_request(); let mut h = host();
    h.begin_command([173;16],&read).unwrap(); assert!(!reference_matches(&review,&h.status("reference-request")));
    h.receive([173;16],&result(&read)); let status = h.status("reference-request"); assert!(reference_matches(&review,&status));
    for key in ["document_id","document_epoch","document_revision","state_revision","association_revision","target"] {
        let mut changed = review.clone(); changed[key] = Value::Null; assert!(!reference_matches(&changed,&status),"{key}");
    }
    let mut changed = review.clone(); changed["payload"]["reference_proof"]["preview_sha256"] = json!("f".repeat(64));
    assert!(!reference_matches(&changed,&status));
    h.reset([174;16]); assert!(!reference_matches(&review,&h.status("reference-request")));
}

#[test] fn review_success_advances_once_and_keeps_exact_local_support_without_alias_claim() {
    let c = review_request(); let good = result(&c); assert!(receipt(&good)); assert!(PeopleKind::valid(&good,Some("document")));
    for (path,bad) in [("/doc_state/people/binding/document_revision",json!(7)),("/doc_state/people/revision",json!(13)),
        ("/doc_state/people/association_revision",json!(4)),("/doc_state/people/face_decoration/support_sha256",json!("f".repeat(64))),
        ("/doc_state/people/face_decoration/reference_proof",proof()),("/payload/reference_proof/landmark_digest",json!("f".repeat(64))),
        ("/batch_id",json!("unreviewed-alias-batch")),("/outcome_unknown",json!(true))] {
        let mut changed = good.clone(); *changed.pointer_mut(path).unwrap() = bad; assert!(!receipt(&changed),"{path}");
    }
}

#[test] fn substituted_or_unknown_write_never_replaces_original_receipt_or_fence() {
    let c = review_request(); let mut h = host(); h.begin_command([173;16],&c).unwrap();
    let mut substituted = result(&c); substituted["face_decoration_request"]["payload"]["region"]["recipe"]["objects"][0]["points"] = json!([[0.1,0.1]]);
    h.receive([173;16],&substituted); let unknown = h.status("review-request");
    assert_eq!(unknown["result"]["outcome_unknown"],true);
    assert_eq!(unknown["result"]["face_decoration_request"],binding(&c).unwrap().unwrap()["face_decoration_request"]);
    h.receive([173;16],&result(&c)); assert_eq!(h.status("review-request"),unknown);
    assert!(h.guards_review([173;16],"review-request"));
    assert!(h.begin_command([173;16],&c).is_err());
}

#[test] fn readonly_classification_never_releases_a_pending_review_mutation() {
    let epoch = [172;16]; let review = review_request();
    crate::project_recovery_fence::issued(epoch,&review).unwrap();
    let mut read = request("face_decoration_reference",json!({})); read["request_id"] = review["request_id"].clone();
    assert!(crate::project_recovery_fence::issued(epoch,&read).is_err());
    crate::project_recovery_fence::observed(epoch,&json!({"event":"people_result","action":"face_decoration_reference",
        "request_id":"review-request","success":true,"outcome_unknown":false}));
    assert!(crate::project_recovery_fence::proof(epoch).is_err());
    crate::project_recovery_fence::observed(epoch,&json!({"event":"project_opened"}));
    crate::project_recovery_fence::issued(epoch,&read).unwrap(); assert!(crate::project_recovery_fence::proof(epoch).is_ok());
}

#[test] fn released_cached_reference_is_known_read_only_without_reusable_proof() {
    let c = request("face_decoration_reference",json!({})); let mut released = result(&c);
    released.as_object_mut().unwrap().remove("payload"); released.as_object_mut().unwrap().remove("doc_state");
    released["payload_released"] = json!(true);
    assert!(released_reference(&released)); assert!(receipt(&released));
    assert!(PeopleKind::valid(&released,Some("document")));
    let mut h = host(); h.begin_command([173;16],&c).unwrap(); h.receive([173;16],&released);
    assert_eq!(h.status("reference-request")["result"],released);
    assert!(!reference_matches(&review_request(),&h.status("reference-request")));
    for (key,bad) in [("success",json!(false)),("outcome_unknown",json!(true)),("error",json!("unknown outcome")),
        ("created_id",json!("new-face")),("batch_id",json!("unreviewed-batch")),("frame_emitted",json!(true)),
        ("payload_released",json!(false)),("payload",json!({})),("doc_state",json!({})),("foreign",json!(true))] {
        let mut changed = released.clone(); changed[key] = bad;
        assert!(!released_reference(&changed),"{key}"); assert!(!receipt(&changed),"{key}");
    }
    let write = review_request(); let mut changed = result(&write);
    changed.as_object_mut().unwrap().remove("payload"); changed.as_object_mut().unwrap().remove("doc_state");
    changed["payload_released"] = json!(true); changed["frame_emitted"] = json!(false);
    assert!(!released_reference(&changed)); assert!(!receipt(&changed));
}

#[test] fn current_active_renderer_diagnostics_keep_the_exact_truthful_composition_contract() {
    let c = request("face_decoration_reference",json!({})); let mut value = result(&c);
    let active = json!({"version":1,"pattern":"freckle_dust","strength":0.5});
    let report = &mut value["doc_state"]["people"]["face_decoration"];
    report["recipe"] = active.clone(); report["reviewed"] = json!(true); report["support_sha256"] = json!("c".repeat(64));
    report["native_available"] = json!(true); report["support_available"] = json!(true); report["support_reason"] = Value::Null;
    report["facts"] = json!({"reviewed_support_pixels":4,"face_frame":"measured-nose-origin-cheek-width-affine",
        "visibility_method":"decoration-review-intersected-with-actual-skin-and-exclusions",
        "limitation":"known-occluders-and-human-review-not-complete-instance-segmentation",
        "face_ref":proof()["face_ref"],"recipe":active,"catalogue_sha256":"d".repeat(64),"semantic_model_sha256":"e".repeat(64),
        "changed_pixels":2,"reason":null,"rasterizer":"exact-source-pixel-area-piecewise-linear-pigment-v1",
        "contribution_model":"bounded-multiplicative-pigment-not-blemish-removal",
        "composition":"direction-preserving-per-pixel-SDR-headroom-gain-no-channel-clipping"});
    value["doc_state"]["people"]["resolved"]["operations"]["lnx.face_decoration.v1"]["/strength"]["value"] = json!(0.5);
    assert!(receipt(&value));
    let path = "/doc_state/people/face_decoration/facts";
    for (key,bad) in [("composition",json!("bounded-multiplicative-pigment-contribution-not-blemish-removal")),
        ("contribution_model",json!("blemish-removal")),("unknown_diagnostic",json!(true))] {
        let mut changed = value.clone(); changed.pointer_mut(path).unwrap()[key] = bad; assert!(!receipt(&changed),"{key}");
    }
    let mut changed = value; changed.pointer_mut(path).unwrap().as_object_mut().unwrap().remove("contribution_model");
    assert!(!receipt(&changed));
}
