//! Optional immutable mapping identity in the reserved bytes of the locking-v2 header.
//! Older all-zero headers remain display-only. Identity-dependent tools require LRI1.
pub const TAG:&[u8;4]=b"LRI1";
pub fn parse(bytes:&[u8])->Option<[u8;16]>{
    if bytes.len()!=32 || &bytes[..4]!=TAG || bytes[20..].iter().any(|b|*b!=0){return None;}
    let id:[u8;16]=bytes[4..20].try_into().ok()?;
    if id==[0;16]{None}else{Some(id)}
}
pub fn hex(id:[u8;16])->String{id.iter().map(|b|format!("{b:02x}")).collect()}
#[cfg(test)]
mod tests {
    use super::*;
    #[test] fn legacy_or_unknown_extension_is_not_identity_capable(){
        assert_eq!(parse(&[0;32]),None);assert_eq!(parse(b"LRI1"),None);
        let mut bytes=[0;32];bytes[..4].copy_from_slice(TAG);assert_eq!(parse(&bytes),None);
        bytes[4]=1;assert!(parse(&bytes).is_some());bytes[31]=1;assert_eq!(parse(&bytes),None);
    }
    #[test] fn identity_and_canonical_hex_are_exact(){
        let mut bytes=[0;32];bytes[..4].copy_from_slice(TAG);
        for i in 0..16{bytes[4+i]=i as u8;}
        assert_eq!(hex(parse(&bytes).unwrap()),"000102030405060708090a0b0c0d0e0f");
    }
}
