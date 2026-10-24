//! AUTHORED / UNRUN. Synthetic transport fixtures, not portrait/render acceptance.
use super::*;
use crate::receipt_host::ReceiptKind;

fn owner(id: char, asset: char, private: bool) -> Value {
    let document = id.to_string().repeat(32);
    json!({"document":{"document_id":document,"epoch":"workspace","revision":3},
        "people_scope":if private {document} else {"project".into()},
        "state_revision":2,"association_revision":1,"graph_sha256":"e".repeat(64),
        "source_proof":{"asset_sha256":asset.to_string().repeat(64),
            "original_sha256":asset.to_string().repeat(64),"creative_source":null}})
}
fn face_ref(asset: char, id: &str) -> Value {
    json!({"asset_sha256":asset.to_string().repeat(64),"face_instance_id":id,"analysis_revision":1})
}
fn selected() -> Value {
    let mut result = json!({});
    for (op, paths) in face_style::LEAVES { result[*op] = json!(paths); }
    result
}
fn intent() -> Value {
    let rows: Vec<Value> = face_style::LEAVES.iter().flat_map(|(op, paths)| paths.iter().map(move |path| {
        let coefficient: f64 = match (*op, path.split('/').nth(1).unwrap_or("")) {
            ("lnx.face_contour.v1", "temple") => -0.12,
            ("lnx.face_contour.v1", "cheekbone") => 0.18,
            ("lnx.face_contour.v1", "jaw") => -0.20,
            ("lnx.eye_shape.v1", "size") => 0.18,
            _ => 0.0,
        };
        json!({"op":op,"path":path,"value":if path.ends_with("/linked") {json!(true)} else {json!(coefficient * 0.5)}})
    })).collect();
    json!(rows)
}
fn request_fixture(named: bool, operation: &str) -> Value {
    let selection = if operation == "unlink" { json!({}) }
        else if !named && operation == "patch" { json!({"lnx.eye_shape.v1":["/size/left"]}) } else { selected() };
    let mut ops: Vec<String> = selection.as_object().unwrap().keys().cloned().collect(); ops.sort();
    let mut request = json!({"cmd":"batch","action":"preflight","request_id":"portrait-review",
        "docs":["b".repeat(32)],"module_scope":ops,"conflict_policy":"recheck",
        "people_transfer":{"target_policy":"persistent_association","operation":operation,"association_id":"person-cohort",
            "source_ref":face_ref('c',"source-face"),"source":owner('a','c',false),"selection":selection,
            "targets":[{"target":owner('b','d',true),"target_refs":[face_ref('d',"target-face")]}]}});
    if named { request["people_transfer"]["face_style"] = json!({"version":1,"style":"classic","amount":0.5}); }
    request
}
fn endpoint(owner: &Value, reference: &Value, index: usize) -> Value {
    let before = json!({"mime":"image/png","width":1024,"height":768,"sha256":(index * 2 + 1).to_string().repeat(64)});
    let after = json!({"mime":"image/png","width":1024,"height":768,"sha256":(index * 2 + 2).to_string().repeat(64)});
    json!({"index":index,"path":if index == 0 {"/source.raw"} else {"/target.raw"},"live":index == 0,
        "document_id":owner["document"]["document_id"],"revision":"3","blocked":null,"before":{},
        "association":{"owner":owner,"ref":reference,"candidate_sha256":"8".repeat(64),"person_id":"person-cohort",
            "portrait_visual":{"version":1,"document_id":owner["document"]["document_id"],"revision":"3",
                "source_proof":owner["source_proof"],"before_state_sha256":"5".repeat(64),"candidate_state_sha256":"5".repeat(64),
                "before_people_sha256":"6".repeat(64),"candidate_people_sha256":"7".repeat(64),
                "source_size":[4000,3000],"before_output_size":[4000,3000],"after_output_size":[4000,3000],
                "before":before,"after":after,"cohort_sha256":"f".repeat(64)}}})
}
fn plan(named: bool, operation: &str) -> Value {
    let request = request_fixture(named, operation); let applies = &request["people_transfer"];
    let source = endpoint(&applies["source"], &applies["source_ref"], 0);
    let target = endpoint(&applies["targets"][0]["target"], &applies["targets"][0]["target_refs"][0], 1);
    let members: Vec<Value> = [&source, &target].iter().map(|row| {
        let a = &row["association"]; json!({"document_id":row["document_id"],"scope_id":a["owner"]["people_scope"],
            "original_sha256":a["owner"]["source_proof"]["original_sha256"],"ref":a["ref"]})
    }).collect();
    json!({"event":"batch_result","action":"preflight","request_id":request["request_id"],"success":true,
        "preflight_token":"9".repeat(32),"module_scope":request["module_scope"],"people_transfer":true,"applies":applies,
        "policy":"recheck","portrait_cohort":true,"persistent_association":{"version":1,"operation":operation,
            "association_id":"person-cohort","generation":"e".repeat(64),"members":members,"intent":intent()},
        "source_snapshot":{"document_id":source["document_id"],"revision":source["revision"],"path":source["path"]},
        "association_source":source,"targets":[target],"ok":1,"blocked":0,"rejected_docs":[]})
}
fn acks(plan: &Value) -> Value {
    json!(std::iter::once(&plan["association_source"]).chain(plan["targets"].as_array().unwrap()).map(|row| {
        let image = &row["association"]["portrait_visual"];
        json!({"document_id":row["document_id"],"revision":row["revision"],"before_sha256":image["before"]["sha256"],
            "after_sha256":image["after"]["sha256"],"cohort_sha256":image["cohort_sha256"]})
    }).collect::<Vec<_>>())
}
fn commit_request(plan: &Value) -> Value {
    let mut value = json!({"cmd":"batch","action":"commit","request_id":"portrait-commit",
        "preflight_token":plan["preflight_token"],"module_scope":plan["module_scope"],(ACK):acks(plan)});
    if plan["collarbone_cohort"] == true {
        value[collarbone::ACK] = json!(std::iter::once(&plan["association_source"])
            .chain(plan["targets"].as_array().unwrap()).map(|row| {
                let image = &row["association"]["collarbone_visual"];
                json!({"document_id":row["document_id"],"revision":row["revision"],"before_sha256":image["before"]["sha256"],
                    "after_sha256":image["after"]["sha256"],"coverage_sha256":image["coverage_sha256"]})
            }).collect::<Vec<_>>());
    }
    value
}
fn terminal(plan: &Value, request: &Value) -> Value {
    let outcomes: Vec<Value> = std::iter::once(&plan["association_source"]).chain(plan["targets"].as_array().unwrap()).map(|row|
        json!({"index":row["index"],"path":row["path"],"document_id":row["document_id"],
            "expected_revision":row["revision"],"result_revision":"4","outcome":"applied","blocked":null})).collect();
    let mut value = json!({"event":"batch_result","action":"commit","request_id":request["request_id"],"success":true,
        "outcome_unknown":false,"preflight_token":request["preflight_token"],"module_scope":request["module_scope"],
        "portrait_cohort":true,(ACK):request[ACK],"people_transfer":true,"batch_id":"cohort-batch",
        "source_snapshot":plan["source_snapshot"],"persistent_association":plan["persistent_association"],
        "source_outcome":outcomes[0],"target_outcomes":outcomes[1..],"applied":[0,1],"skipped":[],
        "source_changed_since_preflight":false,"source_missing":false});
    if request.get(collarbone::ACK).is_some() {
        value[collarbone::ACK] = request[collarbone::ACK].clone(); value["collarbone_cohort"] = json!(true);
    }
    value
}
fn dual(mut plan: Value) -> Value {
    plan["collarbone_cohort"] = json!(true);
    let source = &mut plan["association_source"];
    add_collarbone(source);
    for row in plan["targets"].as_array_mut().unwrap() { add_collarbone(row); }
    plan
}
fn add_collarbone(row: &mut Value) {
    let mut image = row["association"]["portrait_visual"].clone();
    image.as_object_mut().unwrap().remove("cohort_sha256"); image["coverage_sha256"] = json!("c".repeat(64));
    row["association"]["collarbone_visual"] = image;
    row["association"]["collarbone_coverage"] = json!({"version":1,"support_transfer":"none",
        "targets":[{"face_ref":row["association"]["ref"],"scope":"neutral-no-effect","body_review_sha256":null,
            "clavicle_category":null,"clavicle_sides":[]}]});
}
fn host(epoch: [u8;16]) -> crate::batch_host::BatchHost {
    let mut h = crate::batch_host::BatchHost::default(); h.reset(epoch); h.ready(epoch, true); h
}

#[test] fn named_create_patch_are_exact_local_recipes_not_donor_selection() {
    for operation in ["create", "patch"] {
        let request = request_fixture(true, operation);
        assert!(command(&request).is_ok()); assert!(face_style::command(&request).is_ok());
        assert!(collarbone::command(&request).is_ok()); assert!(crate::batch_api::read_only(&request));
        assert!(receipt(&plan(true, operation)));
        for path in ["/people_transfer/source", "/people_transfer/source_ref", "/people_transfer/face_style",
            "/people_transfer/selection/lnx.eye_shape.v1", "/people_transfer/targets/0/target_refs"] {
            let mut changed = request.clone(); *changed.pointer_mut(path).unwrap() = Value::Null;
            assert!(command(&changed).is_err(), "{path}"); assert!(!crate::batch_api::read_only(&changed));
        }
        let mut changed = request.clone(); changed["module_scope"].as_array_mut().unwrap().reverse();
        assert!(command(&changed).is_err()); assert!(!crate::batch_api::read_only(&changed));
        changed = request.clone(); changed["people_transfer"]["selection"]["lnx.eye_shape.v1"][0] = json!("/size/left");
        assert!(command(&changed).is_err());
        changed = request; changed["people_transfer"]["targets"][0]["target"]["people_scope"] = json!("project");
        assert!(command(&changed).is_err());
    }
    let value = plan(true, "create");
    for replacement in [json!(0.7), json!(false), json!("0.09"), Value::Null] {
        let mut changed = value.clone(); changed["persistent_association"]["intent"][0]["value"] = replacement;
        assert!(!receipt(&changed));
    }
    let mut changed = value.clone(); changed["applies"]["face_style"]["style"] = json!("long"); assert!(!receipt(&changed));
    changed = value; changed["applies"]["face_style"]["amount"] = json!(0); assert!(!receipt(&changed));
}
#[test] fn complete_content_keeps_generic_patch_and_unlink_review_required() {
    for operation in ["create", "patch", "unlink"] {
        let request = request_fixture(false, operation); let value = plan(false, operation);
        assert!(command(&request).is_ok()); assert!(read_only(&request)); assert!(receipt(&value));
        assert!(crate::batch_host::BatchKind::valid(&value, None));
        assert!(value["applies"].get("face_style").is_none());
        let mut changed = value.clone(); changed.as_object_mut().unwrap().remove("portrait_cohort"); assert!(!receipt(&changed));
        changed = value.clone(); changed["persistent_association"]["intent"].as_array_mut().unwrap().pop(); assert!(!receipt(&changed));
        changed = value.clone(); changed["association_source"]["association"].as_object_mut().unwrap().remove("portrait_visual");
        assert!(!receipt(&changed));
        changed = value; changed["targets"][0]["association"].as_object_mut().unwrap().remove("portrait_visual"); assert!(!receipt(&changed));
    }
    let mut generic = plan(false, "patch"); generic["persistent_association"]["intent"][1]["value"] = json!(0.31);
    assert!(receipt(&generic)); // No invented named recipe is used to bless a later generic edit.
    let request = request_fixture(false, "unlink"); assert_eq!(request["module_scope"], json!([]));
    let mut changed = request.clone(); changed["people_transfer"]["face_style"] = json!({"version":1,"style":"classic","amount":0.0});
    assert!(command(&changed).is_err());
    changed = request; changed["module_scope"] = json!(["lnx.eye_shape.v1"]); assert!(command(&changed).is_err());
}
#[test] fn public_association_review_stays_capsule_v1_scalar_content_only() {
    let value = plan(true, "create");
    assert!(fields(&value["persistent_association"], &["version", "operation", "association_id", "generation", "members", "intent"]));
    for key in ["face_style", "style", "recipe", "portrait_visual", "local_document_id"] {
        let mut changed = value.clone(); changed["persistent_association"][key] = json!("fabricated"); assert!(!receipt(&changed));
    }
    for key in ["portrait_snapshots", "face_style", "recipe_sha256"] {
        let mut changed = value.clone(); changed["association_source"]["association"][key] = json!({}); assert!(!receipt(&changed));
    }
    // Native does not reconstruct Python's float-bearing generation/cohort JSON.
    let mut changed = value.clone(); changed["persistent_association"]["generation"] = json!("1".repeat(64));
    changed["association_source"]["association"]["portrait_visual"]["cohort_sha256"] = json!("2".repeat(64));
    changed["targets"][0]["association"]["portrait_visual"]["cohort_sha256"] = json!("2".repeat(64)); assert!(receipt(&changed));
    changed["targets"][0]["association"]["portrait_visual"]["cohort_sha256"] = json!("3".repeat(64)); assert!(!receipt(&changed));
}
#[test] fn every_visual_is_bound_to_its_own_source_revision_and_full_dimensions() {
    let value = plan(true, "create");
    for (path, replacement) in [
        ("/association_source/association/portrait_visual/document_id", json!("b".repeat(32))),
        ("/targets/0/association/portrait_visual/revision", json!("4")),
        ("/targets/0/association/portrait_visual/source_proof/asset_sha256", json!("c".repeat(64))),
        ("/targets/0/association/portrait_visual/before/width", json!(256)),
        ("/targets/0/association/portrait_visual/cohort_sha256", json!("a".repeat(64))),
        ("/targets/0/association/owner/graph_sha256", json!("a".repeat(64))),
        ("/targets/0/association/ref/analysis_revision", json!(2)),
        ("/targets/0/index", json!(0)),
        ("/source_snapshot/revision", json!("4")),
    ] {
        let mut changed = value.clone(); *changed.pointer_mut(path).unwrap() = replacement; assert!(!receipt(&changed), "{path}");
    }
    let mut changed = value; changed["targets"][0]["association"]["portrait_visual"]["recipe_sha256"] = json!("f".repeat(64));
    assert!(!receipt(&changed));
}
#[test] fn source_first_commit_is_exact_atomic_and_scope_bound_including_empty_unlink() {
    for (named, operation) in [(true, "create"), (false, "patch"), (false, "unlink")] {
        let plan = plan(named, operation); let request = commit_request(&plan); let value = terminal(&plan, &request);
        assert!(command(&request).is_ok()); assert!(!read_only(&request)); assert!(receipt(&value));
        assert!(crate::batch_host::BatchKind::valid(&value, None));
        let mut h = host([241;16]); h.begin_command([241;16], &request).unwrap(); h.receive([241;16], &value);
        assert_eq!(h.status("portrait-commit")["result"], value);
        for path in ["/source_outcome", "/target_outcomes", "/persistent_association"] {
            let mut changed = value.clone(); *changed.pointer_mut(path).unwrap() = Value::Null; assert!(!receipt(&changed));
        }
        for (path, replacement) in [("/source_outcome/result_revision", json!("3")),
            ("/target_outcomes/0/outcome", json!("skipped")), ("/target_outcomes/0/result_revision", json!("3")),
            ("/source_outcome/document_id", json!("b".repeat(32))), ("/applied/0", json!(1)),
            ("/batch_id", Value::Null), ("/source_changed_since_preflight", json!(true))] {
            let mut changed = value.clone(); *changed.pointer_mut(path).unwrap() = replacement; assert!(!receipt(&changed), "{path}");
        }
        let mut changed = value.clone(); changed[ACK].as_array_mut().unwrap().reverse(); assert!(!receipt(&changed));
        changed = value.clone(); changed["source_outcome"]["current_revision"] = json!("3"); assert!(!receipt(&changed));
        changed = value; changed["module_scope"] = json!(["lnx.nose_shape.v1"]);
        let mut h = host([242;16]); h.begin_command([242;16], &request).unwrap(); h.receive([242;16], &changed);
        assert_eq!(h.status("portrait-commit")["result"]["outcome_unknown"], true);
        assert_eq!(h.status("portrait-commit")["result"]["module_scope"], request["module_scope"]);
    }
    let request = commit_request(&plan(true, "create"));
    for key in ["people_transfer", "docs", "face_style_review_ack", "portrait_cohort", "head_review_ack"] {
        let mut changed = request.clone(); changed[key] = json!({}); assert!(command(&changed).is_err());
    }
    let mut changed = request; changed.as_object_mut().unwrap().remove("module_scope"); assert!(command(&changed).is_err());
}
#[test] fn dual_reviews_share_pixels_but_keep_both_independent_commitments() {
    let plan = dual(plan(true, "create")); let request = commit_request(&plan); let value = terminal(&plan, &request);
    assert!(receipt(&plan)); assert!(crate::batch_host::BatchKind::valid(&plan, None));
    assert!(command(&request).is_ok()); assert!(collarbone::command(&request).is_ok());
    assert!(crate::batch_host::BatchKind::valid(&value, None));
    for path in ["/association_source/association/collarbone_visual/before/sha256",
        "/targets/0/association/collarbone_visual/after/sha256", "/targets/0/association/collarbone_visual/candidate_people_sha256"] {
        let mut changed = plan.clone(); *changed.pointer_mut(path).unwrap() = json!("9".repeat(64)); assert!(!receipt(&changed));
    }
    let mut changed = request.clone(); changed[collarbone::ACK].as_array_mut().unwrap().reverse(); assert!(command(&changed).is_err());
    changed = request.clone(); changed[collarbone::ACK][0]["before_sha256"] = json!("9".repeat(64)); assert!(command(&changed).is_err());
    let bound = binding(&request).unwrap().unwrap(); assert_eq!(bound[ACK], request[ACK]); assert_eq!(bound[collarbone::ACK], request[collarbone::ACK]);
    let mut changed = value; changed[collarbone::ACK][0]["coverage_sha256"] = json!("9".repeat(64));
    let mut h = host([243;16]); h.begin_command([243;16], &request).unwrap(); h.receive([243;16], &changed);
    let unknown = h.status("portrait-commit")["result"].clone(); assert_eq!(unknown["outcome_unknown"], true);
    assert_eq!(unknown[ACK], request[ACK]); assert_eq!(unknown[collarbone::ACK], request[collarbone::ACK]);
}
#[test] fn receipt_cannot_add_an_unrequested_ack_family_or_settle_an_unknown() {
    let plan = plan(true, "create"); let original = commit_request(&plan);
    let dual_plan = dual(plan.clone()); let dual_request = commit_request(&dual_plan);
    let added = terminal(&dual_plan, &dual_request);
    let mut h = host([244;16]); h.begin_command([244;16], &original).unwrap(); h.receive([244;16], &added);
    let unknown = h.status("portrait-commit")["result"].clone();
    assert_eq!(unknown["outcome_unknown"], true); assert!(unknown.get(collarbone::ACK).is_none());
    h.receive([244;16], &terminal(&plan, &original)); assert_eq!(h.status("portrait-commit")["result"], unknown);
    assert!(h.begin_command([244;16], &original).is_err());
}
#[test] fn exact_unclaimed_refusal_is_safe_but_uncertain_commit_retains_both_arrays() {
    let plan = dual(plan(true, "create")); let request = commit_request(&plan);
    let refusal = json!({"event":"batch_result","action":"commit","request_id":request["request_id"],
        "success":false,"outcome_unknown":false,"error":"Frozen plan expired","preflight_token":request["preflight_token"]});
    let mut h = host([245;16]); h.begin_command([245;16], &request).unwrap(); h.receive([245;16], &refusal);
    assert_eq!(h.status("portrait-commit")["result"], refusal);
    let mut h = host([246;16]); h.begin_command([246;16], &request).unwrap(); h.failed("portrait-commit", "Transport disconnected");
    let unknown = h.status("portrait-commit")["result"].clone(); assert_eq!(unknown["outcome_unknown"], true);
    for key in [ACK, collarbone::ACK, "preflight_token", "module_scope"] { assert_eq!(unknown[key], request[key]); }
    assert_eq!(unknown["portrait_cohort"], true); assert_eq!(unknown["collarbone_cohort"], true);
}
fn image_request_fixture() -> Value {
    json!({"cmd":"batch","action":"portrait_cohort_visual","request_id":"portrait-image","preflight_token":"9".repeat(32),
        "document_id":"a".repeat(32),"revision":"3","side":"before","sha256":"1".repeat(64)})
}
#[test] fn image_reads_require_exact_frozen_coordinates_and_echo_even_on_failure() {
    let request = image_request_fixture(); assert!(command(&request).is_ok()); assert!(read_only(&request));
    assert!(crate::batch_api::read_only(&request)); assert!(collarbone::command(&request).is_ok());
    for key in ["docs", "module_scope", "people_transfer", ACK, "path"] {
        let mut changed = request.clone(); changed[key] = json!({}); assert!(command(&changed).is_err()); assert!(!read_only(&changed));
    }
    for key in ["preflight_token", "document_id", "revision", "side", "sha256"] {
        let mut h = host([247;16]); h.begin_command([247;16], &request).unwrap();
        let mut failure = binding(&request).unwrap().unwrap(); failure["action"] = request["action"].clone();
        failure["request_id"] = request["request_id"].clone(); failure["success"] = json!(false);
        failure["outcome_unknown"] = json!(false); failure["error"] = json!("Image expired"); failure[key] = json!("changed");
        h.receive([247;16], &failure); let result = h.status("portrait-image")["result"].clone();
        assert_eq!(result["outcome_unknown"], true); assert_eq!(result[key], request[key]);
    }
}
#[test] fn retrieved_png_bytes_hash_and_compact_metadata_are_checked() {
    let proof = owner('a','c',false)["source_proof"].clone();
    let sample = crate::spill_transfer_protocol::tests::sample_transfer(&json!("a".repeat(32)), &json!("3"), &json!({}), &proof);
    let image = sample["before"].clone(); let mut compact = image.clone(); compact.as_object_mut().unwrap().remove("base64");
    let mut value = image_request_fixture(); value.as_object_mut().unwrap().remove("cmd"); value["success"] = json!(true);
    value["outcome_unknown"] = json!(false); value["sha256"] = image["sha256"].clone(); value["compact"] = compact; value["image"] = image;
    assert!(receipt(&value)); assert!(crate::batch_host::BatchKind::valid(&value, None));
    for (path, replacement) in [("/compact/width", json!(2)), ("/image/base64", json!("AAAA")),
        ("/sha256", json!("f".repeat(64))), ("/compact/sha256", json!("e".repeat(64)))] {
        let mut changed = value.clone(); *changed.pointer_mut(path).unwrap() = replacement; assert!(!receipt(&changed));
    }
    let mut changed = value; changed["doc_state"] = json!({}); assert!(!receipt(&changed));
}
#[test] fn read_only_images_do_not_bypass_pending_mutation_id_collisions() {
    let epoch = [248;16]; let mut image = image_request_fixture(); image["request_id"] = json!("collision");
    crate::project_recovery_fence::issued(epoch, &json!({"cmd":"people","action":"commit","request_id":"collision"})).unwrap();
    assert!(crate::project_recovery_fence::issued(epoch, &image).is_err());
    assert!(crate::project_recovery_fence::proof(epoch).is_err());
    crate::project_recovery_fence::observed(epoch, &json!({"event":"batch_result","action":"portrait_cohort_visual",
        "request_id":"collision","success":true,"outcome_unknown":false}));
    assert!(crate::project_recovery_fence::proof(epoch).is_err());
    crate::project_recovery_fence::observed(epoch, &json!({"event":"project_opened"}));
    crate::project_recovery_fence::issued(epoch, &image).unwrap(); assert!(crate::project_recovery_fence::proof(epoch).is_ok());
}
