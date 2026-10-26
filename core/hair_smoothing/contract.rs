// SPDX-License-Identifier: GPL-3.0-or-later
//! Checked dimensions, storage accounting and transactional FFI preflight.
use std::mem::{align_of, size_of};

pub(crate) const MAX_PIXELS: usize = 32_000_000;
pub(crate) const MAX_BYTES: u64 = 4 * 1024 * 1024 * 1024;
pub(crate) const MAX_LOG_GAIN: f64 = 0.095_310_179_804_324_93; // ln(1.10)
pub(crate) const ABI: i32 = 1;
pub(crate) const INPUT: i32 = 2;
pub(crate) const SCALE: i32 = 3;
pub(crate) const CONTEXT: i32 = 4;
pub(crate) const BUDGET: i32 = 5;
pub(crate) const CANCELLED: i32 = 6;
pub(crate) const NUMERICS: i32 = 7;
pub(crate) const PANIC: i32 = 8;
pub(crate) type Result<T> = std::result::Result<T, i32>;
pub(crate) type Cancel = Option<unsafe extern "C" fn(*mut std::ffi::c_void) -> i32>;

#[derive(Clone, Copy)]
pub(crate) struct Plan {
    pub width: usize,
    pub height: usize,
    pub pixels: usize,
    pub tensor_radius: usize,
    pub halo: usize,
    pub required: u64,
    pub retained: u64,
}
impl Plan {
    pub fn new(width: usize, height: usize, scale: f64) -> Result<Self> {
        if !scale.is_finite() || !(1.0..=8.0).contains(&scale) { return Err(SCALE); }
        if width == 0 || height == 0 || width > 65_536 || height > 65_536 { return Err(ABI); }
        let pixels = width.checked_mul(height).ok_or(ABI)?;
        if pixels > MAX_PIXELS { return Err(BUDGET); }
        let prefix = width.checked_add(1).and_then(|w| height.checked_add(1).and_then(|h| w.checked_mul(h))).ok_or(ABI)?;
        let required = (pixels as u64).checked_mul(120)
            .and_then(|n| (prefix as u64).checked_mul(8).and_then(|p| n.checked_add(p)))
            .and_then(|n| n.checked_add(16 * 1024 * 1024)).ok_or(ABI)?;
        if required > MAX_BYTES { return Err(BUDGET); }
        let tensor_radius = (0.5 * scale).ceil() as usize;
        let halo = tensor_radius + 1 + (2.0 * scale).ceil() as usize + 1;
        Ok(Self { width, height, pixels, tensor_radius, halo, required, retained: 5 * pixels as u64 })
    }
}

pub(crate) fn poll(cancel: Cancel, context: *mut std::ffi::c_void) -> Result<()> {
    // The foreign callback must not unwind, mutate input/output or reenter.
    if let Some(callback) = cancel {
        if unsafe { callback(context) } != 0 { return Err(CANCELLED); }
    }
    Ok(())
}
pub(crate) fn buffer<T>(pointer: *const T, len: usize, expected: usize) -> Result<(usize, usize)> {
    if len != expected || pointer.is_null() || (pointer as usize) % align_of::<T>() != 0 { return Err(ABI); }
    let bytes = len.checked_mul(size_of::<T>()).ok_or(ABI)?;
    if bytes > isize::MAX as usize { return Err(ABI); }
    let start = pointer as usize;
    let end = start.checked_add(bytes).ok_or(ABI)?;
    Ok((start, end))
}
pub(crate) fn disjoint(regions: &[(usize, usize)]) -> Result<()> {
    for (i, one) in regions.iter().enumerate() {
        for two in &regions[i + 1..] {
            if one.0 < two.1 && two.0 < one.1 { return Err(ABI); }
        }
    }
    Ok(())
}
pub(crate) fn allocate<T: Clone>(len: usize, value: T) -> Result<Vec<T>> {
    let mut out = Vec::new();
    out.try_reserve_exact(len).map_err(|_| BUDGET)?;
    out.resize(len, value);
    Ok(out)
}
pub(crate) fn contained(f: impl FnOnce() -> Result<()>) -> i32 {
    match std::panic::catch_unwind(std::panic::AssertUnwindSafe(f)) {
        Ok(Ok(())) => 0,
        Ok(Err(code)) => code,
        Err(_) => PANIC,
    }
}
