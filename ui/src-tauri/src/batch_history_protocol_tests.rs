//! AUTHORED / UNRUN. Existing-history identity and restored-eye regression fixtures.
use super::*;
fn request() -> Value { json!({"cmd":"batch","action":"undo","request_id":"history","batch_id":"restored-eye-batch"}) }
fn result(c: &Value) -> Value {
    json!({"event":"batch_result","action":c["action"],"request_id":c["request_id"],"batch_id":c["batch_id"],
        "success":true,"outcome_unknown":false,"module_scope":["lnx.people_graph.v1"],"restored":[1,2],"conflicts":[],"doc_state":{}})
}
fn host(epoch: [u8;16]) -> crate::batch_host::BatchHost {
    let mut h=crate::batch_host::BatchHost::default();h.reset(epoch);h.ready(epoch,true);h
}
#[test] fn history_binding_does_not_need_a_session_only_eye_classification() {
    let c=request();assert!(command(&c).is_ok());assert_eq!(binding(&c).unwrap(),Some(json!({"batch_id":"restored-eye-batch"})));
    assert!(!crate::batch_api::read_only(&c));let mut h=host([159;16]);h.begin_command([159;16],&c).unwrap();
    assert!(h.guards_review([159;16],"history"));h.receive([159;16],&result(&c));assert_eq!(h.status("history")["result"],result(&c));
}
#[test] fn history_has_no_new_fields_or_write_authority() {
    let c=request();for key in ["module_scope","preflight_token","people_transfer","eye_bag_batch_review","eye_bag_review_ack"] {
        let mut bad=c.clone();bad[key]=json!({});assert!(command(&bad).is_err(),"{key}");
    }
    let mut legacy=c;legacy.as_object_mut().unwrap().remove("request_id");assert!(command(&legacy).is_ok());assert!(binding(&legacy).unwrap().is_none());
}
#[test] fn wrong_or_missing_batch_id_is_unknown_even_when_other_receipt_fields_match() {
    let c=request();for identity in [Value::Null,json!("another-batch")] {
        let mut h=host([160;16]);h.begin_command([160;16],&c).unwrap();let mut bad=result(&c);bad["batch_id"]=identity;
        h.receive([160;16],&bad);let retained=h.status("history")["result"].clone();
        assert_eq!(retained["outcome_unknown"],true);assert_eq!(retained["batch_id"],c["batch_id"]);
        h.receive([160;16],&result(&c));assert_eq!(h.status("history")["result"],retained);
    }
}
#[test] fn restored_eye_unknown_history_keeps_original_identity_and_recovery_fence() {
    let epoch=[161;16];let c=request();let mut h=host(epoch);h.begin_command(epoch,&c).unwrap();
    crate::project_recovery_fence::issued(epoch,&c).unwrap();h.failed("history","History transport outcome unknown");
    let retained=h.status("history");assert_eq!(retained["result"]["batch_id"],c["batch_id"]);
    assert!(crate::project_recovery_fence::proof(epoch).is_err());assert_eq!(retained,h.status("history"));
    let mut different=c.clone();different["action"]=json!("redo");assert!(crate::project_recovery_fence::issued(epoch,&different).is_err());
    h.receive(epoch,&result(&c));assert_eq!(h.status("history"),retained);
    crate::project_recovery_fence::observed(epoch,&json!({"event":"project_opened"}));
}
#[test] fn known_history_failure_still_echoes_exact_batch_identity() {
    let c=request();let failure=json!({"event":"batch_result","action":"undo","request_id":"history","batch_id":c["batch_id"],
        "success":false,"outcome_unknown":false,"error":"Protected target changed"});
    let mut h=host([162;16]);h.begin_command([162;16],&c).unwrap();h.receive([162;16],&failure);assert_eq!(h.status("history")["result"],failure);
    for key in ["batch_id","outcome_unknown"] {
        let mut h=host([163;16]);h.begin_command([163;16],&c).unwrap();let mut bad=failure.clone();bad.as_object_mut().unwrap().remove(key);
        h.receive([163;16],&bad);assert_eq!(h.status("history")["result"]["outcome_unknown"],true);
    }
}
#[test] fn old_scalar_and_ordinary_success_shapes_remain_supported() {
    for action in ["undo","redo"] {for op in ["lnx.head_size.v1","lnx.exposure.v1","lnx.people_graph.v1"] {
        let mut c=request();c["action"]=json!(action);let mut v=result(&c);v["module_scope"]=json!([op]);
        v["conflicts"]=json!([{"index":3,"path":"/target.raw","reason":"Later edit retained"}]);
        assert!(receipt(&v));let mut h=host([164;16]);h.begin_command([164;16],&c).unwrap();h.receive([164;16],&v);
        assert_eq!(h.status("history")["result"],v);
    }}
}
#[test] fn summary_is_bounded_public_provenance_not_a_full_support_record() {
    let mut v=result(&request());v["eye_bag_batch_review"]=json!({"version":1,"review_sha256":"a".repeat(64),"member_count":2});
    assert!(receipt(&v));
    for (key,bad) in [("member_count",json!(0)),("member_count",json!(17)),("member_count",json!(1)),("review_sha256",json!("not-a-digest"))] {
        let mut changed=v.clone();changed["eye_bag_batch_review"][key]=bad;assert!(!receipt(&changed));
    }
    v["eye_bag_batch_review"]["targets"]=json!([]);assert!(!receipt(&v));
}
#[test] fn reopened_eye_cohort_summary_requires_all_members_without_new_authority() {
    let c = request(); let mut v = result(&c);
    v["eye_bag_cohort_review"] = json!({"version":1,"review_sha256":"b".repeat(64),"member_count":2});
    assert!(receipt(&v)); let mut h = host([165;16]); h.begin_command([165;16], &c).unwrap(); h.receive([165;16], &v);
    assert_eq!(h.status("history")["result"], v);
    for key in ["eye_bag_cohort_review", "eye_bag_cohort_ack"] {
        let mut bad = c.clone(); bad[key] = v["eye_bag_cohort_review"].clone(); assert!(command(&bad).is_err());
    }
    for n in [0,1,3,17] { let mut bad = v.clone(); bad["eye_bag_cohort_review"]["member_count"] = json!(n); assert!(!receipt(&bad)); }
    let mut bad = v.clone(); bad["restored"] = json!([1]); assert!(!receipt(&bad));
    bad = v.clone(); bad["eye_bag_batch_review"] = v["eye_bag_cohort_review"].clone(); assert!(!receipt(&bad));
    bad = v; bad["eye_bag_cohort_review"]["support"] = json!({}); assert!(!receipt(&bad));
}
#[test] fn reopened_eye_alias_summary_is_distinct_and_requires_the_whole_reviewed_set() {
    let c = request(); let mut v = result(&c);
    v["eye_bag_alias_review"] = json!({"version":1,"review_sha256":"c".repeat(64),"member_count":2});
    assert!(receipt(&v)); let mut h = host([166;16]); h.begin_command([166;16], &c).unwrap(); h.receive([166;16], &v);
    assert_eq!(h.status("history")["result"], v);
    for key in ["eye_bag_alias_review", "eye_bag_batch_review", "eye_bag_cohort_review", "eye_bag_request"] {
        let mut bad = c.clone(); bad[key] = json!({}); assert!(command(&bad).is_err());
    }
    for n in [0,1,3,17] { let mut bad = v.clone(); bad["eye_bag_alias_review"]["member_count"] = json!(n); assert!(!receipt(&bad)); }
    for key in ["eye_bag_batch_review", "eye_bag_cohort_review"] {
        let mut bad = v.clone(); bad[key] = v["eye_bag_alias_review"].clone(); assert!(!receipt(&bad));
    }
    let mut bad = v.clone(); bad["restored"] = json!([1]); assert!(!receipt(&bad));
    bad = v.clone(); bad["conflicts"] = json!([{"index":2,"path":"/alias.raw","reason":"Changed"}]); assert!(!receipt(&bad));
    bad = v.clone(); bad["module_scope"] = json!(["lnx.eye_bags.v2"]); assert!(!receipt(&bad));
    bad = v; bad["eye_bag_alias_review"]["support"] = json!({}); assert!(!receipt(&bad));
}

fn preset_alias_result(c: &Value) -> Value {
    let mut value = result(c);
    value[PRESET_ALIAS_MARKER] = json!({"version":1,"review_sha256":"d".repeat(64),
        "preset_sha256":"e".repeat(64),"applies_sha256":"f".repeat(64),"current_document_id":"logical-active",
        "member_count":2,"selected_modules":["lnx.eye_bags.v2","lnx.exposure.v1"]}); value
}
#[test] fn reopened_composite_preset_history_keeps_its_distinct_bounded_marker() {
    for action in ["undo", "redo"] {
        let mut c = request(); c["action"] = json!(action); let value = preset_alias_result(&c);
        assert!(receipt(&value)); let mut h = host([238;16]); h.begin_command([238;16], &c).unwrap(); h.receive([238;16], &value);
        assert_eq!(h.status("history")["result"], value);
        for key in [PRESET_ALIAS_MARKER, "eye_bag_preset_ack", "alias_members", "selected_modules"] {
            let mut bad = c.clone(); bad[key] = json!({}); assert!(command(&bad).is_err());
        }
        for old in ["eye_bag_alias_review", "eye_bag_cohort_review", "eye_bag_batch_review"] {
            let mut bad = value.clone(); bad[old] = json!({"version":1,"review_sha256":"a".repeat(64),"member_count":2});
            assert!(!receipt(&bad));
            let mut bad = value.clone(); let marker = bad.as_object_mut().unwrap().remove(PRESET_ALIAS_MARKER).unwrap();
            bad[old] = marker; assert!(!receipt(&bad));
        }
    }
}
#[test] fn composite_history_refuses_partial_restore_or_recipe_scope_substitution() {
    let value = preset_alias_result(&request());
    for (path, changed) in [("/restored",json!([1])),("/module_scope",json!(["lnx.eye_bags.v2","lnx.exposure.v1"])),
        ("/conflicts",json!([{"index":2,"path":"/same.raw","reason":"Sibling edited"}])),
        ("/eye_bag_preset_alias_review/member_count",json!(17)),("/eye_bag_preset_alias_review/current_document_id",json!("")),
        ("/eye_bag_preset_alias_review/applies_sha256",json!("bad")),
        ("/eye_bag_preset_alias_review/selected_modules",json!(["lnx.exposure.v1"])),
        ("/eye_bag_preset_alias_review/selected_modules",json!(["lnx.eye_bags.v2","lnx.eye_bags.v2"])),
        ("/eye_bag_preset_alias_review/selected_modules",json!(["lnx.eye_bags.v2","lnx.people_graph.v1"]))] {
        let mut bad = value.clone(); *bad.pointer_mut(path).unwrap() = changed; assert!(!receipt(&bad), "{path}");
    }
    let mut bad = value; bad[PRESET_ALIAS_MARKER]["active_state"] = json!({}); assert!(!receipt(&bad));
}
#[test] fn unknown_reopened_composite_receipt_never_releases_batch_identity() {
    let c = request(); let epoch = [239;16]; let mut h = host(epoch); h.begin_command(epoch, &c).unwrap();
    crate::project_recovery_fence::issued(epoch, &c).unwrap();
    let mut bad = preset_alias_result(&c); bad["restored"] = json!([1]); h.receive(epoch, &bad);
    let retained = h.status("history"); assert_eq!(retained["result"]["outcome_unknown"], true);
    assert_eq!(retained["result"]["batch_id"], c["batch_id"]); assert!(crate::project_recovery_fence::proof(epoch).is_err());
    h.receive(epoch, &preset_alias_result(&c)); assert_eq!(h.status("history"), retained);
    crate::project_recovery_fence::observed(epoch, &json!({"event":"project_opened"}));
}
