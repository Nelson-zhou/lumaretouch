//! Source-only fixtures: no tests were executed during implementation.
use super::*;
const EPOCH: [u8; 16] = [51; 16];
const SESSION: &str = "11111111111111111111111111111111";
const PREVIEW: &str = "22222222222222222222222222222222";
const RECIPE: &str = "33333333333333333333333333333333";
const OTHER: &str = "44444444444444444444444444444444";
const PNG: &str = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAusB9Y9Zl1sAAAAASUVORK5CYII=";

fn event(state: &str) -> Value {
    json!({"event": "fringe_repair_preview", "protocol": 1, "state": state, "success": state != "failed",
        "document_id": "42", "session_id": SESSION, "preview_id": PREVIEW,
        "recipe_document_id": RECIPE, "recipe_revision": "0"})
}
fn ready() -> Value {
    let mut value = event("ready");
    value["image"] = json!({"before": PNG, "after": PNG, "coverage": PNG, "width": 1, "height": 1,
        "domain": "production-output", "quality": "full-source-render-downsampled-srgb8", "note": "Full-source review"});
    value["source"] = json!({"sha256": "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef", "width": 4000, "height": 6000});
    value["recipe"] = json!({"version": 1, "algorithm": "lrt-fringe-repair-v1", "enabled": true, "strength": 50,
        "source": null, "coverage": {"domain": "post-optics-pre-crop-normalized-v1", "strokes": []}});
    value["defaults"] = json!({"strength": 50, "min_strength": 0, "max_strength": 100});
    value
}
fn host() -> FringeRepairPreviewHost {
    let mut host = FringeRepairPreviewHost::default();
    host.reset(EPOCH); host.begin(EPOCH, "42", SESSION, PREVIEW).unwrap(); host
}
fn show(host: &mut FringeRepairPreviewHost) {
    host.receive(EPOCH, &ready()); host.status(EPOCH, PREVIEW);
    host.presentation_requested().unwrap(); host.receive(EPOCH, &event("presented"));
}
fn receipt() -> Value {
    json!({"event": "fringe_repair_result", "protocol": 1, "action": "apply", "request_id": "one",
        "document_id": "42", "session_id": SESSION, "preview_id": PREVIEW,
        "success": true, "outcome_unknown": false, "requires_reload": false, "no_change": false,
        "history": {"undo_steps": 1, "redo_steps": 0}})
}

#[test]
fn each_delivery_presentation_and_epoch_check_precedes_one_redemption() {
    let mut host = host();
    host.receive(EPOCH, &ready());
    assert!(host.presentation_requested().is_err()); assert!(host.redeem().is_err());
    let delivered = host.status(EPOCH, PREVIEW);
    host.presentation_requested().unwrap(); assert!(host.redeem().is_err());
    host.receive([52; 16], &event("presented")); assert!(host.redeem().is_err());
    host.receive(EPOCH, &event("presented"));
    assert_eq!(host.status(EPOCH, PREVIEW)["image"], delivered["image"]);
    host.redeem().unwrap(); assert!(host.redeem().is_err());
    assert_eq!(host.status(EPOCH, PREVIEW)["state"], "stale");
}

#[test]
fn wrong_bindings_never_become_delivery_or_acknowledgement() {
    for (key, wrong) in [("document_id", "43"), ("session_id", OTHER), ("preview_id", OTHER)] {
        let mut host = host(); let mut value = ready(); value[key] = json!(wrong);
        host.receive(EPOCH, &value); assert_eq!(host.status(EPOCH, PREVIEW)["state"], "running");
        host.receive(EPOCH, &ready()); host.status(EPOCH, PREVIEW); host.presentation_requested().unwrap();
        let mut ack = event("presented"); ack[key] = json!(wrong);
        host.receive(EPOCH, &ack); assert!(host.redeem().is_err());
    }
}

#[test]
fn ack_recipe_must_match_exactly_and_never_replace_review_images() {
    for (key, bad) in [("recipe_document_id", json!(OTHER)), ("recipe_revision", json!("1")),
        ("recipe_document_id", Value::Null), ("recipe_revision", Value::Null)] {
        let mut host = host(); host.receive(EPOCH, &ready()); host.status(EPOCH, PREVIEW);
        host.presentation_requested().unwrap(); let mut ack = event("presented"); ack[key] = bad;
        host.receive(EPOCH, &ack); assert_eq!(host.status(EPOCH, PREVIEW)["state"], "failed");
        assert!(host.redeem().is_err());
    }
    let mut host = host(); host.receive(EPOCH, &ready()); let delivered = host.status(EPOCH, PREVIEW);
    host.presentation_requested().unwrap(); let mut ack = event("presented"); ack["image"] = json!({"after": "replacement"});
    host.receive(EPOCH, &ack); assert_eq!(host.status(EPOCH, PREVIEW)["image"], delivered["image"]);
}

#[test]
fn cancel_invalidation_and_epoch_end_revoke_proofs_and_keep_replay_tombstones() {
    let mut host = host(); show(&mut host); host.cancel_requested();
    host.receive(EPOCH, &event("presented")); assert!(host.redeem().is_err());
    assert_eq!(host.status(EPOCH, PREVIEW)["state"], "cancelling");
    host.receive(EPOCH, &event("cancelled")); assert_eq!(host.status(EPOCH, PREVIEW)["state"], "cancelled");
    host.invalidate(); host.receive(EPOCH, &ready());
    assert_eq!(host.status(EPOCH, PREVIEW)["state"], "stale");
    assert!(host.begin(EPOCH, "42", SESSION, PREVIEW).is_err());
    host.begin(EPOCH, "42", SESSION, OTHER).unwrap(); host.ended(EPOCH);
    assert!(host.begin(EPOCH, "42", SESSION, PREVIEW).is_err());
}

#[test]
fn invalid_images_old_proxy_quality_and_noncanonical_recipe_ids_are_rejected() {
    for (key, bad) in [("domain", json!("source-normalized")), ("quality", json!("proxy-render-srgb8")),
        ("width", json!(801)), ("height", json!(0)), ("note", Value::Null),
        ("before", json!("https://example.invalid/image.png")), ("after", json!("data:image/png;base64,")),
        ("coverage", Value::Null)] {
        let mut host = host(); let mut value = ready(); value["image"][key] = bad;
        host.receive(EPOCH, &value); assert_eq!(host.status(EPOCH, PREVIEW)["state"], "failed");
        assert!(host.presentation_requested().is_err());
    }
    for revision in ["", "-1", "1.0", "01", "18446744073709551616"] {
        let mut host = host(); let mut value = ready(); value["recipe_revision"] = json!(revision);
        host.receive(EPOCH, &value); assert_eq!(host.status(EPOCH, PREVIEW)["state"], "failed");
    }
}

#[test]
fn ready_proof_checks_real_source_recipe_defaults_and_retained_vectors() {
    let mut value = ready(); value["recipe"]["source"] = value["source"].clone();
    assert!(!valid_recipe(&value)); // Auto-only recipe must not retain a binding.
    value["recipe"]["coverage"]["strokes"] = json!([{"id": "saved-stroke", "mode": "subtract",
        "points": [[0.2, 0.3]], "axes": [[0.02, 0.0], [0.0, 0.03]], "opacity": 1.0, "feather": 0.5}]);
    assert!(valid_recipe(&value));
    let mut bad = value.clone(); bad["recipe"]["source"]["width"] = json!(3999); assert!(!valid_recipe(&bad));
    let mut bad = value.clone(); bad["recipe"]["coverage"]["strokes"][0]["axes"] = json!([[1, 1], [1, 1]]);
    assert!(!valid_recipe(&bad));
    let mut bad = value.clone(); bad["recipe"]["coverage"]["strokes"][0]["points"] = json!([[0.1, 1.1]]);
    assert!(!valid_recipe(&bad));
    let mut bad = value.clone(); bad["source"]["sha256"] = json!("not-a-source-digest"); assert!(!valid_recipe(&bad));
    let mut bad = value.clone(); bad["defaults"]["strength"] = json!(60); assert!(!valid_recipe(&bad));
    let mut bad = value; bad["recipe"]["source"] = Value::Null; assert!(!valid_recipe(&bad));
}

#[test]
fn unsolicited_ack_and_late_ready_cannot_make_a_new_presented_proof() {
    let mut host = host(); host.receive(EPOCH, &event("presented")); assert!(host.redeem().is_err());
    let mut host = self::host(); show(&mut host); host.receive(EPOCH, &ready());
    assert_eq!(host.status(EPOCH, PREVIEW)["state"], "failed"); assert!(host.redeem().is_err());
}

#[test]
fn bound_receipts_require_capability_and_retain_the_first_exact_result() {
    let bound = binding("42", SESSION, PREVIEW).unwrap();
    let mut host = FringeRepairHost::default(); host.reset(EPOCH);
    assert!(host.begin_bound(EPOCH, "one", "apply", Some(&bound)).is_err());
    host.ready(EPOCH, true); host.begin_bound(EPOCH, "one", "apply", Some(&bound)).unwrap();
    host.receive([52; 16], &receipt()); assert_eq!(host.status("one")["phase"], "pending");
    host.receive(EPOCH, &receipt()); let mut late = receipt(); late["history"]["undo_steps"] = json!(90);
    host.receive(EPOCH, &late); host.failed("one", "late failure"); host.ended(EPOCH);
    assert_eq!(host.status("one")["result"], receipt());
}

#[test]
fn malformed_receipt_is_bound_unknown_not_success() {
    let bound = binding("42", SESSION, PREVIEW).unwrap();
    let mut host = FringeRepairHost::default(); host.reset(EPOCH); host.ready(EPOCH, true);
    host.begin_bound(EPOCH, "one", "apply", Some(&bound)).unwrap();
    let mut bad = receipt(); bad["preview_id"] = json!(OTHER); host.receive(EPOCH, &bad);
    let result = host.status("one")["result"].clone();
    assert_eq!(result["preview_id"], PREVIEW); assert_eq!(result["success"], false);
    assert_eq!(result["outcome_unknown"], true); assert_eq!(result["requires_reload"], true);
    assert!(result["history"].is_null());
    host.receive(EPOCH, &receipt()); assert_eq!(host.status("one")["result"], result);
}
