// SPDX-License-Identifier: GPL-3.0-or-later
//! AUTHORED / UNRUN. No parser, cargo build or test execution in this delivery.
use super::*;
use serde_json::json;
fn base() -> Catalogue { Catalogue::empty("a".repeat(32)).unwrap() }
fn rules() -> Rules { Rules { aspect_ratio: 0.75, headroom_fraction: 0.1, head_fraction: 0.6, horizontal_position: 0.5 } }
fn create(c: &Catalogue, name: &str) -> Request { Request::Create { catalogue_id: c.catalogue_id.clone(), expected_revision: c.revision, name: name.into(), rules: rules() } }
#[test]
fn lifecycle_has_explicit_updates_and_stale_write_fences() {
    let empty = base(); let first = empty.change(&create(&empty, "证件 3:4")).unwrap();
    assert_eq!(first.revision, 1); assert_eq!(first.entries[0].id, "rule-1");
    assert!(first.change(&create(&empty, "Stale")).is_err());
    assert!(first.change(&create(&first, "证件 3:4")).is_err());
    let renamed = first.change(&Request::Rename { catalogue_id: first.catalogue_id.clone(), expected_revision: 1, id: "rule-1".into(), name: "Rename only".into() }).unwrap();
    assert_eq!(renamed.entries[0].rules, rules());
    let mut changed = rules(); changed.horizontal_position = 0.4;
    let update = Request::Update { catalogue_id: renamed.catalogue_id.clone(), expected_revision: 2, id: "rule-1".into(), rules: changed.clone() };
    let updated = renamed.change(&update).unwrap(); assert_eq!(updated.revision, 3); assert_eq!(updated.entries[0].rules, changed);
    assert!(updated.change(&update).is_err());
    let same = updated.change(&Request::Update { catalogue_id: updated.catalogue_id.clone(), expected_revision: 3, id: "rule-1".into(), rules: changed }).unwrap();
    assert_eq!(same, updated);
    let deleted = updated.change(&Request::Delete { catalogue_id: updated.catalogue_id.clone(), expected_revision: 3, id: "rule-1".into() }).unwrap();
    assert!(deleted.entries.is_empty()); assert_eq!(deleted.revision, 4);
    assert_eq!(deleted.change(&create(&deleted, "Rename only")).unwrap().entries[0].id, "rule-5");
    let mut other_store = deleted.clone(); other_store.catalogue_id = "b".repeat(32);
    assert!(other_store.change(&create(&deleted, "Old store")).is_err());
}
#[test]
fn intent_is_an_exact_four_scalar_allowlist() {
    for key in ["source_uid", "face_id", "crown", "chin", "rect", "rotation", "preview_token", "review_confirmed", "version"] {
        let mut value = serde_json::to_value(rules()).unwrap(); value[key] = json!("forbidden");
        assert!(serde_json::from_value::<Rules>(value).is_err(), "{key}");
    }
    for value in [json!(true), json!("0.75"), json!(null)] {
        let mut input = serde_json::to_value(rules()).unwrap(); input["aspect_ratio"] = value;
        assert!(serde_json::from_value::<Rules>(input).is_err());
    }
    for n in [f64::NAN, f64::INFINITY, -0.1, 0.0, 1001.0] { let mut r = rules(); r.aspect_ratio = n; assert!(r.validate().is_err()); }
    let mut r = rules(); r.head_fraction = 0.0; assert!(r.validate().is_err());
    r = rules(); r.head_fraction = 0.91; assert!(r.validate().is_err());
    r = rules(); r.horizontal_position = 1.01; assert!(r.validate().is_err());
    r = rules(); r.headroom_fraction = -0.01; assert!(r.validate().is_err());
}
#[test]
fn no_unknown_schema_default_migration_or_duplicate_names() {
    assert!(Request::parse(br#"{"action":"list"}"#).is_ok());
    assert!(Request::parse(br#"{"action":"list","anchors":{}}"#).is_err());
    assert!(Request::parse(br#"{"action":"import","rect":[0,0,1,1]}"#).is_err());
    let first = base().change(&create(&base(), "One")).unwrap();
    let mut value = serde_json::to_value(&first).unwrap(); value["schema"] = json!("lrt.portrait-crop-rule-catalogue.v2");
    assert!(serde_json::from_value::<Catalogue>(value).unwrap().validate().is_err());
    let mut invalid = first.clone(); invalid.entries.push(invalid.entries[0].clone()); assert!(invalid.validate().is_err());
    let mut value = serde_json::to_value(&first).unwrap(); value["source"] = json!({"path":"photo.jpg"}); assert!(serde_json::from_value::<Catalogue>(value).is_err());
    let mut invalid = first; invalid.entries[0].id = "rule-01".into(); assert!(invalid.validate().is_err());
    assert!(serde_json::from_value::<Request>(json!({"action":"create","catalogue_id":"a".repeat(32),"expected_revision":0,"name":"X","rules":rules(),"anchors":{}})).is_err());
}
#[test]
fn bounds_are_explicit_and_do_not_silently_normalize() {
    for invalid in ["", " leading", "trailing ", "line\nbreak", "zero\u{200b}width", "bidi\u{202e}text"] { assert!(name(invalid).is_err()); }
    assert!(name(&"a".repeat(65)).is_err()); assert!(name(&"😀".repeat(49)).is_err());
    assert!(name(&"人".repeat(64)).is_ok()); assert!(name("Portrait 3:4").is_ok());
    let mut c = base(); for n in 0..MAX_ENTRIES { c = c.change(&create(&c, &format!("Preset {n}"))).unwrap(); }
    assert!(c.change(&create(&c, "Overflow")).is_err());
    c.revision = MAX_REVISION; assert!(c.change(&create(&c, "Exhausted")).is_err());
}
