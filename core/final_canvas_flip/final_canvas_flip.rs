//! Final-canvas reflection only. No anatomical/processing coordinates enter this ABI.
//! AUTHORED / UNRUN. Caller owns two disjoint, fully allocated packed RGB buffers.
use std::ptr;

#[no_mangle]
pub extern "C" fn lrt_final_canvas_flip_abi() -> u32 { 1 }

/// Copies complete samples as bytes, retaining u8/u16/f32/f64 bit patterns.
/// 0 success; 1 invalid dimensions/type/flags/pointers; 2 overlap/overflow.
#[no_mangle]
pub unsafe extern "C" fn lrt_final_canvas_flip(
    src: *const u8, dst: *mut u8, width: usize, height: usize,
    sample_bytes: usize, horizontal: u8, vertical: u8,
) -> i32 {
    if src.is_null() || dst.is_null() || width == 0 || height == 0
        || ![1, 2, 4, 8].contains(&sample_bytes) || horizontal > 1 || vertical > 1 {
        return 1;
    }
    let pixel = match sample_bytes.checked_mul(3) { Some(v) => v, None => return 2 };
    let bytes = match width.checked_mul(height).and_then(|n| n.checked_mul(pixel)) {
        Some(v) if v <= isize::MAX as usize => v, _ => return 2,
    };
    let a = src as usize; let b = dst as usize;
    let ae = match a.checked_add(bytes) { Some(v) => v, None => return 2 };
    let be = match b.checked_add(bytes) { Some(v) => v, None => return 2 };
    if a < be && b < ae { return 2; }
    for y in 0..height {
        let sy = if vertical == 1 { height - 1 - y } else { y };
        for x in 0..width {
            let sx = if horizontal == 1 { width - 1 - x } else { x };
            ptr::copy_nonoverlapping(src.add((sy * width + sx) * pixel),
                                    dst.add((y * width + x) * pixel), pixel);
        }
    }
    0
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn asymmetric_all_axes_and_involution() {
        for sample in [1, 2, 4, 8] {
            let src: Vec<u8> = (0..5*3*3*sample).map(|i| (i * 37) as u8).collect();
            for h in 0..=1 { for v in 0..=1 {
                let mut got = vec![0; src.len()]; let mut back = vec![0; src.len()];
                unsafe {
                    assert_eq!(lrt_final_canvas_flip(src.as_ptr(), got.as_mut_ptr(), 5, 3, sample, h, v), 0);
                    assert_eq!(lrt_final_canvas_flip(got.as_ptr(), back.as_mut_ptr(), 5, 3, sample, h, v), 0);
                }
                assert_eq!(src, back);
                for y in 0..3 { for x in 0..5 {
                    let sy=if v==1 {2-y} else {y}; let sx=if h==1 {4-x} else {x};
                    assert_eq!(&got[(y*5+x)*3*sample..(y*5+x+1)*3*sample],
                               &src[(sy*5+sx)*3*sample..(sy*5+sx+1)*3*sample]);
                }}
            }}
        }
    }
    #[test]
    fn refuses_overlap_and_overflow() {
        let mut bytes=[0u8;12];
        unsafe {
            assert_eq!(lrt_final_canvas_flip(bytes.as_ptr(),bytes.as_mut_ptr(),2,2,1,1,0),2);
            assert_eq!(lrt_final_canvas_flip(bytes.as_ptr(),bytes.as_mut_ptr(),usize::MAX,2,8,1,0),2);
        }
    }
}
