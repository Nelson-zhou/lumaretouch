// SPDX-License-Identifier: GPL-3.0-or-later
//! Original bounded donor-expression alignment and multiband fusion, ABI 1.
//! Not identity recognition, expression generation, inference, or an image decoder.
//! Source-only foundation. Every authored fixture is UNRUN; see ABI.md.
use std::{mem, panic::{catch_unwind, AssertUnwindSafe}, slice};

pub const MAX_SIDE: usize = 1024;
pub const MAX_PIXELS: usize = MAX_SIDE * MAX_SIDE;
pub const LANDMARK_FLOATS: usize = 478 * 3;
pub const RECEIPT_FLOATS: usize = 16;
pub const REQUIRED_REVIEWS: u32 = 127;
const MAX_LEVELS: usize = 5;
const ANCHORS: [(usize, f64); 8] = [
    (127, 1.0), (356, 1.0), (234, 1.0), (454, 1.0),
    (168, 2.0), (6, 2.0), (197, 2.0), (4, 2.0),
];
const LEFT_EYE: [usize; 8] = [33, 133, 160, 158, 153, 144, 159, 145];
const RIGHT_EYE: [usize; 8] = [263, 362, 387, 385, 380, 373, 386, 374];
const LIPS: [usize; 8] = [61, 291, 0, 17, 13, 14, 78, 308];
const BAD_ABI: i32 = 1;
const BAD_DATA: i32 = 2;
const REVIEW_REQUIRED: i32 = 3;
const BAD_POSE: i32 = 4;
const BAD_ALIGNMENT: i32 = 5;
const BAD_SUPPORT: i32 = 6;
const BAD_COLOUR: i32 = 7;
const RESOURCE: i32 = 8;
const CANCELLED: i32 = 9;
const PANIC: i32 = 10;
pub type Cancel = Option<extern "C" fn() -> i32>;
type Span = (usize, usize);

fn poll(cancel: Cancel) -> Result<(), i32> {
    if cancel.map_or(false, |f| f() != 0) { Err(CANCELLED) } else { Ok(()) }
}
fn unit(v: f32) -> bool { v.is_finite() && (0.0..=1.0).contains(&v) }
fn zeros(n: usize) -> Result<Vec<f32>, i32> {
    let mut v = Vec::new();
    v.try_reserve_exact(n).map_err(|_| RESOURCE)?;
    v.resize(n, 0.0);
    Ok(v)
}
fn copy(v: &[f32]) -> Result<Vec<f32>, i32> {
    let mut result = zeros(v.len())?;
    result.copy_from_slice(v);
    Ok(result)
}
fn count(w: usize, h: usize) -> Result<usize, i32> {
    if w < 2 || h < 2 || w > MAX_SIDE || h > MAX_SIDE { return Err(BAD_ABI); }
    w.checked_mul(h).filter(|&n| n <= MAX_PIXELS).ok_or(RESOURCE)
}
// Arithmetic/address checks cannot establish whether the claimed allocation is live.
fn span(p: *const f32, n: usize) -> Result<Span, i32> {
    let a = p as usize;
    let bytes = n.checked_mul(mem::size_of::<f32>()).ok_or(BAD_ABI)?;
    if p.is_null() || a % mem::align_of::<f32>() != 0 || bytes > isize::MAX as usize {
        return Err(BAD_ABI);
    }
    Ok((a, a.checked_add(bytes).ok_or(BAD_ABI)?))
}
fn disjoint(inputs: &[Span], outputs: &[Span]) -> Result<(), i32> {
    let overlap = |a: Span, b: Span| a.0 < b.1 && b.0 < a.1;
    for (i, &out) in outputs.iter().enumerate() {
        if inputs.iter().any(|&v| overlap(v, out))
            || outputs[..i].iter().any(|&v| overlap(v, out)) { return Err(BAD_ABI); }
    }
    Ok(())
}
fn validate_pixels(rgba: &[f32], cancel: Cancel) -> Result<(), i32> {
    for (i, p) in rgba.chunks_exact(4).enumerate() {
        if i % 4096 == 0 { poll(cancel)?; }
        if p[3] != 1.0 || !p[..3].iter().copied().all(unit) { return Err(BAD_DATA); }
    }
    Ok(())
}
fn validate_landmarks(lm: &[f32]) -> Result<(), i32> {
    if lm.len() != LANDMARK_FLOATS || lm.chunks_exact(3).any(|p|
        !unit(p[0]) || !unit(p[1]) || !p[2].is_finite() || p[2].abs() > 2.0) {
        return Err(BAD_DATA);
    }
    Ok(())
}
fn validate_reviews(reviews: u32) -> Result<(), i32> {
    // Authenticity and human visual review are caller assertions, not inferred identity.
    if reviews != REQUIRED_REVIEWS { Err(REVIEW_REQUIRED) } else { Ok(()) }
}
#[derive(Clone, Copy, Debug)]
struct Point { x: f64, y: f64 }
fn point(lm: &[f32], i: usize, w: usize, h: usize) -> Point {
    Point { x: lm[3*i] as f64 * (w-1) as f64, y: lm[3*i+1] as f64 * (h-1) as f64 }
}
#[derive(Clone, Copy, Debug)]
struct Profile2d { roll: f64, lateral_nose: f64, vertical_nose: f64, aspect: f64 }
fn profile_2d(lm: &[f32], w: usize, h: usize) -> Result<Profile2d, i32> {
    let left = point(lm, 234, w, h); let right = point(lm, 454, w, h);
    let top = point(lm, 10, w, h); let chin = point(lm, 152, w, h);
    let nose = point(lm, 4, w, h);
    let (ux, uy) = (right.x-left.x, right.y-left.y);
    let (vx, vy) = (chin.x-top.x, chin.y-top.y);
    let width = ux.hypot(uy); let height = vx.hypot(vy);
    if width < 16.0 || height < 24.0 || ux*vy-uy*vx <= 0.0
        || (ux*vx+uy*vy).abs() > 0.45*width*height { return Err(BAD_POSE); }
    let p = Profile2d { roll: uy.atan2(ux).to_degrees(),
        lateral_nose: ((nose.x-left.x)*ux+(nose.y-left.y)*uy)/(width*width),
        vertical_nose: ((nose.x-top.x)*vx+(nose.y-top.y)*vy)/(height*height),
        aspect: width/height };
    // These are measured image-shape gates, NOT estimates of yaw or pitch.
    if p.roll.abs() > 45.0 || !(0.30..=0.70).contains(&p.lateral_nose)
        || !(0.35..=0.75).contains(&p.vertical_nose) || !(0.45..=1.5).contains(&p.aspect) {
        return Err(BAD_POSE);
    }
    Ok(p)
}
fn compatible_2d(target: &[f32], donor: &[f32], tw: usize, th: usize, dw: usize, dh: usize)
    -> Result<(), i32> {
    let t = profile_2d(target,tw,th)?; let d = profile_2d(donor,dw,dh)?;
    if (t.roll-d.roll).abs() > 15.0 || (t.lateral_nose-d.lateral_nose).abs() > 0.08
        || (t.vertical_nose-d.vertical_nose).abs() > 0.08
        || (t.aspect/d.aspect-1.0).abs() > 0.20 { return Err(BAD_POSE); }
    Ok(())
}
#[derive(Clone, Copy, Debug)]
struct Similarity { a: f64, b: f64, tx: f64, ty: f64, rms: f64, maximum: f64 }
impl Similarity {
    fn forward(self, p: Point) -> Point {
        Point { x: self.a*p.x-self.b*p.y+self.tx, y: self.b*p.x+self.a*p.y+self.ty }
    }
    fn inverse(self, p: Point) -> Point {
        let d = self.a*self.a+self.b*self.b;
        let x = p.x-self.tx; let y = p.y-self.ty;
        Point { x: (self.a*x+self.b*y)/d, y: (-self.b*x+self.a*y)/d }
    }
    fn scale(self) -> f64 { self.a.hypot(self.b) }
    fn angle(self) -> f64 { self.b.atan2(self.a).to_degrees() }
}
fn fit(target: &[f32], donor: &[f32], tw: usize, th: usize, dw: usize, dh: usize)
    -> Result<Similarity, i32> {
    let mut tc = Point { x: 0.0, y: 0.0 }; let mut dc = tc; let mut mass = 0.0;
    for (i, weight) in ANCHORS {
        let t = point(target, i, tw, th); let d = point(donor, i, dw, dh);
        tc.x += weight*t.x; tc.y += weight*t.y;
        dc.x += weight*d.x; dc.y += weight*d.y; mass += weight;
    }
    tc.x /= mass; tc.y /= mass; dc.x /= mass; dc.y /= mass;
    let (mut xx, mut xy, mut yx, mut yy, mut denom) = (0.0, 0.0, 0.0, 0.0, 0.0);
    let mut dt = [0.0; 3]; let mut tt = [0.0; 3];
    for (i, weight) in ANCHORS {
        let t = point(target, i, tw, th); let d = point(donor, i, dw, dh);
        let (dx, dy, tx, ty) = (d.x-dc.x, d.y-dc.y, t.x-tc.x, t.y-tc.y);
        xx += weight*dx*tx; xy += weight*dx*ty;
        yx += weight*dy*tx; yy += weight*dy*ty;
        denom += weight*(dx*dx+dy*dy);
        dt[0] += weight*dx*dx; dt[1] += weight*dx*dy; dt[2] += weight*dy*dy;
        tt[0] += weight*tx*tx; tt[1] += weight*tx*ty; tt[2] += weight*ty*ty;
    }
    // Reject collinear/tiny geometry and reflection, not merely a small denominator.
    for covariance in [dt, tt] {
        let trace = covariance[0]+covariance[2];
        if trace < mass*16.0 || covariance[0]*covariance[2]-covariance[1]*covariance[1]
            < 0.01*trace*trace { return Err(BAD_ALIGNMENT); }
    }
    if xx*yy-xy*yx <= 0.0 || denom <= 0.0 { return Err(BAD_ALIGNMENT); }
    let a = (xx+yy)/denom; let b = (xy-yx)/denom;
    let mut s = Similarity { a, b, tx: tc.x-a*dc.x+b*dc.y,
        ty: tc.y-b*dc.x-a*dc.y, rms: 0.0, maximum: 0.0 };
    if ANCHORS.iter().all(|&(i, _)| {
        let t = point(target, i, tw, th); let d = point(donor, i, dw, dh);
        t.x == d.x && t.y == d.y
    }) { s.a = 1.0; s.b = 0.0; s.tx = 0.0; s.ty = 0.0; }
    if !(0.75..=4.0/3.0).contains(&s.scale()) || s.angle().abs() > 15.0 {
        return Err(BAD_ALIGNMENT);
    }
    let mut square_error = 0.0;
    for (i, weight) in ANCHORS {
        let t = point(target, i, tw, th); let mapped = s.forward(point(donor, i, dw, dh));
        let error = (t.x-mapped.x).hypot(t.y-mapped.y);
        square_error += weight*error*error; s.maximum = s.maximum.max(error);
    }
    s.rms = (square_error/mass).sqrt();
    let left = point(target, 234, tw, th); let right = point(target, 454, tw, th);
    let face_width = (left.x-right.x).hypot(left.y-right.y);
    if face_width < 16.0 || s.rms > (0.035*face_width).max(1.5)
        || s.maximum > (0.07*face_width).max(3.0) { return Err(BAD_ALIGNMENT); }
    Ok(s)
}
#[derive(Clone, Copy)]
struct Bounds { x0: f64, y0: f64, x1: f64, y1: f64 }
fn expressive_bounds(lm: &[f32], ids: &[usize], w: usize, h: usize) -> Bounds {
    let mut b = Bounds { x0: f64::INFINITY, y0: f64::INFINITY,
        x1: f64::NEG_INFINITY, y1: f64::NEG_INFINITY };
    for &id in ids {
        let p = point(lm, id, w, h);
        b.x0 = b.x0.min(p.x); b.x1 = b.x1.max(p.x);
        b.y0 = b.y0.min(p.y); b.y1 = b.y1.max(p.y);
    }
    let pad = (0.15*(b.x1-b.x0).max(b.y1-b.y0)).max(2.0);
    Bounds { x0: b.x0-pad, y0: b.y0-pad, x1: b.x1+pad, y1: b.y1+pad }
}
fn expressive(p: Point, bounds: &[Bounds; 3]) -> bool {
    bounds.iter().any(|b| p.x >= b.x0 && p.x <= b.x1 && p.y >= b.y0 && p.y <= b.y1)
}
fn features(lm: &[f32], w: usize, h: usize) -> [Bounds; 3] {
    [expressive_bounds(lm, &LEFT_EYE, w, h), expressive_bounds(lm, &RIGHT_EYE, w, h),
        expressive_bounds(lm, &LIPS, w, h)]
}
// Bilinear pixel-centre sampling never clamps a requested point into the donor.
fn taps(p: Point, w: usize, h: usize) -> Result<[(usize, f64); 4], i32> {
    if !p.x.is_finite() || !p.y.is_finite() || p.x < 0.0 || p.y < 0.0
        || p.x > (w-1) as f64 || p.y > (h-1) as f64 { return Err(BAD_SUPPORT); }
    let x0 = p.x.floor() as usize; let y0 = p.y.floor() as usize;
    let x1 = (x0+1).min(w-1); let y1 = (y0+1).min(h-1);
    let (fx, fy) = (p.x-x0 as f64, p.y-y0 as f64);
    Ok([(y0*w+x0, (1.0-fx)*(1.0-fy)), (y0*w+x1, fx*(1.0-fy)),
        (y1*w+x0, (1.0-fx)*fy), (y1*w+x1, fx*fy)])
}
fn sample(source: &[f32], allowed: &[f32], protected: &[f32],
    taps: &[(usize, f64); 4]) -> Result<([f32; 3], f32), i32> {
    let mut rgb = [0.0_f64; 3]; let mut cap = 1.0_f32;
    for &(i, weight) in taps {
        if weight == 0.0 { continue; }
        if protected[i] > 0.0 || allowed[i] <= 0.0 { return Err(BAD_SUPPORT); }
        cap = cap.min(allowed[i]);
        for c in 0..3 { rgb[c] += source[4*i+c] as f64*weight; }
    }
    Ok(([rgb[0] as f32, rgb[1] as f32, rgb[2] as f32], cap))
}

struct Level { width: usize, height: usize, channels: usize, data: Vec<f32> }
fn blur_down(input: &Level, cancel: Cancel) -> Result<Level, i32> {
    let (w, h, channels) = (input.width, input.height, input.channels);
    let mut horizontal = zeros(w*h*channels)?;
    let kernel = [1.0_f64, 4.0, 6.0, 4.0, 1.0];
    for y in 0..h {
        poll(cancel)?;
        for x in 0..w {
            for c in 0..channels {
                let mut sum = 0.0;
                for (k, &weight) in kernel.iter().enumerate() {
                    let sx = (x as isize+k as isize-2).clamp(0, w as isize-1) as usize;
                    sum += weight*input.data[(y*w+sx)*channels+c] as f64;
                }
                horizontal[(y*w+x)*channels+c] = (sum/16.0) as f32;
            }
        }
    }
    let (nw, nh) = ((w+1)/2, (h+1)/2);
    let mut result = Level { width: nw, height: nh, channels, data: zeros(nw*nh*channels)? };
    for y in 0..nh {
        poll(cancel)?;
        for x in 0..nw {
            for c in 0..channels {
                let mut sum = 0.0;
                for (k, &weight) in kernel.iter().enumerate() {
                    let sy = (2*y as isize+k as isize-2).clamp(0, h as isize-1) as usize;
                    sum += weight*horizontal[(sy*w+2*x)*channels+c] as f64;
                }
                result.data[(y*nw+x)*channels+c] = (sum/16.0) as f32;
            }
        }
    }
    Ok(result)
}
fn pyramid(base: Level, levels: usize, cancel: Cancel) -> Result<Vec<Level>, i32> {
    let mut result = Vec::new();
    result.try_reserve_exact(levels).map_err(|_| RESOURCE)?;
    result.push(base);
    for _ in 1..levels {
        let previous = result.last().ok_or(BAD_ABI)?;
        if previous.width < 2 || previous.height < 2 { return Err(BAD_ABI); }
        let next = blur_down(previous, cancel)?;
        result.push(next);
    }
    Ok(result)
}
fn expanded(level: &Level, x: usize, y: usize, c: usize) -> f64 {
    let (fx, fy) = (x as f64*0.5, y as f64*0.5);
    let x0 = (fx as usize).min(level.width-1); let y0 = (fy as usize).min(level.height-1);
    let x1 = (x0+1).min(level.width-1); let y1 = (y0+1).min(level.height-1);
    let (dx, dy) = (fx-fx.floor(), fy-fy.floor());
    let at = |x, y| level.data[(y*level.width+x)*level.channels+c] as f64;
    (at(x0,y0)*(1.0-dx)+at(x1,y0)*dx)*(1.0-dy)
        +(at(x0,y1)*(1.0-dx)+at(x1,y1)*dx)*dy
}
fn multiband(target: Vec<f32>, donor: Vec<f32>, mask: Vec<f32>,
    w: usize, h: usize, levels: usize, cancel: Cancel) -> Result<Vec<f32>, i32> {
    let target = pyramid(Level { width: w, height: h, channels: 3, data: target }, levels, cancel)?;
    let donor = pyramid(Level { width: w, height: h, channels: 3, data: donor }, levels, cancel)?;
    let masks = pyramid(Level { width: w, height: h, channels: 1, data: mask }, levels, cancel)?;
    let last = levels-1;
    let mut merged = Level { width: target[last].width, height: target[last].height,
        channels: 3, data: zeros(target[last].data.len())? };
    for i in 0..merged.width*merged.height {
        if i % 4096 == 0 { poll(cancel)?; }
        let m = masks[last].data[i] as f64;
        for c in 0..3 {
            let j = 3*i+c;
            merged.data[j] = (target[last].data[j] as f64*(1.0-m)+donor[last].data[j] as f64*m) as f32;
        }
    }
    for level in (0..last).rev() {
        let t = &target[level]; let d = &donor[level]; let m = &masks[level];
        let mut fine = Level { width: t.width, height: t.height, channels: 3, data: zeros(t.data.len())? };
        for y in 0..t.height {
            poll(cancel)?;
            for x in 0..t.width {
                let i = y*t.width+x; let weight = m.data[i] as f64;
                for c in 0..3 {
                    let t_band = t.data[3*i+c] as f64-expanded(&target[level+1], x, y, c);
                    let d_band = d.data[3*i+c] as f64-expanded(&donor[level+1], x, y, c);
                    fine.data[3*i+c] = (expanded(&merged, x, y, c)
                        +t_band*(1.0-weight)+d_band*weight) as f32;
                }
            }
        }
        merged = fine;
    }
    Ok(merged.data)
}

struct Inputs<'a> {
    target: &'a [f32], donor: &'a [f32], target_landmarks: &'a [f32], donor_landmarks: &'a [f32],
    target_allowed: &'a [f32], donor_allowed: &'a [f32], target_protection: &'a [f32],
    donor_protection: &'a [f32], fusion: &'a [f32], colour_reference: &'a [f32],
    tw: usize, th: usize, dw: usize, dh: usize, reviews: u32, density: f32,
    colour_strength: f32, levels: usize, cancel: Cancel,
}
fn render(input: &Inputs<'_>) -> Result<(Vec<f32>, Vec<f32>, [f32; RECEIPT_FLOATS]), i32> {
    let n = count(input.tw, input.th)?; let dn = count(input.dw, input.dh)?;
    if input.target.len() != n*4 || input.donor.len() != dn*4
        || input.target_allowed.len() != n || input.target_protection.len() != n
        || input.fusion.len() != n
        || (input.colour_reference.len() != n && !(input.colour_strength == 0.0 && input.colour_reference.is_empty()))
        || input.donor_allowed.len() != dn || input.donor_protection.len() != dn
        || !unit(input.density) || !unit(input.colour_strength)
        || !(1..=MAX_LEVELS).contains(&input.levels) { return Err(BAD_ABI); }
    // Validate level geometry even on the neutral branch.
    let (mut w, mut h) = (input.tw, input.th);
    for _ in 1..input.levels {
        if w < 2 || h < 2 { return Err(BAD_ABI); }
        w = (w+1)/2; h = (h+1)/2;
    }
    poll(input.cancel)?;
    validate_reviews(input.reviews)?;
    validate_pixels(input.target, input.cancel)?; validate_pixels(input.donor, input.cancel)?;
    validate_landmarks(input.target_landmarks)?; validate_landmarks(input.donor_landmarks)?;
    compatible_2d(input.target_landmarks,input.donor_landmarks,input.tw,input.th,input.dw,input.dh)?;
    for values in [input.target_allowed, input.donor_allowed, input.target_protection,
        input.donor_protection, input.fusion, input.colour_reference] {
        for (i, &v) in values.iter().enumerate() {
            if i % 4096 == 0 { poll(input.cancel)?; }
            if !unit(v) { return Err(BAD_DATA); }
        }
    }
    let transform = fit(input.target_landmarks, input.donor_landmarks,
        input.tw, input.th, input.dw, input.dh)?;
    let mut receipt = [0.0; RECEIPT_FLOATS];
    receipt[..8].copy_from_slice(&[transform.a as f32, transform.b as f32, transform.tx as f32,
        transform.ty as f32, transform.scale() as f32, transform.angle() as f32,
        transform.rms as f32, transform.maximum as f32]);
    receipt[13] = input.levels as f32; receipt[14] = input.density; receipt[15] = input.colour_strength;
    let mut active = false;
    for i in 0..n {
        if i % 4096 == 0 { poll(input.cancel)?; }
        if input.fusion[i] > input.target_allowed[i] || input.colour_reference.get(i).copied().unwrap_or(0.0) > input.target_allowed[i] {
            return Err(BAD_SUPPORT);
        }
        active |= input.fusion[i] > 0.0 && input.target_protection[i] == 0.0;
    }
    // No blending or quantization on a valid neutral call.
    if input.density == 0.0 || !active { return Ok((copy(input.target)?, zeros(n)?, receipt)); }
    let target_features = features(input.target_landmarks, input.tw, input.th);
    let donor_features = features(input.donor_landmarks, input.dw, input.dh);
    let mut target_rgb = zeros(n*3)?; let mut donor_rgb = zeros(n*3)?; let mut coverage = zeros(n)?;
    let mut colour_sum = [0.0_f64; 3]; let mut colour_mass = 0.0;
    let mut minimum = [1.0_f64; 3]; let mut maximum = [0.0_f64; 3];
    for y in 0..input.th {
        poll(input.cancel)?;
        for x in 0..input.tw {
            let i = y*input.tw+x;
            target_rgb[3*i..3*i+3].copy_from_slice(&input.target[4*i..4*i+3]);
            donor_rgb[3*i..3*i+3].copy_from_slice(&input.target[4*i..4*i+3]);
            if input.target_protection[i] > 0.0 { continue; }
            let edit = input.fusion[i];
            let colour_weight = if input.colour_strength > 0.0 { input.colour_reference[i] } else { 0.0 };
            if edit == 0.0 && colour_weight == 0.0 { continue; }
            let p = Point { x: x as f64, y: y as f64 }; let dp = transform.inverse(p);
            let (rgb, cap) = sample(input.donor, input.donor_allowed, input.donor_protection,
                &taps(dp, input.dw, input.dh)?)?;
            if colour_weight > 0.0 {
                if expressive(p, &target_features) || expressive(dp, &donor_features) { return Err(BAD_COLOUR); }
                let weight = colour_weight.min(cap) as f64;
                colour_mass += weight;
                for c in 0..3 { colour_sum[c] += weight*(input.target[4*i+c] as f64-rgb[c] as f64); }
            }
            if edit > 0.0 {
                coverage[i] = edit.min(cap);
                donor_rgb[3*i..3*i+3].copy_from_slice(&rgb);
                for c in 0..3 { minimum[c] = minimum[c].min(rgb[c] as f64); maximum[c] = maximum[c].max(rgb[c] as f64); }
            }
        }
    }
    let mut offsets = [0.0_f32; 3];
    if input.colour_strength > 0.0 {
        if colour_mass < 16.0 { return Err(BAD_COLOUR); }
        for c in 0..3 {
            let difference = colour_sum[c]/colour_mass;
            if difference.abs() > 0.20 { return Err(BAD_COLOUR); }
            // Offset is bounded and reduced before applying, never clipped per pixel.
            offsets[c] = (difference.clamp(-0.06, 0.06)*input.colour_strength as f64)
                .clamp(-minimum[c], 1.0-maximum[c]) as f32;
            receipt[8+c] = offsets[c];
        }
    }
    let mut identical = true;
    for i in 0..n {
        if i % 4096 == 0 { poll(input.cancel)?; }
        if coverage[i] == 0.0 { continue; }
        for c in 0..3 {
            let j = 3*i+c;
            donor_rgb[j] = (donor_rgb[j] as f64+offsets[c] as f64) as f32;
            if !unit(donor_rgb[j]) { return Err(BAD_COLOUR); }
            identical &= donor_rgb[j] == target_rgb[j];
        }
    }
    if identical {
        for (i, value) in coverage.iter_mut().enumerate() {
            if i % 4096 == 0 { poll(input.cancel)?; }
            *value *= input.density;
        }
        return Ok((copy(input.target)?, coverage, receipt));
    }
    let fused = multiband(target_rgb, donor_rgb, copy(&coverage)?, input.tw, input.th, input.levels, input.cancel)?;
    let mut output = copy(input.target)?;
    for i in 0..n {
        if i % 4096 == 0 { poll(input.cancel)?; }
        if coverage[i] == 0.0 { continue; }
        let mut delta = [0.0_f64; 3]; let mut limit = 1.0_f64;
        for c in 0..3 {
            let base = input.target[4*i+c] as f64;
            delta[c] = fused[3*i+c] as f64-base;
            if !delta[c].is_finite() { return Err(BAD_DATA); }
            if delta[c] > 0.0 { limit = limit.min((1.0-base)/delta[c]); }
            if delta[c] < 0.0 { limit = limit.min(-base/delta[c]); }
        }
        if limit < 1.0 { receipt[12] += 1.0; }
        // Final hard support cap prevents Gaussian leakage into protected/erased pixels.
        // Density is applied once, linearly. Fusion also caps the spectral result.
        let alpha = input.density as f64*coverage[i] as f64*limit;
        let mut changed = false;
        for c in 0..3 {
            let value = (input.target[4*i+c] as f64+alpha*delta[c]) as f32;
            if !unit(value) { return Err(BAD_DATA); }
            output[4*i+c] = value; changed |= value != input.target[4*i+c];
        }
        if changed { receipt[11] += 1.0; }
        coverage[i] *= input.density;
    }
    poll(input.cancel)?;
    Ok((output, coverage, receipt))
}

#[no_mangle]
pub extern "C" fn lrt_expression_blend_abi() -> u32 { 1 }
/// Declared algorithm features, not proof that an installed runtime passed QA.
#[no_mangle]
pub extern "C" fn lrt_expression_blend_capabilities_v1() -> u64 { 0x3f }
#[no_mangle]
pub extern "C" fn lrt_expression_blend_max_side_v1() -> usize { MAX_SIDE }
#[no_mangle]
pub extern "C" fn lrt_expression_blend_max_levels_v1() -> usize { MAX_LEVELS }

/// All lengths count float32 elements, not bytes. See expression_blend.h and ABI.md.
/// Every nonzero status leaves all three output buffers byte-for-byte unchanged.
/// # Safety
/// Caller owns initialized aligned readable input extents and exclusive writable
/// output extents for the synchronous call. Inputs remain immutable. Output may
/// not alias any input or another output. Callback must not unwind, reenter this core,
/// or mutate/release buffers. Pointer checks cannot validate allocation lifetime.
#[no_mangle]
pub unsafe extern "C" fn lrt_expression_blend_v1(
    target: *const f32, target_len: usize, target_width: usize, target_height: usize,
    donor: *const f32, donor_len: usize, donor_width: usize, donor_height: usize,
    target_landmarks: *const f32, target_landmarks_len: usize,
    donor_landmarks: *const f32, donor_landmarks_len: usize,
    target_allowed: *const f32, target_allowed_len: usize,
    donor_allowed: *const f32, donor_allowed_len: usize,
    target_protection: *const f32, target_protection_len: usize,
    donor_protection: *const f32, donor_protection_len: usize,
    fusion: *const f32, fusion_len: usize, colour_reference: *const f32, colour_reference_len: usize,
    reviews: u32, density: f32, colour_strength: f32,
    levels: usize, output: *mut f32, output_len: usize,
    effective_fusion: *mut f32, effective_fusion_len: usize, receipt: *mut f32, receipt_len: usize,
    cancel: Cancel,
) -> i32 {
    let result = catch_unwind(AssertUnwindSafe(|| -> Result<(), i32> {
        let n = count(target_width, target_height)?; let dn = count(donor_width, donor_height)?;
        let no_reference = colour_reference.is_null() && colour_reference_len == 0 && colour_strength == 0.0;
        if target_len != n*4 || donor_len != dn*4 || target_landmarks_len != LANDMARK_FLOATS
            || donor_landmarks_len != LANDMARK_FLOATS || target_allowed_len != n
            || donor_allowed_len != dn || target_protection_len != n || donor_protection_len != dn
            || fusion_len != n || (!no_reference && colour_reference_len != n)
            || output_len != n*4 || effective_fusion_len != n || receipt_len != RECEIPT_FLOATS { return Err(BAD_ABI); }
        let inputs = [span(target,target_len)?, span(donor,donor_len)?,
            span(target_landmarks,target_landmarks_len)?, span(donor_landmarks,donor_landmarks_len)?,
            span(target_allowed,n)?, span(donor_allowed,dn)?, span(target_protection,n)?,
            span(donor_protection,dn)?, span(fusion,n)?,
            if no_reference { (0,0) } else { span(colour_reference,n)? }];
        disjoint(&inputs, &[span(output,output_len)?, span(effective_fusion,effective_fusion_len)?,
            span(receipt,receipt_len)?])?;
        let input = Inputs {
            target: slice::from_raw_parts(target,target_len), donor: slice::from_raw_parts(donor,donor_len),
            target_landmarks: slice::from_raw_parts(target_landmarks,target_landmarks_len),
            donor_landmarks: slice::from_raw_parts(donor_landmarks,donor_landmarks_len),
            target_allowed: slice::from_raw_parts(target_allowed,n), donor_allowed: slice::from_raw_parts(donor_allowed,dn),
            target_protection: slice::from_raw_parts(target_protection,n), donor_protection: slice::from_raw_parts(donor_protection,dn),
            fusion: slice::from_raw_parts(fusion,n),
            colour_reference: if no_reference { &[] } else { slice::from_raw_parts(colour_reference,n) },
            tw: target_width, th: target_height,
            dw: donor_width, dh: donor_height, reviews, density, colour_strength, levels, cancel,
        };
        let (staged, mask, report) = render(&input)?;
        poll(cancel)?;
        // No fallible work or callback after publication begins.
        std::ptr::copy_nonoverlapping(staged.as_ptr(), output, output_len);
        std::ptr::copy_nonoverlapping(mask.as_ptr(), effective_fusion, effective_fusion_len);
        std::ptr::copy_nonoverlapping(report.as_ptr(), receipt, RECEIPT_FLOATS);
        Ok(())
    }));
    match result { Ok(Ok(())) => 0, Ok(Err(code)) => code, Err(_) => PANIC }
}

#[cfg(test)]
mod tests;
