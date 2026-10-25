// SPDX-License-Identifier: GPL-3.0-or-later
//! Exact portrait-crop transport/evidence validation. This is not a renderer,
//! crop planner, source owner or history writer. AUTHORED / UNRUN.
use std::{collections::HashSet, fmt, io::{self, Write}};
use base64::{engine::general_purpose::STANDARD, Engine as _};
use serde::{de::{self, MapAccess, SeqAccess, Visitor}, Deserialize, Deserializer};
use serde_json::{json, Map, Number, Value};
use sha2::{Digest, Sha256};

pub(crate) const EVENT: &str = "portrait_crop_result";
pub(crate) const COMMAND_BYTES: usize = 64 * 1024;
pub(crate) const RESULT_BYTES: usize = 24 * 1024 * 1024;
pub(crate) const SMALL_BYTES: usize = 256 * 1024;
const IMAGE_BYTES: usize = 8 * 1024 * 1024;
const MAX_DIMENSION: u64 = 1_000_000;
fn fields(v: &Value, keys: &[&str]) -> bool {
    v.as_object().is_some_and(|o| o.len() == keys.len() && keys.iter().all(|k| o.contains_key(*k)))
}
fn allowed(v: &Value, required: &[&str], optional: &[&str]) -> bool {
    v.as_object().is_some_and(|o| required.iter().all(|k| o.contains_key(*k))
        && o.keys().all(|k| required.contains(&k.as_str()) || optional.contains(&k.as_str())))
}
pub(crate) fn token(v: &Value) -> bool {
    v.as_str().is_some_and(|s| !s.is_empty() && s.len() <= 128
        && s.bytes().all(|b| b.is_ascii_alphanumeric() || b"._:-".contains(&b)))
}
pub(crate) fn hash(v: &Value) -> bool {
    v.as_str().is_some_and(|s| s.len() == 64 && s.bytes().all(|b| b.is_ascii_digit() || (b'a'..=b'f').contains(&b)))
}
fn integer(v: &Value, lo: u64, hi: u64) -> bool { v.as_u64().is_some_and(|n| (lo..=hi).contains(&n)) }
fn n(v: &Value) -> f64 { v.as_f64().unwrap_or(f64::NAN) }
fn bounded(v: &Value, lo: f64, hi: f64) -> bool { let n = n(v); n.is_finite() && (lo..=hi).contains(&n) }
fn message(v: &Value) -> bool { v.as_str().is_some_and(|s| s.chars().count() <= 4096 && !s.contains('\0')) }
fn revision(v: &Value) -> bool {
    integer(v, 0, 9_007_199_254_740_991) || v.as_str().is_some_and(|s| !s.is_empty() && s.len() <= 20
        && s.bytes().all(|b| b.is_ascii_digit()) && s.parse::<u64>().is_ok())
}
fn revision_number(v:&Value)->Option<u64> {
    if !revision(v) {return None;}
    v.as_u64().or_else(||v.as_str().and_then(|s|s.parse::<u64>().ok()))
}
fn commit_revision(result:&Value,current:&Value,candidate:&Value)->bool {
    let Some(before)=revision_number(&current["binding"]["revision"]) else{return false;};
    let Some(after)=revision_number(&result["revision"]) else{return false;};
    match result["status"].as_str() {
        Some("no_change")=>after==before && candidate==&current["binding"]["state_sha256"],
        Some("applied")=>before.checked_add(1)==Some(after) && candidate!=&current["binding"]["state_sha256"],
        _=>false,
    }
}
pub(crate) fn digest(bytes: &[u8]) -> String { format!("{:x}", Sha256::digest(bytes)) }
/// Structural equality does not pretend Rust JSON bytes equal Python's hash input.
pub(crate) fn same(a: &Value, b: &Value) -> bool {
    match (a, b) {
        (Value::Number(a), Value::Number(b)) => a == b || a.as_f64() == b.as_f64(),
        (Value::Array(a), Value::Array(b)) => a.len() == b.len() && a.iter().zip(b).all(|(a,b)| same(a,b)),
        (Value::Object(a), Value::Object(b)) => a.len() == b.len() && a.iter().all(|(k,a)| b.get(k).is_some_and(|b| same(a,b))),
        _ => a == b,
    }
}
pub(crate) fn size(value: &Value, limit: usize) -> Result<usize, String> {
    struct Count { bytes: usize, limit: usize }
    impl Write for Count {
        fn write(&mut self, bytes: &[u8]) -> io::Result<usize> {
            self.bytes = self.bytes.checked_add(bytes.len()).ok_or_else(|| io::Error::new(io::ErrorKind::InvalidData,"size overflow"))?;
            if self.bytes > self.limit { return Err(io::Error::new(io::ErrorKind::InvalidData,"size limit")); }
            Ok(bytes.len())
        }
        fn flush(&mut self) -> io::Result<()> { Ok(()) }
    }
    let mut count = Count {bytes:0, limit};
    serde_json::to_writer(&mut count,value).map_err(|_| "人像裁剪数据超过安全字节上限".to_owned())?;
    Ok(count.bytes)
}
struct Unique(Value);
impl<'de> Deserialize<'de> for Unique {
    fn deserialize<D: Deserializer<'de>>(d: D) -> Result<Self,D::Error> {
        struct V;
        impl<'de> Visitor<'de> for V {
            type Value = Unique;
            fn expecting(&self, f:&mut fmt::Formatter) -> fmt::Result { f.write_str("finite JSON without duplicate keys") }
            fn visit_bool<E:de::Error>(self,v:bool)->Result<Unique,E>{Ok(Unique(json!(v)))}
            fn visit_i64<E:de::Error>(self,v:i64)->Result<Unique,E>{Ok(Unique(json!(v)))}
            fn visit_u64<E:de::Error>(self,v:u64)->Result<Unique,E>{Ok(Unique(json!(v)))}
            fn visit_f64<E:de::Error>(self,v:f64)->Result<Unique,E>{Number::from_f64(v).map(|n|Unique(Value::Number(n))).ok_or_else(||E::custom("nonfinite"))}
            fn visit_str<E:de::Error>(self,v:&str)->Result<Unique,E>{Ok(Unique(Value::String(v.into())))}
            fn visit_string<E:de::Error>(self,v:String)->Result<Unique,E>{Ok(Unique(Value::String(v)))}
            fn visit_none<E:de::Error>(self)->Result<Unique,E>{Ok(Unique(Value::Null))}
            fn visit_unit<E:de::Error>(self)->Result<Unique,E>{Ok(Unique(Value::Null))}
            fn visit_seq<A:SeqAccess<'de>>(self,mut seq:A)->Result<Unique,A::Error>{
                let mut values=Vec::new(); while let Some(Unique(v))=seq.next_element::<Unique>()? {values.push(v);} Ok(Unique(Value::Array(values)))
            }
            fn visit_map<A:MapAccess<'de>>(self,mut map:A)->Result<Unique,A::Error>{
                let mut values=Map::new(); while let Some(k)=map.next_key::<String>()? {
                    if values.contains_key(&k){return Err(de::Error::custom("duplicate JSON field"));}
                    let Unique(v)=map.next_value::<Unique>()?; values.insert(k,v);
                } Ok(Unique(Value::Object(values)))
            }
        }
        d.deserialize_any(V)
    }
}
pub(crate) fn unique_json(raw:&str, cap:usize)->Result<Value,String> {
    if raw.len()>cap {return Err("人像裁剪原始 JSON 超限".into());}
    let mut parser=serde_json::Deserializer::from_str(raw);
    let value=Unique::deserialize(&mut parser).map_err(|_|"人像裁剪原始 JSON 含重复字段或非法结构".to_owned())?.0;
    parser.end().map_err(|_|"人像裁剪原始 JSON 含尾部内容".to_owned())?; Ok(value)
}

pub(crate) fn capability(v:&Value)->bool {
    fields(v,&["version","operation_id","available","reason","supported_rotation_degrees","planner","analysis","runtime_acceptance"])
        && v["version"]==1 && v["operation_id"]=="lnx.crop.v1" && v["available"].is_boolean()
        && (v["reason"].is_null() || message(&v["reason"])) && same(&v["supported_rotation_degrees"],&json!([0]))
        && v["analysis"]=="fresh_whole_frame_display_proxy" && v["runtime_acceptance"]=="UNRUN"
        && fields(&v["planner"],&["version","backend","available","abi","capabilities","reason"])
        && v["planner"]["version"]==1 && v["planner"]["backend"]=="rust-portrait-crop-v1"
        && v["planner"]["available"].is_boolean() && integer(&v["planner"]["capabilities"],0,u64::MAX)
        && (v["planner"]["abi"].is_null() || integer(&v["planner"]["abi"],1,u64::MAX))
        && (v["planner"]["reason"].is_null() || message(&v["planner"]["reason"]))
        && (v["available"]!=true || (v["reason"].is_null() && v["planner"]["available"]==true))
}
fn point(v:&Value,w:f64,h:f64)->bool {
    v.as_array().is_some_and(|a|a.len()==2 && bounded(&a[0],0.,w) && bounded(&a[1],0.,h))
}
fn anchors(v:&Value,w:f64,h:f64)->bool {
    fields(v,&["version","crown","chin","face_center"]) && v["version"]==1
        && ["crown","chin","face_center"].iter().all(|k|point(&v[*k],w,h))
        && n(&v["crown"][1])<n(&v["chin"][1])
        && n(&v["crown"][1])<=n(&v["face_center"][1]) && n(&v["face_center"][1])<=n(&v["chin"][1])
}
fn rules(v:&Value)->bool {
    fields(v,&["version","aspect_ratio","headroom_fraction","head_fraction","horizontal_position"]) && v["version"]==1
        && bounded(&v["aspect_ratio"],0.001,1000.) && bounded(&v["headroom_fraction"],0.,1.)
        && bounded(&v["head_fraction"],0.,1.) && n(&v["head_fraction"])>0. && bounded(&v["horizontal_position"],0.,1.)
        && n(&v["headroom_fraction"])+n(&v["head_fraction"])<=1.
}
#[derive(Clone)]
pub(crate) struct Request {pub envelope:Value,pub id:String,pub action:String,pub signature:String}
impl Request {
    pub(crate) fn apply(&self)->bool {self.action=="apply"}
    pub(crate) fn read(&self)->bool {matches!(self.action.as_str(),"current"|"preview")}
}
pub(crate) fn parse_request(v:&Value)->Result<Request,String> {
    size(v,COMMAND_BYTES)?;
    if v["cmd"]!="portrait_crop" || !token(&v["request_id"]) {return Err("人像裁剪原请求身份无效".into());}
    let action=v["action"].as_str().ok_or("人像裁剪动作缺失")?;
    let common=["cmd","action","request_id"];
    let mut keys=common.to_vec();
    match action {
        "capability"|"current"=>{},
        "preview"=>keys.extend_from_slice(&["session_id","capture_sha256","face_id","anchors","rules","anchor_review"]),
        "apply"=>keys.extend_from_slice(&["session_id","capture_sha256","preview_request_id","preview_token","candidate_sha256","before_image_sha256","after_image_sha256","review"]),
        "status"=>keys.push("target_request_id"),
        "cancel"=>keys.push("session_id"),
        _=>return Err("不支持的人像裁剪动作".into()),
    }
    if !fields(v,&keys) {return Err("人像裁剪原请求必须使用完整且唯一的约定字段".into());}
    for key in ["session_id","preview_request_id","preview_token","target_request_id","face_id"] {
        if keys.contains(&key) && !token(&v[key]) {return Err("人像裁剪会话、预览或人脸身份无效".into());}
    }
    for key in ["capture_sha256","candidate_sha256","before_image_sha256","after_image_sha256"] {
        if keys.contains(&key) && !hash(&v[key]) {return Err("人像裁剪内容哈希无效".into());}
    }
    if action=="preview" && (!anchors(&v["anchors"],MAX_DIMENSION as f64,MAX_DIMENSION as f64) || !rules(&v["rules"])
        || !fields(&v["anchor_review"],&["image_sha256","crown_confirmed","chin_confirmed","center_confirmed"])
        || !hash(&v["anchor_review"]["image_sha256"])
        || ["crown_confirmed","chin_confirmed","center_confirmed"].iter().any(|k|v["anchor_review"][*k]!=true)) {
        return Err("人像裁剪需要显式比例及真实完整照片上的三个已确认锚点".into());
    }
    if action=="apply" && v["review"]!="full_before_after_confirmed" {return Err("应用前必须明确核对完整前后照片".into());}
    if action=="status" && v["request_id"]==v["target_request_id"] {return Err("查询必须使用独立身份，不能重发原请求".into());}
    // Never send this local signature as command_sha256. Python owns that hash.
    let signature=digest(serde_json::to_vec(v).map_err(|e|e.to_string())?.as_slice());
    Ok(Request{envelope:v.clone(),id:v["request_id"].as_str().unwrap().into(),action:action.into(),signature})
}
fn crc(bytes:&[u8])->u32 {
    let mut c=0xffff_ffffu32; for b in bytes {c^=u32::from(*b); for _ in 0..8 {c=(c>>1)^(0xedb8_8320 & 0u32.wrapping_sub(c&1));}} !c
}
/// Validate complete PNG transport, not a partial viewport or CSS crop. Actual
/// decoding/presentation and canonical full-resolution rendering remain separate gates.
pub(crate) fn image(v:&Value)->bool {
    if !fields(v,&["mime","width","height","sha256","base64","source_width","source_height","mapping"])
        || v["mime"]!="image/png" || v["mapping"]!="normalized_full_frame" || !hash(&v["sha256"])
        || !integer(&v["width"],1,1400) || !integer(&v["height"],1,1400)
        || !integer(&v["source_width"],1,MAX_DIMENSION) || !integer(&v["source_height"],1,MAX_DIMENSION)
        || n(&v["width"])>n(&v["source_width"]) || n(&v["height"])>n(&v["source_height"])
        || (n(&v["width"])*n(&v["source_height"])-n(&v["height"])*n(&v["source_width"])).abs()>n(&v["source_width"]).max(n(&v["source_height"])) {return false;}
    let Some(encoded)=v["base64"].as_str().filter(|s|s.len()<=((IMAGE_BYTES+2)/3)*4 && s.len()%4==0) else{return false;};
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
                || bytes[at+16]!=8 || bytes[at+17]!=2 || bytes[at+18..at+21]!=[0,0,0] {return false;}
            header=true;
        } else if tag==b"IDAT" {if data_ended{return false;} seen_data=true; data|=length>0;}
        else if tag==b"IEND" {return length==0 && data && end==bytes.len();}
        else {if !tag[0].is_ascii_lowercase() || (tag==b"acTL" || tag==b"fcTL" || tag==b"fdAT") {return false;} if seen_data {data_ended=true;}}
        at=end;
    } false
}
pub(crate) fn image_proof(v:&Value)->Value {
    json!({"mime":v["mime"],"width":v["width"],"height":v["height"],"sha256":v["sha256"],
        "source_width":v["source_width"],"source_height":v["source_height"],"mapping":v["mapping"]})
}
fn source_proof(v:&Value,b:&Value,s:&Value)->bool {
    if !fields(v,&["asset_sha256","creative_source","original_sha256"]) || !hash(&v["asset_sha256"])
        || v["original_sha256"]!=b["original_sha256"] {return false;}
    let c=&v["creative_source"];
    if c.is_null() {v["asset_sha256"]==v["original_sha256"]} else {
        fields(c,&["sha256","width","height"]) && c["sha256"]==v["asset_sha256"] && c["width"]==s["width"] && c["height"]==s["height"]
    }
}
pub(crate) fn current(v:&Value)->bool {
    if !fields(v,&["session_id","capture_sha256","binding","source","before"]) || !token(&v["session_id"])
        || !hash(&v["capture_sha256"]) || !image(&v["before"]) {return false;}
    let b=&v["binding"]; let s=&v["source"];
    if !fields(b,&["document_id","revision","document_epoch","load_id","original_sha256","source_proof","state_sha256","non_crop_sha256","people_sha256","repair_sha256","uncropped_sha256"])
        || !token(&b["document_id"]) || !token(&b["load_id"]) || !revision(&b["revision"]) || !(token(&b["document_epoch"]) || revision(&b["document_epoch"]))
        || ["original_sha256","state_sha256","non_crop_sha256","people_sha256","repair_sha256","uncropped_sha256"].iter().any(|k|!hash(&b[*k]))
        || !fields(s,&["width","height","orientation","mapping","source_sha256","analysis_sha256","model_sha256","semantic_model_sha256","proxy_sha256","proxy_size","inference","image","faces"])
        || !integer(&s["width"],1,MAX_DIMENSION) || !integer(&s["height"],1,MAX_DIMENSION)
        || s["orientation"]!="exif_normalized_once" || s["mapping"]!="source_edge_pixels"
        || s["inference"]!="fresh_whole_frame_display_proxy" || s["source_sha256"]!=b["uncropped_sha256"]
        || ["source_sha256","analysis_sha256","model_sha256","semantic_model_sha256","proxy_sha256"].iter().any(|k|!hash(&s[*k]))
        || !image(&s["image"]) || s["image"]["source_width"]!=s["width"] || s["image"]["source_height"]!=s["height"]
        || n(&v["before"]["source_width"])>n(&s["width"]) || n(&v["before"]["source_height"])>n(&s["height"])
        || !same(&s["proxy_size"],&json!([s["image"]["width"],s["image"]["height"]])) || !source_proof(&b["source_proof"],b,s) {return false;}
    let Some(faces)=s["faces"].as_array().filter(|f|f.len()<=128) else{return false;};
    let mut ids=HashSet::new(); let w=n(&s["width"]);let h=n(&s["height"]);
    faces.iter().all(|f| fields(f,&["face_id","landmarks_sha256","bbox","chin_proposal","center_proposal"])
        && token(&f["face_id"]) && ids.insert(f["face_id"].as_str().unwrap()) && hash(&f["landmarks_sha256"])
        && f["face_id"].as_str()==Some(format!("face:{}",f["landmarks_sha256"].as_str().unwrap()).as_str())
        && point(&f["chin_proposal"],w,h) && point(&f["center_proposal"],w,h)
        && f["bbox"].as_array().is_some_and(|a|a.len()==4 && bounded(&a[0],0.,w) && bounded(&a[1],0.,h)
            && bounded(&a[2],0.,w) && bounded(&a[3],0.,h) && n(&a[0])<n(&a[2]) && n(&a[1])<n(&a[3])))
}
/// Retain the existing cropped-before image identity separately from the complete
/// uncropped edited source used for measurements. Never substitute one for the other.
pub(crate) fn current_proof(v:&Value)->Value {
    let mut source=Map::new();
    if let Some(fields)=v["source"].as_object() {for (key,value) in fields {
        source.insert(key.clone(),if key=="image" {image_proof(value)}else{value.clone()});
    }}
    json!({"session_id":v["session_id"],"capture_sha256":v["capture_sha256"],"binding":v["binding"],
        "source":Value::Object(source),"before":image_proof(&v["before"])})
}
pub(crate) fn preview_request(req:&Request,current:&Value)->bool {
    let v=&req.envelope; let s=&current["source"];
    req.action=="preview" && v["session_id"]==current["session_id"] && v["capture_sha256"]==current["capture_sha256"]
        && v["anchor_review"]["image_sha256"]==s["image"]["sha256"] && anchors(&v["anchors"],n(&s["width"]),n(&s["height"]))
        && s["faces"].as_array().is_some_and(|faces|faces.iter().any(|f|f["face_id"]==v["face_id"]))
}
fn near(a:f64,b:f64)->bool {a.is_finite() && b.is_finite() && (a-b).abs()<=1e-9*a.abs().max(b.abs()).max(1.)}
fn vector(v:&Value,len:usize)->bool {v.as_array().is_some_and(|a|a.len()==len && a.iter().all(|v|n(v).is_finite()))}
fn measure(v:&Value,achieved:bool)->bool {
    let mut keys=vec!["aspect_ratio","headroom_fraction","head_fraction","horizontal_position","vertical_position"];
    if achieved {keys.push("head_height_pixels");}
    fields(v,&keys) && keys.iter().all(|k|n(&v[*k]).is_finite())
}
fn rounded(value:f64)->f64 {let floor=value.floor();let delta=value-floor;if delta<0.5 || delta==0.5 && floor%2.==0. {floor}else{floor+1.}}
pub(crate) fn preview(v:&Value,req:&Request,current:&Value)->bool {
    if !preview_request(req,current) || !fields(v,&["preview_token","capture_sha256","candidate_sha256","preview_request_id","plan","before","after"])
        || !token(&v["preview_token"]) || !hash(&v["candidate_sha256"]) || v["capture_sha256"]!=current["capture_sha256"]
        || v["preview_request_id"]!=req.id || !image(&v["before"]) || !image(&v["after"])
        || !same(&image_proof(&v["before"]),&current["before"]) {return false;}
    let p=&v["plan"];let a=&req.envelope["anchors"];let rules=&req.envelope["rules"];
    let w=n(&current["source"]["width"]);let h=n(&current["source"]["height"]);
    if !fields(p,&["version","convention","operation_id","rotation_degrees","source_size","anchors","rules","continuous_rect_pixels","rect_normalized","pixel_bounds","output_size","requested","achieved","is_full_frame","backend"])
        || p["version"]!=1 || p["convention"]!="lrt.portrait-crop.source-edge-pixels.v1" || p["operation_id"]!="lnx.crop.v1"
        || n(&p["rotation_degrees"])!=0. || p["backend"]!="rust-portrait-crop-v1"
        || !same(&p["source_size"],&json!([w,h])) || !same(&p["anchors"],a) || !same(&p["rules"],rules)
        || !measure(&p["requested"],false) || !measure(&p["achieved"],true)
        || !vector(&p["continuous_rect_pixels"],4) || !vector(&p["rect_normalized"],4) || !vector(&p["pixel_bounds"],4) || !vector(&p["output_size"],2) {return false;}
    let r=&p["pixel_bounds"];let c=&p["continuous_rect_pixels"];let normalized=&p["rect_normalized"];
    if !(0..4).all(|i|integer(&r[i],0,MAX_DIMENSION)) {return false;}
    let l=n(&r[0]);let t=n(&r[1]);let right=n(&r[2]);let bottom=n(&r[3]);let cw=right-l;let ch=bottom-t;
    if l<0. || t<0. || right>w || bottom>h || cw<=0. || ch<=0. || !same(&p["output_size"],&json!([cw,ch]))
        || n(&v["after"]["source_width"])!=cw || n(&v["after"]["source_height"])!=ch
        || !(0..4).all(|i|n(&normalized[i])==n(&r[i]) / if i%2==0 {w}else{h}) {return false;}
    let head=n(&a["chin"][1])-n(&a["crown"][1]);let ideal_h=head/n(&rules["head_fraction"]);let ideal_w=ideal_h*n(&rules["aspect_ratio"]);
    let top=n(&a["crown"][1])-n(&rules["headroom_fraction"])*ideal_h;
    let left=n(&a["face_center"][0])-n(&rules["horizontal_position"])*ideal_w;
    let expected=[left,top,left+ideal_w,top+ideal_h];
    if expected.iter().any(|v|!v.is_finite()) || expected[0]<0. || expected[1]<0. || expected[2]>w || expected[3]>h
        || !(0..4).all(|i|{let dim=if i%2==0 {w}else{h};near(n(&c[i]),expected[i]) && n(&r[i])==rounded(n(&c[i])/dim*dim)})
        || ["crown","chin","face_center"].iter().any(|key| {let x=n(&a[*key][0]);let y=n(&a[*key][1]);x<l || x>right || y<t || y>bottom || x<expected[0] || x>expected[2] || y<expected[1] || y>expected[3]}) {return false;}
    let achieved=&p["achieved"];let requested=&p["requested"];
    let expected_measures=[("aspect_ratio",cw/ch),("headroom_fraction",(n(&a["crown"][1])-t)/ch),("head_fraction",head/ch),
        ("horizontal_position",(n(&a["face_center"][0])-l)/cw),("vertical_position",(n(&a["face_center"][1])-t)/ch),("head_height_pixels",head)];
    expected_measures.iter().all(|(k,v)|near(n(&achieved[*k]),*v))
        && ["aspect_ratio","headroom_fraction","head_fraction","horizontal_position"].iter().all(|k|near(n(&requested[*k]),n(&rules[*k])))
        && near(n(&requested["vertical_position"]),(n(&a["face_center"][1])-top)/ideal_h)
        && p["is_full_frame"].as_bool()==Some(l==0. && t==0. && right==w && bottom==h)
}
pub(crate) fn apply_matches(req:&Request,preview:&Value,current:&Value)->bool {
    let v=&req.envelope;
    req.apply() && v["session_id"]==current["session_id"] && v["capture_sha256"]==current["capture_sha256"]
        && ["capture_sha256","preview_request_id","preview_token","candidate_sha256"].iter().all(|k|v[*k]==preview[*k])
        && v["before_image_sha256"]==preview["before"]["sha256"] && v["after_image_sha256"]==preview["after"]["sha256"]
        && v["review"]=="full_before_after_confirmed"
}
pub(crate) fn phase(v:&Value)->&str {v["phase"].as_str().unwrap_or("")}
pub(crate) fn terminal(v:&Value)->bool {matches!(phase(v),"capability"|"current_ready"|"ready"|"committed"|"cancelled"|"rejected")}
const BASE:[&str;7]=["event","version","request_id","action","command_sha256","original_request","phase"];
fn receipt_fields(v:&Value,extra:&[&str],optional:&[&str])->bool {let mut keys=BASE.to_vec();keys.extend_from_slice(extra);allowed(v,&keys,optional)}
/// The first genuine server digest is pinned only together with the complete
/// echoed request. Do not compute Python canonical JSON from Rust floats.
pub(crate) fn base_receipt(v:&Value,req:&Request,pinned:Option<&str>)->bool {
    v["event"]==EVENT && v["version"]==1 && v["request_id"]==req.id && v["action"]==req.action
        && hash(&v["command_sha256"]) && pinned.map_or(true,|h|v["command_sha256"].as_str()==Some(h))
        && same(&v["original_request"],&req.envelope) && size(v,RESULT_BYTES).is_ok()
}
pub(crate) fn valid_result(v:&Value,req:&Request,pinned:Option<&str>,current:Option<&Value>)->bool {
    if !base_receipt(v,req,pinned) {return false;}
    let text=||["message","error"].iter().all(|k|v.get(*k).map_or(true,message));
    match phase(v) {
        "working"=>req.read() && receipt_fields(v,&["no_write"],&[]) && v["no_write"]==true,
        "rejected"|"cancelled"=>receipt_fields(v,&["no_write"],&["message","error","released_read"])
            && v["no_write"]==true && text() && v.get("released_read").map_or(true,|b|req.read() && b==true)
            && (phase(v)!="cancelled" || req.read() || req.action=="cancel"),
        "unknown"=>matches!(req.action.as_str(),"apply"|"status") && receipt_fields(v,&["outcome_unknown","original_request_id"],&["message","error"])
            && v["outcome_unknown"]==true && text() && v["original_request_id"]==if req.action=="status" {req.envelope["target_request_id"].clone()}else{json!(req.id)},
        "capability"=>req.action=="capability" && receipt_fields(v,&["capability"],&[]) && capability(&v["capability"]),
        "current_ready"=>req.action=="current" && receipt_fields(v,&["current"],&[]) && self::current(&v["current"]),
        "ready"=>req.action=="preview" && receipt_fields(v,&["preview"],&[]) && current.is_some_and(|c|preview(&v["preview"],req,c)),
        "committed"=>req.apply() && receipt_fields(v,&["result","preview_token","candidate_sha256","original_request_id","recovered"],&[])
            && v["original_request_id"]==req.id && v["preview_token"]==req.envelope["preview_token"]
            && v["candidate_sha256"]==req.envelope["candidate_sha256"] && v["recovered"].is_boolean()
            && fields(&v["result"],&["status","document_id","revision"])
            && matches!(v["result"]["status"].as_str(),Some("applied"|"no_change")) && revision(&v["result"]["revision"])
            && current.is_some_and(|c|v["result"]["document_id"]==c["binding"]["document_id"] && commit_revision(&v["result"],c,&v["candidate_sha256"])),
        "status"=>req.action=="status" && receipt_fields(v,&["receipt"],&[]) && v["receipt"].is_object(),
        _=>false,
    }
}

#[cfg(test)]
#[path = "portrait_crop_protocol_unrun.rs"]
mod unrun;
