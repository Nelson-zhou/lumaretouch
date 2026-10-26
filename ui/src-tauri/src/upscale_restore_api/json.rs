// SPDX-License-Identifier: GPL-3.0-or-later
//! Bounded, duplicate-key rejecting transport primitives. No image operations.
use std::{fmt, io::{self, Write}};
use serde::{de::{self, MapAccess, SeqAccess, Visitor}, Deserialize, Deserializer};
use serde_json::{json, Map, Number, Value};
use sha2::{Digest, Sha256};

pub(super) fn fields(v: &Value, keys: &[&str]) -> bool {
    v.as_object().is_some_and(|o| o.len() == keys.len() && keys.iter().all(|k| o.contains_key(*k)))
}
pub(super) fn token(v: &Value) -> bool {
    v.as_str().is_some_and(|s| !s.is_empty() && s.len() <= 128
        && s.bytes().all(|b| b.is_ascii_alphanumeric() || b == b'_' || b == b'-'))
}
pub(super) fn hash(v: &Value) -> bool {
    v.as_str().is_some_and(|s| s.len() == 64 && s.bytes().all(|b| b.is_ascii_digit() || (b'a'..=b'f').contains(&b)))
}
pub(super) fn integer(v: &Value, lo: u64, hi: u64) -> bool { v.as_u64().is_some_and(|n| (lo..=hi).contains(&n)) }
pub(super) fn number(v: &Value) -> f64 { v.as_f64().unwrap_or(f64::NAN) }
pub(super) fn bounded(v: &Value, lo: f64, hi: f64) -> bool { let n = number(v); n.is_finite() && (lo..=hi).contains(&n) }
pub(super) fn message(v: &Value) -> bool { v.as_str().is_some_and(|s| s.encode_utf16().count() <= 4096 && !s.contains('\0')) }
pub(super) fn revision(v: &Value) -> bool {
    v.as_str().is_some_and(|s| !s.is_empty() && s.len() <= 20 && (s == "0" || !s.starts_with('0'))
        && s.bytes().all(|c| c.is_ascii_digit()) && s.parse::<u64>().is_ok())
}
pub(super) fn digest(bytes: &[u8]) -> String { format!("{:x}", Sha256::digest(bytes)) }
pub(super) fn same(a: &Value, b: &Value) -> bool {
    match (a, b) {
        (Value::Number(a), Value::Number(b)) => a.as_f64() == b.as_f64(),
        (Value::Array(a), Value::Array(b)) => a.len() == b.len() && a.iter().zip(b).all(|(a,b)| same(a,b)),
        (Value::Object(a), Value::Object(b)) => a.len() == b.len() && a.iter().all(|(k,a)| b.get(k).is_some_and(|b| same(a,b))),
        _ => a == b,
    }
}
pub(super) fn size(v: &Value, limit: usize) -> Result<usize, String> {
    struct Count { bytes: usize, limit: usize }
    impl Write for Count {
        fn write(&mut self, bytes: &[u8]) -> io::Result<usize> {
            self.bytes = self.bytes.checked_add(bytes.len()).ok_or_else(|| io::Error::new(io::ErrorKind::InvalidData, "size overflow"))?;
            if self.bytes > self.limit { return Err(io::Error::new(io::ErrorKind::InvalidData, "size limit")); }
            Ok(bytes.len())
        }
        fn flush(&mut self) -> io::Result<()> { Ok(()) }
    }
    let mut count = Count { bytes: 0, limit };
    serde_json::to_writer(&mut count, v).map_err(|_| "AI 超清数据超过安全字节上限".to_string())?;
    Ok(count.bytes)
}
struct Unique(Value);
impl<'de> Deserialize<'de> for Unique {
    fn deserialize<D: Deserializer<'de>>(d: D) -> Result<Self, D::Error> {
        struct V;
        impl<'de> Visitor<'de> for V {
            type Value = Unique;
            fn expecting(&self, f: &mut fmt::Formatter) -> fmt::Result { f.write_str("finite JSON without duplicate object keys") }
            fn visit_bool<E: de::Error>(self, v: bool) -> Result<Unique,E> { Ok(Unique(json!(v))) }
            fn visit_i64<E: de::Error>(self, v: i64) -> Result<Unique,E> { Ok(Unique(json!(v))) }
            fn visit_u64<E: de::Error>(self, v: u64) -> Result<Unique,E> { Ok(Unique(json!(v))) }
            fn visit_f64<E: de::Error>(self, v: f64) -> Result<Unique,E> { Number::from_f64(v).map(|n| Unique(Value::Number(n))).ok_or_else(|| E::custom("non-finite number")) }
            fn visit_str<E: de::Error>(self, v: &str) -> Result<Unique,E> { Ok(Unique(Value::String(v.into()))) }
            fn visit_string<E: de::Error>(self, v: String) -> Result<Unique,E> { Ok(Unique(Value::String(v))) }
            fn visit_none<E: de::Error>(self) -> Result<Unique,E> { Ok(Unique(Value::Null)) }
            fn visit_unit<E: de::Error>(self) -> Result<Unique,E> { Ok(Unique(Value::Null)) }
            fn visit_seq<A: SeqAccess<'de>>(self, mut seq: A) -> Result<Unique,A::Error> {
                let mut values = Vec::new();
                while let Some(Unique(v)) = seq.next_element::<Unique>()? { values.push(v); }
                Ok(Unique(Value::Array(values)))
            }
            fn visit_map<A: MapAccess<'de>>(self, mut map: A) -> Result<Unique,A::Error> {
                let mut values = Map::new();
                while let Some(k) = map.next_key::<String>()? {
                    if values.contains_key(&k) { return Err(de::Error::custom("duplicate JSON field")); }
                    let Unique(v) = map.next_value::<Unique>()?; values.insert(k, v);
                }
                Ok(Unique(Value::Object(values)))
            }
        }
        d.deserialize_any(V)
    }
}
pub(super) fn unique_json(raw: &str, cap: usize) -> Result<Value,String> {
    if raw.len() > cap { return Err("AI 超清 JSON 超过安全上限".into()); }
    let mut parser = serde_json::Deserializer::from_str(raw);
    let value = Unique::deserialize(&mut parser).map_err(|_| "AI 超清 JSON 含重复字段、非法数字或结构".to_string())?.0;
    parser.end().map_err(|_| "AI 超清 JSON 含尾部内容".to_string())?;
    Ok(value)
}
