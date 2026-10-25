// SPDX-License-Identifier: GPL-3.0-or-later
//! AUTHORED / UNRUN. These are specifications, not evidence of a passing build.
use super::*;

fn rect(mode: u32, x0: f64, y0: f64, x1: f64, y1: f64) -> OperationV1 {
    OperationV1 { kind: 1, combine: mode, x0, y0, x1, y1, ..OperationV1::default() }
}
fn recipe(width: u32, height: u32, operations: &[OperationV1], points: &[PointV1], radius: u32) -> RecipeV1 {
    RecipeV1 { abi_version: 1, struct_size: mem::size_of::<RecipeV1>() as u32,
        source_width: width, source_height: height, operation_count: operations.len() as u32,
        point_count: points.len() as u32, feather_radius: radius, reserved: 0,
        operations: operations.as_ptr(), points: points.as_ptr() }
}
fn tile(width: u32, height: u32) -> TileV1 { TileV1 { x: 0, y: 0, width, height } }
fn raster(width: u32, height: u32, operations: &[OperationV1], points: &[PointV1], radius: u32, region: TileV1) -> Vec<f32> {
    let r = recipe(width, height, operations, points, radius);
    let mut out = vec![-99.0; region.width as usize * region.height as usize];
    let mut stats = StatsV1::default();
    let status = unsafe { lr_selection_evaluate_v1(&r, &region, ptr::null(), None, ptr::null_mut(),
        out.as_mut_ptr(), out.len() as u64, &mut stats) };
    assert_eq!(status, OK);
    assert_eq!(stats.output_pixels, out.len() as u64);
    assert!(stats.working_bytes <= LimitsV1::default().max_working_bytes);
    assert!(out.iter().all(|x| x.is_finite() && (0.0..=1.0).contains(x)));
    out
}

#[test]
fn abi_v1_layout() {
    assert_eq!(lr_selection_abi_version(), 1);
    assert_eq!(mem::size_of::<PointV1>(), 16);
    assert_eq!(mem::size_of::<OperationV1>(), 72);
    assert_eq!(mem::size_of::<TileV1>(), 16);
    assert_eq!(mem::size_of::<LimitsV1>(), 24);
    assert_eq!(mem::size_of::<StatsV1>(), 24);
    assert_eq!(mem::size_of::<RecipeV1>(), 32 + 2 * mem::size_of::<usize>());
}

#[test]
fn rectangle_fractional_exact_area() {
    let out = raster(3, 2, &[rect(0, 0.25, 0.0, 1.25, 1.0)], &[], 0, tile(3, 2));
    assert_eq!(out, vec![0.75, 0.25, 0.0, 0.0, 0.0, 0.0]);
}

#[test]
fn fractional_set_operations_remain_float_coverage() {
    let first = rect(0, 0.25, 0.0, 1.25, 1.0);
    for (mode, expected) in [(0, vec![0.5, 0.5, 0.0]), (1, vec![0.75, 0.5, 0.0]),
                              (2, vec![0.25, 0.0, 0.0]), (3, vec![0.5, 0.25, 0.0])] {
        assert_eq!(raster(3, 1, &[first, rect(mode, 0.5, 0.0, 1.5, 1.0)], &[], 0, tile(3, 1)), expected);
    }
}

#[test]
fn inversion_is_ordered_and_canvas_bounded() {
    let inverse = OperationV1 { kind: 5, ..OperationV1::default() };
    assert_eq!(raster(3, 1, &[rect(0, 0.25, 0.0, 1.25, 1.0), inverse], &[], 0, tile(3, 1)), vec![0.25, 0.75, 1.0]);
    assert_eq!(raster(3, 1, &[inverse, inverse], &[], 0, tile(3, 1)), vec![0.0; 3]);
    assert_eq!(raster(3, 1, &[inverse], &[], 0, tile(3, 1)), vec![1.0; 3]);
}

#[test]
fn empty_and_degenerate_shapes_are_empty() {
    assert_eq!(raster(4, 4, &[], &[], 0, tile(4, 4)), vec![0.0; 16]);
    for kind in [1, 2] {
        let op = OperationV1 { kind, x0: 2.0, y0: 1.0, x1: 2.0, y1: 3.0, ..OperationV1::default() };
        assert_eq!(raster(4, 4, &[op], &[], 0, tile(4, 4)), vec![0.0; 16]);
    }
}

#[test]
fn lasso_autocloses_and_matches_aligned_rectangle() {
    let points = [PointV1 { x: 1.25, y: 1.0 }, PointV1 { x: 5.75, y: 1.0 },
                  PointV1 { x: 5.75, y: 5.0 }, PointV1 { x: 1.25, y: 5.0 }];
    let op = OperationV1 { kind: 3, point_count: 4, ..OperationV1::default() };
    let expected = raster(8, 8, &[rect(0, 1.25, 1.0, 5.75, 5.0)], &[], 0, tile(8, 8));
    assert_eq!(raster(8, 8, &[op], &points, 0, tile(8, 8)), expected);
    let reversed = [points[3], points[2], points[1], points[0]];
    assert_eq!(raster(8, 8, &[op], &reversed, 0, tile(8, 8)), expected);
}

#[test]
fn lasso_duplicate_closure_and_self_intersection_even_odd() {
    let points = [PointV1 { x: 1.0, y: 1.0 }, PointV1 { x: 5.0, y: 5.0 },
                  PointV1 { x: 1.0, y: 5.0 }, PointV1 { x: 5.0, y: 1.0 }, PointV1 { x: 1.0, y: 1.0 }];
    let op = OperationV1 { kind: 3, point_count: 5, ..OperationV1::default() };
    let out = raster(7, 7, &[op], &points, 0, tile(7, 7));
    assert!((out.iter().map(|&x| x as f64).sum::<f64>() - 8.0).abs() < 1e-6);
    assert_eq!(out[3 * 7], 0.0);
    assert!(out[1 * 7 + 2] > 0.5);
}

#[test]
fn ellipse_has_fractional_edge_and_reasonable_area() {
    let op = OperationV1 { kind: 2, x0: 2.0, y0: 2.0, x1: 10.0, y1: 8.0, ..OperationV1::default() };
    let out = raster(12, 10, &[op], &[], 0, tile(12, 10));
    assert_eq!(out[5 * 12 + 6], 1.0);
    assert_eq!(out[0], 0.0);
    assert!(out.iter().any(|&x| x > 0.0 && x < 1.0));
    let area = out.iter().map(|&x| x as f64).sum::<f64>();
    assert!((area - std::f64::consts::PI * 12.0).abs() < 0.2);
}

fn brush_op(mode: u32, point_count: u32, diameter: f64, hardness: f64, opacity: f64) -> OperationV1 {
    OperationV1 { kind: 4, combine: mode, point_count, diameter, hardness, opacity, ..OperationV1::default() }
}

#[test]
fn brush_connects_sparse_points_without_gaps() {
    let points = [PointV1 { x: 2.5, y: 5.5 }, PointV1 { x: 14.5, y: 5.5 }];
    let out = raster(18, 12, &[brush_op(1, 2, 2.0, 1.0, 1.0)], &points, 0, tile(18, 12));
    for x in 2..15 { assert_eq!(out[5 * 18 + x], 1.0); }
    assert_eq!(out[0], 0.0);
}

#[test]
fn brush_opacity_hardness_and_subtract_are_independent() {
    let points = [PointV1 { x: 5.5, y: 5.5 }];
    let hard = raster(12, 12, &[brush_op(1, 1, 6.0, 1.0, 0.6)], &points, 0, tile(12, 12));
    let soft = raster(12, 12, &[brush_op(1, 1, 6.0, 0.0, 0.6)], &points, 0, tile(12, 12));
    assert!((hard[5 * 12 + 5] - 0.6).abs() < 1e-6);
    assert!(soft[5 * 12 + 7] < hard[5 * 12 + 7]);
    let subtract = raster(12, 12, &[rect(0, 0.0, 0.0, 12.0, 12.0), brush_op(2, 1, 6.0, 1.0, 0.6)], &points, 0, tile(12, 12));
    assert!((subtract[5 * 12 + 5] - 0.4).abs() < 1e-6);
    assert_eq!(subtract[0], 1.0);
}

#[test]
fn repeated_brush_points_do_not_build_up_opacity() {
    let p = PointV1 { x: 5.5, y: 5.5 };
    let single = raster(12, 12, &[brush_op(1, 1, 4.0, 0.5, 0.3)], &[p], 0, tile(12, 12));
    let repeated = raster(12, 12, &[brush_op(1, 3, 4.0, 0.5, 0.3)], &[p, p, p], 0, tile(12, 12));
    assert_eq!(single, repeated);
}

#[test]
fn feather_impulse_has_exact_finite_support() {
    let out = raster(7, 7, &[rect(0, 3.0, 3.0, 4.0, 4.0)], &[], 1, tile(7, 7));
    for y in 0..7 { for x in 0..7 {
        let expected = if (2..=4).contains(&x) && (2..=4).contains(&y) { 1.0 / 9.0 } else { 0.0 };
        assert!((out[y * 7 + x] - expected).abs() < 1e-7);
    } }
}

#[test]
fn feather_uses_zero_extension_not_edge_renormalization() {
    let out = raster(3, 3, &[OperationV1 { kind: 5, ..OperationV1::default() }], &[], 1, tile(3, 3));
    assert!((out[0] - 4.0 / 9.0).abs() < 1e-7);
    assert_eq!(out[4], 1.0);
}

#[test]
fn exact_accumulator_preserves_subnormal_after_subtraction() {
    let mut sum = CoverageSum::default();
    let smallest = f32::from_bits(1);
    sum.add(smallest); sum.add(1.0); sum.subtract(1.0);
    assert_eq!(sum.mean(1.0).to_bits(), smallest.to_bits());
    sum.subtract(smallest);
    assert_eq!(sum.0, [0; 3]);
    for _ in 0..513 { sum.add(1.0); }
    assert_eq!(sum.mean(513.0), 1.0);
    for _ in 0..513 { sum.subtract(1.0); }
    assert_eq!(sum.0, [0; 3]);
}

#[test]
fn tiles_are_bit_identical_to_whole_including_halo_and_invert() {
    let points = [PointV1 { x: -3.5, y: 1.25 }, PointV1 { x: 17.75, y: 5.125 },
        PointV1 { x: 26.0, y: 19.25 }, PointV1 { x: 4.125, y: 22.0 },
        PointV1 { x: 1.25, y: 3.25 }, PointV1 { x: 24.5, y: 17.5 }];
    let ops = [OperationV1 { kind: 3, point_count: 4, ..OperationV1::default() },
        OperationV1 { kind: 2, combine: 2, x0: 6.125, y0: 3.25, x1: 19.75, y1: 20.5, ..OperationV1::default() },
        OperationV1 { point_offset: 4, ..brush_op(1, 2, 5.25, 0.35, 0.7) },
        OperationV1 { kind: 5, ..OperationV1::default() }];
    for radius in [0, 1, 4, 16, 256] {
        let whole = raster(29, 23, &ops, &points, radius, tile(29, 23));
        for y in (0..23).step_by(5) { for x in (0..29).step_by(7) {
            let region = TileV1 { x, y, width: 7.min(29 - x), height: 5.min(23 - y) };
            let part = raster(29, 23, &ops, &points, radius, region);
            for py in 0..region.height { for px in 0..region.width {
                assert_eq!(part[(py * region.width + px) as usize].to_bits(),
                    whole[((y + py) * 29 + x + px) as usize].to_bits());
            } }
        } }
    }
}

unsafe extern "C" fn cancel_now(_: *mut c_void) -> u32 { 1 }
unsafe extern "C" fn cancel_after_polls(context: *mut c_void) -> u32 {
    let left = unsafe { &mut *(context as *mut u32) };
    if *left == 0 { 1 } else { *left -= 1; 0 }
}

#[test]
fn cancellation_never_mutates_output_or_stats() {
    let ops = [rect(0, 1.0, 1.0, 60.0, 60.0)];
    let r = recipe(64, 64, &ops, &[], 8);
    for deferred in [false, true] {
        let mut out = vec![-7.0; 64 * 64];
        let mut stats = StatsV1 { working_bytes: 77, work_units: 88, output_pixels: 99 };
        let mut remaining = 12_u32;
        let callback: CancelV1 = Some(if deferred { cancel_after_polls } else { cancel_now });
        let status = unsafe { lr_selection_evaluate_v1(&r, &tile(64, 64), ptr::null(), callback,
            &mut remaining as *mut u32 as *mut c_void, out.as_mut_ptr(), out.len() as u64, &mut stats) };
        assert_eq!(status, CANCELLED);
        assert!(out.iter().all(|&x| x == -7.0));
        assert_eq!((stats.working_bytes, stats.work_units, stats.output_pixels), (77, 88, 99));
    }
}

#[test]
fn invalid_recipe_and_budgets_fail_without_writes() {
    let good = [rect(0, 0.0, 0.0, 4.0, 4.0)];
    let r = recipe(4, 4, &good, &[], 0);
    let mut out = vec![-9.0; 16];
    for limits in [LimitsV1 { max_working_bytes: 1, ..LimitsV1::default() },
                   LimitsV1 { max_output_pixels: 1, ..LimitsV1::default() },
                   LimitsV1 { max_work_units: 1, ..LimitsV1::default() }] {
        let status = unsafe { lr_selection_evaluate_v1(&r, &tile(4, 4), &limits, None, ptr::null_mut(),
            out.as_mut_ptr(), 16, ptr::null_mut()) };
        assert_eq!(status, LIMIT_ERROR);
        assert_eq!(out, vec![-9.0; 16]);
    }
    let bad = [OperationV1 { x0: f64::NAN, ..good[0] }];
    let r = recipe(4, 4, &bad, &[], 0);
    let status = unsafe { lr_selection_evaluate_v1(&r, &tile(4, 4), ptr::null(), None, ptr::null_mut(),
        out.as_mut_ptr(), 16, ptr::null_mut()) };
    assert_eq!(status, VALUE_ERROR);
    assert_eq!(out, vec![-9.0; 16]);
}

#[test]
fn wrong_abi_null_output_and_outside_tile_are_rejected() {
    let ops = [rect(0, 0.0, 0.0, 4.0, 4.0)];
    let mut r = recipe(4, 4, &ops, &[], 0);
    let mut out = vec![-9.0; 16];
    r.abi_version = 2;
    assert_eq!(unsafe { lr_selection_evaluate_v1(&r, &tile(4, 4), ptr::null(), None, ptr::null_mut(), out.as_mut_ptr(), 16, ptr::null_mut()) }, ABI_ERROR);
    r.abi_version = 1;
    assert_eq!(unsafe { lr_selection_evaluate_v1(&r, &tile(4, 4), ptr::null(), None, ptr::null_mut(), ptr::null_mut(), 16, ptr::null_mut()) }, ABI_ERROR);
    let outside = TileV1 { x: u32::MAX, y: 0, width: 4, height: 4 };
    assert_eq!(unsafe { lr_selection_evaluate_v1(&r, &outside, ptr::null(), None, ptr::null_mut(), out.as_mut_ptr(), 16, ptr::null_mut()) }, VALUE_ERROR);
    assert_eq!(out, vec![-9.0; 16]);
}

#[test]
fn output_cannot_alias_input_geometry() {
    let mut ops = [rect(0, 0.0, 0.0, 4.0, 4.0)];
    let r = recipe(4, 4, &ops, &[], 0);
    let alias = ops.as_mut_ptr() as *mut f32;
    assert_eq!(unsafe { lr_selection_evaluate_v1(&r, &tile(4, 4), ptr::null(), None, ptr::null_mut(), alias, 16, ptr::null_mut()) }, ABI_ERROR);
    assert_eq!(ops[0].kind, 1);
    assert_eq!(ops[0].x1, 4.0);
}

#[test]
fn full_resolution_canvas_accepts_bounded_tile_not_proxy_dimensions() {
    let ops = [rect(0, 2900.0, 1900.0, 3100.0, 2100.0)];
    let part = raster(6000, 4000, &ops, &[], 16, TileV1 { x: 2944, y: 1944, width: 128, height: 128 });
    assert_eq!(part[64 * 128 + 64], 1.0);
    // This is a semantic fixture only. It does not time or claim 24 MP throughput.
}

#[test]
fn malformed_brush_lasso_and_reserved_fields_fail_closed() {
    let points = [PointV1 { x: 1.0, y: 1.0 }, PointV1 { x: 2.0, y: 2.0 }];
    let bad_operations = [
        brush_op(1, 0, 4.0, 0.5, 1.0),
        brush_op(0, 1, 4.0, 0.5, 1.0),
        brush_op(1, 1, 0.0, 0.5, 1.0),
        brush_op(1, 1, 4.0, 1.5, 1.0),
        OperationV1 { kind: 3, point_count: 2, ..OperationV1::default() },
        OperationV1 { kind: 5, opacity: 1.0, ..OperationV1::default() },
        OperationV1 { point_count: 1, ..rect(0, 0.0, 0.0, 4.0, 4.0) },
    ];
    for operation in bad_operations {
        let operations = [operation];
        let r = recipe(4, 4, &operations, &points, 0);
        let mut out = vec![-12.0; 16];
        assert_eq!(unsafe { lr_selection_evaluate_v1(&r, &tile(4, 4), ptr::null(), None,
            ptr::null_mut(), out.as_mut_ptr(), 16, ptr::null_mut()) }, VALUE_ERROR);
        assert_eq!(out, vec![-12.0; 16]);
    }
    let mut r = recipe(4, 4, &[], &[], 0);
    r.reserved = 1;
    let mut out = vec![-12.0; 16];
    assert_eq!(unsafe { lr_selection_evaluate_v1(&r, &tile(4, 4), ptr::null(), None,
        ptr::null_mut(), out.as_mut_ptr(), 16, ptr::null_mut()) }, ABI_ERROR);
}

#[test]
fn outside_geometry_clips_and_large_enclosing_lasso_fills_canvas() {
    assert_eq!(raster(4, 4, &[rect(0, -20.0, -20.0, -10.0, -10.0)], &[], 4, tile(4, 4)), vec![0.0; 16]);
    let points = [PointV1 { x: -10.0, y: -10.0 }, PointV1 { x: 10.0, y: -10.0 },
                  PointV1 { x: 10.0, y: 10.0 }, PointV1 { x: -10.0, y: 10.0 }];
    let operation = OperationV1 { kind: 3, point_count: 4, ..OperationV1::default() };
    assert_eq!(raster(4, 4, &[operation], &points, 0, tile(4, 4)), vec![1.0; 16]);
}
