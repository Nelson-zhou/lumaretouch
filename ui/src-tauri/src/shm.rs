//! 共享内存读端。布局必须与 engine/src/lumaretouch_engine/shm.py 逐字节一致：
//!
//!   GLOBAL_HDR = 64B : magic[4] version u32 slots u32 w u32 h u32 pixel_size u32 slot_size u32 total u32 reserved[32]
//!   SLOT_HDR   = 64B : seq u64  t_ns u64  w u32 h u32 fourcc u32 reserved[36]
//!   槽 i 偏移 = 64 + i * slot_size，元数据之后紧跟 w*h*4 像素

use std::ffi::CString;
use std::io;

pub const HEADER_SIZE: usize = 64;
pub const SLOT_META_SIZE: usize = 64;
const MAGIC: &[u8; 4] = b"LRSH";

#[repr(C)]
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
    path: CString,
    pub slots: usize,
    pub slot_size: usize,
    pub pixel_size: usize,
}

unsafe impl Send for ShmReader {}

impl ShmReader {
    /// 打开并校验表头。文件名（不含 /dev/shm/ 前缀）由引擎经 shm_ready 事件告知。
    pub fn open(name: &str) -> Result<Self, String> {
        let path = CString::new(format!("/dev/shm/{name}"))
            .map_err(|_| "共享内存名含 NUL".to_string())?;
        unsafe {
            let fd = libc::open(path.as_ptr(), libc::O_RDWR);
            if fd < 0 {
                return Err(format!("open 失败: {}", io::Error::last_os_error()));
            }
            let len = libc::lseek(fd, 0, libc::SEEK_END);
            if len <= 0 {
                libc::close(fd);
                return Err("共享内存长度为 0".into());
            }
            let len = len as usize;
            libc::lseek(fd, 0, libc::SEEK_SET);
            let base = libc::mmap(
                std::ptr::null_mut(),
                len,
                libc::PROT_READ | libc::PROT_WRITE,
                libc::MAP_SHARED,
                fd,
                0,
            );
            libc::close(fd); // 映射在 mmap 后独立持有
            if base == libc::MAP_FAILED {
                return Err(format!("mmap 失败: {}", io::Error::last_os_error()));
            }
            let b = base as *mut u8;
            let magic: [u8; 4] = std::slice::from_raw_parts(b, 4).try_into().unwrap();
            if &magic != MAGIC {
                return Err(format!("magic 不匹配: {magic:?}"));
            }
            let version = u32::from_le_bytes(rd4(b, 4));
            if version != 1 {
                return Err(format!("协议版本不支持: {version}"));
            }
            // 字段偏移由 engine 侧 test_byte_layout_is_pinned 钉死：
            // magic@0 version@4 slots@8 w@12 h@16 pixel_size@20 slot_size@24 total@28
            Ok(Self {
                base: b,
                len,
                path,
                slots: u32::from_le_bytes(rd4(b, 8)) as usize,
                pixel_size: u32::from_le_bytes(rd4(b, 20)) as usize,
                slot_size: u32::from_le_bytes(rd4(b, 24)) as usize,
            })
        }
    }

    pub fn path_name(&self) -> &str {
        self.path.to_str().unwrap_or("?")
    }

    fn slot_off(&self, i: usize) -> usize {
        HEADER_SIZE + i * self.slot_size
    }

    pub fn meta(&self, slot: usize) -> SlotMeta {
        let o = self.slot_off(slot);
        SlotMeta {
            seq: u64::from_le_bytes(rd8(self.base, o)),
            t_ns: u64::from_le_bytes(rd8(self.base, o + 8)),
            w: u32::from_le_bytes(rd4(self.base, o + 16)),
            h: u32::from_le_bytes(rd4(self.base, o + 20)),
            fourcc: u32::from_le_bytes(rd4(self.base, o + 24)),
        }
    }

    pub fn freshest(&self) -> Option<(SlotMeta, usize)> {
        let mut best: Option<(SlotMeta, usize)> = None;
        for i in 0..self.slots {
            let m = self.meta(i);
            if m.seq == 0 {
                continue;
            }
            match &best {
                Some((b, _)) if b.seq >= m.seq => {}
                _ => best = Some((m, i)),
            }
        }
        best
    }

    /// 从某槽的字节偏移处拷一段出去（长度由 out 定）。
    /// 脏矩形上传走的就是这里：只把变化那几行拷出来，不再拷整帧。
    ///
    /// 这里不用 assert：调用方的 slot / pixel_size 可能来自一块已被引擎换掉的旧缓冲，
    /// panic 会让整个命令线程倒掉，前端的 pullFrame Promise 永不 resolve、HUD 就地卡死；
    /// 而 slot 越界则是从映射区外读（UB），不是报错而是可能读到错字节。越界当错误返回。
    pub fn copy_span(&self, slot: usize, byte_off: usize, out: &mut [u8]) -> Result<(), String> {
        if slot >= self.slots {
            return Err(format!("slot {slot} 越出槽数 {}", self.slots));
        }
        let start = self.slot_off(slot) + SLOT_META_SIZE + byte_off;
        let end = match start.checked_add(out.len()) {
            Some(e) => e,
            None => return Err("拷读长度溢出".into()),
        };
        if byte_off + out.len() > self.pixel_size || end > self.len {
            return Err(format!(
                "拷读越出像素区：slot={slot} off={byte_off} len={} pixel_size={} 映射={}",
                out.len(),
                self.pixel_size,
                self.len
            ));
        }
        let src = unsafe { std::slice::from_raw_parts(self.base.add(start), out.len()) };
        out.copy_from_slice(src);
        Ok(())
    }
}

/// 小端读取：宽度由函数名定死，避免 from_le_bytes 的数组长度不匹配
fn rd4(base: *mut u8, off: usize) -> [u8; 4] {
    let mut b = [0u8; 4];
    unsafe { std::ptr::copy_nonoverlapping(base.add(off) as *const u8, b.as_mut_ptr(), 4) };
    b
}

fn rd8(base: *mut u8, off: usize) -> [u8; 8] {
    let mut b = [0u8; 8];
    unsafe { std::ptr::copy_nonoverlapping(base.add(off) as *const u8, b.as_mut_ptr(), 8) };
    b
}

impl Drop for ShmReader {
    fn drop(&mut self) {
        unsafe {
            libc::munmap(self.base as *mut _, self.len);
        }
    }
}
