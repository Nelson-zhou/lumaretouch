// SPDX-License-Identifier: GPL-3.0-or-later
// AUTHORED, UNRUN. These are numerical/ABI fixtures, not passing-test evidence.
use super::*;

const IDENTITY: [f64; 6] = [1.0, 0.0, 0.0, 0.0, 1.0, 0.0];

fn close(actual: &[f32], expected: &[f32]) {
    assert_eq!(actual.len(), expected.len());
    for (a, e) in actual.iter().zip(expected) {
        assert!((*a - *e).abs() <= 2e-6 * e.abs().max(1.0), "{a} != {e}");
    }
}

fn tile(
    source: &[f32], size: (usize, usize), base: &[f32], tile_size: (usize, usize),
    inverse: &[f64; 6], origin: (f64, f64), opacity: f32, mode: u32,
    mask: Option<&[f32]>, output: &mut [f32],
) -> i32 {
    assert_eq!(base.len(), output.len());
    unsafe { lrt_creative_composite_tile(
        source.as_ptr(), source.len(), size.0, size.1,
        base.as_ptr(), output.as_mut_ptr(), output.len(), tile_size.0, tile_size.1,
        inverse.as_ptr(), origin.0, origin.1, opacity, mode,
        mask.map_or(ptr::null(), |m| m.as_ptr()), mask.map_or(0, |m| m.len()),
    ) }
}

#[test]
fn five_blends_on_opaque_pixels_have_independent_expected_values() {
    let base = [0.25, 0.5, 0.75, 1.0];
    let source = [0.8, 0.4, 0.2, 1.0];
    let expected = [
        [0.8, 0.4, 0.2, 1.0],
        [0.2, 0.2, 0.15, 1.0],
        [0.85, 0.7, 0.8, 1.0],
        [0.8, 0.5, 0.75, 1.0],
        [0.25, 0.4, 0.2, 1.0],
    ];
    for mode in 0..5 { close(&blend(&base, source, mode).unwrap(), &expected[mode as usize]); }
}

#[test]
fn partial_alpha_blends_follow_independent_straight_colour_reference() {
    let cb = [0.2f64, 0.8, 1.4];
    let cs = [-0.1f64, 0.3, 2.0];
    let (ab, as_) = (0.4f64, 0.6f64);
    let base = [(cb[0]*ab) as f32, (cb[1]*ab) as f32, (cb[2]*ab) as f32, ab as f32];
    let src = [(cs[0]*as_) as f32, (cs[1]*as_) as f32, (cs[2]*as_) as f32, as_ as f32];
    for mode in 0..5 {
        let mut expected = [0.0; 4];
        for c in 0..3 {
            let blended = match mode {
                0 => cs[c], 1 => cb[c]*cs[c], 2 => cb[c]+cs[c]-cb[c]*cs[c],
                3 => cb[c].max(cs[c]), _ => cb[c].min(cs[c]),
            };
            expected[c] = ((1.0-as_)*ab*cb[c] + (1.0-ab)*as_*cs[c] + as_*ab*blended) as f32;
        }
        expected[3] = (as_ + ab*(1.0-as_)) as f32;
        close(&blend(&base, src, mode).unwrap(), &expected);
    }
}

#[test]
fn zero_alpha_is_exact_identity_for_all_modes() {
    let base = [-0.25, 2.0, 4.0, 0.75];
    for mode in 0..5 {
        assert_eq!(blend(&base, [0.0; 4], mode).unwrap(), base);
        assert_eq!(blend(&[0.0; 4], base, mode).unwrap(), base);
    }
}

#[test]
fn identity_samples_actual_imported_pixels_without_edge_replication() {
    let source = [1.0, 0.0, 0.0, 1.0, 0.0, 0.5, 0.0, 0.5];
    let mut out = [99.0; 8];
    assert_eq!(tile(&source, (2,1), &[0.0;8], (2,1), &IDENTITY, (0.0,0.0), 1.0, 0, None, &mut out), 0);
    assert_eq!(out, source);
}

#[test]
fn transparent_boundary_retains_bilinear_half_pixel_coverage() {
    let source = [1.0, 0.0, 0.0, 1.0];
    let transform = [1.0, 0.0, -0.5, 0.0, 1.0, 0.0];
    let mut out = [99.0; 12];
    assert_eq!(tile(&source, (1,1), &[0.0;12], (3,1), &transform, (0.0,0.0), 1.0, 0, None, &mut out), 0);
    close(&out, &[0.5,0.0,0.0,0.5, 0.5,0.0,0.0,0.5, 0.0,0.0,0.0,0.0]);
}

#[test]
fn mask_multiplies_source_taps_before_sampling_and_opacity_once() {
    let source = [1.0,0.0,0.0,1.0, 0.0,0.0,1.0,1.0];
    let transform = [1.0, 0.0, 0.5, 0.0, 1.0, 0.0];
    let mut out = [99.0; 4];
    assert_eq!(tile(&source, (2,1), &[0.0;4], (1,1), &transform, (0.0,0.0), 0.5, 0, Some(&[1.0,0.0]), &mut out), 0);
    close(&out, &[0.25,0.0,0.0,0.25]);
}

#[test]
fn tiled_affine_matches_monolithic_at_horizontal_and_vertical_seams() {
    let mut source = Vec::new();
    for y in 0..4 { for x in 0..6 { source.extend_from_slice(&[x as f32/5.0, y as f32/3.0, 0.2, 1.0]); } }
    let transform = [0.82, 0.12, -0.25, -0.08, 0.93, 0.4];
    let image = Image {pixels:&source, width:6, height:4, mask:None};
    let whole = render(&image, &[0.0;96], 6, 4, &transform, (0.0,0.0), 0.7, 2).unwrap();
    let mut assembled = vec![0.0;96];
    for ty in [0,2] { for tx in [0,3] {
        let part = render(&image, &[0.0;24], 3, 2, &transform, (tx as f64,ty as f64), 0.7, 2).unwrap();
        for y in 0..2 { for x in 0..3 {
            let target = ((ty+y)*6+tx+x)*4;
            let from = (y*3+x)*4;
            assembled[target..target+4].copy_from_slice(&part[from..from+4]);
        } }
    } }
    assert_eq!(assembled, whole);
}

#[test]
fn rotation_and_negative_scale_use_inverse_affine_centers() {
    let source = [1.0,0.0,0.0,1.0, 0.0,1.0,0.0,1.0];
    let mut out = [99.0;8];
    let flip = [-1.0,0.0,2.0,0.0,1.0,0.0];
    assert_eq!(tile(&source,(2,1),&[0.0;8],(2,1),&flip,(0.0,0.0),1.0,0,None,&mut out),0);
    assert_eq!(&out[..4], &source[4..]);
    assert_eq!(&out[4..], &source[..4]);
    let rotate = [0.0,1.0,0.0,-1.0,0.0,1.0];
    assert_eq!(tile(&source,(2,1),&[0.0;8],(1,2),&rotate,(0.0,0.0),1.0,0,None,&mut out),0);
    assert_eq!(out,source);
}

#[test]
fn signed_hdr_is_never_clamped_to_sdr() {
    let base = [2.0,-0.5,4.0,1.0];
    let source = [3.0,2.0,-1.0,1.0];
    close(&blend(&base, source, 1).unwrap(), &[6.0,-1.0,-4.0,1.0]);
    close(&blend(&base, source, 2).unwrap(), &[-1.0,2.5,7.0,1.0]);
}

#[test]
fn isolated_group_opacity_is_applied_to_flattened_result_not_children() {
    let red = [1.0,0.0,0.0,1.0];
    let blue = [0.0,0.0,1.0,1.0];
    let first = blend(&[0.0;4],red,0).unwrap();
    let flattened = blend(&first,blue,0).unwrap();
    let mut grouped = [99.0;4];
    assert_eq!(tile(&flattened,(1,1),&[1.0;4],(1,1),&IDENTITY,(0.0,0.0),0.5,0,None,&mut grouped),0);
    close(&grouped,&[0.5,0.5,1.0,1.0]);
    let wrong = blend(&blend(&[1.0;4],[0.5,0.0,0.0,0.5],0).unwrap(),[0.0,0.0,0.5,0.5],0).unwrap();
    assert_ne!(grouped,wrong);
}

#[test]
fn reject_late_bad_pixel_without_partial_output_write() {
    let source = [1.0,0.0,0.0,1.0, f32::NAN,0.0,0.0,1.0];
    let mut out = [97.0;8];
    assert_eq!(tile(&source,(2,1),&[0.0;8],(2,1),&IDENTITY,(0.0,0.0),1.0,0,None,&mut out),PIXEL_ERROR);
    assert_eq!(out,[97.0;8]);
}

#[test]
fn reject_late_invalid_backdrop_without_partial_write() {
    let source = [0.0;8];
    let base = [0.0,0.0,0.0,0.0, 1.0,0.0,0.0,0.0];
    let mut out = [97.0;8];
    assert_eq!(tile(&source,(2,1),&base,(2,1),&IDENTITY,(0.0,0.0),1.0,0,None,&mut out),PIXEL_ERROR);
    assert_eq!(out,[97.0;8]);
}

#[test]
fn reject_noncanonical_alpha_nonfinite_rgb_and_bad_masks_on_import() {
    for source in [[1.0,0.0,0.0,0.0],[0.0,0.0,0.0,-0.1],[0.0,0.0,0.0,1.1],[f32::INFINITY,0.0,0.0,1.0]] {
        assert_eq!(unsafe {lrt_creative_validate_rgba(source.as_ptr(),4,1,1)},PIXEL_ERROR);
    }
    for mask in [f32::NAN,-0.1,1.1] {
        assert_eq!(unsafe {lrt_creative_validate_mask(&mask,1,1,1)},PIXEL_ERROR);
    }
}

#[test]
fn reject_result_overflow_without_clamping_or_partial_write() {
    let source = [f32::MAX,1.0,1.0,1.0];
    let mut out = [97.0;4];
    assert_eq!(tile(&source,(1,1),&source,(1,1),&IDENTITY,(0.0,0.0),1.0,1,None,&mut out),RESULT_ERROR);
    assert_eq!(out,[97.0;4]);
}

#[test]
fn reject_invalid_settings_atomically() {
    let source = [1.0;4];
    for inverse in [[0.0;6],[f64::NAN,0.0,0.0,0.0,1.0,0.0]] {
        let mut out = [97.0;4];
        assert_eq!(tile(&source,(1,1),&source,(1,1),&inverse,(0.0,0.0),1.0,0,None,&mut out),SETTINGS_ERROR);
        assert_eq!(out,[97.0;4]);
    }
    for (opacity,mode) in [(f32::NAN,0),(-0.1,0),(1.1,0),(1.0,5)] {
        let mut out = [97.0;4];
        assert_eq!(tile(&source,(1,1),&source,(1,1),&IDENTITY,(0.0,0.0),opacity,mode,None,&mut out),SETTINGS_ERROR);
        assert_eq!(out,[97.0;4]);
    }
}

#[test]
fn reject_alias_null_wrong_lengths_and_oversize_before_dereference() {
    let mut source = [1.0;4];
    let source_ptr = source.as_mut_ptr();
    let code = unsafe {lrt_creative_composite_tile(source_ptr,4,1,1,source_ptr,source_ptr,4,1,1,
        IDENTITY.as_ptr(),0.0,0.0,1.0,0,ptr::null(),0)};
    assert_eq!(code,ABI_ERROR);
    assert_eq!(source,[1.0;4]);
    assert_eq!(unsafe {lrt_creative_validate_rgba(ptr::null(),4,1,1)},ABI_ERROR);
    assert_eq!(unsafe {lrt_creative_validate_rgba(source.as_ptr(),3,1,1)},ABI_ERROR);
    assert_eq!(unsafe {lrt_creative_validate_rgba(source.as_ptr(),4,usize::MAX,2)},ABI_ERROR);
    assert_eq!(unsafe {lrt_creative_validate_rgba(source.as_ptr(),4,MAX_SOURCE_PIXELS+1,1)},ABI_ERROR);
}

#[test]
fn reject_mask_length_and_values_atomically() {
    let source = [1.0;4];
    for mask in [&[0.5,0.5][..], &[f32::NAN][..]] {
        let mut out = [97.0;4];
        assert_ne!(tile(&source,(1,1),&source,(1,1),&IDENTITY,(0.0,0.0),1.0,0,Some(mask),&mut out),0);
        assert_eq!(out,[97.0;4]);
    }
}

#[test]
fn zero_opacity_is_exact_without_writing_to_input() {
    let source = [1.0;4];
    let base = [-0.25,2.0,4.0,0.5];
    let mut out = [97.0;4];
    assert_eq!(tile(&source,(1,1),&base,(1,1),&IDENTITY,(0.0,0.0),0.0,2,None,&mut out),0);
    assert_eq!(out,base);
    assert_eq!(source,[1.0;4]);
}

#[test]
fn off_canvas_and_empty_source_support_are_transparent() {
    let source = [1.0;4];
    let base = [0.2,0.3,0.4,0.5];
    let mut out = [97.0;4];
    assert_eq!(tile(&source,(1,1),&base,(1,1),&IDENTITY,(1e6,1e6),1.0,3,None,&mut out),0);
    assert_eq!(out,base);
}

#[test]
fn srgb_transfer_preserves_alpha_and_premultiplies_after_decoding() {
    let source = [0.5,0.04045,1.0,0.5, 1.0,0.5,0.2,0.0];
    let mut output = [97.0;8];
    assert_eq!(unsafe {lrt_creative_linearize_rgba(source.as_ptr(),output.as_mut_ptr(),8)},0);
    close(&output,&[0.10702057,0.0015654025,0.5,0.5, 0.0,0.0,0.0,0.0]);
}

#[test]
fn srgb_transfer_rejects_bad_late_input_and_alias_without_mutation() {
    let source = [0.5,0.5,0.5,1.0, 1.1,0.0,0.0,1.0];
    let mut output = [97.0;8];
    assert_eq!(unsafe {lrt_creative_linearize_rgba(source.as_ptr(),output.as_mut_ptr(),8)},PIXEL_ERROR);
    assert_eq!(output,[97.0;8]);
    let mut same = [0.5;4];
    let pointer = same.as_mut_ptr();
    assert_eq!(unsafe {lrt_creative_linearize_rgba(pointer,pointer,4)},ABI_ERROR);
    assert_eq!(same,[0.5;4]);
}

#[test]
fn reject_partial_overlap_and_misalignment_before_any_read_or_write() {
    let mut storage = [1.0f32;8];
    let base = [0.0;4];
    let source = storage.as_mut_ptr();
    let code = unsafe {lrt_creative_composite_tile(source,4,1,1,base.as_ptr(),source.add(1),4,1,1,
        IDENTITY.as_ptr(),0.0,0.0,1.0,0,ptr::null(),0)};
    assert_eq!(code,ABI_ERROR);
    assert_eq!(storage,[1.0;8]);
    let unaligned = unsafe {(storage.as_ptr() as *const u8).add(1) as *const f32};
    assert_eq!(unsafe {lrt_creative_validate_rgba(unaligned,4,1,1)},ABI_ERROR);
}

#[test]
fn reject_empty_or_oversize_tile_and_noninteger_origin_atomically() {
    let source = [1.0;4];
    let base = [0.0;4];
    let mut output = [97.0;4];
    for (w,h) in [(0,1),(MAX_TILE_PIXELS+1,1),(usize::MAX,2)] {
        assert_eq!(tile(&source,(1,1),&base,(w,h),&IDENTITY,(0.0,0.0),1.0,0,None,&mut output),ABI_ERROR);
        assert_eq!(output,[97.0;4]);
    }
    for origin in [(0.5,0.0),(f64::INFINITY,0.0),(MAX_EXACT_CANVAS_COORD*2.0,0.0)] {
        assert_eq!(tile(&source,(1,1),&base,(1,1),&IDENTITY,origin,1.0,0,None,&mut output),SETTINGS_ERROR);
        assert_eq!(output,[97.0;4]);
    }
}

#[test]
fn reject_alpha_underflow_with_remaining_hdr_instead_of_clipping() {
    let source = [1.0,0.0,0.0,f32::from_bits(1)];
    let mut output = [97.0;4];
    assert_eq!(tile(&source,(1,1),&[0.0;4],(1,1),&IDENTITY,(0.0,0.0),0.25,0,None,&mut output),RESULT_ERROR);
    assert_eq!(output,[97.0;4]);
}

#[test]
fn opaque_sdr_export_encodes_float_rgb_without_quantizing() {
    let source = [0.0,0.21404114,1.0,1.0, 0.0031308,0.5,0.25,1.0];
    let mut output = [97.0;6];
    assert_eq!(unsafe {lrt_creative_encode_opaque_sdr_rgb(source.as_ptr(),output.as_mut_ptr(),8)},0);
    close(&output,&[0.0,0.5,1.0,0.040449936,0.73535698,0.53709873]);
    assert_ne!(output[4],188.0/255.0); // No hidden RGB8 round-trip.
}

#[test]
fn opaque_sdr_export_refuses_transparency_signed_colour_and_hdr_atomically() {
    for bad in [[0.0,0.0,0.0,0.0],[0.5,0.5,0.5,0.5],[-0.01,0.0,0.0,1.0],[1.01,0.0,0.0,1.0]] {
        let source = [1.0,1.0,1.0,1.0,bad[0],bad[1],bad[2],bad[3]];
        let mut output = [97.0;6];
        assert_eq!(unsafe {lrt_creative_encode_opaque_sdr_rgb(source.as_ptr(),output.as_mut_ptr(),8)},PIXEL_ERROR);
        assert_eq!(output,[97.0;6]);
    }
}

#[test]
fn display_matte_clips_only_presentation_copy_and_preserves_input() {
    let source = [2.0,-0.5,0.25,0.5, 0.0,0.0,0.0,0.0];
    let matte = [0.25,0.5,1.0];
    let mut output = [97u8;6];
    assert_eq!(unsafe {lrt_creative_display_rgb8(source.as_ptr(),output.as_mut_ptr(),8,matte.as_ptr())},0);
    assert_eq!(output,[255,0,225,137,188,255]);
    assert_eq!(source,[2.0,-0.5,0.25,0.5, 0.0,0.0,0.0,0.0]);
}

#[test]
fn display_rejects_missing_bad_matte_and_noncanonical_pixels_without_write() {
    let source = [1.0;4];
    let mut output = [97u8;3];
    assert_eq!(unsafe {lrt_creative_display_rgb8(source.as_ptr(),output.as_mut_ptr(),4,ptr::null())},ABI_ERROR);
    assert_eq!(output,[97u8;3]);
    let matte = [-0.1,0.0,0.0];
    assert_eq!(unsafe {lrt_creative_display_rgb8(source.as_ptr(),output.as_mut_ptr(),4,matte.as_ptr())},SETTINGS_ERROR);
    assert_eq!(output,[97u8;3]);
    let bad = [1.0,0.0,0.0,0.0];
    assert_eq!(unsafe {lrt_creative_display_rgb8(bad.as_ptr(),output.as_mut_ptr(),4,[0.0;3].as_ptr())},PIXEL_ERROR);
    assert_eq!(output,[97u8;3]);
}

#[test]
fn extended_capture_preserves_sign_hdr_and_alpha_without_changing_sdr_import() {
    let source = [-0.5,2.0,0.04045,0.5, -1.0,1.0,0.0,0.0];
    let mut output = [97.0;8];
    assert_eq!(unsafe {lrt_creative_linearize_extended_rgba(source.as_ptr(),output.as_mut_ptr(),8)},0);
    let hdr = (((2.0f64+0.055)/1.055).powf(2.4)*0.5) as f32;
    close(&output,&[-0.10702057,hdr,0.0015654025,0.5, 0.0,0.0,0.0,0.0]);
    assert!(output[1]>1.0);
    let mut strict = [97.0;8];
    assert_eq!(unsafe {lrt_creative_linearize_rgba(source.as_ptr(),strict.as_mut_ptr(),8)},PIXEL_ERROR);
    assert_eq!(strict,[97.0;8]);
}

#[test]
fn extended_capture_rejects_excess_hdr_and_bad_alpha_atomically() {
    for bad in [[1000.0,0.0,0.0,1.0],[0.5,0.5,0.5,1.1],[f32::NAN,0.0,0.0,1.0]] {
        let source = [0.5,0.5,0.5,1.0,bad[0],bad[1],bad[2],bad[3]];
        let mut output = [97.0;8];
        assert_eq!(unsafe {lrt_creative_linearize_extended_rgba(source.as_ptr(),output.as_mut_ptr(),8)},PIXEL_ERROR);
        assert_eq!(output,[97.0;8]);
    }
}
