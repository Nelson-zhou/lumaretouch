//! AUTHORED / UNRUN synthetic transport data; no image-quality evidence.
use super::*;
use crate::batch_api::face_style;
pub(super) fn owner(id: char, asset: char, private: bool) -> Value {
    let document = id.to_string().repeat(32);
    json!({"document":{"document_id":document,"epoch":"workspace","revision":3},
        "people_scope":if private {document} else {"project".into()},"state_revision":2,"association_revision":1,
        "graph_sha256":"e".repeat(64),"source_proof":{"asset_sha256":asset.to_string().repeat(64),
            "original_sha256":asset.to_string().repeat(64),"creative_source":null}})
}
fn face(asset: char, id: &str) -> Value {
    json!({"asset_sha256":asset.to_string().repeat(64),"face_instance_id":id,"analysis_revision":1})
}
pub(super) fn request_fixture(operation: &str) -> Value {
    let selection = match operation {
        "unlink" => json!({}), "patch" => json!({"lnx.eye_shape.v1":["/size/left"]}),
        _ => json!({(eye_bag::OP):["/amount", "/preserve"]}),
    };
    let ops: Vec<_> = selection.as_object().unwrap().keys().cloned().collect();
    json!({"cmd":"batch","action":"preflight","request_id":"cohort-review","docs":["b".repeat(32)],
        "module_scope":ops,"conflict_policy":"recheck","people_transfer":{"target_policy":"persistent_association",
        "operation":operation,"association_id":"person-cohort","source_ref":face('c',"source-face"),
        "source":owner('a','c',false),"selection":selection,
        "targets":[{"target":owner('b','d',true),"target_refs":[face('d',"target-face")]}],
        (KEY):{"version":1,"members":[{"document_id":"a".repeat(32),"replace_legacy":true},
            {"document_id":"b".repeat(32),"replace_legacy":false}]}}})
}
fn endpoint(owner: &Value, reference: &Value, choice: &Value, index: usize) -> Value {
    let coverage = json!({"version":1,"support_transfer":"none","replace_legacy":choice["replace_legacy"],"face_ref":reference,
        "before":{"scope":"target-reviewed-ridge","ridge_sha256":(index + 5).to_string().repeat(64),"sides":["left"]},
        "after":{"scope":"target-reviewed-ridge","ridge_sha256":(index + 5).to_string().repeat(64),"sides":["left"]}});
    let before = json!({"mime":"image/png","width":1024,"height":768,"sha256":(index * 2 + 1).to_string().repeat(64)});
    let after = json!({"mime":"image/png","width":1024,"height":768,"sha256":(index * 2 + 2).to_string().repeat(64)});
    json!({"index":index,"path":if index == 0 {"/source.raw"} else {"/target.raw"},"live":index == 0,
        "document_id":owner["document"]["document_id"],"revision":"3","blocked":null,"before":{},
        "association":{"owner":owner,"ref":reference,"candidate_sha256":"8".repeat(64),"person_id":"person-cohort",
            (KEY):coverage,(VISUAL):{"version":1,"document_id":owner["document"]["document_id"],"revision":"3",
                "source_proof":owner["source_proof"],"before_state_sha256":"5".repeat(64),"candidate_state_sha256":"5".repeat(64),
                "before_people_sha256":"6".repeat(64),"candidate_people_sha256":"7".repeat(64),
                "source_size":[4000,3000],"before_output_size":[4000,3000],"after_output_size":[4000,3000],
                "before":before,"after":after,"coverage_sha256":collarbone::request_digest(&coverage)}}})
}
pub(super) fn plan(operation: &str) -> Value {
    let request = request_fixture(operation); let applies = &request["people_transfer"];
    let source = endpoint(&applies["source"], &applies["source_ref"], &applies[KEY]["members"][0], 0);
    let target = endpoint(&applies["targets"][0]["target"], &applies["targets"][0]["target_refs"][0], &applies[KEY]["members"][1], 1);
    let members: Vec<Value> = [&source, &target].iter().map(|row| {
        let a = &row["association"]; json!({"document_id":row["document_id"],"scope_id":a["owner"]["people_scope"],
            "original_sha256":a["owner"]["source_proof"]["original_sha256"],"ref":a["ref"]})
    }).collect();
    let mut intent = json!([{"op":eye_bag::OP,"path":"/amount","value":0.5},{"op":eye_bag::OP,"path":"/preserve","value":1.0}]);
    if operation == "patch" { intent.as_array_mut().unwrap().push(json!({"op":"lnx.eye_shape.v1","path":"/size/left","value":0.1})); }
    json!({"event":"batch_result","action":"preflight","request_id":request["request_id"],"success":true,"outcome_unknown":false,
        "preflight_token":"9".repeat(32),"module_scope":request["module_scope"],"people_transfer":true,"applies":applies,
        "policy":"recheck",(KEY):true,"persistent_association":{"version":1,"operation":operation,
            "association_id":"person-cohort","generation":"e".repeat(64),"members":members,"intent":intent},
        "source_snapshot":{"document_id":source["document_id"],"revision":source["revision"],"path":source["path"]},
        "association_source":source,"targets":[target],"ok":1,"blocked":0,"rejected_docs":[]})
}
pub(super) fn refresh(row: &mut Value) {
    row["association"][VISUAL]["coverage_sha256"] = json!(collarbone::request_digest(&row["association"][KEY]));
}
pub(super) fn commit_request(plan: &Value) -> Value {
    let rows = || std::iter::once(&plan["association_source"]).chain(plan["targets"].as_array().unwrap());
    let acks: Vec<Value> = rows().map(|row| {
        let a = &row["association"]; let image = &a[VISUAL];
        json!({"document_id":row["document_id"],"revision":row["revision"],"before_sha256":image["before"]["sha256"],
            "after_sha256":image["after"]["sha256"],"coverage_sha256":image["coverage_sha256"],"replace_legacy":a[KEY]["replace_legacy"]})
    }).collect();
    let mut value = json!({"cmd":"batch","action":"commit","request_id":"cohort-commit","preflight_token":plan["preflight_token"],
        "module_scope":plan["module_scope"],(ACK):acks});
    for (flag, key, visual_key, hash) in [("portrait_cohort", portrait::ACK, "portrait_visual", "cohort_sha256"),
        ("collarbone_cohort", collarbone::ACK, "collarbone_visual", "coverage_sha256")] {
        if plan[flag] != true { continue; }
        value[key] = json!(rows().map(|row| {
            let image = &row["association"][visual_key];
            json!({"document_id":row["document_id"],"revision":row["revision"],"before_sha256":image["before"]["sha256"],
                "after_sha256":image["after"]["sha256"],(hash):image[hash]})
        }).collect::<Vec<_>>());
    }
    value
}
pub(super) fn terminal(plan: &Value, command: &Value) -> Value {
    let outcomes: Vec<Value> = std::iter::once(&plan["association_source"]).chain(plan["targets"].as_array().unwrap()).map(|row|
        json!({"index":row["index"],"path":row["path"],"document_id":row["document_id"],"expected_revision":row["revision"],
            "result_revision":"4","outcome":"applied","blocked":null})).collect();
    let mut value = binding(command).unwrap().unwrap();
    for (key, field) in json!({"event":"batch_result","action":"commit","request_id":command["request_id"],"success":true,
        "outcome_unknown":false,"people_transfer":true,"batch_id":"existing-cohort-batch","source_snapshot":plan["source_snapshot"],
        "persistent_association":plan["persistent_association"],"source_outcome":outcomes[0],"target_outcomes":outcomes[1..],
        "applied":[0,1],"skipped":[],"source_changed_since_preflight":false,"source_missing":false}).as_object().unwrap() {
        value[key] = field.clone();
    }
    value
}
pub(super) fn mixed(mut v: Value, portrait: bool, collar: bool) -> Value {
    if portrait {
        v["portrait_cohort"] = json!(true);
        for (op, paths) in face_style::LEAVES { for path in *paths {
            if !v["persistent_association"]["intent"].as_array().unwrap().iter().any(|leaf| leaf["op"] == *op && leaf["path"] == *path) {
                v["persistent_association"]["intent"].as_array_mut().unwrap().push(json!({"op":op,"path":path,
                    "value":if path.ends_with("/linked") {json!(true)} else {json!(0.1)}}));
            }
        }}
    }
    if collar {
        v["collarbone_cohort"] = json!(true);
        v["persistent_association"]["intent"].as_array_mut().unwrap().push(json!({"op":collarbone::OP,"path":"/amount","value":0}));
    }
    let mut rows = vec![v["association_source"].clone(),v["targets"][0].clone()];
    for row in &mut rows {
        let a = &mut row["association"];
        if portrait {
            let mut image = a[VISUAL].clone(); image.as_object_mut().unwrap().remove("coverage_sha256"); image["cohort_sha256"] = json!("f".repeat(64));
            a["portrait_visual"] = image;
        }
        if collar {
            a["collarbone_coverage"] = json!({"version":1,"support_transfer":"none","targets":[{"face_ref":a["ref"],
                "scope":"neutral-no-effect","body_review_sha256":null,"clavicle_category":null,"clavicle_sides":[]}]});
            let mut image = a[VISUAL].clone(); image["coverage_sha256"] = json!(collarbone::request_digest(&a["collarbone_coverage"]));
            a["collarbone_visual"] = image;
        }
    }
    v["association_source"] = rows.remove(0); v["targets"][0] = rows.remove(0); v
}
pub(super) fn host(epoch: [u8;16]) -> crate::batch_host::BatchHost {
    let mut h = crate::batch_host::BatchHost::default(); h.reset(epoch); h.ready(epoch, true); h
}
pub(super) fn image_request_fixture() -> Value {
    json!({"cmd":"batch","action":VISUAL,"request_id":"cohort-image","preflight_token":"9".repeat(32),
        "document_id":"a".repeat(32),"revision":"3","side":"before","sha256":"1".repeat(64)})
}
