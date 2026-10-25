// SPDX-License-Identifier: GPL-3.0-or-later
//! Dedicated wire validation for the released expressionReplacement/model.ts.
//! Byte hashes authenticate the supplied command_json, never a reserialization.
//! No rendering, face inference, document publisher, or independent undo owner.
use std::{fmt, io::{self, Write}};
use base64::{engine::general_purpose::STANDARD, Engine as _};
use serde::{de::{self, MapAccess, SeqAccess, Visitor}, Deserialize, Deserializer};
use serde_json::{json, Map, Number, Value};
use sha2::{Digest, Sha256};

pub(crate) const OPERATION: &str = "lnx.expression_replacement.v1";
pub(crate) const EVENT: &str = "expression_replacement_result";
pub(crate) const COMMAND_BYTES: usize = 256 * 1024;
pub(crate) const RESULT_BYTES: usize = 49 * 1024 * 1024;
pub(crate) const PHOTO_BYTES: usize = 17 * 1024 * 1024;
const SAFE_INTEGER: u64 = 9_007_199_254_740_991;

pub(crate) fn fields(v: &Value, names: &[&str]) -> bool {
    v.as_object().is_some_and(|o| o.len() == names.len() && names.iter().all(|k| o.contains_key(*k)))
}
pub(crate) fn id(v: &Value) -> bool {
    v.as_str().is_some_and(|s| !s.is_empty() && s.len() <= 1024 && s.encode_utf16().count() <= 256
        && !s.chars().any(|c| c <= '\u{1f}' || c == '\u{7f}'))
}
pub(crate) fn hash(v: &Value) -> bool {
    v.as_str().is_some_and(|s| s.len() == 64 && s.bytes().all(|b| b.is_ascii_digit() || (b'a'..=b'f').contains(&b)))
}
fn integer(v: &Value, lo: u64, hi: u64) -> bool {
    v.as_u64().is_some_and(|n| (lo..=hi).contains(&n))
        || v.as_f64().is_some_and(|n| n.is_finite() && n.fract() == 0.0 && n >= lo as f64 && n <= hi as f64)
}
fn n(v: &Value) -> f64 { v.as_f64().unwrap_or(f64::NAN) }
fn message(v: &Value, nonempty: bool) -> bool {
    v.as_str().is_some_and(|s| s.len() <= 8192 && (!nonempty || !s.trim().is_empty()))
}
pub(crate) fn digest(bytes: &[u8]) -> String { format!("{:x}", Sha256::digest(bytes)) }

/// The count writer avoids allocating another 49 MiB serialized image envelope.
pub(crate) fn size(v: &Value, limit: usize) -> Result<usize, String> {
    struct Count { count: usize, limit: usize }
    impl Write for Count {
        fn write(&mut self, bytes: &[u8]) -> io::Result<usize> {
            self.count = self.count.checked_add(bytes.len()).ok_or_else(|| io::Error::new(io::ErrorKind::InvalidData, "size overflow"))?;
            if self.count > self.limit { return Err(io::Error::new(io::ErrorKind::InvalidData, "size limit")); }
            Ok(bytes.len())
        }
        fn flush(&mut self) -> io::Result<()> { Ok(()) }
    }
    let mut count = Count { count: 0, limit };
    serde_json::to_writer(&mut count, v).map_err(|_| "表情替换数据超过安全大小上限".to_string())?;
    Ok(count.count)
}

struct Unique(Value);
impl<'de> Deserialize<'de> for Unique {
    fn deserialize<D: Deserializer<'de>>(deserializer: D) -> Result<Self, D::Error> {
        struct UniqueVisitor;
        impl<'de> Visitor<'de> for UniqueVisitor {
            type Value = Unique;
            fn expecting(&self, f: &mut fmt::Formatter) -> fmt::Result { f.write_str("finite JSON without duplicate fields") }
            fn visit_bool<E: de::Error>(self, v: bool) -> Result<Unique, E> { Ok(Unique(json!(v))) }
            fn visit_i64<E: de::Error>(self, v: i64) -> Result<Unique, E> { Ok(Unique(json!(v))) }
            fn visit_u64<E: de::Error>(self, v: u64) -> Result<Unique, E> { Ok(Unique(json!(v))) }
            fn visit_f64<E: de::Error>(self, v: f64) -> Result<Unique, E> {
                Number::from_f64(v).map(|n| Unique(Value::Number(n))).ok_or_else(|| E::custom("non-finite number"))
            }
            fn visit_str<E: de::Error>(self, v: &str) -> Result<Unique, E> { Ok(Unique(Value::String(v.into()))) }
            fn visit_string<E: de::Error>(self, v: String) -> Result<Unique, E> { Ok(Unique(Value::String(v))) }
            fn visit_none<E: de::Error>(self) -> Result<Unique, E> { Ok(Unique(Value::Null)) }
            fn visit_unit<E: de::Error>(self) -> Result<Unique, E> { Ok(Unique(Value::Null)) }
            fn visit_seq<A: SeqAccess<'de>>(self, mut seq: A) -> Result<Unique, A::Error> {
                let mut values = Vec::new();
                while let Some(Unique(value)) = seq.next_element::<Unique>()? { values.push(value); }
                Ok(Unique(Value::Array(values)))
            }
            fn visit_map<A: MapAccess<'de>>(self, mut map: A) -> Result<Unique, A::Error> {
                let mut values = Map::new();
                while let Some(key) = map.next_key::<String>()? {
                    if values.contains_key(&key) { return Err(de::Error::custom("duplicate JSON field")); }
                    let Unique(value) = map.next_value::<Unique>()?;
                    values.insert(key, value);
                }
                Ok(Unique(Value::Object(values)))
            }
        }
        deserializer.deserialize_any(UniqueVisitor)
    }
}
pub(crate) fn unique_json(text: &str, cap: usize) -> Result<Value, String> {
    if text.len() > cap { return Err("JSON 超过表情替换安全上限".into()); }
    let mut parser = serde_json::Deserializer::from_str(text);
    let value = Unique::deserialize(&mut parser).map_err(|_| "JSON 含重复字段、无效数字或非法结构".to_string())?.0;
    parser.end().map_err(|_| "JSON 含额外尾部数据".to_string())?;
    Ok(value)
}
/// Numbers compare by their parsed finite JSON meaning, not spelling (1 vs 1.0).
/// Integer identity fields are separately limited to JavaScript safe integers.
pub(crate) fn same(a: &Value, b: &Value) -> bool {
    match (a, b) {
        (Value::Number(a), Value::Number(b)) => a.as_f64() == b.as_f64(),
        (Value::Array(a), Value::Array(b)) => a.len() == b.len() && a.iter().zip(b).all(|(a,b)| same(a,b)),
        (Value::Object(a), Value::Object(b)) => a.len() == b.len() && a.iter().all(|(k,a)| b.get(k).is_some_and(|b| same(a,b))),
        _ => a == b,
    }
}
pub(crate) fn source(v: &Value) -> bool {
    fields(v, &["asset_sha256","original_sha256","source_kind","width","height","orientation","retained_asset_id"])
        && hash(&v["asset_sha256"]) && hash(&v["original_sha256"])
        && matches!(v["source_kind"].as_str(), Some("original" | "derived"))
        && (v["source_kind"] != "original" || v["original_sha256"] == v["asset_sha256"])
        && integer(&v["width"],2,1_000_000) && integer(&v["height"],2,1_000_000)
        && n(&v["width"]) * n(&v["height"]) <= 100_000_000.0
        && v["orientation"] == "exif_normalized_once" && id(&v["retained_asset_id"])
}
pub(crate) fn binding(v: &Value) -> bool {
    fields(v, &["document_id","document_epoch","load_id","document_revision","state_revision","association_revision","people_graph_sha256","source"])
        && ["document_id","document_epoch","load_id"].iter().all(|k| id(&v[*k]))
        && ["document_revision","state_revision","association_revision"].iter().all(|k| integer(&v[*k],0,SAFE_INTEGER))
        && hash(&v["people_graph_sha256"]) && source(&v["source"])
}
fn face(v: &Value, src: &Value) -> bool {
    let r = &v["face_ref"]; let c = &v["crop"];
    fields(v, &["face_ref","enabled","analysis_status","manual","landmarks_count","landmarks_sha256","crop","eligibility_sha256","protection_sha256"])
        && v["enabled"].is_boolean() && v["analysis_status"] == "verified" && v["manual"] == false
        && n(&v["landmarks_count"]) == 478.0
        && ["landmarks_sha256","eligibility_sha256","protection_sha256"].iter().all(|k| hash(&v[*k]))
        && fields(r, &["asset_sha256","face_instance_id","analysis_revision"])
        && r["asset_sha256"] == src["asset_sha256"] && id(&r["face_instance_id"]) && integer(&r["analysis_revision"],0,SAFE_INTEGER)
        && fields(c, &["left","top","width","height"])
        && integer(&c["left"],0,1_000_000) && integer(&c["top"],0,1_000_000)
        && integer(&c["width"],2,1024) && integer(&c["height"],2,1024)
        && n(&c["left"]) + n(&c["width"]) <= n(&src["width"])
        && n(&c["top"]) + n(&c["height"]) <= n(&src["height"])
}
fn owner(v: &Value) -> bool {
    fields(v, &["source","face"]) && source(&v["source"]) && face(&v["face"], &v["source"]) && v["face"]["enabled"] == true
}
fn fusion(v: &Value, target: &Value) -> bool {
    if !fields(v, &["version","coordinates","initial","strokes"]) || n(&v["version"]) != 1.0
        || v["coordinates"] != "source_normalized_pixel_centres" || v["initial"] != "empty" { return false; }
    let Some(strokes) = v["strokes"].as_array() else { return false; };
    if strokes.len() > 128 || !strokes.iter().any(|s| s["mode"] == "add") { return false; }
    let src = &target["source"]; let crop = &target["face"]["crop"]; let mut total = 0;
    strokes.iter().all(|stroke| {
        let Some(points) = stroke["points"].as_array() else { return false; };
        total += points.len();
        fields(stroke, &["mode","radius_px","points"]) && matches!(stroke["mode"].as_str(), Some("add" | "erase"))
            && n(&stroke["radius_px"]).is_finite() && n(&stroke["radius_px"]) >= 1.0
            && n(&stroke["radius_px"]) <= n(&crop["width"]).min(n(&crop["height"])) / 2.0
            && !points.is_empty() && total <= 2048 && points.iter().all(|p| {
                let Some(p) = p.as_array().filter(|p| p.len() == 2) else { return false; };
                let x = n(&p[0]) * (n(&src["width"]) - 1.0); let y = n(&p[1]) * (n(&src["height"]) - 1.0);
                x.is_finite() && y.is_finite() && x >= n(&crop["left"]) && y >= n(&crop["top"])
                    && x <= n(&crop["left"]) + n(&crop["width"]) - 1.0 && y <= n(&crop["top"]) + n(&crop["height"]) - 1.0
            })
    })
}
fn command(v: &Value) -> bool {
    if n(&v["version"]) != 1.0 || v["operation_id"] != OPERATION || !id(&v["request_id"]) || !binding(&v["binding"]) { return false; }
    match v["action"].as_str() {
        Some("choose_donor") => fields(v, &["version","operation_id","action","request_id","binding"]),
        Some("preview") => {
            let confirmations = ["same_person","same_session","real_measured_landmarks","reviewed_pose","both_unoccluded","fusion_reviewed"];
            fields(v, &["version","operation_id","action","request_id","binding","target","donor","fusion","settings","confirmations"])
                && owner(&v["target"]) && owner(&v["donor"]) && same(&v["target"]["source"], &v["binding"]["source"])
                && v["target"]["source"]["asset_sha256"] != v["donor"]["source"]["asset_sha256"]
                && v["target"]["source"]["original_sha256"] != v["donor"]["source"]["original_sha256"]
                && fusion(&v["fusion"], &v["target"])
                && fields(&v["settings"], &["density","pyramid_levels","colour_match_strength"])
                && n(&v["settings"]["density"]).is_finite() && n(&v["settings"]["density"]) > 0.0 && n(&v["settings"]["density"]) <= 1.0
                && integer(&v["settings"]["pyramid_levels"],1,5) && n(&v["settings"]["colour_match_strength"]) == 0.0
                && fields(&v["confirmations"], &confirmations) && confirmations.iter().all(|k| v["confirmations"][*k] == true)
        },
        Some("apply") => fields(v, &["version","operation_id","action","request_id","binding","return_mode","preview_request_id","preview_command_sha256","preview_token","candidate_sha256","fusion_mask_sha256","before_image_sha256","after_image_sha256","fusion_image_sha256","review"])
            && v["return_mode"] == "new_image" && v["review"] == "full_before_after_and_fusion_confirmed"
            && id(&v["preview_request_id"]) && id(&v["preview_token"]) && v["preview_request_id"] != v["request_id"]
            && ["preview_command_sha256","candidate_sha256","fusion_mask_sha256","before_image_sha256","after_image_sha256","fusion_image_sha256"].iter().all(|k| hash(&v[*k])),
        _ => false,
    }
}
#[derive(Clone)]
pub(crate) struct Packet { pub command: Value, pub command_sha256: String }
#[derive(Clone)]
pub(crate) struct Request {
    pub envelope: Value, pub id: String, pub action: String, pub packet: Option<Packet>,
    pub signature: String, pub command_sha256: String,
}
pub(crate) fn parse_request(v: &Value) -> Result<Request, String> {
    size(v, COMMAND_BYTES * 3)?;
    if v["cmd"] != "expression_replacement" || !id(&v["request_id"]) { return Err("表情替换命令或请求身份无效".into()); }
    let action = v["action"].as_str().ok_or("表情替换动作无效")?;
    let mut packet = None;
    let command_sha256;
    match action {
        "current" => {
            if !fields(v, &["cmd","action","request_id"]) { return Err("当前照片命令字段无效".into()); }
            // String-only keys in explicit order, matching Python sorted compact JSON.
            let bytes = format!("{{\"action\":\"current\",\"cmd\":\"expression_replacement\",\"request_id\":{}}}", serde_json::to_string(&v["request_id"]).map_err(|e| e.to_string())?);
            command_sha256 = digest(bytes.as_bytes());
        },
        "release" => {
            if !fields(v, &["cmd","action","request_id","preview_token"]) || !id(&v["preview_token"]) { return Err("释放预览身份无效".into()); }
            command_sha256 = digest(serde_json::to_string(v).map_err(|e| e.to_string())?.as_bytes());
        },
        "choose_donor" | "preview" | "apply" => {
            let has_path = v.get("path").is_some();
            let expected: &[&str] = if has_path { &["cmd","action","request_id","packet","path"] } else { &["cmd","action","request_id","packet"] };
            if !fields(v, expected) || (has_path && action != "choose_donor") { return Err("表情替换信封字段无效".into()); }
            if has_path && !v["path"].as_str().is_some_and(|s| !s.is_empty() && s.len() <= 4096 && !s.chars().any(char::is_control) && std::path::Path::new(s).is_absolute()) { return Err("供体图片必须使用原生绝对路径".into()); }
            let p = &v["packet"];
            if !fields(p, &["command","command_json","command_sha256"]) || !hash(&p["command_sha256"]) { return Err("表情替换命令包字段无效".into()); }
            let raw = p["command_json"].as_str().ok_or("缺少原始命令字节")?;
            let parsed = unique_json(raw, COMMAND_BYTES)?;
            command_sha256 = digest(raw.as_bytes());
            if p["command_sha256"] != command_sha256 || !same(&parsed,&p["command"]) || !command(&parsed)
                || parsed["request_id"] != v["request_id"] || parsed["action"] != action { return Err("表情替换命令原始字节、摘要、身份或内容不匹配".into()); }
            packet = Some(Packet { command: parsed, command_sha256: command_sha256.clone() });
        },
        _ => return Err("未支持的表情替换动作".into()),
    }
    // Envelope signature includes donor path and original command_json spelling.
    let signature = digest(serde_json::to_string(v).map_err(|e| e.to_string())?.as_bytes());
    Ok(Request { envelope: v.clone(), id: v["request_id"].as_str().unwrap().into(), action: action.into(), packet, signature, command_sha256 })
}

/// Validate the exact full-frame transport bytes and projection. Native does not
/// assert image quality or re-decode pixels; the immutable host owns rendering.
fn image(v: &Value, src: &Value) -> bool {
    if !fields(v, &["mime","width","height","sha256","base64","source_sha256","source_width","source_height","mapping","orientation"])
        || v["mime"] != "image/png" || !hash(&v["sha256"]) || !integer(&v["width"],2,1600) || !integer(&v["height"],2,1600)
        || n(&v["width"]) > n(&src["width"]) || n(&v["height"]) > n(&src["height"])
        || (n(&v["width"])*n(&src["height"]) - n(&v["height"])*n(&src["width"])).abs() > n(&src["width"]).max(n(&src["height"]))
        || v["source_sha256"] != src["asset_sha256"] || !same(&v["source_width"],&src["width"]) || !same(&v["source_height"],&src["height"])
        || v["mapping"] != "normalized_full_frame" || v["orientation"] != "exif_normalized_once" { return false; }
    let Some(encoded) = v["base64"].as_str().filter(|s| s.len() > 32 && s.len() <= 16_000_000 && s.len()%4 == 0) else { return false; };
    let Ok(bytes) = STANDARD.decode(encoded) else { return false; };
    if bytes.len() < 45 || bytes[..8] != [137,80,78,71,13,10,26,10] || bytes[8..12] != [0,0,0,13] || &bytes[12..16] != b"IHDR"
        || u32::from_be_bytes(bytes[16..20].try_into().unwrap()) as f64 != n(&v["width"])
        || u32::from_be_bytes(bytes[20..24].try_into().unwrap()) as f64 != n(&v["height"])
        || digest(&bytes) != v["sha256"].as_str().unwrap() { return false; }
    // Chunk framing must terminate exactly at IEND and contain image data. CRC,
    // inflate and perceptual validation belong to the actual host image encoder.
    let mut at = 8usize; let mut data = false; let mut chunks = 0;
    while at.checked_add(12).is_some_and(|end| end <= bytes.len()) {
        chunks += 1; if chunks > 65_536 { return false; }
        let length = u32::from_be_bytes(bytes[at..at+4].try_into().unwrap()) as usize;
        let Some(end) = at.checked_add(12).and_then(|p| p.checked_add(length)).filter(|end| *end <= bytes.len()) else { return false; };
        let tag = &bytes[at+4..at+8];
        if tag == b"IHDR" && at != 8 { return false; }
        if tag == b"IDAT" && length > 0 { data = true; }
        if tag == b"IEND" { return length == 0 && data && end == bytes.len(); }
        at = end;
    }
    false
}
pub(crate) fn photograph(v: &Value) -> bool {
    if !fields(v, &["source","label","faces","image"]) || !source(&v["source"]) || !id(&v["label"]) { return false; }
    let Some(faces) = v["faces"].as_array().filter(|v| v.len() <= 128) else { return false; };
    faces.iter().enumerate().all(|(index,f)| face(f,&v["source"])
        && !faces[..index].iter().any(|old| same(&old["face_ref"],&f["face_ref"]))) && image(&v["image"],&v["source"])
}
pub(crate) fn current(v: &Value) -> bool {
    fields(v, &["binding","photo","available","unavailable_reason"]) && binding(&v["binding"]) && photograph(&v["photo"])
        && same(&v["binding"]["source"],&v["photo"]["source"]) && v["available"].is_boolean()
        && (v["unavailable_reason"].is_null() || message(&v["unavailable_reason"],false))
}
fn receipt_fields(v: &Value, extra: &[&str]) -> bool {
    let mut names = vec!["version","operation_id","request_id","command_sha256","action","binding","phase"];
    names.extend_from_slice(extra); fields(v,&names)
}
pub(crate) fn receipt(v: &Value, packet: &Packet) -> bool {
    let command = &packet.command;
    if n(&v["version"]) != 1.0 || v["operation_id"] != OPERATION || v["request_id"] != command["request_id"] || v["action"] != command["action"]
        || v["command_sha256"] != packet.command_sha256 || !binding(&v["binding"]) || !same(&v["binding"],&command["binding"]) { return false; }
    match v["phase"].as_str() {
        Some("pending" | "unknown" | "cancelling") => receipt_fields(v,&["message"]) && message(&v["message"],false)
            && !(command["action"] == "apply" && v["phase"] == "cancelling"),
        Some("cancelled" | "rejected") => receipt_fields(v,&["no_write","message"]) && v["no_write"] == true && message(&v["message"],true)
            && !(command["action"] == "apply" && v["phase"] == "cancelled"),
        Some("donor_ready") => command["action"] == "choose_donor" && receipt_fields(v,&["photo"]) && photograph(&v["photo"]),
        Some("ready") => {
            let p = &v["preview"]; let src = &command["target"]["source"];
            command["action"] == "preview" && receipt_fields(v,&["preview"])
                && fields(p,&["preview_token","candidate_sha256","fusion_mask_sha256","output_width","output_height","before","after","fusion_image"])
                && id(&p["preview_token"]) && hash(&p["candidate_sha256"]) && hash(&p["fusion_mask_sha256"])
                && same(&p["output_width"],&src["width"]) && same(&p["output_height"],&src["height"])
                && ["before","after","fusion_image"].iter().all(|key| image(&p[*key],src))
                && ["width","height"].iter().all(|key| same(&p["before"][*key],&p["after"][*key]) && same(&p["before"][*key],&p["fusion_image"][*key]))
        },
        Some("committed") => command["action"] == "apply" && receipt_fields(v,&["preview_token","candidate_sha256","fusion_mask_sha256","result_document_id","copied_original_document_id","result_source_sha256","result_revision","no_change"])
            && ["preview_token","candidate_sha256","fusion_mask_sha256"].iter().all(|key| v[*key] == command[*key])
            && id(&v["result_document_id"]) && v["result_document_id"] != command["binding"]["document_id"]
            && v["copied_original_document_id"] == command["binding"]["document_id"] && v["result_source_sha256"] == command["candidate_sha256"]
            && integer(&v["result_revision"],0,SAFE_INTEGER) && v["no_change"].is_boolean() && command["return_mode"] == "new_image",
        _ => false,
    }
}
pub(crate) fn valid_result(v: &Value, req: &Request) -> bool {
    if v["event"] != EVENT || v["request_id"] != req.id || size(v,RESULT_BYTES).is_err() { return false; }
    if let Some(packet) = &req.packet { return fields(v,&["event","request_id","receipt"]) && receipt(&v["receipt"],packet); }
    match v["phase"].as_str() {
        Some("rejected" | "cancelled") => fields(v,&["event","request_id","phase","no_write","message"])
            && v["no_write"] == true && message(&v["message"],true) && (v["phase"] != "cancelled" || req.action == "current"),
        Some("current_ready") => req.action == "current" && fields(v,&["event","request_id","phase","current"]) && current(&v["current"]),
        Some("released") => req.action == "release" && fields(v,&["event","request_id","phase","preview_token"]) && v["preview_token"] == req.envelope["preview_token"],
        _ => false,
    }
}
pub(crate) fn phase(v: &Value) -> &str { v["receipt"]["phase"].as_str().or_else(|| v["phase"].as_str()).unwrap_or("") }
pub(crate) fn terminal(v: &Value) -> bool { matches!(phase(v),"rejected"|"cancelled"|"donor_ready"|"ready"|"committed"|"current_ready"|"released") }
pub(crate) fn pending(req: &Request, phase: &str, why: &str) -> Value {
    if let Some(packet) = &req.packet {
        json!({"event":EVENT,"request_id":req.id,"receipt":{"version":1,"operation_id":OPERATION,"request_id":req.id,
            "command_sha256":packet.command_sha256,"action":req.action,"binding":packet.command["binding"],"phase":phase,"message":why}})
    } else {
        json!({"event":EVENT,"request_id":req.id,"phase":phase,"command_sha256":req.command_sha256,"message":why})
    }
}
pub(crate) fn rejected(req: &Request, why: &str) -> Value {
    let mut v = pending(req,"rejected",why);
    if req.packet.is_some() { v["receipt"]["no_write"] = json!(true); }
    else { v.as_object_mut().unwrap().remove("command_sha256"); v["no_write"] = json!(true); }
    v
}
pub(crate) fn apply_matches(apply: &Request, preview: &Request, result: &Value) -> bool {
    let (Some(a),Some(p)) = (&apply.packet,&preview.packet) else { return false; };
    let a = &a.command; let proof = &result["receipt"]["preview"];
    apply.action == "apply" && preview.action == "preview" && phase(result) == "ready"
        && a["preview_request_id"] == preview.id && a["preview_command_sha256"] == p.command_sha256
        && same(&a["binding"],&p.command["binding"])
        && ["preview_token","candidate_sha256","fusion_mask_sha256"].iter().all(|key| a[*key] == proof[*key])
        && [("before_image_sha256","before"),("after_image_sha256","after"),("fusion_image_sha256","fusion_image")].iter().all(|(field,image)| a[*field] == proof[*image]["sha256"])
}

#[cfg(test)]
#[path = "expression_replacement_protocol_unrun.rs"]
mod tests;
