// SPDX-License-Identifier: GPL-3.0-or-later
//! Original deterministic semantic-conditioned joint-OKLab fitting.
//!
//! Correspondences are conditional on semantic class AND luminance-rank
//! stratum. This is distribution transfer, not a spatial/texture correspondence,
//! a learned colour model, or a measurement of photographic quality.
use crate::colour::{self as C, Operator, PARAMS};

pub const CLASSES: usize = 6;
pub const STRATA: usize = 4;
pub const PROTOTYPES_PER_STRATUM: usize = 6;
pub const PROTOTYPES: usize = STRATA * PROTOTYPES_PER_STRATUM;
const MIN_CLASS_SAMPLES: usize = 32;
const KMEANS_STEPS: usize = 6;
const SINKHORN_STEPS: usize = 256;
const OT_TOLERANCE: f64 = 1e-6;
const OT_ACCEPTANCE: f64 = 5e-4;
pub type Cancel = Option<extern "C" fn() -> i32>;

pub fn cancelled(c: Cancel) -> Result<(), i32> {
    if c.map(|f| f() != 0).unwrap_or(false) { Err(9) } else { Ok(()) }
}

#[derive(Clone)]
struct Sample { rgb: [f64; 3], lab: [f64; 3], w: f64 }
#[derive(Clone)]
struct Prototype { rgb: [f64; 3], lab: [f64; 3], w: f64 }
#[derive(Clone)]
struct Pair { rgb: [f64; 3], want: [f64; 3], w: f64, class: usize }
struct Group { train: Vec<Pair>, validation: Vec<Pair>, ot_error: f64 }

fn effective_samples(samples: &[Sample]) -> f64 {
    let mass: f64 = samples.iter().map(|s| s.w).sum();
    let squares: f64 = samples.iter().map(|s| s.w * s.w).sum();
    if squares > 0.0 { mass * mass / squares } else { 0.0 }
}

/// Canonical ordering makes the split independent of caller row ordering. This
/// is a deterministic validation split, NOT an independent photographic test.
fn split_samples(samples: &[Sample]) -> Option<(Vec<Sample>, Vec<Sample>)> {
    if samples.len() < MIN_CLASS_SAMPLES { return None; }
    let mut sorted = samples.to_vec();
    sorted.sort_by(|a, b| {
        a.lab[0].total_cmp(&b.lab[0])
            .then_with(|| a.lab[1].total_cmp(&b.lab[1]))
            .then_with(|| a.lab[2].total_cmp(&b.lab[2]))
            .then_with(|| a.rgb[0].total_cmp(&b.rgb[0]))
            .then_with(|| a.rgb[1].total_cmp(&b.rgb[1]))
            .then_with(|| a.rgb[2].total_cmp(&b.rgb[2]))
            .then_with(|| a.w.total_cmp(&b.w))
    });
    if effective_samples(&sorted) < 16.0 { return None; }
    let (mut train, mut validation) = (Vec::new(), Vec::new());
    for (i, sample) in sorted.into_iter().enumerate() {
        if i % 4 == 3 { validation.push(sample); } else { train.push(sample); }
    }
    if effective_samples(&train) < 12.0 || effective_samples(&validation) < 4.0 {
        return None;
    }
    Some((train, validation))
}

fn nearest(lab: [f64; 3], centres: &[[f64; 3]]) -> usize {
    let mut best = 0;
    let mut distance = C::distance(lab, centres[0]);
    for (i, centre) in centres.iter().enumerate().skip(1) {
        let candidate = C::distance(lab, *centre);
        if candidate < distance { best = i; distance = candidate; }
    }
    best
}

/// Weighted deterministic k-means followed by actual-sample representatives.
/// Never combine a mean encoded-RGB input with an incompatible mean OKLab value.
fn prototypes(samples: &[Sample], cancel: Cancel) -> Result<Vec<Prototype>, i32> {
    if samples.is_empty() { return Err(2); }
    let total: f64 = samples.iter().map(|s| s.w).sum();
    if !total.is_finite() || total <= 0.0 { return Err(2); }
    let mut mean = [0.0; 3];
    for s in samples { for c in 0..3 { mean[c] += s.lab[c] * (s.w / total); } }
    let first = samples.iter().enumerate().min_by(|(_, a), (_, b)| {
        C::distance(a.lab, mean).total_cmp(&C::distance(b.lab, mean))
    }).map(|(i, _)| i).ok_or(2)?;
    let k = PROTOTYPES_PER_STRATUM.min(samples.len());
    let mut centres = vec![samples[first].lab];
    while centres.len() < k {
        cancelled(cancel)?;
        let (mut best, mut best_distance) = (0, 0.0);
        for (i, s) in samples.iter().enumerate() {
            let distance = C::distance(s.lab, centres[nearest(s.lab, &centres)]) * (s.w / total).sqrt();
            if distance > best_distance { best = i; best_distance = distance; }
        }
        // Constant-colour populations must produce one valid prototype, not
        // twelve duplicated/empty centres or an insufficient-pairs failure.
        if best_distance <= 1e-18 { break; }
        centres.push(samples[best].lab);
    }
    for _ in 0..KMEANS_STEPS {
        cancelled(cancel)?;
        let mut sums = vec![[0.0; 4]; centres.len()];
        for s in samples {
            let j = nearest(s.lab, &centres);
            let weight = s.w / total;
            for c in 0..3 { sums[j][c] += s.lab[c] * weight; }
            sums[j][3] += weight;
        }
        for (centre, sum) in centres.iter_mut().zip(&sums) {
            if sum[3] > 0.0 { *centre = [sum[0] / sum[3], sum[1] / sum[3], sum[2] / sum[3]]; }
        }
    }
    let mut mass = vec![0.0; centres.len()];
    let mut representatives: Vec<Option<usize>> = vec![None; centres.len()];
    let mut distances = vec![f64::INFINITY; centres.len()];
    for (i, s) in samples.iter().enumerate() {
        let j = nearest(s.lab, &centres);
        mass[j] += s.w / total;
        let distance = C::distance(s.lab, centres[j]);
        if distance < distances[j] { distances[j] = distance; representatives[j] = Some(i); }
    }
    let mut out = Vec::with_capacity(centres.len());
    for j in 0..centres.len() {
        if let Some(i) = representatives[j] {
            let weight = mass[j];
            if weight > 0.0 { out.push(Prototype { rgb: samples[i].rgb, lab: samples[i].lab, w: weight }); }
        }
    }
    if out.is_empty() { return Err(2); }
    Ok(out)
}

fn lse(values: impl Iterator<Item = f64>) -> f64 {
    let values: Vec<_> = values.collect();
    let maximum = values.iter().copied().fold(f64::NEG_INFINITY, f64::max);
    maximum + values.iter().map(|x| (x - maximum).exp()).sum::<f64>().ln()
}

fn marginal_error(cost: &[Vec<f64>], u: &[f64], v: &[f64], t: &[Prototype], r: &[Prototype]) -> f64 {
    let mut error: f64 = 0.0;
    for i in 0..t.len() {
        let mass = lse((0..r.len()).map(|j| cost[i][j] + u[i] + v[j])).exp();
        if !mass.is_finite() { return f64::INFINITY; }
        error = error.max((mass - t[i].w).abs());
    }
    for j in 0..r.len() {
        let mass = lse((0..t.len()).map(|i| cost[i][j] + u[i] + v[j])).exp();
        if !mass.is_finite() { return f64::INFINITY; }
        error = error.max((mass - r[j].w).abs());
    }
    error
}

/// Log-domain balanced OT on the full joint 3-D distribution inside one stratum.
/// Both marginals are checked. Entropy retry is bounded and mode-independent.
fn transport(t: &[Prototype], r: &[Prototype], class: usize, cancel: Cancel) -> Result<(Vec<Pair>, f64), i32> {
    let (n, m) = (t.len(), r.len());
    if n == 0 || m == 0 { return Err(2); }
    // Entropic smoothing must not invent a correction for exactly identical
    // distributions. Their diagonal coupling already solves the colour task.
    if n == m && t.iter().zip(r).all(|(a, b)| a.rgb == b.rgb && a.w == b.w) {
        return Ok((t.iter().map(|p| Pair { rgb: p.rgb, want: p.lab, w: p.w, class }).collect(), 0.0));
    }
    for epsilon in [0.0025, 0.005, 0.01] {
        let cost: Vec<Vec<f64>> = t.iter().map(|a| r.iter().map(|b| {
            -0.04 * (C::distance(a.lab, b.lab) / 0.04).ln_1p() / epsilon
        }).collect()).collect();
        let (mut u, mut v) = (vec![0.0; n], vec![0.0; m]);
        let mut error = f64::INFINITY;
        for iteration in 0..SINKHORN_STEPS {
            cancelled(cancel)?;
            for i in 0..n { u[i] = t[i].w.ln() - lse((0..m).map(|j| cost[i][j] + v[j])); }
            for j in 0..m { v[j] = r[j].w.ln() - lse((0..n).map(|i| cost[i][j] + u[i])); }
            if iteration % 8 == 7 || iteration + 1 == SINKHORN_STEPS {
                error = marginal_error(&cost, &u, &v, t, r);
                if !error.is_finite() { return Err(4); }
                if error <= OT_TOLERANCE { break; }
            }
        }
        if error > OT_ACCEPTANCE { continue; }
        let mut pairs = Vec::with_capacity(n);
        for i in 0..n {
            let log_mass = lse((0..m).map(|j| cost[i][j] + u[i] + v[j]));
            let mut want = [0.0; 3];
            for j in 0..m {
                let conditional = (cost[i][j] + u[i] + v[j] - log_mass).exp();
                for c in 0..3 { want[c] += r[j].lab[c] * conditional; }
            }
            if want.iter().any(|x| !x.is_finite()) { return Err(4); }
            // Use the known source mass, not a residual numerical row error.
            pairs.push(Pair { rgb: t[i].rgb, want, w: t[i].w, class });
        }
        return Ok((pairs, error));
    }
    Err(4)
}

/// Samples are already sorted by L. Count-quantile strata retain at least one
/// row even when soft-mask weights are very uneven; weights remain in each OT.
fn correspondences(reference: &[Sample], target: &[Sample], class: usize, cancel: Cancel) -> Result<(Vec<Pair>, f64), i32> {
    let total: f64 = target.iter().map(|s| s.w).sum();
    let mut pairs = Vec::with_capacity(PROTOTYPES);
    let mut error: f64 = 0.0;
    for stratum in 0..STRATA {
        cancelled(cancel)?;
        let r = &reference[stratum * reference.len() / STRATA..(stratum + 1) * reference.len() / STRATA];
        let t = &target[stratum * target.len() / STRATA..(stratum + 1) * target.len() / STRATA];
        let reference_prototypes = prototypes(r, cancel)?;
        let target_prototypes = prototypes(t, cancel)?;
        let (mut conditional, discrepancy) = transport(&target_prototypes, &reference_prototypes, class, cancel)?;
        let stratum_mass = t.iter().map(|s| s.w).sum::<f64>() / total;
        for pair in &mut conditional { pair.w *= stratum_mass; }
        pairs.extend(conditional);
        error = error.max(discrepancy);
    }
    Ok((pairs, error))
}

struct FitRow {
    base: [f64; 3], before_lab: [f64; 3], lo: [f64; 3], hi: [f64; 3],
    baseline_span: f64, want: [f64; 3], w: f64, class: usize,
}

/// For a local recipe, these are G(x), G(x-delta), G(x+delta). Candidate
/// evaluation is exactly L(G(x)), not a reordered operator or a cumulative
/// sequence of other local classes. Mask=1 is all that RGB/class/weight input
/// can identify; soft-mask boundaries need separate full-image validation.
fn rows(pairs: &[Pair], global: Option<&Operator>) -> Result<Vec<FitRow>, i32> {
    let evaluate = |rgb: [f64; 3]| -> Result<[f64; 3], i32> {
        let input = rgb.map(|v| v as f32);
        match global {
            Some(op) => op.render(input, 1.0).map(|v| v.map(|c| c as f64)).map_err(|_| 3),
            None => Ok(input.map(|v| v as f64)),
        }
    };
    pairs.iter().map(|pair| {
        let base = evaluate(pair.rgb)?;
        let lo = evaluate(pair.rgb.map(|v| v - 0.005))?;
        let hi = evaluate(pair.rgb.map(|v| v + 0.005))?;
        Ok(FitRow { base, before_lab: C::lab(base), lo, hi,
            baseline_span: C::lab(hi)[0] - C::lab(lo)[0],
            want: pair.want, w: pair.w, class: pair.class })
    }).collect()
}

#[derive(Clone, Copy)]
struct Score { objective: f64, residual: f64, gamut_fraction: f64 }

fn objective(p: &[f64; PARAMS], samples: &[FitRow], mode: u32) -> Result<Score, i32> {
    let op = Operator::new(p, 1.0, 1.0).map_err(|_| 3)?;
    let (mut loss, mut residual, mut mass, mut outside) = (0.0, 0.0, 0.0, 0.0);
    for s in samples {
        let after = op.render(s.base.map(|v| v as f32), 1.0).map_err(|_| 3)?.map(|v| v as f64);
        let actual = C::lab(after);
        if after.iter().chain(actual.iter()).any(|x| !x.is_finite()) { return Err(3); }
        let distance = C::distance(actual, s.want);
        residual += s.w * distance;
        mass += s.w;
        loss += s.w * 0.01 * (distance / 0.01).ln_1p();
        if after.iter().any(|v| *v < 0.0 || *v > 1.0) { outside += s.w; }
        // Do not force pre-existing extended-range input into SDR. Penalize
        // NEW excursions relative to this stage's input, without clipping.
        let gamut: f64 = (0..3).map(|c| {
            ((-after[c]).max(0.0) - (-s.base[c]).max(0.0)).max(0.0).powi(2)
                + ((after[c] - 1.0).max(0.0) - (s.base[c] - 1.0).max(0.0)).max(0.0).powi(2)
        }).sum();
        let skin = if s.class == 2 || s.class == 3 { 3.0 } else { 1.0 };
        let chroma = s.before_lab[1].hypot(s.before_lab[2]);
        let neutral = 1.0 + 3.0 / (1.0 + (chroma / 0.03).powi(2));
        let chroma_movement = (actual[1] - s.before_lab[1]).powi(2) + (actual[2] - s.before_lab[2]).powi(2);
        loss += s.w * (0.04 * gamut + 0.012 * skin * neutral * chroma_movement);
        let hi = op.render(s.hi.map(|v| v as f32), 1.0).map_err(|_| 3)?.map(|v| v as f64);
        let lo = op.render(s.lo.map(|v| v as f32), 1.0).map_err(|_| 3)?.map(|v| v as f64);
        let span = C::lab(hi)[0] - C::lab(lo)[0];
        let contrast_change = (span - s.baseline_span) / s.baseline_span.abs().max(0.001);
        loss += s.w * 0.002 * contrast_change.powi(2).min(4.0);
        if span * s.baseline_span < 0.0 { loss += s.w * 0.01; }
    }
    if !mass.is_finite() || mass <= 0.0 { return Err(2); }
    // Mode changes regularization ONLY, never transport, a hidden model, or
    // fabricated neural confidence. Normalize data loss before regularization
    // so global and per-class fits have the same regularization strength.
    let regularization = if mode == 0 { 0.0008 } else { 0.004 };
    let identity = C::identity();
    let mut penalty = 0.0;
    for i in 0..PARAMS {
        let scale = if i < 4 { 1.0 } else if i < 6 { 100.0 }
            else if i < 26 { 0.25 } else if (i - 26) % 3 == 0 { 60.0 } else { 100.0 };
        penalty += regularization * ((p[i] - identity[i]) / scale).powi(2);
    }
    for c in 0..4 {
        for k in 1..4 {
            let j = 6 + c * 5 + k;
            penalty += 0.05 * (p[j - 1] - 2.0 * p[j] + p[j + 1]).powi(2);
        }
        for k in 0..4 {
            let j = 6 + c * 5 + k;
            penalty += 0.1 * (p[j] - p[j + 1]).max(0.0).powi(2);
        }
    }
    for band in 0..8 {
        for channel in 0..3 {
            let scale = if channel == 0 { 60.0 } else { 100.0 };
            penalty += regularization * 0.2 * ((p[26 + band * 3 + channel]
                - p[26 + ((band + 1) % 8) * 3 + channel]) / scale).powi(2);
        }
    }
    let score = Score { objective: loss / mass + penalty,
        residual: (residual / mass).sqrt(), gamut_fraction: outside / mass };
    if !score.objective.is_finite() || !score.residual.is_finite() { return Err(3); }
    Ok(score)
}

fn fit_pairs(train: &[Pair], validation: &[Pair], mode: u32, global: Option<&Operator>, allow_hsv: bool, cancel: Cancel)
    -> Result<([f64; PARAMS], [f64; 6]), i32>
{
    let training_rows = rows(train, global)?;
    let validation_rows = rows(validation, global)?;
    let identity = C::identity();
    let mut p = identity;
    let before = objective(&identity, &validation_rows, mode)?;
    let mut best = objective(&p, &training_rows, mode)?.objective;
    let mut evaluations = 2.0;
    // Genuine editable controls, explicitly fitted subset: EV, R/B log gains,
    // saturation, three interior master PCHIP ordinates, and legacy HSV8.
    // G gain, contrast, RGB curves and endpoints remain exactly neutral.
    let mut indices = vec![0usize, 1, 3, 4, 7, 8, 9];
    // A tiny nonzero legacy HSV change clamps the whole input to SDR. Do not
    // introduce that discontinuity automatically for sampled extended-range
    // input. Manual HSV edits retain documented legacy SDR semantics.
    if allow_hsv && training_rows.iter().chain(&validation_rows).all(|s| s.base.iter().all(|v| (0.0..=1.0).contains(v))) {
        indices.extend(26..PARAMS);
    }
    for fraction in [1.0, 1.0, 1.0, 0.5, 0.25, 0.125, 0.0625] {
        for &i in &indices {
            cancelled(cancel)?;
            let step = fraction * if i == 0 { 0.5 } else if i < 4 { 0.25 }
                else if i < 6 { 20.0 } else if i < 26 { 0.08 }
                else if (i - 26) % 3 == 0 { 8.0 } else { 20.0 };
            let original = p[i];
            let mut winner = original;
            for direction in [-1.0, 1.0] {
                p[i] = original + direction * step;
                if !C::validate(&p) || ((7..=9).contains(&i)
                    && (p[i] < p[i - 1] + 0.01 || p[i] > p[i + 1] - 0.01)) { continue; }
                let score = objective(&p, &training_rows, mode)?.objective;
                evaluations += 1.0;
                if score + 1e-14 < best { best = score; winner = p[i]; }
            }
            p[i] = winner;
        }
    }
    // Validation can veto/back off a candidate, so diagnostics are explicitly
    // selection-set measurements, not an unbiased test-set quality estimate.
    let fitted = p;
    let mut selected = identity;
    let mut validation_score = before;
    for fraction in [1.0, 0.5, 0.25] {
        cancelled(cancel)?;
        let mut candidate = identity;
        for i in 0..PARAMS { candidate[i] += (fitted[i] - identity[i]) * fraction; }
        let score = objective(&candidate, &validation_rows, mode)?;
        evaluations += 1.0;
        if score.objective <= before.objective + 1e-12 && score.residual <= before.residual + 1e-10 {
            selected = candidate;
            validation_score = score;
            break;
        }
    }
    let training_score = objective(&selected, &training_rows, mode)?;
    evaluations += 1.0;
    Ok((selected, [before.residual, validation_score.residual, training_score.objective,
        evaluations, validation_score.gamut_fraction, train.len() as f64]))
}

fn decode(raw: &[f64]) -> Result<Vec<Vec<Sample>>, i32> {
    if raw.len() % 5 != 0 { return Err(1); }
    let mut out = vec![vec![]; CLASSES];
    for v in raw.chunks_exact(5) {
        if v.iter().any(|x| !x.is_finite()) || v[..3].iter().any(|x| x.abs() > 16.0)
            || v[3] < 0.0 || v[3] >= CLASSES as f64 || v[3].fract() != 0.0
            || !(0.0..=1.0).contains(&v[4]) { return Err(1); }
        if v[4] > 0.0 {
            let rgb = [v[0], v[1], v[2]];
            out[v[3] as usize].push(Sample { rgb, lab: C::lab(rgb), w: v[4] });
        }
    }
    for class in &mut out {
        // Invariant to common scaling of soft-mask weights, while avoiding
        // underflow if a class contains only extremely small positive weights.
        let maximum = class.iter().map(|s| s.w).fold(0.0, f64::max);
        if maximum > 0.0 { for sample in class { sample.w /= maximum; } }
    }
    Ok(out)
}

pub fn fit(reference: &[f64], target: &[f64], mode: u32, cancel: Cancel) -> Result<(Vec<f64>, Vec<f64>), i32> {
    if mode > 1 { return Err(1); }
    cancelled(cancel)?;
    let (r, t) = (decode(reference)?, decode(target)?);
    let mut groups: Vec<Option<Group>> = (0..CLASSES).map(|_| None).collect();
    let mut stats = vec![0.0f64; (CLASSES + 1) * 10];
    let (mut all_train, mut all_validation) = (Vec::new(), Vec::new());
    for class in 0..CLASSES {
        cancelled(cancel)?;
        let base = (class + 1) * 10;
        let reference_count = r[class].len() as f64;
        let target_count = t[class].len() as f64;
        stats[base + 6] = reference_count;
        stats[base + 7] = target_count;
        stats[6] += reference_count;
        stats[7] += target_count;
        let (r_train, r_validation) = match split_samples(&r[class]) { Some(split) => split, None => continue };
        let (t_train, t_validation) = match split_samples(&t[class]) { Some(split) => split, None => continue };
        let (train, train_error) = correspondences(&r_train, &t_train, class, cancel)?;
        let (validation, validation_error) = correspondences(&r_validation, &t_validation, class, cancel)?;
        let ot_error = train_error.max(validation_error);
        stats[base + 8] = ot_error;
        stats[base + 9] = 1.0;
        stats[8] = stats[8].max(ot_error);
        // Each available semantic class has unit mass: a large background
        // cannot silently erase the contribution of a smaller supported face.
        all_train.extend(train.iter().cloned());
        all_validation.extend(validation.iter().cloned());
        groups[class] = Some(Group { train, validation, ot_error });
    }
    if all_train.is_empty() || all_validation.is_empty() { return Err(2); }
    let global_hsv = r.iter().chain(&t).flatten().all(|s| s.rgb.iter().all(|v| (0.0..=1.0).contains(v)));
    let (global, diagnostics) = fit_pairs(&all_train, &all_validation, mode, None, global_hsv, cancel)?;
    stats[..6].copy_from_slice(&diagnostics);
    stats[9] = 1.0;
    let mut parameters = global.to_vec();
    let global_operator = Operator::new(&global, 1.0, 1.0).map_err(|_| 3)?;
    for class in 0..CLASSES {
        cancelled(cancel)?;
        match &groups[class] {
            None => parameters.extend(C::identity()),
            Some(group) => {
                // Inspect all supplied rows, not just compressed representatives:
                // a rare HDR sample must not disappear behind a prototype.
                let local_hsv = r[class].iter().all(|s| s.rgb.iter().all(|v| (0.0..=1.0).contains(v)))
                    && t[class].iter().all(|s| global_operator.render(s.rgb.map(|v| v as f32), 1.0)
                        .map(|rgb| rgb.iter().all(|v| (0.0..=1.0).contains(v))).unwrap_or(false));
                let (local, diagnostics) = fit_pairs(&group.train, &group.validation, mode, Some(&global_operator), local_hsv, cancel)?;
                parameters.extend(local);
                stats[(class + 1) * 10..(class + 1) * 10 + 6].copy_from_slice(&diagnostics);
                stats[(class + 1) * 10 + 8] = group.ot_error;
            }
        }
    }
    cancelled(cancel)?;
    Ok((parameters, stats))
}

#[cfg(test)]
mod tests {
    use super::*;

    fn sample(rgb: [f64; 3]) -> Sample { Sample { rgb, lab: C::lab(rgb), w: 1.0 } }
    fn population() -> Vec<Sample> {
        (0..64).map(|i| {
            let x = i as f64 / 80.0;
            sample([x, 0.1 + x * 0.8, 0.2 + x * 0.5])
        }).collect()
    }

    #[test]
    fn validation_split_is_disjoint_and_order_invariant() {
        let input = population();
        let (train, validation) = split_samples(&input).unwrap();
        let mut reversed = input.clone(); reversed.reverse();
        let (other_train, other_validation) = split_samples(&reversed).unwrap();
        assert_eq!(train.len(), 48); assert_eq!(validation.len(), 16);
        assert!(train.iter().all(|a| validation.iter().all(|b| a.rgb != b.rgb)));
        assert_eq!(train.iter().map(|s| s.rgb).collect::<Vec<_>>(), other_train.iter().map(|s| s.rgb).collect::<Vec<_>>());
        assert_eq!(validation.iter().map(|s| s.rgb).collect::<Vec<_>>(), other_validation.iter().map(|s| s.rgb).collect::<Vec<_>>());
    }

    #[test]
    fn prototypes_use_real_inputs_with_consistent_oklab() {
        let input = population();
        let compressed = prototypes(&input, None).unwrap();
        assert!(compressed.len() <= PROTOTYPES_PER_STRATUM);
        assert!((compressed.iter().map(|p| p.w).sum::<f64>() - 1.0).abs() < 1e-12);
        for p in compressed { assert_eq!(p.lab, C::lab(p.rgb)); assert!(input.iter().any(|s| s.rgb == p.rgb)); }
    }

    #[test]
    fn constant_population_has_a_valid_single_prototype() {
        let compressed = prototypes(&vec![sample([0.4; 3]); 32], None).unwrap();
        assert_eq!(compressed.len(), 1);
        let (pairs, error) = transport(&compressed, &compressed, 3, None).unwrap();
        assert_eq!(pairs.len(), 1); assert!(error < OT_TOLERANCE);
        assert!(C::distance(C::lab(pairs[0].rgb), pairs[0].want) < 1e-24);
    }

    #[test]
    fn constant_identity_fit_is_available_not_insufficient_pairs() {
        let mut raw = Vec::new();
        for _ in 0..32 { raw.extend([0.4, 0.4, 0.4, 3.0, 1.0]); }
        let (parameters, diagnostics) = fit(&raw, &raw, 1, None).unwrap();
        for group in parameters.chunks_exact(PARAMS) { assert_eq!(group, &C::identity()[..]); }
        assert_eq!(diagnostics[9], 1.0); assert_eq!(diagnostics[49], 1.0);
        assert_eq!(diagnostics[6], 32.0); assert_eq!(diagnostics[7], 32.0);
    }

    #[test]
    fn local_rows_evaluate_global_before_local_including_contrast_probes() {
        let mut global = C::identity(); global[0] = 0.4; global[7] = 0.3;
        let global = Operator::new(&global, 1.0, 1.0).unwrap();
        let source = [0.15, 0.4, 0.65];
        let pair = Pair { rgb: source, want: C::lab(source), w: 1.0, class: 0 };
        let rows = rows(&[pair], Some(&global)).unwrap();
        let render = |rgb: [f64; 3]| global.render(rgb.map(|v| v as f32), 1.0).unwrap().map(|v| v as f64);
        assert_eq!(rows[0].base, render(source));
        assert_eq!(rows[0].hi, render(source.map(|v| v + 0.005)));
        assert_eq!(rows[0].lo, render(source.map(|v| v - 0.005)));
    }

    #[test]
    fn mode_does_not_change_identity_data_objective() {
        let input = Pair { rgb: [0.2, 0.3, 0.4], want: C::lab([0.3, 0.4, 0.5]), w: 1.0, class: 2 };
        let rows = rows(&[input], None).unwrap();
        let p = C::identity();
        assert_eq!(objective(&p, &rows, 0).unwrap().objective, objective(&p, &rows, 1).unwrap().objective);
    }

    #[test]
    fn unsupported_or_unbalanced_classes_are_not_fabricated() {
        let mut raw = Vec::new();
        for i in 0..32 { raw.extend([0.3, 0.4, 0.5, 1.0, if i == 0 { 1.0 } else { 1e-8 }]); }
        assert_eq!(fit(&raw, &raw, 0, None).err(), Some(2));
    }

    #[test]
    fn sinkhorn_barycentre_respects_reference_masses() {
        let t = vec![Prototype { rgb: [0.3, 0.4, 0.5], lab: C::lab([0.3, 0.4, 0.5]), w: 1.0 }];
        let r = vec![
            Prototype { rgb: [0.2, 0.3, 0.4], lab: C::lab([0.2, 0.3, 0.4]), w: 0.25 },
            Prototype { rgb: [0.5, 0.6, 0.7], lab: C::lab([0.5, 0.6, 0.7]), w: 0.75 },
        ];
        let (pairs, error) = transport(&t, &r, 4, None).unwrap();
        let mut expected = [0.0; 3];
        for c in 0..3 { expected[c] = r[0].lab[c] * 0.25 + r[1].lab[c] * 0.75; }
        assert!(C::distance(pairs[0].want, expected) < 1e-20);
        assert!(error <= OT_ACCEPTANCE); assert_eq!(pairs[0].class, 4);
    }

    #[test]
    fn luminance_strata_do_not_cross_reference_stratum_bounds() {
        let target = population();
        let reference: Vec<_> = target.iter().map(|s| sample(s.rgb.map(|v| v + 0.06))).collect();
        let (t, _) = split_samples(&target).unwrap();
        let (r, _) = split_samples(&reference).unwrap();
        let (pairs, error) = correspondences(&r, &t, 5, None).unwrap();
        assert!(pairs.len() <= PROTOTYPES); assert!(error <= OT_ACCEPTANCE);
        assert!((pairs.iter().map(|p| p.w).sum::<f64>() - 1.0).abs() < 1e-12);
        for stratum in 0..STRATA {
            let source = &t[stratum * t.len() / STRATA..(stratum + 1) * t.len() / STRATA];
            let reference = &r[stratum * r.len() / STRATA..(stratum + 1) * r.len() / STRATA];
            let lower = reference.first().unwrap().lab[0];
            let upper = reference.last().unwrap().lab[0];
            for pair in pairs.iter().filter(|p| source.iter().any(|s| s.rgb == p.rgb)) {
                assert!(pair.want[0] >= lower - 1e-12 && pair.want[0] <= upper + 1e-12);
            }
        }
    }

    #[test]
    fn fit_keeps_declared_neutral_controls_and_validates_selection() {
        let (mut reference, mut target) = (Vec::new(), Vec::new());
        for s in population() {
            target.extend([s.rgb[0], s.rgb[1], s.rgb[2], 2.0, 1.0]);
            reference.extend([s.rgb[0] + 0.06, s.rgb[1] + 0.06, s.rgb[2] + 0.06, 2.0, 1.0]);
        }
        let (parameters, stats) = fit(&reference, &target, 0, None).unwrap();
        assert_eq!(parameters.len(), 7 * PARAMS); assert_eq!(stats.len(), 70);
        for group in parameters.chunks_exact(PARAMS) {
            assert!(C::validate(group)); assert_eq!(group[2], 0.0); assert_eq!(group[5], 0.0);
            assert_eq!(&group[11..26], &C::identity()[11..26]);
            assert_eq!(group[6], 0.0); assert_eq!(group[10], 1.0);
        }
        for row in stats.chunks_exact(10).filter(|row| row[9] == 1.0) {
            assert!(row[1] <= row[0] + 1e-10);
            assert!(row[3] <= 440.0); assert!(row[8] <= OT_ACCEPTANCE);
        }
    }

    #[test]
    fn cancellation_returns_a_distinct_status() {
        extern "C" fn stop() -> i32 { 1 }
        assert_eq!(fit(&[], &[], 0, Some(stop)).err(), Some(9));
    }
}
