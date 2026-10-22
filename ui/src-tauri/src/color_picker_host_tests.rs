use super::*;
const CAPTURE: &str = "0123456789abcdef0123456789abcdef";
const RECIPE: &str = "11111111111111111111111111111111";
fn request(action: &str, channel: &str) -> Value {
    json!({"request_id":"r", "document_id":"123", "capture_id":CAPTURE, "ticket":"7",
        "generation":"9007199254740993", "recipe_document_id":RECIPE, "recipe_revision":"0",
        "action":action, "channel":channel, "region":{"x":2,"y":3,"width":1,"height":1}, "delta":0.})
}
fn levels() -> Value {
    let row = json!({"input_black":0., "input_white":1., "gamma":1., "output_black":0., "output_white":1.});
    json!({"version":1,"space":"srgb-display","enabled":true,"master":row,"red":row,"green":row,"blue":row})
}
fn receipt(action: &str, channel: &str, before: Value, after: Value) -> Value {
    let mut result = request(action, channel);
    result["protocol"] = json!(1); result["success"] = json!(true);
    result["outcome_unknown"] = json!(false); result["requires_reload"] = json!(false);
    result["history"] = json!({"undo_steps":1,"redo_steps":0});
    result["sample"] = json!({"version":1, "policy":"stage-targeted-srgb-v1", "action":action,
        "channel":channel,"source_stage":stage(action,channel),"region":result["region"],
        "samples":1,"mean_srgb":[0.2,0.3,0.4],"hsl":[210.,0.3,0.3]});
    result["no_change"] = json!(before == after);
    result["before"] = before; result["after"] = after;
    result
}
fn bound(action: &str, channel: &str) -> String { binding(&request(action, channel)).unwrap() }
#[test]
fn receipt_requires_every_bound_identity_and_actual_post_history_recipe() {
    let binding = bound("levels_black", "master");
    let mut after = levels(); after["red"]["input_black"] = json!(0.2);
    let result = receipt("levels_black", "master", levels(), after);
    assert!(ColorPickerKind::valid(&result, Some(&binding)));
    for key in IDENTITY_KEYS {
        let mut wrong = result.clone(); wrong[*key] = json!("wrong");
        assert!(!ColorPickerKind::valid(&wrong, Some(&binding)), "{key}");
    }
    for key in ["before", "after", "history", "no_change"] {
        let mut wrong = result.clone(); wrong.as_object_mut().unwrap().remove(key);
        assert!(!ColorPickerKind::valid(&wrong, Some(&binding)), "{key}");
    }
    let mut wrong = result.clone(); wrong["sample"]["region"]["x"] = json!(3);
    assert!(!ColorPickerKind::valid(&wrong, Some(&binding)));
    wrong = result.clone(); wrong["sample"]["hsl"][1] = json!(2.);
    assert!(!ColorPickerKind::valid(&wrong, Some(&binding)));
    wrong = result; wrong["sample"]["source_stage"] = json!("proxy-output");
    assert!(!ColorPickerKind::valid(&wrong, Some(&binding)));
}
#[test]
fn levels_picker_may_change_only_selected_rgb_endpoints() {
    for action in ["levels_black", "levels_white"] {
        let binding = bound(action, "master");
        let base = receipt(action, "master", levels(), levels());
        for (channel, key) in [("master","input_black"),("red","gamma"),("green","output_white"),
            ("blue", if action == "levels_black" {"input_white"} else {"input_black"})] {
            let mut wrong = base.clone(); wrong["after"][channel][key] = json!(0.7);
            wrong["no_change"] = json!(false);
            assert!(!ColorPickerKind::valid(&wrong, Some(&binding)), "{action}:{channel}:{key}");
        }
        let mut wrong = base; wrong["after"]["extension"] = json!(true);
        assert!(!ColorPickerKind::valid(&wrong, Some(&binding)));
    }
}
#[test]
fn hue_picker_preserves_every_saturation_and_lightness_value() {
    let binding = bound("hsl", "master");
    let mut value = receipt("hsl", "master", json!(vec![0.;24]), json!(vec![0.;24]));
    value["sample"]["weights"] = json!([0.,0.,0.,1.,0.,0.,0.,0.]);
    value["sample"]["achieved_delta"] = json!(0.);
    assert!(ColorPickerKind::valid(&value, Some(&binding)));
    for index in (0..24).filter(|i| i % 3 != 0) {
        let mut wrong = value.clone(); wrong["after"][index] = json!(1.); wrong["no_change"] = json!(false);
        assert!(!ColorPickerKind::valid(&wrong, Some(&binding)));
    }
}
#[test]
fn curve_preserves_schema_and_other_channels_but_allows_first_luminance_curve() {
    let before = json!({"version":1,"space":"srgb-display","interpolation":"pchip","boundary":"linear",
        "enabled":true,"master":[[0.,0.],[1.,1.]],"red":[[0.,0.],[1.,1.]],"green":[[0.,0.],[1.,1.]],"blue":[[0.,0.],[1.,1.]]});
    let mut after = before.clone(); after["version"] = json!(2);
    after["luminance_space"] = json!("linear-srgb-y-ratio"); after["luminance"] = json!([[0.,0.],[0.3,0.4],[1.,1.]]);
    let binding = bound("curve", "luminance");
    let mut value = receipt("curve", "luminance", before, after);
    value["sample"]["point"] = json!([0.3,0.4]); value["sample"]["point_index"] = json!(1);
    value["sample"]["sample_x"] = json!(0.3); value["sample"]["achieved_delta"] = json!(0.1);
    assert!(ColorPickerKind::valid(&value, Some(&binding)));
    value["after"]["red"] = json!([[0.,0.1],[1.,1.]]);
    assert!(!ColorPickerKind::valid(&value, Some(&binding)));
}
#[test]
fn wrong_epoch_duplicates_and_invalid_completion_never_replace_success() {
    let binding = bound("levels_black", "master");
    let result = receipt("levels_black", "master", levels(), levels());
    let mut host = ColorPickerHost::default(); host.reset([1;16]); host.ready([1;16], true);
    host.begin_bound([1;16], "r", "levels_black", Some(&binding)).unwrap();
    host.receive([2;16], &result); assert_eq!(host.status("r")["phase"], "pending");
    host.receive([1;16], &result); host.ended([1;16]);
    assert_eq!(host.status("r")["result"]["success"], true);
    assert!(host.begin_bound([1;16], "r", "levels_black", Some(&binding)).is_err());
    let mut other = ColorPickerHost::default(); other.reset([1;16]); other.ready([1;16], true);
    other.begin_bound([1;16], "r", "levels_black", Some(&binding)).unwrap();
    let mut wrong = result; wrong["generation"] = json!("8"); other.receive([1;16], &wrong);
    let status = other.status("r");
    assert_eq!(status["result"]["outcome_unknown"], true);
    assert_eq!(status["result"]["requires_reload"], true);
    assert_eq!(status["result"]["generation"], "9007199254740993");
}
#[test]
fn probes_are_single_flight_and_only_matching_terminal_receipts_release_admission() {
    let binding = bound("levels_black", "master");
    let mut host = ColorPickerProbeHost::default(); host.reset([1;16]); host.ready([1;16], true);
    host.begin_bound([1;16], "r", "levels_black", Some(&binding)).unwrap();
    assert!(host.begin_bound([1;16], "next", "levels_black", Some(&binding)).is_err());
    let mut result = request("levels_black", "master");
    result["protocol"] = json!(1); result["success"] = json!(false); result["outcome_unknown"] = json!(false);
    host.receive([2;16], &result);
    assert!(host.begin_bound([1;16], "next", "levels_black", Some(&binding)).is_err());
    host.receive([1;16], &result);
    host.begin_bound([1;16], "next", "levels_black", Some(&binding)).unwrap();
    host.ended([2;16]); assert_eq!(host.status("next")["phase"], "pending");
    host.ended([1;16]); assert_eq!(host.status("next")["result"]["success"], false);
    assert_eq!(host.status("next")["result"]["requires_reload"], false);
}
