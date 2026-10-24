//! AUTHORED / UNRUN. Protocol/ledger fixtures, never render or runtime acceptance.
use super::*;
use crate::receipt_host::ReceiptKind;
#[path = "eye_bag_cohort_fixtures.rs"]
mod fixtures;
use fixtures::*;

#[test] fn all_operations_require_exact_source_first_member_choices() {
    for operation in ["create", "patch", "unlink"] {
        let c = request_fixture(operation); assert!(command(&c).is_ok()); assert!(crate::batch_api::read_only(&c));
        assert!(portrait::command(&c).is_ok()); assert!(collarbone::command(&c).is_ok());
        for path in ["/people_transfer/eye_bag_cohort/members/0/replace_legacy", "/people_transfer/source_ref",
            "/people_transfer/targets/0/target", "/people_transfer/targets/0/target_refs"] {
            let mut bad = c.clone(); *bad.pointer_mut(path).unwrap() = Value::Null;
            assert!(command(&bad).is_err(), "{path}"); assert!(!crate::batch_api::read_only(&bad));
        }
        let mut bad = c.clone(); bad["people_transfer"][KEY]["members"].as_array_mut().unwrap().reverse(); assert!(command(&bad).is_err());
        bad = c.clone(); bad["people_transfer"][KEY]["members"].as_array_mut().unwrap().pop(); assert!(command(&bad).is_err());
        bad = c.clone(); bad["people_transfer"][KEY]["members"][1] = bad["people_transfer"][KEY]["members"][0].clone(); assert!(command(&bad).is_err());
        for key in ["support", "eyes", "before", "source"] {
            let mut bad = c.clone(); bad["people_transfer"][KEY][key] = json!({}); assert!(command(&bad).is_err());
        }
    }
}
#[test] fn ordinary_ack_and_policy_cannot_authorize_cohort() {
    let c = commit_request(&plan("create"));
    for key in [eye_bag::ACK, "eye_bag_preset_ack", "eye_bag_replace_legacy", "people_transfer", "docs", KEY] {
        let mut bad = c.clone(); bad[key] = json!({}); assert!(command(&bad).is_err(), "{key}");
    }
    let mut ordinary = c; ordinary[eye_bag::ACK] = ordinary[ACK].clone(); ordinary.as_object_mut().unwrap().remove(ACK);
    assert!(eye_bag::command(&ordinary).is_err());
    let mut missing = request_fixture("create"); missing["people_transfer"].as_object_mut().unwrap().remove(KEY);
    assert!(command(&missing).is_err());
}
#[test] fn persistent_capsule_v1_never_acquires_support_or_recipe_content() {
    let v = plan("create"); assert!(receipt(&v)); assert!(crate::batch_host::BatchKind::valid(&v, None));
    assert!(fields(&v["persistent_association"], &["version", "operation", "association_id", "generation", "members", "intent"]));
    for key in [KEY, VISUAL, "support", "replace_legacy", "local_document_id"] {
        let mut bad = v.clone(); bad["persistent_association"][key] = json!({}); assert!(!receipt(&bad));
    }
    let mut bad = v; bad["persistent_association"]["version"] = json!(2); assert!(!receipt(&bad));
}
#[test] fn generic_patch_and_unlink_retain_complete_member_review() {
    for operation in ["patch", "unlink"] {
        let v = plan(operation); assert!(receipt(&v)); assert!(crate::batch_host::BatchKind::valid(&v, None));
        for path in ["/association_source/association/eye_bag_cohort", "/association_source/association/eye_bag_cohort_visual",
            "/targets/0/association/eye_bag_cohort", "/targets/0/association/eye_bag_cohort_visual", "/association_source"] {
            let mut bad = v.clone(); *bad.pointer_mut(path).unwrap() = Value::Null; assert!(!receipt(&bad), "{path}");
        }
        let mut bad = v.clone(); bad["targets"] = json!([]); assert!(!receipt(&bad));
        bad = v.clone(); bad["targets"][0]["blocked"] = json!("Not independently reviewed"); assert!(!receipt(&bad));
        bad = v; bad.as_object_mut().unwrap().remove(KEY); assert!(!receipt(&bad));
    }
}
#[test] fn before_and_after_coverage_are_target_owned_and_side_exact() {
    let v = plan("patch");
    for side in ["before", "after"] { for (key, replacement) in [("scope", json!("source-reviewed-ridge")),
        ("ridge_sha256", Value::Null), ("sides", json!([])), ("sides", json!(["right", "left"])),
        ("sides", json!(["left", "left"]))] {
        let mut bad = v.clone(); bad["targets"][0]["association"][KEY][side][key] = replacement;
        refresh(&mut bad["targets"][0]); assert!(!receipt(&bad));
    }}
    for (key, replacement) in [("face_ref", v["association_source"]["association"]["ref"].clone()),
        ("replace_legacy", json!(true)), ("support_transfer", json!("source"))] {
        let mut bad = v.clone(); bad["targets"][0]["association"][KEY][key] = replacement;
        refresh(&mut bad["targets"][0]); assert!(!receipt(&bad));
    }
}
#[test] fn neutral_and_partial_intents_do_not_invent_member_support() {
    let mut v = plan("create"); v["persistent_association"]["intent"][0]["value"] = json!(0); assert!(receipt(&v));
    let neutral = json!({"scope":"neutral-no-effect","ridge_sha256":null,"sides":[]});
    v["association_source"]["association"][KEY]["after"] = neutral.clone(); refresh(&mut v["association_source"]);
    v["targets"][0]["association"][KEY]["after"] = neutral; refresh(&mut v["targets"][0]); assert!(receipt(&v));
    // Active before remains independently reviewed even when after is neutral.
    v["targets"][0]["association"][KEY]["before"]["ridge_sha256"] = Value::Null; refresh(&mut v["targets"][0]); assert!(!receipt(&v));
    let mut partial = plan("create"); partial["applies"]["selection"][eye_bag::OP] = json!(["/preserve"]);
    partial["persistent_association"]["intent"].as_array_mut().unwrap().remove(0); assert!(receipt(&partial));
    for bad in [json!(true), json!(1.1), json!("0.5")] {
        let mut changed = partial.clone(); changed["persistent_association"]["intent"][0]["value"] = bad; assert!(!receipt(&changed));
    }
}
#[test] fn complete_render_identity_cannot_be_substituted_or_downscaled() {
    let v = plan("create");
    for (path, replacement) in [("/targets/0/association/eye_bag_cohort_visual/source_proof/asset_sha256", json!("c".repeat(64))),
        ("/targets/0/association/eye_bag_cohort_visual/revision", json!("4")),
        ("/targets/0/association/eye_bag_cohort_visual/before/width", json!(256)),
        ("/targets/0/association/eye_bag_cohort_visual/coverage_sha256", json!("f".repeat(64))),
        ("/targets/0/association/owner/graph_sha256", json!("1".repeat(64))), ("/targets/0/index", json!(0))] {
        let mut bad = v.clone(); *bad.pointer_mut(path).unwrap() = replacement; assert!(!receipt(&bad), "{path}");
    }
}
#[test] fn full_mixed_portrait_collarbone_review_keeps_independent_proofs() {
    for (portrait_required, collar_required) in [(true, false), (false, true), (true, true)] {
        let v = mixed(plan("patch"), portrait_required, collar_required); let c = commit_request(&v); let done = terminal(&v, &c);
        assert!(receipt(&v)); assert!(crate::batch_host::BatchKind::valid(&v, None));
        assert!(command(&c).is_ok()); assert!(portrait::command(&c).is_ok()); assert!(collarbone::command(&c).is_ok());
        assert!(receipt(&done)); assert!(crate::batch_host::BatchKind::valid(&done, None));
        for (required, key, visual) in [(portrait_required, portrait::ACK, "portrait_visual"), (collar_required, collarbone::ACK, "collarbone_visual")] {
            if !required { continue; }
            let mut bad = v.clone(); bad["targets"][0]["association"][visual]["candidate_people_sha256"] = json!("a".repeat(64)); assert!(!receipt(&bad));
            let mut bad = c.clone(); bad[key].as_array_mut().unwrap().reverse(); assert!(command(&bad).is_err());
            let mut bad = done.clone(); bad.as_object_mut().unwrap().remove(key); assert!(!receipt(&bad));
        }
    }
}
#[test] fn retained_required_families_cannot_disappear_even_on_generic_unlink() {
    let v = mixed(plan("unlink"), true, true); assert!(receipt(&v)); assert_eq!(v["module_scope"], json!([]));
    for (marker, keys) in [("portrait_cohort", vec!["portrait_visual"]), ("collarbone_cohort", vec!["collarbone_coverage", "collarbone_visual"])] {
        let mut bad = v.clone(); bad.as_object_mut().unwrap().remove(marker);
        for key in keys { bad["association_source"]["association"].as_object_mut().unwrap().remove(key); bad["targets"][0]["association"].as_object_mut().unwrap().remove(key); }
        assert!(!receipt(&bad));
    }
}
#[test] fn unsupported_visual_combinations_are_refused_not_partially_reviewed() {
    for op in UNSUPPORTED {
        let mut c = request_fixture("patch"); c["people_transfer"]["selection"] = json!({(*op):["/amount"]}); c["module_scope"] = json!([op]);
        assert!(command(&c).is_err()); assert!(!read_only(&c));
        let mut v = plan("unlink"); v["persistent_association"]["intent"].as_array_mut().unwrap().push(json!({"op":op,"path":"/amount","value":0}));
        assert!(!receipt(&v));
    }
}
#[test] fn ordered_atomic_commit_includes_source_and_every_member() {
    for operation in ["create", "patch", "unlink"] {
        let v = plan(operation); let c = commit_request(&v); let done = terminal(&v, &c);
        assert!(command(&c).is_ok()); assert!(!read_only(&c)); assert!(receipt(&done));
        let mut h = host([171;16]); h.begin_command([171;16], &c).unwrap(); h.receive([171;16], &done); assert_eq!(h.status("cohort-commit")["result"], done);
        for (path, replacement) in [("/source_outcome/result_revision", json!("3")), ("/target_outcomes/0/outcome", json!("noop")),
            ("/target_outcomes/0/result_revision", json!("3")), ("/source_missing", json!(true)), ("/applied", json!([1])),
            ("/batch_id", Value::Null), ("/target_outcomes", json!([]))] {
            let mut bad = done.clone(); *bad.pointer_mut(path).unwrap() = replacement; assert!(!receipt(&bad), "{path}");
        }
        let mut bad = done.clone(); bad[ACK].as_array_mut().unwrap().reverse(); assert!(!receipt(&bad));
        bad = c; bad.as_object_mut().unwrap().remove("module_scope"); assert!(command(&bad).is_err());
    }
}
#[test] fn current_intent_is_not_replaceable_by_scalar_only_receipt() {
    let v = plan("patch"); let c = commit_request(&v); let done = terminal(&v, &c);
    let mut stripped = done; stripped.as_object_mut().unwrap().remove(ACK); stripped.as_object_mut().unwrap().remove(KEY); assert!(!receipt(&stripped));
    let mut scalar = v; scalar.as_object_mut().unwrap().remove(KEY); scalar["applies"].as_object_mut().unwrap().remove(KEY);
    for row in ["association_source"] { scalar[row]["association"].as_object_mut().unwrap().remove(KEY); scalar[row]["association"].as_object_mut().unwrap().remove(VISUAL); }
    scalar["targets"][0]["association"].as_object_mut().unwrap().remove(KEY); scalar["targets"][0]["association"].as_object_mut().unwrap().remove(VISUAL);
    assert!(!receipt(&scalar));
}
#[test] fn mismatched_ack_or_extra_family_latches_original_query_only_unknown() {
    let v = plan("patch"); let c = commit_request(&v); let done = terminal(&v, &c);
    for (key, replacement) in [("module_scope", json!([])), ("preflight_token", json!("a".repeat(32))),
        (portrait::ACK, json!([])), ("portrait_cohort", json!(true))] {
        let mut h = host([172;16]); h.begin_command([172;16], &c).unwrap(); let mut bad = done.clone(); bad[key] = replacement; h.receive([172;16], &bad);
        let unknown = h.status("cohort-commit")["result"].clone(); assert_eq!(unknown["outcome_unknown"], true);
        for key in [ACK, KEY, "module_scope", "preflight_token"] { assert_eq!(unknown[key], binding(&c).unwrap().unwrap()[key]); }
        h.receive([172;16], &done); assert_eq!(h.status("cohort-commit")["result"], unknown); assert!(h.begin_command([172;16], &c).is_err());
    }
    let v = mixed(v, true, true); let c = commit_request(&v); let mut h = host([173;16]); h.begin_command([173;16], &c).unwrap();
    let mut bad = terminal(&v, &c); bad[ACK][0]["replace_legacy"] = json!(false); h.receive([173;16], &bad);
    assert_eq!(h.status("cohort-commit")["result"][ACK], c[ACK]); assert_eq!(h.status("cohort-commit")["result"]["outcome_unknown"], true);
}
#[test] fn failure_needs_exact_request_identity_even_without_publication() {
    let v = plan("create"); let c = commit_request(&v); let mut failure = binding(&c).unwrap().unwrap();
    failure["action"] = json!("commit"); failure["request_id"] = c["request_id"].clone(); failure["success"] = json!(false);
    failure["outcome_unknown"] = json!(false); failure["error"] = json!("Frozen target changed");
    let mut h = host([174;16]); h.begin_command([174;16], &c).unwrap(); h.receive([174;16], &failure); assert_eq!(h.status("cohort-commit")["result"], failure);
    for key in [ACK, KEY, "module_scope", "preflight_token"] {
        let mut bad = failure.clone(); bad.as_object_mut().unwrap().remove(key);
        let mut h = host([175;16]); h.begin_command([175;16], &c).unwrap(); h.receive([175;16], &bad); assert_eq!(h.status("cohort-commit")["result"]["outcome_unknown"], true);
    }
}
#[test] fn image_reads_keep_byte_proof_and_exact_coordinates_without_write_authority() {
    let c = image_request_fixture(); assert!(command(&c).is_ok()); assert!(read_only(&c)); assert!(crate::batch_api::read_only(&c));
    assert!(collarbone::command(&c).is_ok());
    for key in ["docs", "module_scope", "people_transfer", ACK, "path"] {
        let mut bad = c.clone(); bad[key] = json!({}); assert!(command(&bad).is_err()); assert!(!read_only(&bad));
    }
    let proof = owner('a','c',false)["source_proof"].clone();
    let sample = crate::spill_transfer_protocol::tests::sample_transfer(&json!("a".repeat(32)), &json!("3"), &json!({}), &proof);
    let image = sample["before"].clone(); let mut compact = image.clone(); compact.as_object_mut().unwrap().remove("base64");
    let mut v = c; v.as_object_mut().unwrap().remove("cmd"); v["success"] = json!(true); v["outcome_unknown"] = json!(false);
    v["sha256"] = image["sha256"].clone(); v["compact"] = compact; v["image"] = image; assert!(receipt(&v)); assert!(crate::batch_host::BatchKind::valid(&v, None));
    v["image"]["base64"] = json!("AAAA"); assert!(!receipt(&v));
}
#[test] fn failed_image_coordinates_and_mutation_id_collisions_remain_guarded() {
    let c = image_request_fixture();
    for key in ["preflight_token", "document_id", "revision", "side", "sha256"] {
        let mut failure = binding(&c).unwrap().unwrap(); failure["action"] = c["action"].clone(); failure["request_id"] = c["request_id"].clone();
        failure["success"] = json!(false); failure["outcome_unknown"] = json!(false); failure["error"] = json!("Expired image"); failure[key] = json!("changed");
        let mut h = host([176;16]); h.begin_command([176;16], &c).unwrap(); h.receive([176;16], &failure);
        assert_eq!(h.status("cohort-image")["result"]["outcome_unknown"], true); assert_eq!(h.status("cohort-image")["result"][key], c[key]);
    }
    let epoch = [177;16]; let mut image = c; image["request_id"] = json!("collision");
    crate::project_recovery_fence::issued(epoch, &json!({"cmd":"people","action":"commit","request_id":"collision"})).unwrap();
    assert!(crate::project_recovery_fence::issued(epoch, &image).is_err()); assert!(crate::project_recovery_fence::proof(epoch).is_err());
    crate::project_recovery_fence::observed(epoch, &json!({"event":"project_opened"}));
}

#[test] fn explicit_member_override_wins_over_shared_amount_in_both_directions() {
    let mut v = plan("patch"); v["persistent_association"]["intent"][0]["value"] = json!(0);
    assert!(receipt(&v)); // Shared zero, actual member explicit positive.
    v["persistent_association"]["intent"][0]["value"] = json!(0.5);
    v["targets"][0]["association"][KEY]["after"] = json!({"scope":"neutral-no-effect","ridge_sha256":null,"sides":[]});
    refresh(&mut v["targets"][0]); assert!(receipt(&v)); // Shared positive, actual member explicit zero.
}
#[test] fn retained_positive_legacy_intent_may_be_masked_by_approved_local_zero() {
    let mut v = plan("patch"); v["persistent_association"]["intent"].as_array_mut().unwrap()
        .push(json!({"op":"lnx.enhance.v1","path":"/eye_bags","value":0.3}));
    assert!(receipt(&v));
    v["applies"]["selection"]["lnx.enhance.v1"] = json!(["/eye_bags"]);
    v["module_scope"].as_array_mut().unwrap().push(json!("lnx.enhance.v1"));
    assert!(!receipt(&v)); // Newly selected positive legacy conflicts with actual active v2.
}
#[test] fn active_local_collarbone_requires_complete_proof_without_shared_leaf() {
    let mut v = mixed(plan("patch"), false, true);
    v["persistent_association"]["intent"].as_array_mut().unwrap().retain(|leaf| leaf["op"] != collarbone::OP);
    assert!(receipt(&v)); assert!(crate::batch_host::BatchKind::valid(&v, None));
    let c = commit_request(&v); assert!(receipt(&terminal(&v, &c)));
    v["targets"][0]["association"].as_object_mut().unwrap().remove("collarbone_visual"); assert!(!receipt(&v));
}
