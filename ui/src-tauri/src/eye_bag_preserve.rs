//! Independent source-owned eye-bag ridge review. AUTHORED / UNRUN.
//! The existing people receipt owner retains authority and uncertainty.
use serde_json::{json, Value};
use crate::original_shadow_transfer_protocol::hex;
const CONTEXT: &[&str] = &["document_id", "document_epoch", "document_revision", "state_revision", "association_revision", "target"];
fn fields(v: &Value, names: &[&str]) -> bool {v.as_object().is_some_and(|m| m.len() == names.len() && names.iter().all(|k| m.contains_key(*k)))}
fn text(v: &Value) -> bool {v.as_str().is_some_and(|s| !s.trim().is_empty() && s.len() <= 128 && !s.contains('\0'))}
fn mask_id(v: &Value) -> bool {v.as_str().is_some_and(|s| (1..=64).contains(&s.len())
    && s.bytes().all(|b| b.is_ascii_alphanumeric() || b == b'_' || b == b'-'))}
fn mask_name(v: &Value) -> bool {v.as_str().is_some_and(|s| !s.trim().is_empty() && s.chars().count() <= 80 && s.chars().all(|c| c as u32 >= 32))}
fn unit(v: &Value) -> bool {v.as_f64().is_some_and(|n| n.is_finite() && (0.0..=1.0).contains(&n))}
fn recipe(v: &Value) -> bool {fields(v, &["version", "amount", "preserve"]) && v["version"].as_u64() == Some(2) && unit(&v["amount"]) && unit(&v["preserve"])}
pub(crate) fn same_recipe(a: &Value, b: &Value) -> bool {recipe(a) && recipe(b)
    && a["amount"].as_f64() == b["amount"].as_f64() && a["preserve"].as_f64() == b["preserve"].as_f64()}
fn point(v: &Value, bound: f64) -> bool {v.as_array().is_some_and(|p| p.len() == 2 && p.iter().all(|n| n.as_f64().is_some_and(|f| f.is_finite() && f.abs() <= bound)))}
fn eyes(v: &Value, allow_empty: bool) -> bool {
    let Some(map) = v.as_object() else {return false;};
    let mut total = 0usize;
    (allow_empty || !map.is_empty()) && map.len() <= 2 && map.iter().all(|(side, eye)| {
        if !matches!(side.as_str(), "left" | "right") || !fields(eye, &["recipe", "visible", "unoccluded", "ownership_confirmed"])
            || ["visible", "unoccluded", "ownership_confirmed"].iter().any(|k| eye[*k] != true) {return false;}
        let mask = &eye["recipe"];
        let Some(objects) = mask["objects"].as_array() else {return false;};
        let mut ids = std::collections::BTreeSet::new();
        fields(mask, &["version", "domain", "objects"]) && mask["version"].as_u64() == Some(1) && mask["domain"] == "source-normalized"
            && (1..=64).contains(&objects.len()) && objects.iter().any(|o| o["enabled"] == true && o["operation"] == "add" && o["opacity"].as_f64() == Some(1.0))
            && objects.iter().all(|o| {
                if !fields(o, &["id", "name", "enabled", "operation", "kind", "opacity", "feather", "points", "axes"])
                    || !mask_id(&o["id"]) || !mask_name(&o["name"]) || !ids.insert(o["id"].as_str().unwrap()) || !o["enabled"].is_boolean()
                    || !matches!(o["operation"].as_str(), Some("add" | "subtract")) || o["kind"] != "brush" || o["opacity"].as_f64() != Some(1.0)
                    || !o["feather"].as_f64().is_some_and(|f| f.is_finite() && (0.0..=100.0).contains(&f)) {return false;}
                let (Some(points), Some(axes)) = (o["points"].as_array(), o["axes"].as_array()) else {return false;};
                total += points.len();
                (1..=1024).contains(&points.len()) && total <= 4096 && points.iter().all(|p| point(p, 1.0)
                    && p.as_array().unwrap().iter().all(unit)) && axes.len() == 2 && axes.iter().all(|p| point(p, 4.0))
                    && (axes[0][0].as_f64().unwrap() * axes[1][1].as_f64().unwrap()
                        - axes[0][1].as_f64().unwrap() * axes[1][0].as_f64().unwrap()).abs() >= 1e-12
            })
    })
}
pub(crate) fn action(v: &Value) -> bool {matches!(v["action"].as_str(), Some("eye_bag_reference" | "eye_bag_source_image" | "eye_bag_preview" | "eye_bag_image" | "eye_bag_confirm"))}
fn ack(v: &Value) -> bool {fields(v, &["review_sha256", "before_sha256", "after_sha256", "support_overlay_sha256"])
    && ["review_sha256", "before_sha256", "after_sha256", "support_overlay_sha256"].iter().all(|k| hex(&v[*k], 64))}
pub(crate) fn command(v: &Value) -> Result<(), String> {
    if !action(v) {return Ok(());}
    let mut context = json!({}); for k in CONTEXT {context[*k] = v[*k].clone();}
    let p = &v["payload"];
    let valid = super::valid_context(&context) && v["target"]["scope"] == "face" && match v["action"].as_str() {
        Some("eye_bag_reference") => fields(p, &[]),
        Some("eye_bag_source_image") => fields(p, &["token", "side", "sha256"]) && hex(&p["token"], 32) && hex(&p["sha256"], 64)
            && matches!(p["side"].as_str(), Some("left" | "right")),
        Some("eye_bag_preview") => fields(p, &["recipe", "eyes", "replace_legacy"]) && recipe(&p["recipe"])
            && p["recipe"]["amount"].as_f64().is_some_and(|n| n > 0.0) && eyes(&p["eyes"], false) && p["replace_legacy"].is_boolean(),
        Some("eye_bag_image") => fields(p, &["token", "side", "sha256"]) && hex(&p["token"], 32) && hex(&p["sha256"], 64)
            && matches!(p["side"].as_str(), Some("before" | "after" | "support")),
        Some("eye_bag_confirm") => fields(p, &["token", "ack"]) && hex(&p["token"], 32) && ack(&p["ack"]),
        _ => false,
    };
    if valid {Ok(())} else {Err("卧蚕保护请求需要当前单脸、真实源图笔迹和完整图像审核凭据".into())}
}
pub(crate) fn binding(v: &Value) -> Result<Option<Value>, String> {
    if v["cmd"] != "people" || !action(v) {return Ok(None);} command(v)?;
    let mut r = json!({"action":v["action"], "payload":v["payload"]}); for k in CONTEXT {r[*k] = v[*k].clone();}
    Ok(Some(json!({"eye_bag_request":r})))
}
pub(crate) fn read_only(v: &Value) -> bool {
    v["cmd"] == "people" && matches!(v["action"].as_str(), Some("eye_bag_reference" | "eye_bag_source_image" | "eye_bag_preview" | "eye_bag_image"))
        && command(v).is_ok() && v.as_object().is_some_and(|m| m.len() == 10 || (m.len() == 11 && hex(&v["host_epoch"], 32)))
        && text(&v["request_id"])
}
fn source_preview(v: &Value, source: &Value) -> bool {
    use base64::{engine::general_purpose::STANDARD, Engine as _};
    if !fields(v, &["mime", "base64", "width", "height", "source_sha256", "source_width", "source_height", "decoded_width", "decoded_height", "mapping", "orientation"])
        || !fields(source, &["sha256", "width", "height"]) || !hex(&source["sha256"], 64)
        || v["mime"] != "image/png" || v["source_sha256"] != source["sha256"] || v["source_width"] != source["width"] || v["source_height"] != source["height"]
        || v["mapping"] != "normalized_full_frame" || v["orientation"] != "exif_normalized_once" {return false;}
    let numbers: Option<Vec<u64>> = ["source_width", "source_height", "decoded_width", "decoded_height", "width", "height"].iter().map(|k| v[*k].as_u64()).collect();
    let Some(n) = numbers else {return false;}; let (sw, sh, dw, dh, w, h) = (n[0], n[1], n[2], n[3], n[4], n[5]);
    if n.iter().any(|v| !(2..=1_000_000).contains(v)) || dw > sw || dh > sh || w > dw || h > dh || w.max(h) > 1280
        || ((dw != sw || dh != sh) && (dw % 8 != 0 || dh % 8 != 0 || dw * sh >= (dh + 8) * sw || dh * sw >= (dw + 8) * sh))
        || (if dw.max(dh) <= 1280 {w != dw || h != dh} else {w.max(h) != 1280 || (w * dh).abs_diff(h * dw) > dw.max(dh)}) {return false;}
    let Some(encoded) = v["base64"].as_str() else {return false;};
    if encoded.is_empty() || encoded.len() > 8 * 1024 * 1024 {return false;}
    let Ok(bytes) = STANDARD.decode(encoded) else {return false;};
    bytes.len() <= 6 * 1024 * 1024 && STANDARD.encode(&bytes) == encoded && crate::torso_transfer_protocol::png(&bytes, w as u32, h as u32)
}
fn support_mapping(source: &Value, image: &Value, size: (u64, u64)) -> bool {
    if !fields(source, &["source_width", "source_height", "decoded_width", "decoded_height"])
        || !fields(image, &["mime", "width", "height", "sha256"]) || image["mime"] != "image/png" || !hex(&image["sha256"], 64) {return false;}
    let numbers: Option<Vec<u64>> = ["source_width", "source_height", "decoded_width", "decoded_height"].iter().map(|k| source[*k].as_u64()).collect();
    let Some(n) = numbers else {return false;};
    let (Some(w), Some(h)) = (image["width"].as_u64(), image["height"].as_u64()) else {return false;};
    let (sw, sh, dw, dh) = (n[0], n[1], n[2], n[3]);
    n.iter().all(|n| (2..=1_000_000).contains(n)) && (sw, sh) == size && dw <= sw && dh <= sh
        && (1..=1024).contains(&w) && (1..=1024).contains(&h)
        && ((dw == sw && dh == sh) || (dw % 8 == 0 && dh % 8 == 0 && dw * sh < (dh + 8) * sw && dh * sw < (dw + 8) * sh))
        && (if dw.max(dh) <= 1024 {w == dw && h == dh} else {w.max(h) == 1024 && (w * dh).abs_diff(h * dw) <= dw.max(dh)})
}
/// Native spatial sampling, not native sample precision: display PNGs are RGB8.
/// The host owns the full source/repair snapshot and never authorizes geometry
/// from these transport checks alone. Browser decode is separately required.
fn crop_image(v: &Value, width: u64, height: u64) -> Option<usize> {
    use base64::{engine::general_purpose::STANDARD, Engine as _};
    use sha2::{Digest, Sha256};
    if !(1..=2048).contains(&width) || !(1..=2048).contains(&height)
        || width * height > 4_000_000 || !fields(v, &["mime", "width", "height", "sha256", "base64"])
        || v["mime"] != "image/png" || v["width"].as_u64() != Some(width)
        || v["height"].as_u64() != Some(height) || !hex(&v["sha256"], 64) {return None;}
    let encoded = v["base64"].as_str()?;
    if encoded.is_empty() || encoded.len() > 5_592_408 {return None;}
    let bytes = STANDARD.decode(encoded).ok()?;
    (bytes.len() <= 4 * 1024 * 1024 && STANDARD.encode(&bytes) == encoded
        && crate::torso_transfer_protocol::png(&bytes, width as u32, height as u32)
        // RGB only: the common PNG framing checker also permits RGBA.
        && bytes.get(25) == Some(&2)
        && format!("{:x}", Sha256::digest(&bytes)) == v["sha256"].as_str().unwrap()).then_some(bytes.len())
}
fn source_crops(v: &Value, source: &Value) -> bool {
    if !fields(v, &["version", "token", "mapping", "orientation", "source_sha256", "source_width", "source_height",
        "input_stage", "snapshot_sha256", "display_encoding", "sampling", "eyes"])
        || !fields(source, &["sha256", "width", "height"]) || !hex(&source["sha256"], 64)
        || v["version"].as_u64() != Some(1) || !hex(&v["token"], 32) || v["mapping"] != "source_pixel_edges"
        || v["orientation"] != "exif_normalized_once" || v["source_sha256"] != source["sha256"]
        || v["source_width"] != source["width"] || v["source_height"] != source["height"]
        || !matches!(v["input_stage"].as_str(), Some("source" | "committed_repair"))
        || !hex(&v["snapshot_sha256"], 64) || v["display_encoding"] != "srgb_rgb8"
        || v["sampling"] != "one_source_pixel_per_image_pixel" || !fields(&v["eyes"], &["left", "right"]) {return false;}
    let (Some(sw), Some(sh)) = (source["width"].as_u64(), source["height"].as_u64()) else {return false;};
    if !(1..=1_000_000).contains(&sw) || !(1..=1_000_000).contains(&sh) {return false;}
    let mut pixels = 0u64;
    ["left", "right"].iter().all(|side| {
        let eye = &v["eyes"][*side];
        if !fields(eye, &["rect", "image"]) {return false;}
        let Some(rect) = eye["rect"].as_array() else {return false;};
        if rect.len() != 4 {return false;}
        let (Some(x), Some(y), Some(w), Some(h)) = (rect[0].as_u64(), rect[1].as_u64(), rect[2].as_u64(), rect[3].as_u64()) else {return false;};
        if !(1..=2048).contains(&w) || !(1..=2048).contains(&h) || x > sw || y > sh || w > sw - x || h > sh - y {return false;}
        pixels += w * h;
        if pixels > 4_000_000 {return false;}
        let image = &eye["image"];
        fields(image, &["mime", "width", "height", "sha256"]) && image["mime"] == "image/png"
            && image["width"].as_u64() == Some(w) && image["height"].as_u64() == Some(h) && hex(&image["sha256"], 64)
    })
}
fn review(v: &Value, r: &Value) -> bool {
    let o = &v["owner"]; let visual = &v["visual"];
    let source_size = &visual["source_size"];
    let size = source_size.as_array().and_then(|a| (a.len() == 2).then_some(a)).and_then(|a| a[0].as_u64().zip(a[1].as_u64()));
    fields(v, &["version", "token", "recipe", "owner", "face_ref", "support_sha256", "candidate_state_revision", "replace_legacy", "visual", "support_overlay", "support_source", "review_sha256"])
        && v["version"].as_u64() == Some(1) && hex(&v["token"], 32) && same_recipe(&v["recipe"], &r["payload"]["recipe"])
        && v["candidate_state_revision"].as_u64().zip(o["state_revision"].as_u64()).is_some_and(|(after, before)|
            after <= 9_007_199_254_740_991 && after > before && after - before <= 4)
        && v["replace_legacy"] == r["payload"]["replace_legacy"] && hex(&v["support_sha256"], 64) && hex(&v["review_sha256"], 64)
        && fields(o, &["document", "people_scope", "state_revision", "association_revision", "graph_sha256", "source_proof"])
        && fields(&o["document"], &["document_id", "epoch", "revision"]) && o["document"]["document_id"] == r["document_id"]
        && o["document"]["epoch"] == r["document_epoch"] && o["document"]["revision"] == r["document_revision"]
        && o["state_revision"] == r["state_revision"] && o["association_revision"] == r["association_revision"] && hex(&o["graph_sha256"], 64)
        && (o["people_scope"] == "project" || o["people_scope"] == r["document_id"])
        && v["face_ref"] == r["target"]["face_ref"] && o["source_proof"]["asset_sha256"] == v["face_ref"]["asset_sha256"]
        && super::face_style::visual_shape(visual) && visual["source_proof"] == o["source_proof"]
        && visual["document_id"] == r["document_id"] && visual["revision"].as_str() == r["document_revision"].as_u64().map(|n| n.to_string()).as_deref()
        && size.is_some_and(|s| support_mapping(&v["support_source"], &v["support_overlay"], s))
}
pub(crate) fn receipt(v: &Value) -> bool {
    if !action(v) {return true;}
    let r = &v["eye_bag_request"];
    if !fields(r, &["action", "document_id", "document_epoch", "document_revision", "state_revision", "association_revision", "target", "payload"])
        || command(r).is_err() || r["action"] != v["action"] || r["document_id"] != v["document_id"] {return false;}
    if v["success"] != true {return true;}
    let p = &v["payload"];
    match v["action"].as_str() {
        Some("eye_bag_reference") => fields(p, &["kind", "source", "face_ref", "source_preview", "source_crops", "legacy_amount", "recipe", "eyes"])
            && p["kind"] == "eye_bag_reference" && p["face_ref"] == r["target"]["face_ref"] && p["source"]["sha256"] == p["face_ref"]["asset_sha256"]
            && recipe(&p["recipe"]) && unit(&p["legacy_amount"]) && eyes(&p["eyes"], true) && source_preview(&p["source_preview"], &p["source"])
            && source_crops(&p["source_crops"], &p["source"]),
        Some("eye_bag_preview") => fields(p, &["kind", "review"]) && p["kind"] == "eye_bag_preview" && review(&p["review"], r),
        Some("eye_bag_source_image") => fields(p, &["kind", "token", "side", "snapshot_sha256", "image"])
            && p["kind"] == "eye_bag_source_image" && p["token"] == r["payload"]["token"] && p["side"] == r["payload"]["side"]
            && hex(&p["snapshot_sha256"], 64) && p["image"]["sha256"] == r["payload"]["sha256"]
            && p["image"]["width"].as_u64().zip(p["image"]["height"].as_u64())
                .is_some_and(|(w,h)| crop_image(&p["image"], w, h).is_some()),
        Some("eye_bag_image") => fields(p, &["kind", "token", "side", "sha256", "review_sha256", "image"])
            && p["kind"] == "eye_bag_image" && p["token"] == r["payload"]["token"] && p["side"] == r["payload"]["side"]
            && p["sha256"] == r["payload"]["sha256"] && p["sha256"] == p["image"]["sha256"] && hex(&p["review_sha256"], 64) && super::face_style::image(&p["image"]),
        Some("eye_bag_confirm") => fields(p, &["kind", "token", "review_sha256", "ack", "recipe", "support_sha256", "replace_legacy", "candidate_state_revision"])
            && p["kind"] == "eye_bag_confirm" && p["token"] == r["payload"]["token"] && p["ack"] == r["payload"]["ack"]
            && p["review_sha256"] == p["ack"]["review_sha256"] && recipe(&p["recipe"]) && hex(&p["support_sha256"], 64) && p["replace_legacy"].is_boolean()
            && p["candidate_state_revision"].as_u64().zip(r["state_revision"].as_u64()).is_some_and(|(after,before)|
                after <= 9_007_199_254_740_991 && after > before && after - before <= 4),
        _ => false,
    }
}

#[cfg(test)]
#[path = "eye_bag_preserve_unrun.rs"]
mod tests;
