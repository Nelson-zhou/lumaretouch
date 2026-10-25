// SPDX-License-Identifier: GPL-3.0-or-later
//! Original source-grid creative-selection coverage. AUTHORED / UNRUN.
//! No third-party rasterizer, image dependencies, inference or proxy inputs.
//! See docs/creative-selection/{CORE,NUMERICS,ABI,ACCEPTANCE-UNRUN}.md.

use std::{ffi::c_void, mem, panic, ptr, slice};

pub const ABI_VERSION: u32 = 1;
pub const OK: i32 = 0;
pub const ABI_ERROR: i32 = 1;
pub const VALUE_ERROR: i32 = 2;
pub const LIMIT_ERROR: i32 = 3;
pub const CANCELLED: i32 = 4;
pub const ALLOCATION_ERROR: i32 = 5;
pub const PANIC_ERROR: i32 = 6;
pub const MAX_OPERATIONS: usize = 4096;
pub const MAX_POINTS: usize = 262_144;
pub const MAX_SOURCE_EDGE: u32 = 131_072;
pub const MAX_SOURCE_PIXELS: u64 = 1_u64 << 32;
pub const MAX_FEATHER: u32 = 256;
const MAX_COORDINATE: f64 = 1_048_576.0;
const MAX_WORKING_BYTES: u64 = 512 * 1024 * 1024;
const MAX_OUTPUT_PIXELS: u64 = 16_777_216;
const MAX_WORK_UNITS: u64 = 4_000_000_000;

#[repr(C)]
#[derive(Clone, Copy, Debug, Default)]
pub struct PointV1 { pub x: f64, pub y: f64 }

#[repr(C)]
#[derive(Clone, Copy, Debug, Default)]
pub struct OperationV1 {
    pub kind: u32, pub combine: u32, pub point_offset: u32, pub point_count: u32,
    pub x0: f64, pub y0: f64, pub x1: f64, pub y1: f64,
    pub diameter: f64, pub hardness: f64, pub opacity: f64,
}

#[repr(C)]
#[derive(Clone, Copy, Debug)]
pub struct RecipeV1 {
    pub abi_version: u32, pub struct_size: u32,
    pub source_width: u32, pub source_height: u32,
    pub operation_count: u32, pub point_count: u32,
    pub feather_radius: u32, pub reserved: u32,
    pub operations: *const OperationV1, pub points: *const PointV1,
}

#[repr(C)]
#[derive(Clone, Copy, Debug, Default)]
pub struct TileV1 { pub x: u32, pub y: u32, pub width: u32, pub height: u32 }

#[repr(C)]
#[derive(Clone, Copy, Debug)]
pub struct LimitsV1 {
    pub max_working_bytes: u64, pub max_output_pixels: u64, pub max_work_units: u64,
}
impl Default for LimitsV1 {
    fn default() -> Self {
        Self { max_working_bytes: 64 * 1024 * 1024,
               max_output_pixels: 1_048_576, max_work_units: 100_000_000 }
    }
}

#[repr(C)]
#[derive(Clone, Copy, Debug, Default)]
pub struct StatsV1 { pub working_bytes: u64, pub work_units: u64, pub output_pixels: u64 }
pub type CancelV1 = Option<unsafe extern "C" fn(*mut c_void) -> u32>;

struct Budget { limit: u64, used: u64, last_poll: u64, cancel: CancelV1, context: *mut c_void }
impl Budget {
    fn poll(&mut self) -> Result<(), i32> {
        self.last_poll = self.used;
        if let Some(callback) = self.cancel {
            // Caller guarantees the callback and its context are live, thread-safe
            // for this invocation, non-throwing, and do not mutate ABI spans.
            if unsafe { callback(self.context) } != 0 { return Err(CANCELLED); }
        }
        Ok(())
    }
    fn charge(&mut self, amount: u64) -> Result<(), i32> {
        self.used = self.used.checked_add(amount).ok_or(LIMIT_ERROR)?;
        if self.used > self.limit { return Err(LIMIT_ERROR); }
        if self.used - self.last_poll >= 4096 { self.poll()?; }
        Ok(())
    }
    fn sorting(&mut self, n: usize) -> Result<(), i32> {
        let levels = if n <= 1 { 0 } else { usize::BITS - (n - 1).leading_zeros() };
        self.charge((n as u64) * (levels as u64 + 1))?;
        self.poll()
    }
}

fn reserve<T>(capacity: usize) -> Result<Vec<T>, i32> {
    let mut values = Vec::new();
    values.try_reserve_exact(capacity).map_err(|_| ALLOCATION_ERROR)?;
    Ok(values)
}
fn zeros(count: usize) -> Result<Vec<f32>, i32> {
    let mut values = reserve(count)?;
    values.resize(count, 0.0);
    Ok(values)
}

#[derive(Clone, Copy)]
struct Edge { a: PointV1, b: PointV1 }
impl Edge {
    fn low(&self) -> f64 { self.a.y.min(self.b.y) }
    fn high(&self) -> f64 { self.a.y.max(self.b.y) }
    fn crossing(&self, y: f64) -> f64 {
        self.a.x + (y - self.a.y) / (self.b.y - self.a.y) * (self.b.x - self.a.x)
    }
}

#[derive(Clone, Copy)]
struct Segment { a: PointV1, b: PointV1, length2: f64 }
impl Segment {
    fn new(a: PointV1, b: PointV1) -> Self {
        let dx = b.x - a.x;
        let dy = b.y - a.y;
        Self { a, b, length2: dx * dx + dy * dy }
    }
    fn low(&self, r: f64) -> f64 { self.a.y.min(self.b.y) - r }
    fn high(&self, r: f64) -> f64 { self.a.y.max(self.b.y) + r }
    fn distance(&self, x: f64, y: f64) -> f64 {
        if self.length2 == 0.0 { return (x - self.a.x).hypot(y - self.a.y); }
        let dx = self.b.x - self.a.x;
        let dy = self.b.y - self.a.y;
        let t = (((x - self.a.x) * dx + (y - self.a.y) * dy) / self.length2).clamp(0.0, 1.0);
        (x - (self.a.x + t * dx)).hypot(y - (self.a.y + t * dy))
    }
    /// A capsule is two endpoint disks plus a central oriented rectangle.
    /// Its convex horizontal slice is one interval, not its large axis-aligned bbox.
    fn extent(&self, y: f64, radius: f64) -> Option<(f64, f64)> {
        let mut left = f64::INFINITY;
        let mut right = f64::NEG_INFINITY;
        for p in [self.a, self.b] {
            let v = (y - p.y) / radius;
            if v.abs() <= 1.0 {
                let dx = radius * (1.0 - v * v).max(0.0).sqrt();
                left = left.min(p.x - dx);
                right = right.max(p.x + dx);
            }
        }
        if self.length2 > 0.0 {
            let length = self.length2.sqrt();
            let nx = -(self.b.y - self.a.y) / length * radius;
            let ny = (self.b.x - self.a.x) / length * radius;
            let corners = [
                PointV1 { x: self.a.x + nx, y: self.a.y + ny },
                PointV1 { x: self.b.x + nx, y: self.b.y + ny },
                PointV1 { x: self.b.x - nx, y: self.b.y - ny },
                PointV1 { x: self.a.x - nx, y: self.a.y - ny },
            ];
            for i in 0..4 {
                let e = Edge { a: corners[i], b: corners[(i + 1) % 4] };
                if e.a.y == e.b.y {
                    if y == e.a.y { left = left.min(e.a.x.min(e.b.x)); right = right.max(e.a.x.max(e.b.x)); }
                } else if y >= e.low() && y < e.high() {
                    let x = e.crossing(y);
                    left = left.min(x); right = right.max(x);
                }
            }
        }
        if left <= right { Some((left, right)) } else { None }
    }
}

struct Scratch {
    mask: Vec<f32>, row: Vec<f32>, subrow: Vec<f32>, horizontal: Vec<f32>, result: Vec<f32>,
    edges: Vec<Edge>, segments: Vec<Segment>, active: Vec<usize>, hits: Vec<f64>,
}

#[derive(Clone, Copy)]
struct Patch { x: u32, y: u32, width: usize, height: usize }

fn finite_coordinate(x: f64) -> bool { x.is_finite() && x.abs() <= MAX_COORDINATE }
fn validate_operations(ops: &[OperationV1], points: &[PointV1], budget: &mut Budget) -> Result<usize, i32> {
    let mut largest = 0;
    for (i, p) in points.iter().enumerate() {
        if i % 4096 == 0 { budget.poll()?; }
        if !finite_coordinate(p.x) || !finite_coordinate(p.y) { return Err(VALUE_ERROR); }
    }
    budget.charge(points.len() as u64)?;
    for op in ops {
        budget.charge(1)?;
        if op.combine > 3 || ![op.x0, op.y0, op.x1, op.y1].iter().all(|&x| finite_coordinate(x))
            || !op.diameter.is_finite() || !op.hardness.is_finite() || !op.opacity.is_finite() {
            return Err(VALUE_ERROR);
        }
        let end = op.point_offset.checked_add(op.point_count).ok_or(VALUE_ERROR)? as usize;
        if end > points.len() { return Err(VALUE_ERROR); }
        largest = largest.max(op.point_count as usize);
        let no_box = op.x0 == 0.0 && op.y0 == 0.0 && op.x1 == 0.0 && op.y1 == 0.0;
        let no_brush = op.diameter == 0.0 && op.hardness == 0.0 && op.opacity == 0.0;
        let no_points = op.point_count == 0 && op.point_offset == 0;
        match op.kind {
            1 | 2 if no_points && no_brush && op.x0 <= op.x1 && op.y0 <= op.y1 => {},
            3 if no_box && no_brush && op.point_count >= 3 => {},
            4 if no_box && op.point_count >= 1 && (op.combine == 1 || op.combine == 2)
                && (1.0 / 64.0..=262_144.0).contains(&op.diameter)
                && (0.0..=1.0).contains(&op.hardness) && (0.0..=1.0).contains(&op.opacity) => {},
            5 if no_box && no_brush && no_points && op.combine == 0 => {},
            _ => return Err(VALUE_ERROR),
        }
    }
    Ok(largest)
}

fn memory_plan(patch: Patch, tile: TileV1, max_points: usize, feather: u32) -> Result<u64, i32> {
    let p = (patch.width as u64).checked_mul(patch.height as u64).ok_or(LIMIT_ERROR)?;
    let out = (tile.width as u64) * (tile.height as u64);
    let horizontal = if feather == 0 { 0 } else { tile.width as u64 * patch.height as u64 };
    // mask + row + four brush subpixel lanes + horizontal pass + transactional result.
    let floats = p.checked_add(patch.width as u64 * 5).and_then(|n| n.checked_add(horizontal))
        .and_then(|n| n.checked_add(out)).ok_or(LIMIT_ERROR)?;
    let geometry = (max_points as u64) * (mem::size_of::<Edge>() + mem::size_of::<Segment>()
        + mem::size_of::<usize>() + mem::size_of::<f64>()) as u64;
    floats.checked_mul(4).and_then(|n| n.checked_add(geometry)).ok_or(LIMIT_ERROR)
}

fn allocate(patch: Patch, tile: TileV1, max_points: usize, feather: u32) -> Result<Scratch, i32> {
    Ok(Scratch {
        mask: zeros(patch.width * patch.height)?, row: zeros(patch.width)?,
        subrow: zeros(patch.width * 4)?,
        horizontal: zeros(if feather == 0 { 0 } else { tile.width as usize * patch.height })?,
        result: zeros(tile.width as usize * tile.height as usize)?,
        edges: reserve(max_points)?, segments: reserve(max_points)?,
        active: reserve(max_points)?, hits: reserve(max_points)?,
    })
}

fn clipped_range(left: f64, right: f64, patch: Patch) -> (usize, usize) {
    let origin = patch.x as f64;
    let start = (left - origin).floor().max(0.0).min(patch.width as f64) as usize;
    let end = (right - origin).ceil().max(0.0).min(patch.width as f64) as usize;
    (start, end.max(start))
}

fn add_interval(row: &mut [f32], patch: Patch, left: f64, right: f64, weight: f64,
                budget: &mut Budget) -> Result<(), i32> {
    if right <= left { return Ok(()); }
    let (start, end) = clipped_range(left, right, patch);
    budget.charge((end - start) as u64)?;
    for (i, value) in row.iter_mut().enumerate().take(end).skip(start) {
        if i % 4096 == 0 { budget.poll()?; }
        let x = patch.x as f64 + i as f64;
        let length = ((x + 1.0).min(right) - x.max(left)).clamp(0.0, 1.0);
        *value += (length * weight) as f32;
    }
    Ok(())
}

fn combine_row(destination: &mut [f32], shape: &[f32], mode: u32, budget: &mut Budget) -> Result<(), i32> {
    budget.charge(destination.len() as u64)?;
    for (i, (a, b)) in destination.iter_mut().zip(shape).enumerate() {
        if i % 4096 == 0 { budget.poll()?; }
        let b = b.clamp(0.0, 1.0);
        *a = match mode { 0 => b, 1 => (*a).max(b), 2 => (*a - b).max(0.0), 3 => (*a).min(b), _ => unreachable!() };
    }
    Ok(())
}

fn regular(op: &OperationV1, patch: Patch, scratch: &mut Scratch, budget: &mut Budget) -> Result<(), i32> {
    let rx = (op.x1 - op.x0) * 0.5;
    let ry = (op.y1 - op.y0) * 0.5;
    let cx = op.x0 + rx;
    let cy = op.y0 + ry;
    for y in 0..patch.height {
        budget.poll()?;
        scratch.row.fill(0.0);
        let top = patch.y as f64 + y as f64;
        if op.kind == 1 {
            let overlap = ((top + 1.0).min(op.y1) - top.max(op.y0)).clamp(0.0, 1.0);
            if overlap > 0.0 { add_interval(&mut scratch.row, patch, op.x0, op.x1, overlap, budget)?; }
        } else if rx > 0.0 && ry > 0.0 {
            for sub in 0..8 {
                let v = (top + (sub as f64 + 0.5) / 8.0 - cy) / ry;
                if v.abs() < 1.0 {
                    let half = rx * (1.0 - v * v).max(0.0).sqrt();
                    add_interval(&mut scratch.row, patch, cx - half, cx + half, 1.0 / 8.0, budget)?;
                }
            }
        }
        let begin = y * patch.width;
        combine_row(&mut scratch.mask[begin..begin + patch.width], &scratch.row, op.combine, budget)?;
    }
    Ok(())
}

fn lasso(op: &OperationV1, points: &[PointV1], patch: Patch, scratch: &mut Scratch,
         budget: &mut Budget) -> Result<(), i32> {
    scratch.edges.clear(); scratch.active.clear();
    for i in 0..points.len() {
        if i % 4096 == 0 { budget.poll()?; }
        let edge = Edge { a: points[i], b: points[(i + 1) % points.len()] };
        if edge.a.y != edge.b.y { scratch.edges.push(edge); }
    }
    budget.sorting(scratch.edges.len())?;
    scratch.edges.sort_unstable_by(|a, b| a.low().total_cmp(&b.low()));
    let mut next = 0;
    for row_index in 0..patch.height {
        budget.poll()?; scratch.row.fill(0.0);
        for sub in 0..8 {
            let y = patch.y as f64 + row_index as f64 + (sub as f64 + 0.5) / 8.0;
            while next < scratch.edges.len() && scratch.edges[next].low() <= y {
                scratch.active.push(next); next += 1;
            }
            budget.charge(scratch.active.len() as u64)?;
            scratch.active.retain(|&i| scratch.edges[i].high() > y);
            scratch.hits.clear();
            for &i in &scratch.active { scratch.hits.push(scratch.edges[i].crossing(y)); }
            budget.sorting(scratch.hits.len())?;
            scratch.hits.sort_unstable_by(f64::total_cmp);
            // Half-open edge crossings and implicit closure give even parity;
            // duplicate crossings have zero interval and are harmless.
            if scratch.hits.len() % 2 != 0 { return Err(VALUE_ERROR); }
            for pair in scratch.hits.chunks_exact(2) {
                add_interval(&mut scratch.row, patch, pair[0], pair[1], 1.0 / 8.0, budget)?;
            }
        }
        let begin = row_index * patch.width;
        combine_row(&mut scratch.mask[begin..begin + patch.width], &scratch.row, op.combine, budget)?;
    }
    Ok(())
}

fn brush(op: &OperationV1, points: &[PointV1], patch: Patch, scratch: &mut Scratch,
         budget: &mut Budget) -> Result<(), i32> {
    scratch.segments.clear(); scratch.active.clear();
    if points.len() == 1 { scratch.segments.push(Segment::new(points[0], points[0])); }
    else {
        for (i, pair) in points.windows(2).enumerate() {
            if i % 4096 == 0 { budget.poll()?; }
            scratch.segments.push(Segment::new(pair[0], pair[1]));
        }
    }
    let radius = op.diameter * 0.5;
    let inner = op.hardness * radius;
    budget.sorting(scratch.segments.len())?;
    scratch.segments.sort_unstable_by(|a, b| a.low(radius).total_cmp(&b.low(radius)));
    let mut next = 0;
    for row_index in 0..patch.height {
        budget.poll()?; scratch.row.fill(0.0);
        for sy in 0..4 {
            scratch.subrow.fill(0.0);
            let y = patch.y as f64 + row_index as f64 + (sy as f64 + 0.5) / 4.0;
            while next < scratch.segments.len() && scratch.segments[next].low(radius) <= y {
                scratch.active.push(next); next += 1;
            }
            budget.charge(scratch.active.len() as u64)?;
            scratch.active.retain(|&i| scratch.segments[i].high(radius) > y);
            for &segment_index in &scratch.active {
                let segment = scratch.segments[segment_index];
                if let Some((left, right)) = segment.extent(y, radius) {
                    let (start, end) = clipped_range(left, right, patch);
                    budget.charge((end - start) as u64 * 4)?;
                    for x in start..end {
                        if x % 1024 == 0 { budget.poll()?; }
                        for sx in 0..4 {
                            let sample_x = patch.x as f64 + x as f64 + (sx as f64 + 0.5) / 4.0;
                            let distance = segment.distance(sample_x, y);
                            let weight = if distance >= radius { 0.0 }
                                else if distance <= inner { 1.0 }
                                else {
                                    let t = (radius - distance) / (radius - inner);
                                    t * t * (3.0 - 2.0 * t)
                                };
                            let value = (op.opacity * weight) as f32;
                            let index = x * 4 + sx;
                            scratch.subrow[index] = scratch.subrow[index].max(value);
                        }
                    }
                }
            }
            budget.charge(patch.width as u64 * 4)?;
            for x in 0..patch.width {
                let lane = &scratch.subrow[x * 4..x * 4 + 4];
                let sum = lane.iter().map(|v| *v as f64).sum::<f64>();
                scratch.row[x] += (sum / 16.0) as f32;
            }
        }
        let begin = row_index * patch.width;
        combine_row(&mut scratch.mask[begin..begin + patch.width], &scratch.row, op.combine, budget)?;
    }
    Ok(())
}

/// Exact sum of nonnegative binary32 numbers <= 1, in units of 2^-149.
/// A 513-sample window needs at most 159 bits; three limbs supply 192 bits.
/// Addition/subtraction are integer exact, so sliding-window start positions do
/// not change feather rounding. This is not a quantized/byte mask.
#[derive(Default, Clone, Copy)]
struct CoverageSum([u64; 3]);
impl CoverageSum {
    fn terms(value: f32) -> (usize, u64, u64) {
        let bits = value.to_bits();
        let exponent = (bits >> 23) & 255;
        let mantissa = ((bits & 0x7f_ffff) | if exponent == 0 { 0 } else { 1 << 23 }) as u64;
        let shift = (if exponent == 0 { 0 } else { exponent - 1 }) as usize;
        let bit = shift % 64;
        (shift / 64, mantissa << bit, if bit == 0 { 0 } else { mantissa >> (64 - bit) })
    }
    fn add_word(&mut self, mut limb: usize, mut value: u64) {
        while value != 0 && limb < 3 {
            let (sum, carry) = self.0[limb].overflowing_add(value);
            self.0[limb] = sum; value = u64::from(carry); limb += 1;
        }
    }
    fn subtract_word(&mut self, mut limb: usize, mut value: u64) {
        while value != 0 && limb < 3 {
            let (difference, borrow) = self.0[limb].overflowing_sub(value);
            self.0[limb] = difference; value = u64::from(borrow); limb += 1;
        }
    }
    fn add(&mut self, value: f32) {
        let (limb, low, high) = Self::terms(value);
        self.add_word(limb, low); self.add_word(limb + 1, high);
    }
    fn subtract(&mut self, value: f32) {
        let (limb, low, high) = Self::terms(value);
        self.subtract_word(limb, low); self.subtract_word(limb + 1, high);
    }
    fn mean(&self, denominator: f64) -> f32 {
        let value = ((self.0[2] as f64 * 4.76837158203125e-7)
            + (self.0[1] as f64 * 2.5849394142282115e-26))
            + self.0[0] as f64 * 1.401298464324817e-45;
        (value / denominator).clamp(0.0, 1.0) as f32
    }
}

fn feather(recipe: RecipeV1, tile: TileV1, patch: Patch, scratch: &mut Scratch,
           budget: &mut Budget) -> Result<(), i32> {
    let radius = recipe.feather_radius as i64;
    if radius == 0 {
        budget.charge(scratch.result.len() as u64)?;
        scratch.result.copy_from_slice(&scratch.mask);
        return Ok(());
    }
    let width = tile.width as usize;
    let height = tile.height as usize;
    let denominator = (2 * radius + 1) as f64;
    for y in 0..patch.height {
        budget.poll()?;
        let mut sum = CoverageSum::default();
        let first = (tile.x as i64 - radius).max(0);
        let end = (tile.x as i64 + radius + 1).min(recipe.source_width as i64);
        budget.charge((end - first) as u64 + width as u64 * 3)?;
        for x in first..end { sum.add(scratch.mask[y * patch.width + (x - patch.x as i64) as usize]); }
        for x in 0..width {
            if x % 4096 == 0 { budget.poll()?; }
            scratch.horizontal[y * width + x] = sum.mean(denominator);
            if x + 1 < width {
                let leaving = tile.x as i64 + x as i64 - radius;
                let entering = tile.x as i64 + x as i64 + radius + 1;
                if leaving >= 0 { sum.subtract(scratch.mask[y * patch.width + (leaving - patch.x as i64) as usize]); }
                if entering < recipe.source_width as i64 { sum.add(scratch.mask[y * patch.width + (entering - patch.x as i64) as usize]); }
            }
        }
    }
    for x in 0..width {
        budget.poll()?;
        let mut sum = CoverageSum::default();
        let first = (tile.y as i64 - radius).max(0);
        let end = (tile.y as i64 + radius + 1).min(recipe.source_height as i64);
        budget.charge((end - first) as u64 + height as u64 * 3)?;
        for y in first..end { sum.add(scratch.horizontal[(y - patch.y as i64) as usize * width + x]); }
        for y in 0..height {
            if y % 4096 == 0 { budget.poll()?; }
            scratch.result[y * width + x] = sum.mean(denominator);
            if y + 1 < height {
                let leaving = tile.y as i64 + y as i64 - radius;
                let entering = tile.y as i64 + y as i64 + radius + 1;
                if leaving >= 0 { sum.subtract(scratch.horizontal[(leaving - patch.y as i64) as usize * width + x]); }
                if entering < recipe.source_height as i64 { sum.add(scratch.horizontal[(entering - patch.y as i64) as usize * width + x]); }
            }
        }
    }
    Ok(())
}

fn evaluate(recipe: RecipeV1, tile: TileV1, limits: LimitsV1, ops: &[OperationV1], points: &[PointV1],
            cancel: CancelV1, context: *mut c_void) -> Result<(Vec<f32>, StatsV1), i32> {
    let mut budget = Budget { limit: limits.max_work_units, used: 0, last_poll: 0, cancel, context };
    budget.poll()?;
    let largest = validate_operations(ops, points, &mut budget)?;
    let radius = recipe.feather_radius;
    let x = tile.x.saturating_sub(radius);
    let y = tile.y.saturating_sub(radius);
    let right = (tile.x + tile.width + radius).min(recipe.source_width);
    let bottom = (tile.y + tile.height + radius).min(recipe.source_height);
    let patch = Patch { x, y, width: (right - x) as usize, height: (bottom - y) as usize };
    let working_bytes = memory_plan(patch, tile, largest, radius)?;
    if working_bytes > limits.max_working_bytes { return Err(LIMIT_ERROR); }
    let mut scratch = allocate(patch, tile, largest, radius)?;
    budget.charge((scratch.mask.len() + scratch.result.len() + scratch.horizontal.len()) as u64)?;
    for op in ops {
        budget.poll()?;
        let start = op.point_offset as usize;
        let geometry = &points[start..start + op.point_count as usize];
        match op.kind {
            1 | 2 => regular(op, patch, &mut scratch, &mut budget)?,
            3 => lasso(op, geometry, patch, &mut scratch, &mut budget)?,
            4 => brush(op, geometry, patch, &mut scratch, &mut budget)?,
            5 => {
                budget.charge(scratch.mask.len() as u64)?;
                for (i, value) in scratch.mask.iter_mut().enumerate() {
                    if i % 4096 == 0 { budget.poll()?; }
                    *value = 1.0 - *value;
                }
            },
            _ => return Err(VALUE_ERROR),
        }
    }
    feather(recipe, tile, patch, &mut scratch, &mut budget)?;
    budget.poll()?;
    let stats = StatsV1 { working_bytes, work_units: budget.used,
                          output_pixels: tile.width as u64 * tile.height as u64 };
    Ok((scratch.result, stats))
}

fn span<T>(pointer: *const T, count: usize) -> Result<(usize, usize), i32> {
    if count == 0 { return Ok((0, 0)); }
    let start = pointer as usize;
    let bytes = count.checked_mul(mem::size_of::<T>()).ok_or(ABI_ERROR)?;
    if pointer.is_null() || start % mem::align_of::<T>() != 0 || bytes > isize::MAX as usize { return Err(ABI_ERROR); }
    Ok((start, start.checked_add(bytes).ok_or(ABI_ERROR)?))
}
fn overlaps(a: (usize, usize), b: (usize, usize)) -> bool { a.0 < b.1 && b.0 < a.1 }

unsafe fn entry(recipe_pointer: *const RecipeV1, tile_pointer: *const TileV1, limits_pointer: *const LimitsV1,
                cancel: CancelV1, context: *mut c_void, output: *mut f32, output_len: u64,
                stats_pointer: *mut StatsV1) -> Result<(), i32> {
    let recipe_span = span(recipe_pointer, 1)?;
    let tile_span = span(tile_pointer, 1)?;
    let limits_span = span(limits_pointer, usize::from(!limits_pointer.is_null()))?;
    let stats_span = span(stats_pointer, usize::from(!stats_pointer.is_null()))?;
    let recipe = unsafe { ptr::read(recipe_pointer) };
    let tile = unsafe { ptr::read(tile_pointer) };
    let limits = if limits_pointer.is_null() { LimitsV1::default() } else { unsafe { ptr::read(limits_pointer) } };
    if recipe.abi_version != ABI_VERSION || recipe.struct_size as usize != mem::size_of::<RecipeV1>() || recipe.reserved != 0 {
        return Err(ABI_ERROR);
    }
    if recipe.source_width == 0 || recipe.source_height == 0 || recipe.source_width > MAX_SOURCE_EDGE
        || recipe.source_height > MAX_SOURCE_EDGE || recipe.source_width as u64 * recipe.source_height as u64 > MAX_SOURCE_PIXELS
        || recipe.operation_count as usize > MAX_OPERATIONS || recipe.point_count as usize > MAX_POINTS
        || recipe.feather_radius > MAX_FEATHER { return Err(LIMIT_ERROR); }
    if tile.width == 0 || tile.height == 0
        || tile.x.checked_add(tile.width).ok_or(VALUE_ERROR)? > recipe.source_width
        || tile.y.checked_add(tile.height).ok_or(VALUE_ERROR)? > recipe.source_height { return Err(VALUE_ERROR); }
    if limits.max_working_bytes == 0 || limits.max_working_bytes > MAX_WORKING_BYTES
        || limits.max_output_pixels == 0 || limits.max_output_pixels > MAX_OUTPUT_PIXELS
        || limits.max_work_units == 0 || limits.max_work_units > MAX_WORK_UNITS { return Err(LIMIT_ERROR); }
    let pixels = tile.width as u64 * tile.height as u64;
    if pixels > limits.max_output_pixels { return Err(LIMIT_ERROR); }
    if output_len != pixels { return Err(ABI_ERROR); }
    let length = usize::try_from(output_len).map_err(|_| ABI_ERROR)?;
    let output_span = span(output, length)?;
    let ops_span = span(recipe.operations, recipe.operation_count as usize)?;
    let points_span = span(recipe.points, recipe.point_count as usize)?;
    let spans = [recipe_span, tile_span, limits_span, stats_span, output_span, ops_span, points_span];
    for i in 0..spans.len() {
        for j in i + 1..spans.len() { if overlaps(spans[i], spans[j]) { return Err(ABI_ERROR); } }
    }
    let ops = if recipe.operation_count == 0 { &[] } else { unsafe { slice::from_raw_parts(recipe.operations, recipe.operation_count as usize) } };
    let points = if recipe.point_count == 0 { &[] } else { unsafe { slice::from_raw_parts(recipe.points, recipe.point_count as usize) } };
    let (result, stats) = evaluate(recipe, tile, limits, ops, points, cancel, context)?;
    // Final commit only. Callers must not publish/copy partial buffers while this
    // call is running. No cancellation callback is invoked after this point.
    unsafe { ptr::copy_nonoverlapping(result.as_ptr(), output, length); }
    if !stats_pointer.is_null() { unsafe { ptr::write(stats_pointer, stats); } }
    Ok(())
}

#[no_mangle]
pub extern "C" fn lr_selection_abi_version() -> u32 { ABI_VERSION }

/// # Safety
/// Input/output pointers must identify valid aligned live non-overlapping spans
/// of the declared lengths. The function cannot validate address ownership.
/// Callback must not panic/unwind, mutate spans, or free storage during a call.
#[no_mangle]
pub unsafe extern "C" fn lr_selection_evaluate_v1(
    recipe: *const RecipeV1, tile: *const TileV1, limits: *const LimitsV1,
    cancel: CancelV1, cancel_context: *mut c_void, output: *mut f32, output_len: u64,
    stats: *mut StatsV1,
) -> i32 {
    match panic::catch_unwind(panic::AssertUnwindSafe(|| unsafe {
        entry(recipe, tile, limits, cancel, cancel_context, output, output_len, stats)
    })) {
        Ok(Ok(())) => OK, Ok(Err(code)) => code, Err(_) => PANIC_ERROR,
    }
}

#[cfg(test)]
mod tests;
