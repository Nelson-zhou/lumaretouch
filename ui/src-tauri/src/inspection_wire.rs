//! Independent full-source patch envelope. Pure parsing only: SHM ownership,
//! resource leases and the application's delivery/ack lifecycle are not wired yet.
#[path = "refinement.rs"]
pub mod refinement;
use refinement::{Budget, Request, Roi, Ticket};

pub const HEADER_BYTES: usize = 128;
const MAGIC: &[u8;4] = b"LRIF";
const RGBA8: u32 = 0x41424752;

#[derive(Debug, PartialEq, Eq)]
pub struct Header {
    pub epoch: [u8;16],
    pub ticket: Ticket,
    pub canvas_width:u64, pub canvas_height:u64,
    pub roi:Roi, pub payload_bytes:usize,
    pub decoded_bits:u16, pub source_bits:Option<u16>,
}

/// Call with only the fixed header BEFORE allocating/mapping the payload.
/// expected/budget must come from the host's admitted request, never UI assertions.
pub fn parse_header(bytes:&[u8], epoch:[u8;16], expected:&Request,
                    budget:&Budget, max_payload:u64)->Result<Header,&'static str>{
    if bytes.len()!=HEADER_BYTES {return Err("inspection header length mismatch");}
    let u16_at=|p|u16::from_le_bytes(bytes[p..p+2].try_into().unwrap());
    let u32_at=|p|u32::from_le_bytes(bytes[p..p+4].try_into().unwrap());
    let u64_at=|p|u64::from_le_bytes(bytes[p..p+8].try_into().unwrap());
    if &bytes[..4]!=MAGIC || u16_at(4)!=1 || u16_at(6)!=128 {
        return Err("inspection protocol mismatch");
    }
    if epoch==[0;16] || bytes[8..24]!=epoch {return Err("inspection engine epoch mismatch");}
    if u32_at(96)!=RGBA8 || u16_at(100)!=1 || u16_at(102)!=1 || bytes[108..].iter().any(|b|*b!=0) {
        return Err("inspection format/profile/quality/reserved mismatch");
    }
    let decoded_bits=u16_at(104); let source=u16_at(106);
    if ![8,16,32].contains(&decoded_bits) || source>32 {
        return Err("inspection precision metadata invalid");
    }
    let ticket=Ticket{id:u64_at(24),document:u64_at(32),source_generation:u64_at(40),
        recipe:u64_at(48),viewport:u64_at(56)};
    let canvas_width=u32_at(64) as u64; let canvas_height=u32_at(68) as u64;
    let roi=Roi{x:u32_at(72) as u64,y:u32_at(76) as u64,
        width:u32_at(80) as u64,height:u32_at(84) as u64};
    if ticket!=expected.ticket || canvas_width!=expected.canvas_width ||
       canvas_height!=expected.canvas_height || roi!=expected.roi {
        return Err("inspection identity/canvas/ROI mismatch");
    }
    expected.validate(budget)?;
    let payload=u64_at(88);
    if payload!=expected.rgba_bytes()? || payload>max_payload {
        return Err("inspection payload exceeds layout or budget");
    }
    let total=payload.checked_add(HEADER_BYTES as u64).ok_or("inspection total size overflow")?;
    if total>isize::MAX as u64 {return Err("inspection payload exceeds addressable allocation");}
    let payload_bytes=usize::try_from(payload).map_err(|_|"inspection payload usize overflow")?;
    Ok(Header{epoch,ticket,canvas_width,canvas_height,roi,payload_bytes,
        decoded_bits,source_bits:if source==0{None}else{Some(source)}})
}

/// Borrow validated pixels without allocating. Readers must keep ownership/lock
/// through this call and re-check the desired generation before publishing.
pub fn parse_packet<'a>(bytes:&'a [u8], epoch:[u8;16], expected:&Request,
                       budget:&Budget,max_payload:u64)->Result<(Header,&'a [u8]),&'static str>{
    let prefix=bytes.get(..HEADER_BYTES).ok_or("inspection header truncated")?;
    let header=parse_header(prefix,epoch,expected,budget,max_payload)?;
    if bytes.len()!=HEADER_BYTES+header.payload_bytes {return Err("inspection packet length mismatch");}
    let pixels=&bytes[HEADER_BYTES..];
    if pixels.chunks_exact(4).any(|p|p[3]!=255){return Err("inspection RGBA must be opaque");}
    Ok((header,pixels))
}

#[cfg(test)]
mod tests {
    use super::*;
    fn request()->Request {Request{ticket:Ticket{id:9007199254740993,document:2,
        source_generation:3,recipe:4,viewport:5},source_width:10,source_height:10,
        canvas_width:10,canvas_height:10,roi:Roi{x:1,y:2,width:2,height:1},estimated_live_bytes:1000}}
    fn budget()->Budget {Budget{source_pixels:100,patch_pixels:2,live_bytes:1000}}
    fn packet()->Vec<u8>{
        let mut p=vec![0u8;136];p[..4].copy_from_slice(MAGIC);
        p[4..6].copy_from_slice(&1u16.to_le_bytes());p[6..8].copy_from_slice(&128u16.to_le_bytes());
        p[8..24].copy_from_slice(&[7;16]);
        for (i,n) in [9007199254740993u64,2,3,4,5].iter().enumerate(){p[24+i*8..32+i*8].copy_from_slice(&n.to_le_bytes());}
        for (i,n) in [10u32,10,1,2,2,1].iter().enumerate(){p[64+i*4..68+i*4].copy_from_slice(&n.to_le_bytes());}
        p[88..96].copy_from_slice(&8u64.to_le_bytes());p[96..100].copy_from_slice(&RGBA8.to_le_bytes());
        p[100..102].copy_from_slice(&1u16.to_le_bytes());p[102..104].copy_from_slice(&1u16.to_le_bytes());
        p[104..106].copy_from_slice(&16u16.to_le_bytes());p[128..].copy_from_slice(&[1,2,3,255,4,5,6,255]);p
    }
    #[test] fn matches_shared_python_rust_golden_vector(){
        let hex=include_str!("../../../core/inspection/packet-v1.hex").trim();
        let bytes:Vec<u8>=(0..hex.len()).step_by(2).map(|i|u8::from_str_radix(&hex[i..i+2],16).unwrap()).collect();
        assert_eq!(bytes,packet());
        assert!(parse_packet(&bytes,[7;16],&request(),&budget(),8).is_ok());
    }
    #[test] fn preserves_large_identity_and_borrows_pixels(){
        let p=packet();let (h,px)=parse_packet(&p,[7;16],&request(),&budget(),8).unwrap();
        assert_eq!(h.ticket.id,9007199254740993);assert_eq!(h.source_bits,None);
        assert_eq!(px,&[1,2,3,255,4,5,6,255]);assert_eq!(px.as_ptr(),p[128..].as_ptr());
    }
    #[test] fn canonical_float_source_precision_is_not_original_precision(){
        let mut p=packet();p[104..106].copy_from_slice(&32u16.to_le_bytes());
        let (h,_)=parse_packet(&p,[7;16],&request(),&budget(),8).unwrap();
        assert_eq!(h.decoded_bits,32);assert_eq!(h.source_bits,None);
    }
    #[test] fn rejects_short_extra_and_truncated_payload(){
        let p=packet();for n in [0,127,128,135]{assert!(parse_packet(&p[..n],[7;16],&request(),&budget(),8).is_err());}
        let mut p=packet();p.push(0);assert!(parse_packet(&p,[7;16],&request(),&budget(),8).is_err());
    }
    #[test] fn rejects_every_identity_and_layout_field_mismatch(){
        for offset in [8,24,32,40,48,56,64,68,72,76,80,84,88]{
            let mut p=packet();p[offset]^=1;assert!(parse_packet(&p,[7;16],&request(),&budget(),8).is_err(),"offset {offset}");
        }
    }
    #[test] fn rejects_unknown_enums_reserved_and_precision(){
        for offset in [0,4,6,96,100,102,108,127]{let mut p=packet();p[offset]^=2;
            assert!(parse_packet(&p,[7;16],&request(),&budget(),8).is_err());}
        let mut p=packet();p[104]=12;assert!(parse_packet(&p,[7;16],&request(),&budget(),8).is_err());
        p=packet();p[106]=33;assert!(parse_packet(&p,[7;16],&request(),&budget(),8).is_err());
    }
    #[test] fn checked_pixel_multiplication_cannot_wrap(){
        let mut r=request();r.canvas_width=u32::MAX as u64;r.canvas_height=u32::MAX as u64;
        r.roi=Roi{x:0,y:0,width:u32::MAX as u64,height:u32::MAX as u64};
        let b=Budget{source_pixels:100,patch_pixels:u64::MAX,live_bytes:1000};
        let mut p=packet();
        for (i,n) in [u32::MAX,u32::MAX,0,0,u32::MAX,u32::MAX].iter().enumerate(){
            p[64+i*4..68+i*4].copy_from_slice(&n.to_le_bytes());
        }
        assert_eq!(parse_header(&p[..128],[7;16],&r,&b,u64::MAX).unwrap_err(),"patch size overflow");
    }
    #[test] fn header_only_and_known_precision_do_not_require_payload(){
        let mut p=packet();p[106]=12;
        let h=parse_header(&p[..128],[7;16],&request(),&budget(),8).unwrap();
        assert_eq!(h.source_bits,Some(12));
        for b in [Budget{source_pixels:100,patch_pixels:1,live_bytes:1000},
                  Budget{source_pixels:100,patch_pixels:2,live_bytes:999}]{
            assert!(parse_header(&p[..128],[7;16],&request(),&b,8).is_err());
        }
    }
    #[test] fn admission_and_opacity_are_required(){
        assert!(parse_header(&packet()[..128],[7;16],&request(),&budget(),7).is_err());
        assert!(parse_header(&packet()[..128],[0;16],&request(),&budget(),8).is_err());
        let mut p=packet();p[131]=0;assert!(parse_packet(&p,[7;16],&request(),&budget(),8).is_err());
        let b=Budget{source_pixels:99,patch_pixels:2,live_bytes:1000};
        assert!(parse_header(&packet()[..128],[7;16],&request(),&b,8).is_err());
    }
}
