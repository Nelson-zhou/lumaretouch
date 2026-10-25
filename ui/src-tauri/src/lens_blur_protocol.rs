// SPDX-License-Identifier: GPL-3.0-or-later
//! Exact protocol-3 lens wire validation. Native validates evidence; it never
//! generates a preview, a depth inference, a result image or a history entry.
use std::{collections::HashSet, fmt, io::{self, Write}};
use base64::{engine::general_purpose::STANDARD, Engine as _};
use serde::{de::{self, MapAccess, SeqAccess, Visitor}, Deserialize, Deserializer};
use serde_json::{json, Map, Number, Value};
use sha2::{Digest, Sha256};

pub(crate) const PROTOCOL: u64 = 3;
pub(crate) const OPERATION: &str = "lnx.lens_blur.v1";
pub(crate) const EVENT: &str = "lens_blur_result";
pub(crate) const COMMAND_BYTES: usize = 512 * 1024;
pub(crate) const RESULT_BYTES: usize = 12 * 1024 * 1024;
pub(crate) const CONTEXT_BYTES: usize = 9 * 1024 * 1024;
pub(crate) const SMALL_BYTES: usize = 32 * 1024;
const IMAGE_BYTES: usize = 4 * 1024 * 1024;
pub(crate) const KERNELS: [&str;5] = ["circular_disk","rim_weighted_disk","regular_pentagon","regular_octagon","cat_eye_intersection"];

pub(crate) fn fields(v: &Value, keys: &[&str]) -> bool {
    v.as_object().is_some_and(|o| o.len() == keys.len() && keys.iter().all(|k| o.contains_key(*k)))
}
pub(crate) fn token(v: &Value) -> bool {
    v.as_str().is_some_and(|s| !s.is_empty() && s.len() <= 128 && s.bytes().all(|b| b.is_ascii_alphanumeric() || b == b'_' || b == b'-'))
}
pub(crate) fn hash(v: &Value) -> bool {
    v.as_str().is_some_and(|s| s.len() == 64 && s.bytes().all(|b| b.is_ascii_digit() || (b'a'..=b'f').contains(&b)))
}
fn integer(v: &Value, lo: u64, hi: u64) -> bool { v.as_u64().is_some_and(|n| (lo..=hi).contains(&n)) }
fn n(v: &Value) -> f64 { v.as_f64().unwrap_or(f64::NAN) }
fn bounded(v: &Value, lo: f64, hi: f64) -> bool { let x = n(v); x.is_finite() && (lo..=hi).contains(&x) }
fn unit(v: &Value) -> bool { bounded(v,0.0,1.0) }
fn message(v: &Value) -> bool { v.as_str().is_some_and(|s| s.encode_utf16().count() <= 4096 && !s.contains('\0')) }
fn revision(v: &Value) -> bool {
    v.as_str().is_some_and(|s| !s.is_empty() && s.len() <= 20 && (s == "0" || !s.starts_with('0'))
        && s.bytes().all(|c| c.is_ascii_digit()) && s.parse::<u64>().is_ok())
}
pub(crate) fn digest(bytes: &[u8]) -> String { format!("{:x}",Sha256::digest(bytes)) }
pub(crate) fn same(a: &Value, b: &Value) -> bool {
    match (a,b) {
        (Value::Number(a),Value::Number(b)) => a.as_f64() == b.as_f64(),
        (Value::Array(a),Value::Array(b)) => a.len() == b.len() && a.iter().zip(b).all(|(a,b)| same(a,b)),
        (Value::Object(a),Value::Object(b)) => a.len() == b.len() && a.iter().all(|(k,a)| b.get(k).is_some_and(|b| same(a,b))),
        _ => a == b,
    }
}
pub(crate) fn size(v: &Value, limit: usize) -> Result<usize,String> {
    struct Count { bytes: usize, limit: usize }
    impl Write for Count {
        fn write(&mut self, bytes: &[u8]) -> io::Result<usize> {
            self.bytes = self.bytes.checked_add(bytes.len()).ok_or_else(|| io::Error::new(io::ErrorKind::InvalidData,"size overflow"))?;
            if self.bytes > self.limit { return Err(io::Error::new(io::ErrorKind::InvalidData,"size limit")); }
            Ok(bytes.len())
        }
        fn flush(&mut self) -> io::Result<()> { Ok(()) }
    }
    let mut count = Count { bytes:0, limit };
    serde_json::to_writer(&mut count,v).map_err(|_| "镜头数据超过安全字节上限".to_string())?;
    Ok(count.bytes)
}
struct Unique(Value);
impl<'de> Deserialize<'de> for Unique {
    fn deserialize<D: Deserializer<'de>>(d: D) -> Result<Self,D::Error> {
        struct V;
        impl<'de> Visitor<'de> for V {
            type Value = Unique;
            fn expecting(&self,f: &mut fmt::Formatter) -> fmt::Result { f.write_str("finite JSON without duplicate object keys") }
            fn visit_bool<E: de::Error>(self,v:bool)->Result<Unique,E>{Ok(Unique(json!(v)))}
            fn visit_i64<E: de::Error>(self,v:i64)->Result<Unique,E>{Ok(Unique(json!(v)))}
            fn visit_u64<E: de::Error>(self,v:u64)->Result<Unique,E>{Ok(Unique(json!(v)))}
            fn visit_f64<E: de::Error>(self,v:f64)->Result<Unique,E>{Number::from_f64(v).map(|n|Unique(Value::Number(n))).ok_or_else(||E::custom("non-finite number"))}
            fn visit_str<E: de::Error>(self,v:&str)->Result<Unique,E>{Ok(Unique(Value::String(v.into())))}
            fn visit_string<E: de::Error>(self,v:String)->Result<Unique,E>{Ok(Unique(Value::String(v)))}
            fn visit_none<E: de::Error>(self)->Result<Unique,E>{Ok(Unique(Value::Null))}
            fn visit_unit<E: de::Error>(self)->Result<Unique,E>{Ok(Unique(Value::Null))}
            fn visit_seq<A: SeqAccess<'de>>(self,mut seq:A)->Result<Unique,A::Error>{
                let mut values=Vec::new(); while let Some(Unique(v))=seq.next_element::<Unique>()? {values.push(v);} Ok(Unique(Value::Array(values)))
            }
            fn visit_map<A: MapAccess<'de>>(self,mut map:A)->Result<Unique,A::Error>{
                let mut values=Map::new(); while let Some(k)=map.next_key::<String>()? {
                    if values.contains_key(&k){return Err(de::Error::custom("duplicate JSON field"));}
                    let Unique(v)=map.next_value::<Unique>()?; values.insert(k,v);
                } Ok(Unique(Value::Object(values)))
            }
        }
        d.deserialize_any(V)
    }
}
pub(crate) fn unique_json(raw: &str, cap: usize) -> Result<Value,String> {
    if raw.len()>cap {return Err("镜头 JSON 超过安全上限".into());}
    let mut parser=serde_json::Deserializer::from_str(raw);
    let value=Unique::deserialize(&mut parser).map_err(|_|"镜头 JSON 含重复字段、非法数字或结构".to_string())?.0;
    parser.end().map_err(|_|"镜头 JSON 含尾部内容".to_string())?; Ok(value)
}
pub(crate) fn capability(v:&Value)->bool {
    fields(v,&["version","operation_id","status","kernels","renderers","reason"]) && v["version"] == 2 && v["operation_id"] == OPERATION
        && message(&v["reason"]) && v["renderers"].as_array().is_some_and(|rs| rs.len()<=2
            && rs.iter().all(|r|matches!(r.as_str(),Some("direct-v1"|"cohort-fft-v2")))
            && rs.iter().filter_map(Value::as_str).collect::<HashSet<_>>().len()==rs.len()
            && ((v["status"]=="available" && !rs.is_empty()) || (v["status"]=="unavailable" && rs.is_empty())))
        && v["kernels"].as_array().is_some_and(|ks| ks.len()<=5
            && ks.iter().all(|k| k.as_str().is_some_and(|k| KERNELS.contains(&k)))
            && ks.iter().filter_map(Value::as_str).collect::<HashSet<_>>().len()==ks.len()
            && ((v["status"]=="available" && !ks.is_empty()) || (v["status"]=="unavailable" && ks.is_empty())))
}
pub(crate) fn source(v:&Value)->bool {
    fields(v,&["sha256","width","height","orientation"]) && hash(&v["sha256"])
        && integer(&v["width"],2,1_000_000) && integer(&v["height"],2,1_000_000)
        && n(&v["width"])*n(&v["height"])<=100_000_000.0 && v["orientation"]=="exif_normalized_once"
}
pub(crate) fn owner(v:&Value)->bool {
    fields(v,&["document_id","document_epoch","document_revision","source"])
        && token(&v["document_id"]) && token(&v["document_epoch"]) && revision(&v["document_revision"]) && source(&v["source"])
}
fn whole_frame(width:&Value,height:&Value,src:&Value)->bool {
    n(width)<=n(&src["width"]) && n(height)<=n(&src["height"])
        && (n(width)*n(&src["height"])-n(height)*n(&src["width"])).abs()<=n(&src["width"]).max(n(&src["height"]))
}
fn crc(bytes:&[u8])->u32 {
    let mut crc=0xffff_ffffu32; for byte in bytes {crc^=u32::from(*byte); for _ in 0..8 {crc=(crc>>1)^(0xedb8_8320 & (0u32.wrapping_sub(crc&1)));}} !crc
}
/// Verify complete PNG bytes, CRCs, exact full-frame dimensions and content hash.
/// Deflate/pixel decode and real visible presentation remain separate UI/host gates.
pub(crate) fn image(v:&Value,src:&Value)->bool {
    if !fields(v,&["mime","width","height","sha256","base64"]) || v["mime"]!="image/png" || !hash(&v["sha256"])
        || !integer(&v["width"],2,1280) || !integer(&v["height"],2,1280) || !whole_frame(&v["width"],&v["height"],src) {return false;}
    let Some(encoded)=v["base64"].as_str().filter(|s|s.len()<=((IMAGE_BYTES+2)/3)*4 && s.len()%4==0) else {return false;};
    let Ok(bytes)=STANDARD.decode(encoded) else{return false;};
    if bytes.len()<57 || bytes.len()>IMAGE_BYTES || bytes[..8]!=[137,80,78,71,13,10,26,10]
        || STANDARD.encode(&bytes)!=encoded || digest(&bytes)!=v["sha256"].as_str().unwrap() {return false;}
    let mut at=8usize; let mut header=false; let mut data=false; let mut seen_data=false; let mut data_ended=false;
    while at.checked_add(12).is_some_and(|end|end<=bytes.len()) {
        let length=u32::from_be_bytes(bytes[at..at+4].try_into().unwrap()) as usize;
        let Some(end)=at.checked_add(12).and_then(|i|i.checked_add(length)).filter(|i|*i<=bytes.len()) else{return false;};
        let tag=&bytes[at+4..at+8];
        if !tag.iter().all(|b|b.is_ascii_alphabetic()) || !tag[2].is_ascii_uppercase()
            || crc(&bytes[at+4..end-4])!=u32::from_be_bytes(bytes[end-4..end].try_into().unwrap()) {return false;}
        if !header {
            if tag!=b"IHDR" || length!=13 || u32::from_be_bytes(bytes[at+8..at+12].try_into().unwrap()) as f64!=n(&v["width"])
                || u32::from_be_bytes(bytes[at+12..at+16].try_into().unwrap()) as f64!=n(&v["height"])
                || bytes[at+16]!=8 || ![2,6].contains(&bytes[at+17]) || bytes[at+18..at+21]!=[0,0,0] {return false;}
            header=true;
        } else if tag==b"IDAT" {if data_ended{return false;} seen_data=true; data|=length>0;}
        else if tag==b"IEND" {return length==0 && data && end==bytes.len();}
        else {if !tag[0].is_ascii_lowercase() || tag==b"acTL" || tag==b"fcTL" || tag==b"fdAT" {return false;} if seen_data {data_ended=true;}}
        at=end;
    } false
}
fn provenance(v:&Value)->bool {
    // This host has no verified AI depth backend or supplied-depth entry point.
    fields(v,&["kind","method","depth_value","acknowledgement_id"]) && v["kind"]=="manual"
        && v["method"]=="user_defined_plane" && unit(&v["depth_value"]) && token(&v["acknowledgement_id"])
}
pub(crate) fn depth(v:&Value,own:&Value)->bool {
    if !fields(v,&["version","token","owner","convention","mapping","orientation","raster","provenance","subject_focus"])
        || v["version"]!=1 || !token(&v["token"]) || !owner(&v["owner"]) || !same(&v["owner"],own)
        || v["convention"]!="near-zero-far-one" || v["mapping"]!="normalized_full_frame_pixel_centres"
        || v["orientation"]!="exif_normalized_once" || !provenance(&v["provenance"]) || !v["subject_focus"].is_null() {return false;}
    let r=&v["raster"];
    if !fields(r,&["format","width","height","sha256","base64"]) || r["format"]!="u16-le" || !hash(&r["sha256"])
        || !integer(&r["width"],2,1024) || !integer(&r["height"],2,1024) || !whole_frame(&r["width"],&r["height"],&own["source"]) {return false;}
    let length=(r["width"].as_u64().unwrap()*r["height"].as_u64().unwrap()*2) as usize;
    let Some(encoded)=r["base64"].as_str().filter(|s|s.len()==((length+2)/3)*4) else{return false;};
    let Ok(bytes)=STANDARD.decode(encoded) else{return false;};
    let expected=(n(&v["provenance"]["depth_value"])*65535.0+0.5).floor() as u16;
    bytes.len()==length && STANDARD.encode(&bytes)==encoded && digest(&bytes)==r["sha256"].as_str().unwrap()
        && bytes.chunks_exact(2).all(|p|u16::from_le_bytes([p[0],p[1]])==expected)
}
pub(crate) fn context(v:&Value)->bool {
    fields(v,&["session_id","owner","source_image","depth","depth_status","message"]) && token(&v["session_id"])
        && owner(&v["owner"]) && image(&v["source_image"],&v["owner"]["source"]) && message(&v["message"])
        && if v["depth_status"]=="ready" {depth(&v["depth"],&v["owner"])} else {
            matches!(v["depth_status"].as_str(),Some("pending"|"missing-model"|"manual-required"|"failed")) && v["depth"].is_null()
        }
}
fn point(v:&Value)->bool {fields(v,&["x","y"]) && unit(&v["x"]) && unit(&v["y"])}
pub(crate) fn recipe(v:&Value)->bool {
    let mut keys=vec!["version","operation_id","source","depth","aperture","max_radius_px","focus","depth_falloff","occlusion_tolerance","rotation_radians","refinements"];
    if v["version"]==2 {
        keys.push("math_identity");
        if v["operation_id"]!="lnx.lens_blur.cohort.v2" || v["math_identity"]!="cohort-fft-f64-v2-00020001"
            || v["depth"]["provenance"]["kind"]!="manual" || v["depth"]["provenance"]["method"]!="user_defined_plane" {return false;}
    } else if v["version"]!=1 || v["operation_id"]!=OPERATION {return false;}
    if !fields(v,&keys) || !source(&v["source"]) || !fields(&v["depth"],&["token","sha256","provenance"])
        || !token(&v["depth"]["token"]) || !hash(&v["depth"]["sha256"]) || !provenance(&v["depth"]["provenance"])
        || !v["aperture"].as_str().is_some_and(|k|KERNELS.contains(&k)) || !bounded(&v["max_radius_px"],0.0,128.0)
        || !bounded(&v["depth_falloff"],0.000001,1.0) || !unit(&v["occlusion_tolerance"])
        || !bounded(&v["rotation_radians"],-std::f64::consts::PI,std::f64::consts::PI) {return false;}
    let f=&v["focus"];
    if !fields(f,&["mode","near","far","point"]) || !unit(&f["near"]) || !unit(&f["far"]) || n(&f["near"])>n(&f["far"])
        || !(if f["mode"]=="point" {point(&f["point"])} else {f["mode"]=="interval" && f["point"].is_null()}) {return false;}
    let Some(strokes)=v["refinements"].as_array().filter(|s|s.len()<=64) else{return false;};
    let mut ids=HashSet::new(); let mut total=0usize;
    strokes.iter().all(|s| {
        let Some(points)=s["points"].as_array() else{return false;}; total+=points.len();
        fields(s,&["id","mode","amount","flow","feather","radius","points"]) && token(&s["id"])
            && ids.insert(s["id"].as_str().unwrap()) && matches!(s["mode"].as_str(),Some("clear"|"blur"))
            && ["amount","flow","feather"].iter().all(|k|unit(&s[*k])) && bounded(&s["radius"],0.0,0.25) && n(&s["radius"])>0.0
            && !points.is_empty() && points.len()<=2048 && total<=8192 && points.iter().all(point)
    }) && size(v,COMMAND_BYTES).is_ok()
}
pub(crate) fn command(v:&Value)->bool {
    if v["version"]!=PROTOCOL || !token(&v["request_id"]) || !token(&v["session_id"]) || !owner(&v["owner"]) || size(v,COMMAND_BYTES).is_err() {return false;}
    match v["action"].as_str() {
        Some("prepare_manual_plane") => fields(v,&["version","action","request_id","session_id","owner","depth_value","acknowledged_manual"])
            && unit(&v["depth_value"]) && v["acknowledged_manual"]==true,
        Some("preview") => fields(v,&["version","action","request_id","session_id","owner","recipe"])
            && recipe(&v["recipe"]) && same(&v["recipe"]["source"],&v["owner"]["source"]),
        Some("apply") => fields(v,&["version","action","request_id","session_id","owner","token","recipe_sha256","before_sha256","after_sha256","reviewed","return_mode","result_source_sha256"])
            && token(&v["token"]) && ["recipe_sha256","before_sha256","after_sha256","result_source_sha256"].iter().all(|k|hash(&v[*k]))
            && v["reviewed"]==true && v["return_mode"]=="new_image",
        Some("cancel") => fields(v,&["version","action","request_id","session_id","owner","token"]) && (v["token"].is_null() || token(&v["token"])),
        _=>false,
    }
}
#[derive(Clone)]
pub(crate) struct Request {pub envelope:Value,pub id:String,pub action:String,pub signature:String}
impl Request {
    pub(crate) fn write(&self)->bool {self.action=="submit"}
    pub(crate) fn apply(&self)->bool {self.write() && self.envelope["command"]["action"]=="apply"}
    pub(crate) fn read(&self)->bool {matches!(self.action.as_str(),"current"|"prepare_manual_plane"|"preview")}
    pub(crate) fn inner(&self)->&Value {&self.envelope["command"]}
}
pub(crate) fn parse_request(v:&Value)->Result<Request,String> {
    size(v,COMMAND_BYTES+4096)?;
    if v["cmd"]!="lens_blur" || !token(&v["request_id"]) {return Err("镜头原生信封身份无效".into());}
    let action=v["action"].as_str().ok_or("镜头动作缺失")?;
    if action=="current" {
        if !fields(v,&["cmd","action","request_id"]) {return Err("镜头当前照片命令含未知字段".into());}
    } else {
        if !fields(v,&["cmd","action","request_id","command"]) || !command(&v["command"])
            || (action!="receipt" && v["request_id"]!=v["command"]["request_id"]) {return Err("镜头完整命令身份、字段或版本无效".into());}
        let inner=v["command"]["action"].as_str().unwrap_or("");
        if !match action {"prepare_manual_plane"|"preview"=>inner==action,"submit"|"receipt"=>matches!(inner,"apply"|"cancel"),_=>false} {
            return Err("镜头传输动作不匹配原命令".into());
        }
        if action=="receipt" && v["request_id"]==v["command"]["request_id"] {return Err("核对必须使用独立查询身份，不得重发原写入".into());}
    }
    // Local replay signature only, NOT Python's recipe/command hash. Read cancel
    // sends this retained envelope as proof; Python hashes its own parsed form.
    let signature=digest(serde_json::to_string(v).map_err(|e|e.to_string())?.as_bytes());
    Ok(Request{envelope:v.clone(),id:v["request_id"].as_str().unwrap().into(),action:action.into(),signature})
}
pub(crate) fn receipt(v:&Value,c:&Value)->bool {
    if !command(c) || !matches!(c["action"].as_str(),Some("apply"|"cancel"))
        || v["version"]!=PROTOCOL || ["request_id","session_id","action","owner","token"].iter().any(|k|!same(&v[*k],&c[*k]))
        || !owner(&v["owner"]) || !message(&v["message"]) {return false;}
    let mut keys=vec!["version","request_id","session_id","action","owner","token","phase","outcome_unknown","message"];
    if matches!(v["phase"].as_str(),Some("pending"|"unknown")) {return fields(v,&keys) && v["outcome_unknown"]==true;}
    if v["phase"]!="done" || v["outcome_unknown"]!=false {return false;}
    keys.push("outcome");
    if v["outcome"]=="rejected" || v["outcome"]=="cancelled" {return fields(v,&keys) && (v["outcome"]!="cancelled" || c["action"]=="cancel");}
    keys.extend_from_slice(&["recipe_sha256","before_sha256","after_sha256","return_mode","copied_original_document_id","result_document_id","result_revision","result_source_sha256","no_change"]);
    fields(v,&keys) && v["outcome"]=="applied" && c["action"]=="apply"
        && ["recipe_sha256","before_sha256","after_sha256","return_mode","result_source_sha256"].iter().all(|k|v[*k]==c[*k])
        && v["copied_original_document_id"]==c["owner"]["document_id"] && token(&v["result_document_id"])
        && v["result_document_id"]!=v["copied_original_document_id"] && revision(&v["result_revision"])
        && v["no_change"].as_bool()==Some(v["result_source_sha256"]==c["owner"]["source"]["sha256"])
}
pub(crate) fn review(v:&Value,c:&Value)->bool {
    fields(v,&["version","request_id","session_id","token","owner","recipe","recipe_sha256","before","after","notes","result_source_sha256"])
        && v["version"]==PROTOCOL && c["action"]=="preview" && ["request_id","session_id","owner","recipe"].iter().all(|k|same(&v[*k],&c[*k]))
        && owner(&v["owner"]) && token(&v["token"]) && recipe(&v["recipe"]) && hash(&v["recipe_sha256"]) && hash(&v["result_source_sha256"])
        && image(&v["before"],&c["owner"]["source"]) && image(&v["after"],&c["owner"]["source"])
        && v["before"]["width"]==v["after"]["width"] && v["before"]["height"]==v["after"]["height"]
        && v["notes"].as_array().is_some_and(|a|a.len()<=32 && a.iter().all(message))
}
pub(crate) fn valid_result(v:&Value,req:&Request)->bool {
    if v["event"]!=EVENT || v["request_id"]!=req.id || size(v,RESULT_BYTES).is_err() {return false;}
    if req.write() || req.action=="receipt" {
        return fields(v,&["event","request_id","status","receipt"]) && v["status"]=="ready" && receipt(&v["receipt"],req.inner());
    }
    match v["status"].as_str() {
        Some("rejected"|"cancelled")=>fields(v,&["event","request_id","status","message"]) && message(&v["message"]),
        Some("ready")=>match req.action.as_str() {
            "current" => capability(&v["capability"]) && if v["context"].is_null() {
                fields(v,&["event","request_id","status","capability","context","message"]) && v["capability"]["status"]=="unavailable" && message(&v["message"])
            } else {fields(v,&["event","request_id","status","capability","context"]) && v["capability"]["status"]=="available" && context(&v["context"])
                && v["context"]["depth"].is_null() && v["context"]["depth_status"]=="manual-required"},
            "prepare_manual_plane"=>fields(v,&["event","request_id","status","context"]) && context(&v["context"])
                && ["session_id","owner"].iter().all(|k|same(&v["context"][*k],&req.inner()[*k])) && v["context"]["depth_status"]=="ready"
                && v["context"]["depth"]["provenance"]["acknowledgement_id"]==req.id
                && same(&v["context"]["depth"]["provenance"]["depth_value"],&req.inner()["depth_value"]),
            "preview"=>fields(v,&["event","request_id","status","review"]) && review(&v["review"],req.inner()),
            _=>false,
        },
        _=>false,
    }
}
pub(crate) fn terminal(v:&Value)->bool { if v.get("receipt").is_some() {v["receipt"]["phase"]=="done"} else {matches!(v["status"].as_str(),Some("ready"|"rejected"|"cancelled"))} }
pub(crate) fn pending(req:&Request,status:&str,why:&str)->Value {
    if req.write() || req.action=="receipt" {
        let c=req.inner(); json!({"event":EVENT,"request_id":req.id,"status":"ready","receipt":{"version":PROTOCOL,
            "request_id":c["request_id"],"session_id":c["session_id"],"action":c["action"],"owner":c["owner"],"token":c["token"],
            "phase":status,"outcome_unknown":true,"message":why}})
    } else {json!({"event":EVENT,"request_id":req.id,"status":status,"message":why})}
}
pub(crate) fn rejected(req:&Request,why:&str)->Value {
    let mut v=pending(req,"unknown",why);
    if req.write() {v["receipt"]["phase"]=json!("done");v["receipt"]["outcome_unknown"]=json!(false);v["receipt"]["outcome"]=json!("rejected");}
    else if req.action!="receipt" {v["status"]=json!("rejected");}
    v
}
pub(crate) fn apply_matches(req:&Request,review:&Value)->bool {
    let c=req.inner(); req.apply() && review["version"]==PROTOCOL && ["session_id","owner","token","recipe_sha256","result_source_sha256"].iter().all(|k|same(&c[*k],&review[*k]))
        && c["before_sha256"]==review["before"]["sha256"] && c["after_sha256"]==review["after"]["sha256"]
}
#[cfg(test)]
#[path="lens_blur_protocol_unrun.rs"]
mod tests;
