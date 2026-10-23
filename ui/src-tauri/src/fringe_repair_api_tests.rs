//! Source-only fixtures: no tests were executed during implementation.
use super::*;
fn stroke() -> Value {
    json!({"id": "11111111111111111111111111111111", "mode": "add", "points": [[0.0, 1.0]],
        "radius": 0.05, "opacity": 1.0, "feather": 0.5})
}
fn set() -> Value {
    json!({"action": "set", "enabled": true, "strength": 50.0, "reset_coverage": false, "strokes": [stroke()]})
}

#[test]
fn only_enter_and_complete_bounded_set_mutations_are_accepted() {
    assert!(mutation(&json!({"action": "enter"})).is_ok());
    assert!(mutation(&set()).is_ok());
    let mut erase = set(); erase["strokes"][0]["mode"] = json!("subtract");
    assert!(mutation(&erase).is_ok());
    for strength in [0, 100] {
        let mut value = set(); value["strength"] = json!(strength); assert!(mutation(&value).is_ok());
    }
    for invalid in [json!({"action": "enter", "enabled": true}), json!({"action": "clear"}), Value::Null] {
        assert!(mutation(&invalid).is_err());
    }
    for (key, bad) in [("strength", json!(-1)), ("strength", json!(101)), ("strength", json!("50")),
        ("enabled", json!(1)), ("reset_coverage", Value::Null), ("strokes", Value::Null), ("unrecognized", json!(0))] {
        let mut value = set(); value[key] = bad; assert!(mutation(&value).is_err());
    }
}

#[test]
fn stroke_ids_modes_geometry_and_extra_fields_are_fail_closed() {
    for (key, bad) in [("id", json!("00000000000000000000000000000000")), ("mode", json!("erase")),
        ("radius", json!(0)), ("radius", json!(0.50001)), ("opacity", json!(-0.1)), ("feather", json!(1.1)),
        ("points", json!([])), ("points", json!([[1.1, 0.5]])), ("points", json!([[0, 0, 0]])),
        ("points", json!([[0, "0.5"]])), ("extra", json!(true))] {
        let mut value = set(); value["strokes"][0][key] = bad; assert!(mutation(&value).is_err());
    }
    let mut duplicate = set(); duplicate["strokes"] = json!([stroke(), stroke()]);
    assert!(mutation(&duplicate).is_err());
    let mut too_many_points = set(); too_many_points["strokes"][0]["points"] = json!(vec![[0.5, 0.5]; 1025]);
    assert!(mutation(&too_many_points).is_err());
    let mut exact_limit = set(); exact_limit["strokes"][0]["points"] = json!(vec![[0.5, 0.5]; 1024]);
    assert!(mutation(&exact_limit).is_ok());
}
