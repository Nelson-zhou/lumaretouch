//! LCS1: magic + little-endian u32 count + count opaque RGB f32 triplets.
use crate::scopes::{Scopes, MAX_SAMPLES};
pub const MAX_BYTES: usize = 8 + MAX_SAMPLES * 12;
pub fn decode(bytes: &[u8]) -> Result<Scopes, &'static str> {
    if bytes.len()<8 || &bytes[..4]!=b"LCS1" {return Err("invalid colour-scope header");}
    let count=u32::from_le_bytes(bytes[4..8].try_into().unwrap()) as usize;
    if count==0 || count>MAX_SAMPLES {return Err("invalid colour sample count");}
    let expected=count.checked_mul(12).and_then(|n|n.checked_add(8)).ok_or("sample size overflow")?;
    if bytes.len()!=expected {return Err("truncated or trailing colour sample bytes");}
    let mut result=Scopes::new();
    for pixel in bytes[8..].chunks_exact(12) {
        result.add(std::array::from_fn(|i|f32::from_le_bytes(pixel[i*4..i*4+4].try_into().unwrap()) as f64))?;
    }
    Ok(result)
}
#[cfg(test)]
mod tests {
    use super::*;
    #[test] fn wire_rejects_empty_truncated_trailing_and_unbounded_payloads() {
        assert!(decode(b"LCS1").is_err());
        let mut b=b"LCS1".to_vec();b.extend(1u32.to_le_bytes());
        assert!(decode(&b).is_err());b.extend([0u8;12]);assert!(decode(&b).is_ok());
        b.push(0);assert!(decode(&b).is_err());
        b[4..8].copy_from_slice(&((MAX_SAMPLES+1) as u32).to_le_bytes());assert!(decode(&b).is_err());
    }
}
