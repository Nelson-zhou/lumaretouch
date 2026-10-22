// SPDX-License-Identifier: GPL-3.0-or-later
// LumaRetouch optical output -> input mapping. No Lensfun algorithm is copied:
// calibration/interpolation remains in the separately staged Lensfun library.
use std::slice;

#[no_mangle]
pub extern "C" fn lrt_optics_abi() -> u32 { 1 }

// Pointer lengths are explicit and checked. The Python caller owns nonaliasing
// allocations for the duration of these synchronous calls. Errors never unwind.
#[no_mangle]
pub unsafe extern "C" fn lrt_optics_map(w: u32, h: u32, y0: u32, rows: u32,
    inverse: *const f64, distortion: f64, zoom: f64, output: *mut f64, count: usize) -> i32 {
    let n = (w as usize).checked_mul(rows as usize).and_then(|v| v.checked_mul(2));
    if w == 0 || h == 0 || w > 65536 || h > 65536 || y0.checked_add(rows).map_or(true, |v| v > h)
        || n != Some(count) || inverse.is_null() || output.is_null() || !distortion.is_finite()
        || distortion.abs() > 100. || !zoom.is_finite() || zoom < 1. || zoom > 32. { return 1; }
    let m = slice::from_raw_parts(inverse, 9);
    if m.iter().any(|v| !v.is_finite()) { return 2; }
    let out = slice::from_raw_parts_mut(output, count);
    let diag2 = (w as f64).powi(2)+(h as f64).powi(2);
    for y in 0..rows { for x in 0..w {
        let dx = ((2.*x as f64+1.)/w as f64-1.)/zoom;
        let dy = ((2.*(y+y0) as f64+1.)/h as f64-1.)/zoom;
        let den = m[6]*dx+m[7]*dy+m[8];
        if !den.is_finite() || den.abs() < 1e-9 { return 3; }
        let px = (m[0]*dx+m[1]*dy+m[2])/den;
        let py = (m[3]*dx+m[4]*dy+m[5])/den;
        let r2 = ((px*w as f64).powi(2)+(py*h as f64).powi(2))/diag2;
        let k = 1.+distortion*.002*r2;
        let i = ((y*w+x) as usize)*2;
        out[i] = (px*k+1.)*w as f64*.5-.5;
        out[i+1] = (py*k+1.)*h as f64*.5-.5;
    }}
    0
}

#[no_mangle]
pub unsafe extern "C" fn lrt_optics_sample(source: *const f64, w: u32, h: u32, channels: u32,
    source_len: usize, coords: *const f64, points: usize, output: *mut f64, output_len: usize) -> i32 {
    if w == 0 || h == 0 || channels == 0 || channels > 8 || w > 65536 || h > 65536
        || points > 64_000_000 || source.is_null() || coords.is_null() || output.is_null()
        || (w as usize).checked_mul(h as usize).and_then(|n| n.checked_mul(channels as usize)) != Some(source_len)
        || points.checked_mul(channels as usize) != Some(output_len) { return 1; }
    let src = slice::from_raw_parts(source, source_len);
    let xy = slice::from_raw_parts(coords, points*2);
    let dst = slice::from_raw_parts_mut(output, output_len);
    let c = channels as usize;
    for i in 0..points {
        let x = xy[2*i]; let y = xy[2*i+1];
        // Outside the pixel-cell footprint is empty canvas; values within its
        // half-pixel edge use constant extension, matching normalized edges.
        if !x.is_finite() || !y.is_finite() || x < -0.5 || y < -0.5 || x > w as f64-0.5 || y > h as f64-0.5 {
            for k in 0..c { dst[i*c+k] = 0.; } continue;
        }
        let sx = x.max(0.).min(w as f64-1.); let sy = y.max(0.).min(h as f64-1.);
        let xa = sx.floor() as usize; let ya = sy.floor() as usize;
        let xb = (xa+1).min(w as usize-1); let yb = (ya+1).min(h as usize-1);
        let fx = sx-xa as f64; let fy = sy-ya as f64;
        for k in 0..c {
            let a = src[(ya*w as usize+xa)*c+k]; let b = src[(ya*w as usize+xb)*c+k];
            let d = src[(yb*w as usize+xa)*c+k]; let e = src[(yb*w as usize+xb)*c+k];
            dst[i*c+k] = (a+(b-a)*fx)*(1.-fy)+(d+(e-d)*fx)*fy;
        }
    }
    0
}
