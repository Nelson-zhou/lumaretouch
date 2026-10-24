//! AUTHORED / UNRUN. Transport fixtures only, not render/browser acceptance.
use super::*;
use crate::receipt_host::ReceiptKind;

fn owner(id: char, asset: char) -> Value {
    json!({"document":{"document_id":id.to_string().repeat(32),"epoch":"workspace","revision":3},
        "people_scope":"project","state_revision":2,"association_revision":1,"graph_sha256":"e".repeat(64),
        "source_proof":{"asset_sha256":asset.to_string().repeat(64),"original_sha256":asset.to_string().repeat(64),"creative_source":null}})
}
fn face(asset: char, id: &str) -> Value {
    json!({"asset_sha256":asset.to_string().repeat(64),"face_instance_id":id,"analysis_revision":1})
}
fn request_fixture() -> Value {
    json!({"cmd":"batch","action":"preflight","request_id":"eye-review","docs":["b".repeat(32)],
        "module_scope":[OP],"conflict_policy":"recheck","people_transfer":{"target_policy":"explicit_face_map",
        "source_ref":face('c',"source-face"),"source":owner('a','c'),"selection":{(OP):["/pattern","/strength"]},
        "targets":[{"target":owner('b','d'),"target_refs":[face('d',"target-face")]}]}})
}
fn review_fixture() -> Value {
    let c = request_fixture(); let a = &c["people_transfer"]; let owner = &a["targets"][0]["target"];
    let coverage = json!({"version":1,"support_transfer":"none","targets":[{"face_ref":face('d',"target-face"),
        "scope":"target-reviewed-visible-skin","visibility_sha256":"8".repeat(64),"recipe_sha256":"7".repeat(64)}]});
    let image = json!({"mime":"image/png","width":1024,"height":768,"sha256":"f".repeat(64)});
    let visual = json!({"version":1,"document_id":"b".repeat(32),"revision":"3","source_proof":owner["source_proof"],
        "before_state_sha256":"1".repeat(64),"candidate_state_sha256":"2".repeat(64),
        "before_people_sha256":"3".repeat(64),"candidate_people_sha256":"4".repeat(64),
        "source_size":[4000,3000],"before_output_size":[4000,3000],"after_output_size":[4000,3000],
        "before":image,"after":image,"coverage_sha256":collarbone::request_digest(&coverage)});
    let transfer = json!({"version":1,"source_document":a["source"]["document"],"target_document":owner["document"],
        "source_ref":a["source_ref"],"target_refs":a["targets"][0]["target_refs"],"parameters":[
            {"operation_id":OP,"parameter_path":"/pattern","value":"freckle_dust"},
            {"operation_id":OP,"parameter_path":"/strength","value":0.5}],
        "source_state_revision":2,"target_state_revision":2,"source_association_revision":1,"target_association_revision":1,
        "transfer_policy":"selected_parameter_keys_replace","excluded":["local_assets","landmarks","masks","identity_links"],
        "source_owner":a["source"],"target_owner":owner,"target_policy":"explicit_face_map",
        "face_decoration_coverage":coverage,"face_decoration_visual":visual});
    json!({"event":"batch_result","action":"preflight","request_id":c["request_id"],"success":true,
        "outcome_unknown":false,"preflight_token":"9".repeat(32),"module_scope":[OP],"people_transfer":true,"face_decoration_visual_required":true,
        "applies":a,"policy":"recheck","source_snapshot":{"document_id":"a".repeat(32),"revision":"3","path":"/source.raw"},
        "targets":[{"document_id":"b".repeat(32),"revision":"3","index":1,"path":"/target.raw","blocked":null,
            "people_transfer":transfer}],"ok":1,"blocked":0,"rejected_docs":[]})
}
fn commit_fixture() -> Value {
    json!({"cmd":"batch","action":"commit","request_id":"eye-commit","preflight_token":"9".repeat(32),
        (ACK):[{"document_id":"b".repeat(32),"revision":"3","before_sha256":"f".repeat(64),
            "after_sha256":"f".repeat(64),"coverage_sha256":"8".repeat(64)}]})
}
fn terminal(c: &Value) -> Value {
    let mut v = json!({"event":"batch_result","action":"commit","request_id":c["request_id"],"success":true,
        "outcome_unknown":false,"preflight_token":c["preflight_token"],"module_scope":[OP],(ACK):c[ACK],
        "people_transfer":true,"face_decoration_visual_required":true,"face_decoration_batch_review":{"version":1,"review_sha256":collarbone::request_digest(&c[ACK]),"member_count":1},"batch_id":"batch","source_snapshot":{"document_id":"a".repeat(32),"revision":"3","path":"/source.raw"},
        "applied":[1],"target_outcomes":[{"document_id":"b".repeat(32),"expected_revision":"3","current_revision":"3",
            "result_revision":"4","index":1,"blocked":null,"outcome":"applied"}]});
    if let Some(other) = c.get(collarbone::ACK) {
        v[collarbone::ACK] = other.clone(); v["module_scope"] = json!([collarbone::OP, OP]);
    }
    v
}
fn image_request_fixture() -> Value {
    json!({"cmd":"batch","action":"face_decoration_visual","request_id":"eye-image","preflight_token":"9".repeat(32),
        "document_id":"b".repeat(32),"revision":"3","side":"before","sha256":"f".repeat(64)})
}
fn host(epoch: [u8;16]) -> crate::batch_host::BatchHost {
    let mut h = crate::batch_host::BatchHost::default(); h.reset(epoch); h.ready(epoch,true); h
}
fn refresh_coverage(v: &mut Value) {
    let digest = collarbone::request_digest(&v["targets"][0]["people_transfer"]["face_decoration_coverage"]);
    v["targets"][0]["people_transfer"]["face_decoration_visual"]["coverage_sha256"] = json!(digest);
}
// AUTHORED / UNRUN. Exact packet fixtures only.
#[test] fn complete_target_review_requires_marker_and_all_coverage() {
    let mut v=review_fixture();assert!(receipt(&v));assert!(crate::batch_host::BatchKind::valid(&v,None));
    v.as_object_mut().unwrap().remove("face_decoration_visual_required");assert!(!receipt(&v));
    v=review_fixture();v["targets"][0]["people_transfer"]["face_decoration_coverage"]["targets"][0]["visibility_sha256"]=json!("bad");refresh_coverage(&mut v);assert!(!receipt(&v));
}
#[test] fn commands_are_exact_and_scalar_only() {
    assert!(read_only(&request_fixture()));assert!(read_only(&image_request_fixture()));assert!(command(&commit_fixture()).is_ok());
    let mut v=request_fixture();v["people_transfer"]["selection"][OP]=json!(["/support"]);assert!(!read_only(&v));
    let mut v=image_request_fixture();v["force"]=json!(true);assert!(command(&v).is_err());
}
#[test] fn commit_outcome_and_unknown_receipt_keep_exact_targets() {
    let c=commit_fixture();assert!(receipt(&terminal(&c)));let mut v=terminal(&c);
    v["target_outcomes"][0]["document_id"]=json!("e".repeat(32));assert!(!receipt(&v));
    let mut v=json!({"action":"commit","success":false,"outcome_unknown":true,"error":"uncertain",
        "preflight_token":c["preflight_token"],(ACK):c[ACK],"face_decoration_visual_required":true});assert!(receipt(&v));
    v.as_object_mut().unwrap().remove(ACK);assert!(!receipt(&v));
}
#[test] fn retained_active_other_face_requires_own_review() {
    let mut v=review_fixture();let t=&mut v["targets"][0]["people_transfer"];
    let mut other=t["face_decoration_coverage"]["targets"][0].clone();other["face_ref"]["face_instance_id"]=json!("zz-other");
    t["face_decoration_coverage"]["targets"].as_array_mut().unwrap().push(other);refresh_coverage(&mut v);assert!(receipt(&v));
    v["targets"][0]["people_transfer"]["face_decoration_coverage"]["targets"][1]["face_ref"]["asset_sha256"]=json!("c".repeat(64));refresh_coverage(&mut v);assert!(!receipt(&v));
}
#[test] fn mixed_families_must_ack_the_same_complete_images() {
    let mut c=commit_fixture();c[collarbone::ACK]=c[ACK].clone();assert!(command(&c).is_ok());
    c[collarbone::ACK][0]["after_sha256"]=json!("0".repeat(64));assert!(command(&c).is_err());
}
#[test] fn history_marker_never_authorizes_partial_restore() {
    let mut v=json!({"action":"undo","batch_id":"existing","success":true,"outcome_unknown":false,
        "module_scope":["lnx.people_graph.v1"],"restored":[1],"conflicts":[],
        "face_decoration_batch_review":{"version":1,"review_sha256":"a".repeat(64),"member_count":1}});
    assert!(crate::batch_api::history::receipt(&v));v["face_decoration_batch_review"]["member_count"]=json!(2);assert!(!crate::batch_api::history::receipt(&v));
}
#[test] fn mismatched_image_read_cannot_release_original_request() {
    let epoch=[194;16];let mut h=host(epoch);let c=image_request_fixture();h.begin_command(epoch,&c).unwrap();
    let v=json!({"event":"batch_result","action":"face_decoration_visual","success":false,"outcome_unknown":false,
        "error":"expired","request_id":c["request_id"],"preflight_token":c["preflight_token"],"document_id":"e".repeat(32),
        "revision":c["revision"],"side":c["side"],"sha256":c["sha256"]});h.receive(epoch,&v);
    assert_eq!(h.status("eye-image")["result"]["outcome_unknown"],json!(true));
}
#[test] fn dual_history_and_noop_have_distinct_marker_rules() {
    let mut history=json!({"action":"redo","batch_id":"existing","success":true,"outcome_unknown":false,
        "module_scope":["lnx.people_graph.v1"],"restored":[1],"conflicts":[],
        "face_decoration_batch_review":{"version":1,"review_sha256":"a".repeat(64),"member_count":1},
        "eye_bag_batch_review":{"version":1,"review_sha256":"b".repeat(64),"member_count":1}});
    assert!(crate::batch_api::history::receipt(&history));
    history["eye_bag_batch_review"]["member_count"]=json!(2);assert!(!crate::batch_api::history::receipt(&history));
    let mut result=terminal(&commit_fixture());result["batch_id"]=Value::Null;result["applied"]=json!([]);
    result["target_outcomes"][0]["outcome"]=json!("noop");result["target_outcomes"][0]["result_revision"]=json!("3");
    result.as_object_mut().unwrap().remove("face_decoration_batch_review");assert!(receipt(&result));
    result["face_decoration_batch_review"]=json!({"version":1,"review_sha256":"a".repeat(64),"member_count":1});assert!(!receipt(&result));
}
#[test] fn selected_neutral_eye_leaf_does_not_invent_dedicated_eye_ack() {
    let mut result=terminal(&commit_fixture());
    result["module_scope"]=json!([OP,crate::batch_api::eye_bag::OP]);
    assert!(receipt(&result));assert!(crate::batch_api::eye_bag::receipt(&result));
    // If an actual dedicated eye ACK was submitted, its exact shape and image
    // pairing are mandatory; operation-list membership is not that authority.
    result[crate::batch_api::eye_bag::ACK]=json!([]);assert!(!receipt(&result));
}
