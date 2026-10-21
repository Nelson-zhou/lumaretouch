//! Optional per-slot geometry. Parsed while the same flock protects the pixels.
#[derive(Debug,Clone,Copy,PartialEq,Eq)]
pub struct Presentation {pub document:u64,pub width:u32,pub height:u32,pub geometry:u64,pub kind:u32}
impl Presentation {
    pub fn parse(bytes:&[u8])->Result<Option<Self>,String>{
        if bytes.len()!=36{return Err("presentation metadata length".into());}
        if &bytes[..4]!=b"LPR1"{return Ok(None);}
        let u32at=|n|u32::from_le_bytes(bytes[n..n+4].try_into().unwrap());
        let u64at=|n|u64::from_le_bytes(bytes[n..n+8].try_into().unwrap());
        let p=Self{document:u64at(4),width:u32at(12),height:u32at(16),geometry:u64at(20),kind:u32at(28)};
        if p.width==0||p.height==0||p.geometry==0||!(1..=4).contains(&p.kind)||
            (p.document==0&&p.kind!=4)||u32at(32)!=0{return Err("invalid presentation metadata".into());}
        Ok(Some(p))
    }
    pub fn encode(&self)->[u8;36]{
        let mut b=[0;36];b[..4].copy_from_slice(b"LPR1");b[4..12].copy_from_slice(&self.document.to_le_bytes());
        b[12..16].copy_from_slice(&self.width.to_le_bytes());b[16..20].copy_from_slice(&self.height.to_le_bytes());
        b[20..28].copy_from_slice(&self.geometry.to_le_bytes());b[28..32].copy_from_slice(&self.kind.to_le_bytes());b
    }
}
#[cfg(test)] mod tests {
    use super::*;
    #[test] fn legacy_is_display_only_and_known_invalid_is_rejected(){
        assert_eq!(Presentation::parse(&[0;36]).unwrap(),None);
        let mut b=[0;36];b[..4].copy_from_slice(b"LPR1");assert!(Presentation::parse(&b).is_err());
    }
    #[test] fn identity_and_aspect_survive_without_float_conversion(){
        let p=Presentation{document:9007199254740993,width:4000,height:4000,geometry:u64::MAX,kind:1};
        assert_eq!(Presentation::parse(&p.encode()).unwrap(),Some(p));
        let mut b=p.encode();b[32]=1;assert!(Presentation::parse(&b).is_err());
    }
}
