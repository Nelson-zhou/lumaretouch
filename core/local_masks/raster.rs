//! Source-normalized local-mask raster math. No model/network/GUI dependencies.
use crate::wire::{Object, Shape, Tile, MAX_WORK};

fn inverse(axes: [[f64; 2]; 2], p: [f64; 2]) -> [f64; 2] {
    let det = axes[0][0] * axes[1][1] - axes[0][1] * axes[1][0];
    [(axes[1][1] * p[0] - axes[1][0] * p[1]) / det,
     (-axes[0][1] * p[0] + axes[0][0] * p[1]) / det]
}
fn linear(v: f64) -> f64 {
    if v <= 0.04045 { v / 12.92 } else { ((v + 0.055) / 1.055).powf(2.4) }
}
fn float_at(bytes: &[u8], offset: usize) -> f64 {
    f32::from_le_bytes(bytes[offset..offset+4].try_into().unwrap()) as f64
}
fn charge(work: &mut u64, amount: usize) -> Result<(), &'static str> {
    *work = work.checked_add(amount as u64).ok_or("local mask work overflow")?;
    if *work > MAX_WORK { Err("local mask work budget exceeded") } else { Ok(()) }
}

/// Continuous swept elliptical brush, max across segments, never stamp buildup.
fn brush(out: &mut [f32], points: &[[f64; 2]], axes: [[f64; 2]; 2],
         shape: Shape, tile: Tile, work: &mut u64) -> Result<(), &'static str> {
    let ex = axes[0][0].hypot(axes[1][0]) * shape.w as f64;
    let ey = axes[0][1].hypot(axes[1][1]) * shape.h as f64;
    for i in 0..points.len().saturating_sub(1).max(1) {
        let a = points[i];
        let b = points[(i+1).min(points.len()-1)];
        let xa = ((a[0].min(b[0]) * shape.w as f64 - 0.5 - ex).floor().max(tile.x as f64) as usize).min(tile.x+tile.w);
        let xb = ((a[0].max(b[0]) * shape.w as f64 - 0.5 + ex).ceil()+1.).max(tile.x as f64).min((tile.x+tile.w) as f64) as usize;
        let ya = ((a[1].min(b[1]) * shape.h as f64 - 0.5 - ey).floor().max(tile.y as f64) as usize).min(tile.y+tile.h);
        let yb = ((a[1].max(b[1]) * shape.h as f64 - 0.5 + ey).ceil()+1.).max(tile.y as f64).min((tile.y+tile.h) as f64) as usize;
        charge(work, xb.saturating_sub(xa)*yb.saturating_sub(ya))?;
        let delta = inverse(axes, [b[0]-a[0], b[1]-a[1]]);
        let length = delta[0]*delta[0]+delta[1]*delta[1];
        for y in ya..yb { for x in xa..xb {
            let u = inverse(axes, [(x as f64+0.5)/shape.w as f64-a[0], (y as f64+0.5)/shape.h as f64-a[1]]);
            let t = if length > 1e-20 { ((u[0]*delta[0]+u[1]*delta[1])/length).clamp(0.,1.) } else { 0. };
            let distance = (u[0]-t*delta[0]).hypot(u[1]-t*delta[1]);
            if distance <= 1. { out[(y-tile.y)*tile.w+x-tile.x] = 1.; }
        }}
    }
    Ok(())
}

/// Separable finite-support box feather. Replicate global-edge samples. Halo
/// pixels isolate the returned core from artificial per-tile boundaries.
fn feather(input: &[f32], w: usize, h: usize, radius: usize) -> Vec<f32> {
    let mut horizontal = vec![0f32; w*h];
    let divisor = (radius*2+1) as f64;
    for y in 0..h {
        let row = &input[y*w..(y+1)*w];
        let mut sum = row[0] as f64*(radius+1) as f64;
        for x in 1..=radius { sum += row[x.min(w-1)] as f64; }
        for x in 0..w {
            horizontal[y*w+x] = (sum/divisor) as f32;
            sum += row[(x+radius+1).min(w-1)] as f64;
            sum -= row[x.saturating_sub(radius)] as f64;
        }
    }
    let mut output = vec![0f32; w*h];
    for x in 0..w {
        let mut sum = horizontal[x] as f64*(radius+1) as f64;
        for y in 1..=radius { sum += horizontal[y.min(h-1)*w+x] as f64; }
        for y in 0..h {
            output[y*w+x] = (sum/divisor) as f32;
            sum += horizontal[(y+radius+1).min(h-1)*w+x] as f64;
            sum -= horizontal[y.saturating_sub(radius)*w+x] as f64;
        }
    }
    output
}

pub fn render(request: &crate::wire::Request<'_>, work: &mut u64) -> Result<Vec<u8>, &'static str> {
    let tile = request.tile;
    let shape = request.shape;
    let area = tile.w*tile.h;
    let mut composed = vec![0f32; tile.cw*tile.ch];
    for obj in &request.objects {
        let mut field = vec![0f32; area];
        if let Object::Brush { points, axes } = &obj.kind {
            brush(&mut field, points, *axes, shape, tile, work)?;
        } else {
            charge(work, area)?;
            for y in 0..tile.h { for x in 0..tile.w {
                let n = y*tile.w+x;
                let p = [(tile.x+x) as f64+0.5, (tile.y+y) as f64+0.5];
                let p = [p[0]/shape.w as f64, p[1]/shape.h as f64];
                let value = match &obj.kind {
                    Object::Full => 1.,
                    Object::Linear { start, end, cross } => {
                        inverse([[end[0]-start[0], end[1]-start[1]], *cross], [p[0]-start[0],p[1]-start[1]])[0].clamp(0.,1.)
                    },
                    Object::Radial { center, axes } => {
                        let u = inverse(*axes, [p[0]-center[0],p[1]-center[1]]);
                        (1.-u[0].hypot(u[1])).clamp(0.,1.)
                    },
                    Object::Color { color, tolerance } => {
                        let offset = request.rgb.ok_or("missing immutable source RGB")?+n*12;
                        let mut distance = 0.;
                        for (c, target) in color.iter().enumerate() {
                            let v = float_at(request.bytes, offset+c*4);
                            if !v.is_finite() { return Err("nonfinite immutable source RGB"); }
                            // Compare in the same f32 sampling domain, including
                            // zero tolerance for a selected uint8/uint16 colour.
                            let target = *target as f32 as f64;
                            distance += (v-target)*(v-target);
                        }
                        // Normalized encoded-sRGB Euclidean distance, not a Lab/Delta-E claim.
                        if (distance/3.).sqrt() <= *tolerance { 1. } else { 0. }
                    },
                    Object::Luminance { low, high } => {
                        let offset = request.rgb.ok_or("missing immutable source RGB")?+n*12;
                        let mut value = 0.;
                        for (c, coefficient) in [0.2126,0.7152,0.0722].iter().enumerate() {
                            let v = float_at(request.bytes, offset+c*4);
                            if !v.is_finite() { return Err("nonfinite immutable source RGB"); }
                            value += linear(v)*coefficient;
                        }
                        if value >= *low && value <= *high { 1. } else { 0. }
                    },
                    Object::Semantic { index } => {
                        let value = float_at(request.bytes, request.semantic[*index]+n*4);
                        if !value.is_finite() || !(0.0..=1.0).contains(&value) { return Err("invalid semantic source probability"); }
                        value
                    },
                    Object::Brush { .. } => unreachable!(),
                };
                field[n] = value as f32;
            }}
        }
        if obj.radius > 0 {
            // Two passes plus initialization loops (radius bounded by tile halo).
            charge(work, area*2 + obj.radius*(tile.w+tile.h))?;
            field = feather(&field, tile.w, tile.h, obj.radius);
        }
        charge(work, composed.len())?;
        for y in 0..tile.ch { for x in 0..tile.cw {
            let n = y*tile.cw+x;
            let value = (field[(y+tile.cy)*tile.w+x+tile.cx] as f64*obj.opacity).clamp(0.,1.) as f32;
            composed[n] = match obj.operation {
                0 => composed[n].max(value),
                1 => (composed[n]-value).max(0.),
                2 => composed[n].min(value),
                _ => return Err("unknown local mask operation"),
            };
        }}
    }
    Ok(composed.into_iter().map(|v|(v.clamp(0.,1.)*255.).round() as u8).collect())
}
