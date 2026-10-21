//! Protocol v2 shared-frame reader. A shared flock covers metadata selection and
//! pixel copying; the Python writer holds the same file's exclusive flock.
//! Ping-pong slots alone do not protect a slow reader against a later overwrite.
use std::fs::File;
use std::io;
use std::os::fd::AsRawFd;

pub const HEADER_SIZE: usize = 64;
pub const SLOT_META_SIZE: usize = 64;
const MAGIC: &[u8; 4] = b"LRSH";

#[derive(Debug, Clone, Copy)]
pub struct SlotMeta {
    pub seq: u64,
    pub t_ns: u64,
    pub w: u32,
    pub h: u32,
    pub fourcc: u32,
}

pub struct ShmReader {
    base: *mut u8,
    len: usize,
    path: String,
    file: File,
    width: u32,
    height: u32,
    instance: Option<[u8;16]>,
    pub slots: usize,
    pub slot_size: usize,
    pub pixel_size: usize,
}
unsafe impl Send for ShmReader {}

fn flock(file: &File, operation: libc::c_int) -> Result<(), String> {
    loop {
        if unsafe { libc::flock(file.as_raw_fd(), operation) } == 0 { return Ok(()); }
        let err = io::Error::last_os_error();
        if err.kind() != io::ErrorKind::Interrupted { return Err(format!("frame flock: {err}")); }
    }
}

/// The borrow keeps the mapping and descriptor alive until the lock is released.
/// Metadata/pixel access is exposed only through this guard.
pub struct FrameReadGuard<'a> { reader: &'a ShmReader }
impl Drop for FrameReadGuard<'_> {
    fn drop(&mut self) { let _ = flock(&self.reader.file, libc::LOCK_UN); }
}

impl ShmReader {
    pub fn open(name: &str) -> Result<Self, String> {
        if name.is_empty() || name.contains('/') || name.contains('\0') {
            return Err("invalid shared-memory name".into());
        }
        let path = format!("/dev/shm/{name}");
        let file = File::open(&path).map_err(|e| format!("open: {e}"))?;
        let len = usize::try_from(file.metadata().map_err(|e| e.to_string())?.len())
            .map_err(|_| "shared-memory length overflow")?;
        if len < HEADER_SIZE { return Err("shared-memory header truncated".into()); }
        let base = unsafe { libc::mmap(std::ptr::null_mut(), len, libc::PROT_READ,
                                      libc::MAP_SHARED, file.as_raw_fd(), 0) };
        if base == libc::MAP_FAILED { return Err(format!("mmap: {}", io::Error::last_os_error())); }
        // Construct first so every subsequent error unmaps and closes via Drop.
        let mut reader = Self { base: base as *mut u8, len, path, file,
                                width: 0, height: 0, instance: None, slots: 0, slot_size: 0, pixel_size: 0 };
        let hdr = {
            let _guard = reader.read()?;
            let mut hdr = [0u8; HEADER_SIZE];
            unsafe { std::ptr::copy_nonoverlapping(reader.base, hdr.as_mut_ptr(), HEADER_SIZE); }
            hdr
        };
        let word = |off: usize| u32::from_le_bytes(hdr[off..off+4].try_into().unwrap()) as usize;
        if &hdr[..4] != MAGIC || word(4) != 2 {
            return Err("shared-memory magic/version mismatch (requires locking protocol v2)".into());
        }
        let (slots,w,h,pixel_size,slot_size,total) = (word(8),word(12),word(16),word(20),word(24),word(28));
        let pixels = w.checked_mul(h).and_then(|x| x.checked_mul(4));
        let stride = pixel_size.checked_add(SLOT_META_SIZE);
        let expected = slot_size.checked_mul(slots).and_then(|x| x.checked_add(HEADER_SIZE));
        if slots == 0 || w == 0 || h == 0 || pixels != Some(pixel_size)
            || stride != Some(slot_size) || expected != Some(len) || total != len {
            return Err("shared-memory layout is inconsistent or overflows".into());
        }
        reader.slots=slots; reader.slot_size=slot_size; reader.pixel_size=pixel_size;
        reader.width=w as u32; reader.height=h as u32;
        reader.instance=crate::frame_identity::parse(&hdr[32..64]);
        Ok(reader)
    }

    pub fn instance_id(&self)->Option<[u8;16]>{self.instance}
    pub fn path_name(&self) -> &str { &self.path }
    pub fn read(&self) -> Result<FrameReadGuard<'_>, String> {
        flock(&self.file, libc::LOCK_SH)?;
        let guard=FrameReadGuard { reader: self };
        if self.file.metadata().map_err(|e| e.to_string())?.len() != self.len as u64 {
            return Err("SHM_CHANGED: reopen resized frame mapping".into());
        }
        if self.pixel_size != 0 && (u32::from_le_bytes(rd4(self.base,4)) != 2
            || u32::from_le_bytes(rd4(self.base,12)) != self.width
            || u32::from_le_bytes(rd4(self.base,16)) != self.height) {
            return Err("SHM_CHANGED: frame layout changed".into());
        }
        if self.pixel_size != 0 {
            let mut reserved=[0u8;32];
            unsafe { std::ptr::copy_nonoverlapping(self.base.add(32),reserved.as_mut_ptr(),32); }
            if crate::frame_identity::parse(&reserved)!=self.instance {
                return Err("SHM_CHANGED: shared-frame instance replaced".into());
            }
        }
        Ok(guard)
    }
}

impl FrameReadGuard<'_> {
    fn meta(&self, slot: usize) -> SlotMeta {
        let r=self.reader;
        let off=HEADER_SIZE+slot*r.slot_size;
        SlotMeta { seq: u64::from_le_bytes(rd8(r.base,off)),
                   t_ns: u64::from_le_bytes(rd8(r.base,off+8)),
                   w: u32::from_le_bytes(rd4(r.base,off+16)),
                   h: u32::from_le_bytes(rd4(r.base,off+20)),
                   fourcc: u32::from_le_bytes(rd4(r.base,off+24)) }
    }

    pub fn freshest(&self) -> Result<Option<(SlotMeta,usize)>,String> {
        let mut best: Option<(SlotMeta,usize)> = None;
        for i in 0..self.reader.slots {
            let meta=self.meta(i);
            if meta.seq==0 { continue; }
            if meta.w != self.reader.width || meta.h != self.reader.height || meta.fourcc != 0x41424752 {
                return Err("frame metadata does not match mapped RGBA8 layout".into());
            }
            if best.as_ref().map(|(b,_)| b.seq >= meta.seq).unwrap_or(false) { continue; }
            best=Some((meta,i));
        }
        Ok(best)
    }

    pub fn copy_span(&self, slot: usize, byte_off: usize, out: &mut [u8]) -> Result<(),String> {
        let r=self.reader;
        if slot>=r.slots { return Err("frame slot out of bounds".into()); }
        let span_end=byte_off.checked_add(out.len()).ok_or("frame span overflow")?;
        if span_end>r.pixel_size { return Err("frame span outside pixels".into()); }
        let start=HEADER_SIZE+slot*r.slot_size+SLOT_META_SIZE+byte_off;
        let end=start.checked_add(out.len()).ok_or("frame mapping overflow")?;
        if end>r.len { return Err("frame span outside mapping".into()); }
        let src=unsafe { std::slice::from_raw_parts(r.base.add(start),out.len()) };
        out.copy_from_slice(src);
        Ok(())
    }
}

fn rd4(base:*mut u8, off:usize)->[u8;4] {
    let mut out=[0;4];
    unsafe { std::ptr::copy_nonoverlapping(base.add(off),out.as_mut_ptr(),4); }
    out
}
fn rd8(base:*mut u8, off:usize)->[u8;8] {
    let mut out=[0;8];
    unsafe { std::ptr::copy_nonoverlapping(base.add(off),out.as_mut_ptr(),8); }
    out
}
impl Drop for ShmReader {
    fn drop(&mut self) { unsafe { libc::munmap(self.base as *mut _,self.len); } }
}
