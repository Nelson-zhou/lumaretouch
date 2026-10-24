// SPDX-License-Identifier: GPL-3.0-or-later
//! Original observed-source, manually reviewed 2D collarbone contrast. AUTHORED / UNRUN.
//! Not anatomical detection, AI3D reconstruction, relighting or missing-bone synthesis.
use std::{ffi::c_void, mem, panic, slice};

pub const MAX_PIXELS: usize = 32_000_000;
pub const MAX_DIMENSION: usize = 65_536;
pub const MAX_WORKING_BYTES: usize = 4 * 1024 * 1024 * 1024;
pub const NATIVE_SCRATCH_BYTES_PER_PIXEL: usize = 32;
pub const MAX_LOG_GAIN: f64 = 0.12;
pub const SIGNAL_LOW: f64 = 0.010;
pub const SIGNAL_FULL: f64 = 0.040;
pub const STATS_LEN: usize = 8;
pub const ABI_ERROR: i32 = 1;
pub const SETTINGS_ERROR: i32 = 2;
pub const PIXEL_ERROR: i32 = 3;
pub const CANCELLED: i32 = 4;
pub const RESOURCE_ERROR: i32 = 5;
pub const PANIC_ERROR: i32 = 6;
pub type Cancel = Option<extern "C" fn(*mut c_void) -> i32>;

#[derive(Clone, Copy, Debug)]
pub struct Point { pub x: f64, pub y: f64 }
#[derive(Clone, Debug)]
pub struct Trace { pub points: Vec<Point>, pub half_width: f64 }
#[derive(Clone, Copy, Debug)]
pub struct Rect { pub x: usize, pub y: usize, pub width: usize, pub height: usize }

fn unit(v: f32) -> bool { v.is_finite() && (0.0..=1.0).contains(&v) }
fn poll<F: FnMut() -> bool>(cancel: &mut F) -> Result<(), i32> {
    if cancel() { Err(CANCELLED) } else { Ok(()) }
}
fn dimensions(width: usize, height: usize) -> Result<usize, i32> {
    if width == 0 || height == 0 || width > MAX_DIMENSION || height > MAX_DIMENSION {
        return Err(ABI_ERROR);
    }
    let n = width.checked_mul(height).ok_or(RESOURCE_ERROR)?;
    if n > MAX_PIXELS { return Err(RESOURCE_ERROR); }
    Ok(n)
}
fn rect_in(rect: Rect, width: usize, height: usize) -> Result<usize, i32> {
    let n = dimensions(rect.width, rect.height)?;
    if rect.x.checked_add(rect.width).ok_or(ABI_ERROR)? > width
        || rect.y.checked_add(rect.height).ok_or(ABI_ERROR)? > height { return Err(ABI_ERROR); }
    Ok(n)
}
fn contains(outer: Rect, inner: Rect) -> bool {
    inner.x >= outer.x && inner.y >= outer.y
        && inner.x + inner.width <= outer.x + outer.width
        && inner.y + inner.height <= outer.y + outer.height
}
fn filled<T: Clone, F: FnMut() -> bool>(n: usize, value: T, cancel: &mut F) -> Result<Vec<T>, i32> {
    poll(cancel)?;
    let mut result = Vec::new();
    result.try_reserve_exact(n).map_err(|_| RESOURCE_ERROR)?;
    for i in 0..n {
        if i % 256 == 0 { poll(cancel)?; }
        result.push(value.clone());
    }
    Ok(result)
}
fn decode(v: f64) -> f64 {
    if v <= 0.04045 { v / 12.92 } else { ((v + 0.055) / 1.055).powf(2.4) }
}
fn encode(v: f64) -> f32 {
    if v <= 0.0031308 { (12.92 * v) as f32 } else { (1.055 * v.powf(1.0 / 2.4) - 0.055) as f32 }
}
fn luminance(rgb: &[f32], i: usize) -> f64 {
    0.2126 * decode(f64::from(rgb[3*i])) + 0.7152 * decode(f64::from(rgb[3*i+1]))
        + 0.0722 * decode(f64::from(rgb[3*i+2]))
}
fn smooth(low: f64, high: f64, v: f64) -> f64 {
    // Permission/evidence scalar bounds, never output-channel clipping.
    let t = ((v - low) / (high - low)).clamp(0.0, 1.0);
    t*t*(3.0 - 2.0*t)
}
fn reliability(rgb: &[f32], i: usize) -> f64 {
    let peak = rgb[3*i..3*i+3].iter().copied().fold(0.0_f32, f32::max);
    smooth(0.005, 0.03, luminance(rgb, i)) * (1.0 - smooth(0.94, 0.995, f64::from(peak)))
}
fn source_sample(rgb: &[f32], coverage: &[f32], i: usize) -> [f64; 3] {
    let w = f64::from(coverage[i]);
    if w == 0.0 { return [0.0; 3]; }
    let y = luminance(rgb, i);
    let peak = rgb[3*i..3*i+3].iter().copied().fold(0.0_f32, f32::max);
    let rel = smooth(0.005, 0.03, y) * (1.0-smooth(0.94, 0.995, f64::from(peak)));
    [w, w * y.max(1e-6).ln(), w * rel]
}

/// Narrow, coverage-normalized source average. Whole windows must be real source
/// pixels: crop-edge/truncated/reflected/replicated observations are forbidden.
/// Result [mean logY, mean reliability], or NaN sentinel for unavailable evidence.
fn narrow_mean<F: FnMut() -> bool>(rgb: &[f32], coverage: &[f32], width: usize,
    height: usize, radius: usize, cancel: &mut F) -> Result<Vec<[f32; 2]>, i32> {
    let mut rows = filled(width*height, [0.0_f64; 3], cancel)?;
    for y in 0..height {
        poll(cancel)?;
        let mut sum = [0.0_f64; 3];
        for x in 0..=radius.min(width-1) {
            let v = source_sample(rgb, coverage, y*width+x);
            for k in 0..3 { sum[k] += v[k]; }
        }
        for x in 0..width {
            if x % 256 == 0 { poll(cancel)?; }
            rows[y*width+x] = sum;
            if x >= radius {
                let v = source_sample(rgb, coverage, y*width+x-radius);
                for k in 0..3 { sum[k] -= v[k]; }
            }
            if x + radius + 1 < width {
                let v = source_sample(rgb, coverage, y*width+x+radius+1);
                for k in 0..3 { sum[k] += v[k]; }
            }
        }
    }
    let mut result = filled(width*height, [f32::NAN; 2], cancel)?;
    let area = ((2*radius+1)*(2*radius+1)) as f64;
    for x in 0..width {
        poll(cancel)?;
        let mut sum = [0.0_f64; 3];
        for y in 0..=radius.min(height-1) {
            for k in 0..3 { sum[k] += rows[y*width+x][k]; }
        }
        for y in 0..height {
            if y % 256 == 0 { poll(cancel)?; }
            let i = y*width+x;
            if x >= radius && y >= radius && x + radius < width && y + radius < height
                && coverage[i] > 0.0 && sum[0] >= 1.0 && sum[0] / area >= 0.20 {
                let mean = sum[1] / sum[0];
                let rel = (sum[2] / sum[0]).clamp(0.0, 1.0);
                if !mean.is_finite() || !rel.is_finite() { return Err(PIXEL_ERROR); }
                result[i] = [mean as f32, rel as f32];
            }
            if y >= radius { for k in 0..3 { sum[k] -= rows[(y-radius)*width+x][k]; } }
            if y + radius + 1 < height { for k in 0..3 { sum[k] += rows[(y+radius+1)*width+x][k]; } }
        }
    }
    Ok(result)
}
fn sub(a: Point, b: Point) -> Point { Point { x: a.x-b.x, y: a.y-b.y } }
fn norm(a: Point) -> f64 { a.x.hypot(a.y) }
fn cross(a: Point, b: Point) -> f64 { a.x*b.y-a.y*b.x }
fn dot(a: Point, b: Point) -> f64 { a.x*b.x+a.y*b.y }
fn direction(a: Point, b: Point) -> Point {
    let v = sub(b,a); let length = norm(v); Point { x: v.x/length, y: v.y/length }
}
fn segments_touch(a: Point, b: Point, c: Point, d: Point) -> bool {
    let ab = sub(b,a); let cd = sub(d,c);
    let o1 = cross(ab,sub(c,a)); let o2 = cross(ab,sub(d,a));
    let o3 = cross(cd,sub(a,c)); let o4 = cross(cd,sub(b,c));
    let boxes = a.x.min(b.x) <= c.x.max(d.x) && c.x.min(d.x) <= a.x.max(b.x)
        && a.y.min(b.y) <= c.y.max(d.y) && c.y.min(d.y) <= a.y.max(b.y);
    boxes && o1*o2 <= 0.0 && o3*o4 <= 0.0
}
fn traces_valid(traces: &[Trace], width: usize, height: usize) -> bool {
    if !(1..=2).contains(&traces.len()) { return false; }
    for trace in traces {
        if !(3..=8).contains(&trace.points.len()) || !trace.half_width.is_finite()
            || !(4.0..=256.0).contains(&trace.half_width) { return false; }
        if !trace.points.iter().all(|p| p.x.is_finite() && p.y.is_finite()
            && p.x > -0.5 && p.y > -0.5 && p.x < width as f64 - 0.5 && p.y < height as f64 - 0.5) { return false; }
        let mut length = 0.0;
        for pair in trace.points.windows(2) {
            let segment = norm(sub(pair[1],pair[0]));
            if segment < 2.0 { return false; }
            length += segment;
        }
        if length < 2.0*trace.half_width { return false; }
        for triple in trace.points.windows(3) {
            // Prevent a folding/unstable normal, not automatic anatomy repair.
            if dot(direction(triple[0],triple[1]),direction(triple[1],triple[2])) <= 0.0 { return false; }
        }
        for a in 0..trace.points.len()-1 {
            for b in a+2..trace.points.len()-1 {
                if segments_touch(trace.points[a],trace.points[a+1],trace.points[b],trace.points[b+1]) { return false; }
            }
        }
    }
    if traces.len() == 2 {
        for a in traces[0].points.windows(2) { for b in traces[1].points.windows(2) {
            if segments_touch(a[0],a[1],b[0],b[1]) { return false; }
        } }
    }
    true
}
fn vertex_tangent(points: &[Point], index: usize) -> Point {
    if index == 0 { return direction(points[0],points[1]); }
    if index + 1 == points.len() { return direction(points[index-1],points[index]); }
    let a = direction(points[index-1],points[index]); let b = direction(points[index],points[index+1]);
    let sum = Point { x: a.x+b.x, y: a.y+b.y }; let length = norm(sum);
    Point { x: sum.x/length, y: sum.y/length }
}
/// Stable nearest segment, smoothly interpolated reviewed trace tangent, endpoint
/// taper. No mirroring to an absent side or extrapolation beyond endpoints.
fn geometry(trace: &Trace, pixel: Point) -> (f64, Point, f64) {
    let mut best = f64::INFINITY; let mut normal = Point { x: 0.0, y: 0.0 };
    let mut along = 0.0; let mut start = 0.0;
    for (index,pair) in trace.points.windows(2).enumerate() {
        let vector = sub(pair[1],pair[0]); let length = norm(vector);
        let t = (dot(sub(pixel,pair[0]),vector)/(length*length)).clamp(0.0,1.0);
        let distance = norm(sub(pixel,Point { x: pair[0].x+t*vector.x, y: pair[0].y+t*vector.y }));
        if distance < best {
            best = distance; along = start+t*length;
            let a = vertex_tangent(&trace.points,index); let b = vertex_tangent(&trace.points,index+1);
            let tangent = Point { x: (1.0-t)*a.x+t*b.x, y: (1.0-t)*a.y+t*b.y };
            let size = norm(tangent); normal = Point { x: -tangent.y/size, y: tangent.x/size };
        }
        start += length;
    }
    let taper = (1.0-smooth(0.0,trace.half_width,best))
        * smooth(0.0,trace.half_width,along) * smooth(0.0,trace.half_width,start-along);
    (best/trace.half_width,normal,taper)
}
fn sample(mean: &[[f32;2]], coverage: &[f32], window: Rect, p: Point) -> Option<[f64;2]> {
    let x = p.x-window.x as f64; let y = p.y-window.y as f64;
    if x < 0.0 || y < 0.0 || x > (window.width-1) as f64 || y > (window.height-1) as f64 { return None; }
    let left = x.floor() as usize; let top = y.floor() as usize;
    let right = (left+1).min(window.width-1); let bottom = (top+1).min(window.height-1);
    let fx = x-left as f64; let fy = y-top as f64;
    let taps = [(left,top,(1.0-fx)*(1.0-fy)),(right,top,fx*(1.0-fy)),
                (left,bottom,(1.0-fx)*fy),(right,bottom,fx*fy)];
    let mut sum = [0.0_f64;2];
    for (tx,ty,w) in taps {
        if w == 0.0 { continue; }
        let i = ty*window.width+tx;
        if coverage[i] == 0.0 || !mean[i].iter().all(|v| v.is_finite()) { return None; }
        for k in 0..2 { sum[k] += w*f64::from(mean[i][k]); }
    }
    Some(sum)
}
fn real_filter_domain(p: Point, radius: usize, width: usize, height: usize) -> bool {
    p.x >= radius as f64 && p.y >= radius as f64
        && p.x.ceil() + radius as f64 <= (width-1) as f64
        && p.y.ceil() + radius as f64 <= (height-1) as f64
}

/// Stats: reviewed band, covered band, source-border refusal, unsupported sample,
/// unreliable source, insufficient/ambiguous signal, admitted pixels, overlap ties.
/// The field is private until success; source-owned coverage authorizes BOTH the
/// target and every sampled source neighborhood. No amount/current RGB is read.
pub fn prepare_into<F: FnMut() -> bool>(reference: &[f32], coverage: &[f32],
    window: Rect, source_width: usize, source_height: usize, traces: &[Trace],
    output_window: Rect, field: &mut [f32], stats: &mut [u64;STATS_LEN], mut cancel: F,
) -> Result<(), i32> {
    dimensions(source_width,source_height)?;
    let n = rect_in(window,source_width,source_height)?;
    let out_n = rect_in(output_window,source_width,source_height)?;
    if !contains(window,output_window) || reference.len() != 3*n || coverage.len() != n || field.len() != out_n { return Err(ABI_ERROR); }
    if !traces_valid(traces,source_width,source_height) { return Err(SETTINGS_ERROR); }
    let bytes = n.checked_mul(48).and_then(|v| out_n.checked_mul(4).and_then(|f| v.checked_add(f))).ok_or(RESOURCE_ERROR)?;
    if bytes > MAX_WORKING_BYTES { return Err(RESOURCE_ERROR); }
    *stats = [0;STATS_LEN];
    for i in 0..n {
        if i%256 == 0 { poll(&mut cancel)?; }
        if !unit(coverage[i]) || !reference[3*i..3*i+3].iter().copied().all(unit) { return Err(PIXEL_ERROR); }
    }
    for i in 0..out_n { if i%256 == 0 { poll(&mut cancel)?; } field[i] = 0.0; }
    for (owner,trace) in traces.iter().enumerate() {
        let radius = ((trace.half_width/4.0).floor() as usize).max(1);
        let mean = narrow_mean(reference,coverage,window.width,window.height,radius,&mut cancel)?;
        for i in 0..out_n {
            if i%256 == 0 { poll(&mut cancel)?; }
            let p = Point { x: (output_window.x+i%output_window.width) as f64,
                            y: (output_window.y+i/output_window.width) as f64 };
            let (distance,normal,taper) = geometry(trace,p);
            if distance >= 1.0 || taper == 0.0 { continue; }
            let mut selected = true; let mut overlap = false;
            for (other_index,other) in traces.iter().enumerate() {
                if other_index == owner { continue; }
                let (other_distance,_,other_taper) = geometry(other,p);
                if other_distance < 1.0 && other_taper > 0.0 {
                    overlap = true;
                    if other_distance < distance || (other_distance == distance && other_index < owner) { selected = false; }
                }
            }
            if !selected { continue; }
            stats[0] += 1; if overlap { stats[7] += 1; }
            let local = (p.y as usize-window.y)*window.width+(p.x as usize-window.x);
            if coverage[local] == 0.0 { continue; }
            stats[1] += 1;
            let a = Point { x: p.x-2.0*trace.half_width*normal.x, y: p.y-2.0*trace.half_width*normal.y };
            let b = Point { x: p.x+2.0*trace.half_width*normal.x, y: p.y+2.0*trace.half_width*normal.y };
            if ![p,a,b].iter().all(|&v| real_filter_domain(v,radius,source_width,source_height)) {
                stats[2] += 1; continue;
            }
            let samples = match (sample(&mean,coverage,window,p),sample(&mean,coverage,window,a),sample(&mean,coverage,window,b)) {
                (Some(center),Some(left),Some(right)) => [center,left,right],
                _ => { stats[3] += 1; continue; }
            };
            let rel = reliability(reference,local).min(samples[0][1]).min(samples[1][1]).min(samples[2][1]);
            if rel <= 0.05 { stats[4] += 1; continue; }
            let residual = samples[0][0]-0.5*(samples[1][0]+samples[2][0]);
            let evidence = smooth(SIGNAL_LOW,SIGNAL_FULL,residual.abs())
                * (1.0-smooth(0.35,0.70,residual.abs()))
                * (1.0-smooth(0.30,0.70,(samples[1][0]-samples[2][0]).abs()));
            if evidence == 0.0 { stats[5] += 1; continue; }
            let delta = f64::from(coverage[local])*taper*rel*evidence
                * MAX_LOG_GAIN*(0.65*residual/MAX_LOG_GAIN).tanh();
            if !delta.is_finite() || delta.abs() > MAX_LOG_GAIN { return Err(PIXEL_ERROR); }
            field[i] = delta as f32;
            if field[i] != 0.0 { stats[6] += 1; } else { stats[5] += 1; }
        }
        // mean and all filter scratch are dropped before the next curve.
    }
    poll(&mut cancel)
}
fn adjusted(current: [f32;3], delta: f64) -> Result<[f32;3],i32> {
    if delta == 0.0 || current.iter().all(|&v| v == 0.0) || current.iter().all(|&v| v == 1.0) { return Ok(current); }
    let linear = current.map(|v| decode(f64::from(v)));
    let peak = linear.into_iter().fold(0.0_f64,f64::max);
    let gain = if delta > 0.0 { delta.exp().min(1.0+(1.0/peak-1.0).max(0.0)*(1.0-1e-12)) } else { delta.exp() };
    if gain == 1.0 { return Ok(current); }
    let target = linear.map(|v| v*gain);
    if !target.iter().all(|v| v.is_finite() && (0.0..=1.0).contains(v)) { return Err(PIXEL_ERROR); }
    let encoded = target.map(encode);
    if !encoded.iter().copied().all(unit) { return Err(PIXEL_ERROR); }
    Ok(encoded)
}
/// Composition is pointwise, using global source coordinates. Preparing once and
/// composing disjoint current-stage tiles is numerically identical to full-grid
/// composition. It does not re-estimate evidence from edited/current pixels.
pub fn compose_into<F: FnMut() -> bool>(current: &[f32], tile: Rect, field: &[f32],
    field_window: Rect, source_width: usize, source_height: usize, amount: f32,
    output: &mut [f32], mut cancel: F) -> Result<(),i32> {
    dimensions(source_width,source_height)?;
    let n = rect_in(tile,source_width,source_height)?;
    let field_n = rect_in(field_window,source_width,source_height)?;
    if current.len() != 3*n || output.len() != 3*n || field.len() != field_n { return Err(ABI_ERROR); }
    if !unit(amount) { return Err(SETTINGS_ERROR); }
    for i in 0..field_n {
        if i%256 == 0 { poll(&mut cancel)?; }
        if !field[i].is_finite() || f64::from(field[i]).abs() > MAX_LOG_GAIN+1e-8 { return Err(PIXEL_ERROR); }
    }
    for i in 0..n {
        if i%256 == 0 { poll(&mut cancel)?; }
        let rgb = [current[3*i],current[3*i+1],current[3*i+2]];
        if !rgb.iter().copied().all(unit) { return Err(PIXEL_ERROR); }
        let x = tile.x+i%tile.width; let y = tile.y+i/tile.width;
        let delta = if x >= field_window.x && y >= field_window.y
            && x < field_window.x+field_window.width && y < field_window.y+field_window.height {
            f64::from(amount)*f64::from(field[(y-field_window.y)*field_window.width+x-field_window.x])
        } else { 0.0 };
        output[3*i..3*i+3].copy_from_slice(&adjusted(rgb,delta)?);
    }
    poll(&mut cancel)
}

fn span<T>(pointer: *const T, length: usize) -> Result<(usize,usize),i32> {
    let start = pointer as usize;
    let bytes = length.checked_mul(mem::size_of::<T>()).ok_or(ABI_ERROR)?;
    if pointer.is_null() || start%mem::align_of::<T>() != 0 || bytes > isize::MAX as usize { return Err(ABI_ERROR); }
    Ok((start,start.checked_add(bytes).ok_or(ABI_ERROR)?))
}
fn overlaps(a: (usize,usize), b: (usize,usize)) -> bool { a.0 < b.1 && b.0 < a.1 }
fn result_code(result: std::thread::Result<Result<(),i32>>) -> i32 {
    match result { Ok(Ok(())) => 0, Ok(Err(code)) => code, Err(_) => PANIC_ERROR }
}
#[no_mangle]
pub extern "C" fn lrt_collarbone_abi() -> u32 { 1 }

/// # Safety
/// Live aligned pointers/lengths, immutable inputs, exclusive non-overlapping
/// outputs. Callback cannot unwind/reenter/mutate inputs. Discard every output on
/// any nonzero status. Panic containment does not make invalid pointers safe.
#[no_mangle]
pub unsafe extern "C" fn lrt_collarbone_prepare_v1(
    reference: *const f32, reference_len: usize, coverage: *const f32, coverage_len: usize,
    source_width: usize, source_height: usize, window_x: usize, window_y: usize,
    window_width: usize, window_height: usize,
    points: *const f64, points_len: usize, counts: *const u32, counts_len: usize,
    widths: *const f64, widths_len: usize,
    output_x: usize, output_y: usize, output_width: usize, output_height: usize,
    field: *mut f32, field_len: usize, stats: *mut u64, stats_len: usize,
    cancel: Cancel, context: *mut c_void,
) -> i32 {
    result_code(panic::catch_unwind(panic::AssertUnwindSafe(|| -> Result<(),i32> {
        dimensions(source_width,source_height)?;
        let window = Rect { x:window_x,y:window_y,width:window_width,height:window_height };
        let out = Rect { x:output_x,y:output_y,width:output_width,height:output_height };
        let n = rect_in(window,source_width,source_height)?; let out_n = rect_in(out,source_width,source_height)?;
        if reference_len != 3*n || coverage_len != n || field_len != out_n || stats_len != STATS_LEN
            || !(1..=2).contains(&counts_len) || widths_len != counts_len || points_len > 32 || points_len < 6 { return Err(ABI_ERROR); }
        let outputs = [span(field,field_len)?,span(stats,stats_len)?];
        if overlaps(outputs[0],outputs[1]) { return Err(ABI_ERROR); }
        for input in [span(reference,reference_len)?,span(coverage,coverage_len)?,span(points,points_len)?,span(counts,counts_len)?,span(widths,widths_len)?] {
            if outputs.iter().any(|&output| overlaps(input,output)) { return Err(ABI_ERROR); }
        }
        let count_values = slice::from_raw_parts(counts,counts_len);
        if !count_values.iter().all(|&v| (3..=8).contains(&v)) || count_values.iter().map(|&v|v as usize).sum::<usize>()*2 != points_len { return Err(SETTINGS_ERROR); }
        let xy = slice::from_raw_parts(points,points_len); let ws = slice::from_raw_parts(widths,widths_len);
        let mut traces = Vec::new(); traces.try_reserve_exact(counts_len).map_err(|_|RESOURCE_ERROR)?;
        let mut cursor = 0;
        for j in 0..counts_len {
            let mut vertices = Vec::new(); vertices.try_reserve_exact(count_values[j] as usize).map_err(|_|RESOURCE_ERROR)?;
            for _ in 0..count_values[j] {
                vertices.push(Point { x:xy[cursor]*source_width as f64 - 0.5,y:xy[cursor+1]*source_height as f64 - 0.5 }); cursor += 2;
            }
            traces.push(Trace { points:vertices,half_width:ws[j]*source_width.min(source_height) as f64 });
        }
        let mut report = [0_u64;STATS_LEN];
        prepare_into(slice::from_raw_parts(reference,reference_len),slice::from_raw_parts(coverage,coverage_len),
            window,source_width,source_height,&traces,out,slice::from_raw_parts_mut(field,field_len),&mut report,
            || cancel.map_or(false,|f|f(context)!=0))?;
        slice::from_raw_parts_mut(stats,stats_len).copy_from_slice(&report);
        Ok(())
    })))
}
/// # Safety
/// Same buffer/callback contract as prepare. Output must not overlap either input.
#[no_mangle]
pub unsafe extern "C" fn lrt_collarbone_compose_v1(
    current: *const f32, current_len: usize, tile_x: usize, tile_y: usize, tile_width: usize, tile_height: usize,
    field: *const f32, field_len: usize, field_x: usize, field_y: usize, field_width: usize, field_height: usize,
    source_width: usize, source_height: usize, amount: f32, output: *mut f32, output_len: usize,
    cancel: Cancel, context: *mut c_void,
) -> i32 {
    result_code(panic::catch_unwind(panic::AssertUnwindSafe(|| -> Result<(),i32> {
        dimensions(source_width,source_height)?;
        let tile = Rect {x:tile_x,y:tile_y,width:tile_width,height:tile_height};
        let window = Rect {x:field_x,y:field_y,width:field_width,height:field_height};
        let n = rect_in(tile,source_width,source_height)?; let f = rect_in(window,source_width,source_height)?;
        if current_len != 3*n || output_len != 3*n || field_len != f { return Err(ABI_ERROR); }
        let output_span = span(output,output_len)?;
        if overlaps(output_span,span(current,current_len)?) || overlaps(output_span,span(field,field_len)?) { return Err(ABI_ERROR); }
        compose_into(slice::from_raw_parts(current,current_len),tile,slice::from_raw_parts(field,field_len),window,
            source_width,source_height,amount,slice::from_raw_parts_mut(output,output_len),
            || cancel.map_or(false,|f|f(context)!=0))
    })))
}

#[cfg(test)]
mod tests;
