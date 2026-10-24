// SPDX-License-Identifier: GPL-3.0-or-later
//! AUTHORED / UNRUN. These fixtures have not established native acceptance.
use super::*;

const FRAME: [f64; 7] = [1.0, 0.0, 0.0, -1.0, 50.0, 60.0, 100.0];
const POINTS: [f64; 12] = [80.0, 30.0, 20.0, 30.0, 85.0, 60.0,
                           15.0, 60.0, 75.0, 90.0, 25.0, 90.0];
const ROLES: [f64; 18] = [1.0, 0.0, 0.0, 1.0, 0.0, 0.0,
                          0.0, 1.0, 0.0, 0.0, 1.0, 0.0,
                          0.0, 0.0, 1.0, 0.0, 0.0, 1.0];
const SIDES: [f64; 6] = [1.0, -1.0, 1.0, -1.0, 1.0, -1.0];

fn run(values: &[f64; 6], frame: &[f64; 7]) -> [f64; 12] {
    let mut output = [77.0; 12];
    let code = unsafe {
        lrt_face_contour_controls_v1(
            POINTS.as_ptr(), POINTS.len(), ROLES.as_ptr(), ROLES.len(),
            SIDES.as_ptr(), SIDES.len(), frame.as_ptr(), frame.len(),
            values.as_ptr(), values.len(), SIDES.len(), output.as_mut_ptr(), output.len())
    };
    assert_eq!(code, 0);
    output
}

#[test]
fn neutral_is_exact_positive_zero_including_negative_zero_controls() {
    for value in [0.0, -0.0] {
        assert!(run(&[value; 6], &FRAME).iter().all(|v| v.to_bits() == 0));
    }
}

#[test]
fn positive_expands_temple_and_jaw_but_narrows_cheekbone() {
    let output = run(&[1.0; 6], &FRAME);
    for (i, expected) in [3.5, -3.5, -3.5, 3.5, 3.5, -3.5].iter().enumerate() {
        assert!((output[2 * i] - expected).abs() < 1.0e-12);
        assert_eq!(output[2 * i + 1], 0.0);
    }
    let reversed = run(&[-1.0; 6], &FRAME);
    for i in 0..output.len() { assert_eq!(reversed[i], -output[i]); }
}

#[test]
fn corrected_slim_profile_contracts_all_regions_with_independent_subject_sides() {
    // New lnx.slim_face.v2 policy, NOT migration of old 0.11-width strengths.
    // Subject-left +0.8 narrows; subject-right -0.4 expands.
    let output = run(&[-0.8, 0.4, 0.8, -0.4, -0.8, 0.4], &FRAME);
    for (i, expected) in [-2.8, -1.4, -2.8, -1.4, -2.8, -1.4].iter().enumerate() {
        assert!((output[2 * i] - expected).abs() < 1.0e-12);
        assert_eq!(output[2 * i + 1], 0.0);
    }
}

#[test]
fn corrected_slim_overlap_taper_is_bounded_and_zero_side_stays_exact() {
    let mut roles = ROLES;
    // Verified-oval transition profile: .65 temple plus .15 cheekbone.
    roles[0] = 0.65; roles[1] = 0.15;
    let mut output = [77.0; 12];
    let values = [-1.0, 0.0, 1.0, 0.0, -1.0, 0.0];
    let code = unsafe {
        lrt_face_contour_controls_v1(
            POINTS.as_ptr(), 12, roles.as_ptr(), 18, SIDES.as_ptr(), 6,
            FRAME.as_ptr(), 7, values.as_ptr(), 6, 6, output.as_mut_ptr(), 12)
    };
    assert_eq!(code, 0);
    assert!((output[0] + 2.8).abs() < 1.0e-12);
    for i in [1, 3, 5] {
        assert_eq!(output[2 * i].to_bits(), 0);
        assert_eq!(output[2 * i + 1].to_bits(), 0);
    }
}

#[test]
fn each_subject_side_uses_its_own_control_without_hidden_linking() {
    let output = run(&[0.8, 0.0, 0.0, -0.6, 0.0, 0.4], &FRAME);
    for (i, expected) in [2.8, 0.0, 0.0, -2.1, 0.0, -1.4].iter().enumerate() {
        assert!((output[2 * i] - expected).abs() < 1.0e-12);
    }
}

#[test]
fn rotated_frame_moves_along_head_lateral_only() {
    let frame = [0.6, 0.8, 0.8, -0.6, 50.0, 60.0, 100.0];
    let result = run(&[0.5; 6], &frame);
    assert!((result[0] - 1.05).abs() < 1.0e-12);
    assert!((result[1] - 1.4).abs() < 1.0e-12);
    for displacement in result.chunks_exact(2) {
        assert!((displacement[0] * frame[2] + displacement[1] * frame[3]).abs() < 1.0e-12);
    }
}

#[test]
fn face_width_scales_motion_not_absolute_position() {
    let first = run(&[0.5; 6], &FRAME);
    let mut frame = FRAME;
    frame[4] += 1000.0;
    frame[5] -= 1000.0;
    frame[6] *= 2.0;
    let second = run(&[0.5; 6], &frame);
    for i in 0..first.len() { assert_eq!(second[i], 2.0 * first[i]); }
}

#[test]
fn over_budget_absolute_sum_refuses_even_when_signed_terms_cancel() {
    let mut output = [77.0; 12];
    let roles = [1.0; 18];
    // Signed sum .035 would pass a resultant-only bound, but absolute .105 must not.
    let code = unsafe {
        lrt_face_contour_controls_v1(
            POINTS.as_ptr(), 12, roles.as_ptr(), 18, SIDES.as_ptr(), 6,
            FRAME.as_ptr(), 7, [1.0; 6].as_ptr(), 6, 6, output.as_mut_ptr(), 12)
    };
    assert_eq!(code, BOUND_ERROR);
    assert_eq!(output, [77.0; 12]);
}

#[test]
fn all_input_ranges_are_validated_before_any_output_write() {
    let mut output = [77.0; 12];
    for bad in [f64::NAN, f64::INFINITY, f64::NEG_INFINITY, 1.01, -1.01] {
        let mut values = [0.0; 6];
        values[5] = bad;
        let code = unsafe {
            lrt_face_contour_controls_v1(
                POINTS.as_ptr(), 12, ROLES.as_ptr(), 18, SIDES.as_ptr(), 6,
                FRAME.as_ptr(), 7, values.as_ptr(), 6, 6, output.as_mut_ptr(), 12)
        };
        assert_eq!(code, VALUE_ERROR);
        assert_eq!(output, [77.0; 12]);
    }
    for bad in [0.0, 0.5, 2.0, f64::NAN] {
        let mut sides = SIDES;
        sides[5] = bad;
        let code = unsafe {
            lrt_face_contour_controls_v1(
                POINTS.as_ptr(), 12, ROLES.as_ptr(), 18, sides.as_ptr(), 6,
                FRAME.as_ptr(), 7, [0.0; 6].as_ptr(), 6, 6, output.as_mut_ptr(), 12)
        };
        assert_eq!(code, VALUE_ERROR);
        assert_eq!(output, [77.0; 12]);
    }
}

#[test]
fn invalid_frame_or_points_refuse_even_when_neutral() {
    let mut output = [77.0; 12];
    for frame in [
        [0.0, 0.0, 0.0, -1.0, 50.0, 60.0, 100.0],
        [1.0, 0.0, 1.0, 0.0, 50.0, 60.0, 100.0],
        [1.0, 0.0, 0.0, -1.0, 50.0, 60.0, 0.0],
    ] {
        let code = unsafe {
            lrt_face_contour_controls_v1(
                POINTS.as_ptr(), 12, ROLES.as_ptr(), 18, SIDES.as_ptr(), 6,
                frame.as_ptr(), 7, [0.0; 6].as_ptr(), 6, 6, output.as_mut_ptr(), 12)
        };
        assert_eq!(code, FRAME_ERROR);
        assert_eq!(output, [77.0; 12]);
    }
    let mut points = POINTS;
    points[11] = f64::NAN;
    let code = unsafe {
        lrt_face_contour_controls_v1(
            points.as_ptr(), 12, ROLES.as_ptr(), 18, SIDES.as_ptr(), 6,
            FRAME.as_ptr(), 7, [0.0; 6].as_ptr(), 6, 6, output.as_mut_ptr(), 12)
    };
    assert_eq!(code, VALUE_ERROR);
    assert_eq!(output, [77.0; 12]);
}

#[test]
fn wrong_lengths_null_misaligned_and_alias_are_rejected_before_dereference() {
    let mut output = [77.0; 12];
    for (pointer, length) in [
        (std::ptr::null(), 12), (1usize as *const f64, 12),
        ((usize::MAX - 7) as *const f64, 12), (POINTS.as_ptr(), usize::MAX),
    ] {
        let code = unsafe {
            lrt_face_contour_controls_v1(
                pointer, length, ROLES.as_ptr(), 18, SIDES.as_ptr(), 6,
                FRAME.as_ptr(), 7, [0.0; 6].as_ptr(), 6, 6, output.as_mut_ptr(), 12)
        };
        assert_eq!(code, ABI_ERROR);
        assert_eq!(output, [77.0; 12]);
    }
    let mut points = POINTS;
    let code = unsafe {
        lrt_face_contour_controls_v1(
            points.as_ptr(), 12, ROLES.as_ptr(), 18, SIDES.as_ptr(), 6,
            FRAME.as_ptr(), 7, [0.0; 6].as_ptr(), 6, 6, points.as_mut_ptr(), 12)
    };
    assert_eq!(code, ABI_ERROR);
    assert_eq!(points, POINTS);
    for count in [0, MAX_CONTROLS + 1, usize::MAX] {
        let code = unsafe {
            lrt_face_contour_controls_v1(
                POINTS.as_ptr(), 12, ROLES.as_ptr(), 18, SIDES.as_ptr(), 6,
                FRAME.as_ptr(), 7, [0.0; 6].as_ptr(), 6, count, output.as_mut_ptr(), 12)
        };
        assert_eq!(code, ABI_ERROR);
    }
}

#[test]
fn maximum_count_zero_roles_stay_exactly_zero() {
    let points = [0.0; MAX_CONTROLS * 2];
    let roles = [0.0; MAX_CONTROLS * 3];
    let sides = [1.0; MAX_CONTROLS];
    let mut output = [77.0; MAX_CONTROLS * 2];
    let code = unsafe {
        lrt_face_contour_controls_v1(
            points.as_ptr(), points.len(), roles.as_ptr(), roles.len(),
            sides.as_ptr(), sides.len(), FRAME.as_ptr(), 7,
            [1.0; 6].as_ptr(), 6, MAX_CONTROLS, output.as_mut_ptr(), output.len())
    };
    assert_eq!(code, 0);
    assert!(output.iter().all(|v| v.to_bits() == 0));
}

#[test]
fn every_buffer_length_and_every_writable_overlap_are_checked() {
    let correct_lengths = [12usize, 18, 6, 7, 6, 12];
    let mut output = [77.0; 12];
    for index in 0..correct_lengths.len() {
        for bad_length in [0, correct_lengths[index] - 1, usize::MAX] {
            let mut lengths = correct_lengths;
            lengths[index] = bad_length;
            let code = unsafe {
                lrt_face_contour_controls_v1(
                    POINTS.as_ptr(), lengths[0], ROLES.as_ptr(), lengths[1],
                    SIDES.as_ptr(), lengths[2], FRAME.as_ptr(), lengths[3],
                    [0.0; 6].as_ptr(), lengths[4], 6, output.as_mut_ptr(), lengths[5])
            };
            assert_eq!(code, ABI_ERROR);
            assert_eq!(output, [77.0; 12]);
        }
    }
    // Output aliases each input in turn. Shared storage has enough allocated
    // extent even for the longest declaration; rejection must precede reading.
    for index in 0..5 {
        let mut storage = [77.0; 32];
        let values = [0.0; 6];
        let mut inputs = [POINTS.as_ptr(), ROLES.as_ptr(), SIDES.as_ptr(),
                          FRAME.as_ptr(), values.as_ptr()];
        inputs[index] = storage.as_ptr();
        let code = unsafe {
            lrt_face_contour_controls_v1(
                inputs[0], 12, inputs[1], 18, inputs[2], 6,
                inputs[3], 7, inputs[4], 6, 6, storage.as_mut_ptr(), 12)
        };
        assert_eq!(code, ABI_ERROR);
        assert_eq!(storage, [77.0; 32]);
    }
}

#[test]
fn fractional_region_weight_and_invalid_roles_are_not_clipped() {
    let mut roles = ROLES;
    roles[0] = 0.25;
    let mut output = [77.0; 12];
    let code = unsafe {
        lrt_face_contour_controls_v1(
            POINTS.as_ptr(), 12, roles.as_ptr(), 18, SIDES.as_ptr(), 6,
            FRAME.as_ptr(), 7, [1.0; 6].as_ptr(), 6, 6, output.as_mut_ptr(), 12)
    };
    assert_eq!(code, 0);
    assert!((output[0] - 0.875).abs() < 1.0e-12);
    for invalid in [-0.001, 1.001, f64::NAN, f64::INFINITY] {
        roles[17] = invalid;
        output.fill(77.0);
        let code = unsafe {
            lrt_face_contour_controls_v1(
                POINTS.as_ptr(), 12, roles.as_ptr(), 18, SIDES.as_ptr(), 6,
                FRAME.as_ptr(), 7, [1.0; 6].as_ptr(), 6, 6, output.as_mut_ptr(), 12)
        };
        assert_eq!(code, VALUE_ERROR);
        assert_eq!(output, [77.0; 12]);
    }
}
