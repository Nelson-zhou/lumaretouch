// SPDX-License-Identifier: GPL-3.0-or-later
// AUTHORED / UNRUN. Expected properties, not passing-test evidence.
use super::*;
use std::ptr;

fn settings() -> Settings {
    Settings { aperture: 0, max_radius_px: 2.0, focus_near: 0.2, focus_far: 0.3,
               depth_falloff: 0.5, occlusion_tolerance: 0.0, rotation_radians: 0.0 }
}
fn pixels(width: usize, height: usize, colour: [f32; 4]) -> Vec<f32> {
    (0..width*height).flat_map(|_| colour).collect()
}
fn render(source: &[f32], depth: &[f32], width: usize, height: usize,
          settings: Settings, refinement: Option<&[f32]>) -> Vec<f32> {
    let mut result = vec![91.0; source.len()];
    render_tile_into(source, depth, refinement, width, height, 0, 0, width, height,
                     settings, &mut result, || false).unwrap();
    result
}
fn close(a: f32, b: f32) {
    assert!((a-b).abs() <= 2e-6 * b.abs().max(1.0), "{a} != {b}");
}

#[test]
fn zero_radius_is_bitwise_identity_including_negative_zero() {
    let source = [-0.0, -0.25, 4.0, 0.5, 0.0, 0.0, 0.0, 0.0];
    let mut s = settings(); s.max_radius_px = 0.0;
    let result = render(&source, &[0.0, 1.0], 2, 1, s, None);
    assert_eq!(result.iter().map(|v| v.to_bits()).collect::<Vec<_>>(),
               source.iter().map(|v| v.to_bits()).collect::<Vec<_>>());
}

#[test]
fn every_depth_in_focus_is_bitwise_identity() {
    let source = [0.1, 0.2, 0.3, 1.0, 0.9, 0.8, 0.7, 1.0];
    let result = render(&source, &[0.2, 0.3], 2, 1, settings(), None);
    assert_eq!(result, source);
}

#[test]
fn depth_radius_uses_interval_distance_not_focal_length() {
    let mut s = settings(); s.max_radius_px = 10.0;
    assert_eq!(source_radius(0.25, 0.0, s), 0.0);
    close(source_radius(0.8, 0.0, s) as f32, 10.0);
    close(source_radius(0.0, 0.0, s) as f32, 4.0);
    assert_eq!(source_radius(0.8, -1.0, s), 0.0);
    assert_eq!(source_radius(0.25, 1.0, s), 10.0);
}

#[test]
fn circular_aperture_is_flat_inside_and_compact_not_gaussian() {
    let a = Aperture::new(settings());
    assert_eq!(a.weight(0.0, 0.0, 5.0), a.weight(2.0, 0.0, 5.0));
    assert_eq!(a.weight(6.0, 0.0, 5.0), 0.0);
    assert_eq!(a.weight(4.0, 4.0, 5.0), 0.0);
}

#[test]
fn radius_one_impulse_matches_independent_midpoint_counts() {
    // 4x4 midpoint counts at radius 1: centre=16, axial=8, diagonal=1.
    // Total=52, so normalized output is 16/52, 8/52, 1/52 respectively.
    let mut source = pixels(7, 7, [0.0, 0.0, 0.0, 1.0]);
    source[4*(3*7+3)] = 1.0;
    let mut s = settings(); s.max_radius_px = 1.0;
    let result = render(&source, &[1.0; 49], 7, 7, s, None);
    close(result[4*(3*7+3)], 4.0/13.0);
    close(result[4*(3*7+4)], 2.0/13.0);
    close(result[4*(4*7+4)], 1.0/52.0);
    assert_eq!(result[4*(3*7+5)], 0.0);
}

#[test]
fn five_original_kernels_are_pairwise_distinct() {
    let signatures: Vec<Vec<f64>> = (0..5).map(|id| {
        let mut s = settings(); s.aperture = id;
        let a = Aperture::new(s);
        (-8..=8).flat_map(|y| (-8..=8).map(move |x| (x, y)))
            .map(|(x,y)| a.weight(x as f64, y as f64, 7.0)).collect()
    }).collect();
    for i in 0..5 { for j in i+1..5 { assert_ne!(signatures[i], signatures[j]); } }
}

#[test]
fn cat_eye_rotation_changes_support_axis_but_not_disk() {
    let mut s = settings(); s.aperture = 4;
    let horizontal = Aperture::new(s);
    s.rotation_radians = std::f32::consts::FRAC_PI_2;
    let vertical = Aperture::new(s);
    assert_eq!(horizontal.transmission(0.8, 0.0), 0.0);
    assert_eq!(vertical.transmission(0.8, 0.0), 1.0);
    s.aperture = 0;
    assert_eq!(Aperture::new(s).transmission(0.8, 0.0), 1.0);
}

#[test]
fn constant_signed_hdr_and_partial_alpha_survive_all_apertures() {
    let pixel = [-0.25, 4.0, 12.0, 0.5];
    let source = pixels(5, 4, pixel);
    for id in 0..5 {
        let mut s = settings(); s.aperture = id;
        let result = render(&source, &[1.0;20], 5, 4, s, None);
        for p in result.chunks_exact(4) {
            for c in 0..4 { close(p[c], pixel[c]); }
            assert!(valid_pixel(p));
        }
    }
}

#[test]
fn transparent_constant_remains_canonical_zero() {
    let result = render(&[0.0;64], &[1.0;16], 4, 4, settings(), None);
    assert!(result.iter().all(|v| *v == 0.0));
}

#[test]
fn transparent_boundary_blurs_premultiplied_colour_and_alpha_together() {
    let source = [0.0,0.0,0.0,0.0, 0.5,0.0,0.0,0.5, 0.0,0.0,0.0,0.0];
    let result = render(&source, &[1.0;3], 3, 1, settings(), None);
    assert!(result[0] > 0.0 && result[4] < 0.5);
    for p in result.chunks_exact(4) { assert_eq!(p[0], p[3]); assert!(valid_pixel(p)); }
}

#[test]
fn farther_emitter_cannot_contaminate_opaque_focused_foreground() {
    let source = [1.0,0.0,0.0,1.0, 0.0,0.0,1.0,1.0];
    let result = render(&source, &[0.25,1.0], 2, 1, settings(), None);
    assert_eq!(&result[..4], &source[..4]);
}

#[test]
fn near_defocused_emitter_can_spread_over_far_receiver() {
    let source = [1.0,0.0,0.0,1.0, 0.0,0.0,1.0,1.0];
    let mut s = settings(); s.focus_near = 1.0; s.focus_far = 1.0;
    let result = render(&source, &[0.0,1.0], 2, 1, s, None);
    assert!(result[4] > 0.0 && result[6] < 1.0);
}

#[test]
fn alpha_visibility_rule_is_exact_and_explicit() {
    assert_eq!(visibility(0.9, 0.1, 1.0, 0.0), 0.0);
    assert_eq!(visibility(0.9, 0.1, 0.75, 0.0), 0.25);
    assert_eq!(visibility(0.9, 0.1, 0.0, 0.0), 1.0);
    assert_eq!(visibility(0.1, 0.9, 1.0, 0.0), 1.0);
    assert_eq!(visibility(0.9, 0.1, 1.0, 1.0), 1.0);
}

#[test]
fn explicit_clear_receiver_is_exact_even_beside_near_blur() {
    let source = [1.0,0.0,0.0,1.0, -0.0,0.0,1.0,1.0];
    let mut s = settings(); s.focus_near = 1.0; s.focus_far = 1.0;
    let result = render(&source, &[0.0,1.0], 2, 1, s, Some(&[0.0,-1.0]));
    assert_eq!(result[4].to_bits(), source[4].to_bits());
    assert_eq!(&result[4..], &source[4..]);
}

#[test]
fn tile_boundaries_use_full_source_halo_and_equal_monolithic() {
    let (width, height) = (9, 7);
    let mut source = Vec::new();
    let mut depth = Vec::new();
    for i in 0..width*height {
        source.extend_from_slice(&[(i%9) as f32/8.0, (i%5) as f32/4.0, 2.0, 1.0]);
        depth.push((i%11) as f32/10.0);
    }
    let expected = render(&source, &depth, width, height, settings(), None);
    for (x,y,tw,th) in [(0,0,4,3), (4,0,5,3), (0,3,4,4), (4,3,5,4)] {
        let mut result = vec![91.0;tw*th*4];
        render_tile_into(&source,&depth,None,width,height,x,y,tw,th,settings(),
                         &mut result,|| false).unwrap();
        for row in 0..th {
            assert_eq!(&result[row*tw*4..(row+1)*tw*4],
                       &expected[((y+row)*width+x)*4..((y+row)*width+x+tw)*4]);
        }
    }
}

#[test]
fn invalid_depth_and_refinement_never_publish_even_when_neutral() {
    let source = pixels(2,1,[0.0,0.0,0.0,1.0]);
    let mut s = settings(); s.max_radius_px=0.0;
    for bad in [f32::NAN,f32::INFINITY,-0.1,1.1] {
        let mut result=[91.0;8];
        assert_eq!(render_tile_into(&source,&[0.5,bad],None,2,1,0,0,2,1,s,
                                   &mut result,|| false),Err(PIXEL_ERROR));
        assert_eq!(result,[91.0;8]);
    }
    let mut result=[91.0;8];
    assert_eq!(render_tile_into(&source,&[0.5;2],Some(&[0.0,1.1]),2,1,0,0,2,1,s,
                               &mut result,|| false),Err(PIXEL_ERROR));
    assert_eq!(result,[91.0;8]);
}

#[test]
fn noncanonical_alpha_and_hdr_are_rejected_without_clipping() {
    for pixel in [[1.0,0.0,0.0,0.0], [1.0,0.0,0.0,-0.1],
                  [65505.0,0.0,0.0,1.0], [40000.0,0.0,0.0,0.5],
                  [f32::NAN,0.0,0.0,1.0]] {
        assert_eq!(validate_inputs(&pixel,&[0.5],None,1,1,|| false),Err(PIXEL_ERROR));
    }
    assert_eq!(validate_inputs(&[-65504.0,65504.0,0.0,1.0],&[0.5],None,1,1,|| false),Ok(()));
}

#[test]
fn settings_and_resource_limits_are_fail_closed() {
    let mut s=settings(); s.aperture=5; assert_eq!(s.validate(),Err(SETTINGS_ERROR));
    s=settings(); s.max_radius_px=129.0; assert_eq!(s.validate(),Err(SETTINGS_ERROR));
    s=settings(); s.focus_near=0.9; assert_eq!(s.validate(),Err(SETTINGS_ERROR));
    s=settings(); s.depth_falloff=0.0; assert_eq!(s.validate(),Err(SETTINGS_ERROR));
    s=settings(); s.rotation_radians=f32::NAN; assert_eq!(s.validate(),Err(SETTINGS_ERROR));
    assert_eq!(count(usize::MAX,2,MAX_SOURCE_PIXELS),Err(RESOURCE_ERROR));
    assert_eq!(candidate_budget(10000,10000,65536,129),Err(RESOURCE_ERROR));
    assert_eq!(candidate_budget(10000,10000,1,129),Ok(259*259));
}

#[test]
fn cancellation_before_and_during_work_preserves_all_output() {
    let source=pixels(9,9,[0.2,0.3,0.4,1.0]);
    for cancel_at in [1,4,12] {
        let mut calls=0;
        let mut result=vec![91.0;source.len()];
        assert_eq!(render_tile_into(&source,&[1.0;81],None,9,9,0,0,9,9,settings(),
            &mut result,|| { calls+=1; calls>=cancel_at }),Err(CANCELLED));
        assert!(result.iter().all(|v| *v==91.0));
    }
}

#[test]
fn full_validation_detects_bad_data_outside_a_rendered_tile() {
    let source=pixels(20,1,[0.2,0.3,0.4,1.0]);
    let mut depth=[0.5;20]; depth[19]=f32::NAN;
    assert_eq!(validate_inputs(&source,&depth,None,20,1,|| false),Err(PIXEL_ERROR));
    // Render validates its actual halo only; full snapshot validation is a
    // required upstream step, not secretly repeated for every tile.
    let mut result=[91.0;4];
    assert_eq!(render_tile_into(&source,&depth,None,20,1,0,0,1,1,settings(),
                               &mut result,|| false),Ok(()));
}

#[test]
fn ffi_detects_partial_alias_without_constructing_mutable_slice() {
    let mut storage=pixels(2,1,[0.2,0.3,0.4,1.0]);
    let before=storage.clone();
    let source=storage.as_ptr(); let output=unsafe { storage.as_mut_ptr().add(4) };
    let depth=[1.0;2];
    let status=unsafe { lrt_lens_aperture_render_tile_v1(source,8,depth.as_ptr(),2,
        ptr::null(),0,2,1,0,0,1,1,settings(),output,4,None,ptr::null_mut()) };
    assert_eq!(status,ABI_ERROR); assert_eq!(storage,before);
}

#[test]
fn ffi_null_optional_plane_requires_zero_length() {
    let source=[0.2,0.3,0.4,1.0]; let depth=[1.0];
    let status=unsafe { lrt_lens_aperture_validate_v1(source.as_ptr(),4,depth.as_ptr(),1,
        ptr::null(),1,1,1,None,ptr::null_mut()) };
    assert_eq!(status,ABI_ERROR);
}

#[test]
fn ffi_abi_and_struct_layout_match_header() {
    assert_eq!(lrt_lens_aperture_abi(),1);
    assert_eq!(lrt_lens_aperture_kernel_mask_v1(),31);
    assert_eq!(mem::size_of::<Settings>(),28);
    assert_eq!(mem::align_of::<Settings>(),mem::align_of::<f32>());
}
