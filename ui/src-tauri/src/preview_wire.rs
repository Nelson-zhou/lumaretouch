//! LRF1: a versioned complete/dirty preview transport header, independent of UI.
use crate::frame_presentation::Presentation;
pub const HEADER_BYTES:usize=128;
pub struct Header {pub seq:u64,pub emitted:u64,pub pulled:u64,pub width:u32,pub height:u32,
    pub payload:u32,pub y0:u32,pub instance:Option<[u8;16]>,pub presentation:Option<Presentation>}
impl Header {
    pub fn encode(&self)->Result<[u8;HEADER_BYTES],String>{
        let stride=self.width as u64*4;
        if self.width==0||self.height==0||self.seq==0||self.y0>=self.height||
            (self.payload as u64)%stride!=0||self.payload as u64>stride*(self.height-self.y0)as u64 {
            return Err("invalid preview frame dimensions/payload".into());
        }
        let mut b=[0;HEADER_BYTES];b[..4].copy_from_slice(b"LRF1");b[4..6].copy_from_slice(&1u16.to_le_bytes());
        b[6..8].copy_from_slice(&(HEADER_BYTES as u16).to_le_bytes());
        for (offset,value) in [(8,self.seq),(16,self.emitted),(24,self.pulled)] {b[offset..offset+8].copy_from_slice(&value.to_le_bytes());}
        for (offset,value) in [(32,self.width),(36,self.height),(40,self.payload),(44,self.y0)] {b[offset..offset+4].copy_from_slice(&value.to_le_bytes());}
        if let Some(id)=self.instance {b[48..64].copy_from_slice(&id);}
        if let Some(p)=self.presentation {let metadata=p.encode();Presentation::parse(&metadata)?;b[64..100].copy_from_slice(&metadata);}
        Ok(b)
    }
}
#[cfg(test)] mod tests {
    use super::*;
    fn header()->Header{Header{seq:9007199254740993,emitted:2,pulled:3,width:2,height:2,payload:16,y0:0,
        instance:Some([1;16]),presentation:Some(Presentation{document:4,width:4000,height:4000,geometry:5,kind:1})}}
    #[test] fn preserves_frame_bound_aspect_and_integer_identity(){let b=header().encode().unwrap();
        assert_eq!(&b[..4],b"LRF1");assert_eq!(u64::from_le_bytes(b[8..16].try_into().unwrap()),9007199254740993);
        assert_eq!(Presentation::parse(&b[64..100]).unwrap().unwrap().width,4000);assert!(b[100..].iter().all(|v|*v==0));
        let text=include_str!("../../../docs/protocols/preview-frame-v1.hex").trim();
        let expected=(0..text.len()).step_by(2).map(|i|u8::from_str_radix(&text[i..i+2],16).unwrap()).collect::<Vec<_>>();
        assert_eq!(&b[..],&expected[..128]);}
    #[test] fn rejects_partial_rows_and_outside_image_payload(){let mut h=header();h.payload=15;assert!(h.encode().is_err());
        h.payload=16;h.y0=1;assert!(h.encode().is_err());h.payload=8;assert!(h.encode().is_ok());h.payload=0;assert!(h.encode().is_ok());}
}
