//! LRCP v1 framing for a complete, identified proxy display capture.
pub const HEADER_BYTES:usize=128;
pub const MAX_PAYLOAD:usize=128*1024*1024;
#[derive(Clone,Debug,PartialEq,Eq)]
pub struct Identity {
    pub epoch:[u8;16],pub instance:[u8;16],pub capture:[u8;16],
    pub seq:u64,pub generation:u64,pub document:u64,pub ticket:u64,
    pub width:u32,pub height:u32,pub presentation_width:u32,pub presentation_height:u32,
}
impl Identity {
    pub fn payload_len(&self)->Result<usize,&'static str>{
        if self.epoch==[0;16]||self.instance==[0;16]||self.capture==[0;16]||
            self.seq==0||self.generation==0||self.document==0||self.ticket==0||
            self.width==0||self.height==0||self.presentation_width==0||self.presentation_height==0 {
            return Err("zero capture identity or geometry");
        }
        let n=(self.width as usize).checked_mul(self.height as usize).and_then(|v|v.checked_mul(4))
            .ok_or("capture dimensions overflow")?;
        if n>MAX_PAYLOAD{return Err("capture exceeds 128 MiB budget");}
        Ok(n)
    }
    pub fn header(&self)->Result<[u8;HEADER_BYTES],&'static str>{
        let n=self.payload_len()?;let mut h=[0u8;HEADER_BYTES];
        h[..4].copy_from_slice(b"LRCP");h[4..6].copy_from_slice(&1u16.to_le_bytes());
        h[6..8].copy_from_slice(&(HEADER_BYTES as u16).to_le_bytes());
        h[8..24].copy_from_slice(&self.epoch);h[24..40].copy_from_slice(&self.instance);h[40..56].copy_from_slice(&self.capture);
        for (offset,value) in [(56,self.seq),(64,self.generation),(72,self.document),(80,self.ticket),(104,n as u64)] {
            h[offset..offset+8].copy_from_slice(&value.to_le_bytes());
        }
        for (offset,value) in [(88,self.width),(92,self.height),(96,self.presentation_width),(100,self.presentation_height)] {
            h[offset..offset+4].copy_from_slice(&value.to_le_bytes());
        }
        Ok(h)
    }
}
#[cfg(test)]
mod tests {
    use super::*;
    fn identity()->Identity{Identity{epoch:std::array::from_fn(|i|(i+1)as u8),
        instance:std::array::from_fn(|i|(i+17)as u8),capture:std::array::from_fn(|i|(i+33)as u8),
        seq:9007199254740993,generation:17,document:123,ticket:22,width:1,height:1,presentation_width:1,presentation_height:1}}
    #[test] fn golden_header_preserves_large_ids_and_reserved_zeroes(){
        let text=include_str!("../../../docs/protocols/color-capture-v1.hex").trim();
        let expected=(0..text.len()).step_by(2).map(|i|u8::from_str_radix(&text[i..i+2],16).unwrap()).collect::<Vec<_>>();
        assert_eq!(identity().header().unwrap().as_slice(),&expected[..HEADER_BYTES]);
        assert_eq!(&expected[HEADER_BYTES..],&[10,20,30,255]);
    }
    #[test] fn rejects_invalid_ids_overflow_and_payload_budget(){
        let mut id=identity();id.seq=0;assert!(id.header().is_err());
        id=identity();id.width=u32::MAX;id.height=u32::MAX;assert!(id.header().is_err());
        id=identity();id.width=MAX_PAYLOAD as u32/4+1;assert!(id.header().is_err());
    }
}
