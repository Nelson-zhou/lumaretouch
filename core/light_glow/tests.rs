// SPDX-License-Identifier: GPL-3.0-or-later
// AUTHORED / UNRUN. These cases are obligations, not reported test results.
use super::*;

fn geometry(w: u32, h: u32, x: u32, y: u32, tw: u32, th: u32) -> Geometry {
    Geometry { struct_bytes: mem::size_of::<Geometry>() as u32, full_width: w,
        full_height: h, tile_x: x, tile_y: y, tile_width: tw, tile_height: th, reserved: 0 }
}
fn source(w: u32, h: u32) -> Vec<f32> {
    let mut out = Vec::new();
    for y in 0..h {
        for x in 0..w {
            let alpha = if (x + y) % 11 == 0 { 0.0 } else if x % 3 == 0 { 0.5 } else { 1.0 };
            let r = ((x * 17 + y * 5) % 101) as f32 / 100.0;
            let g = ((x * 9 + y * 13) % 101) as f32 / 100.0;
            let b = ((x * 3 + y * 19) % 101) as f32 / 100.0;
            out.extend([r * alpha, g * alpha, b * alpha, alpha]);
        }
    }
    out
}
fn extract(input: &[f32], width: u32, p: &Plan) -> Vec<f32> {
    let mut out = Vec::new();
    for y in p.region_y..p.region_y + p.region_height {
        let offset = (y * width + p.region_x) as usize * 4;
        out.extend_from_slice(&input[offset..offset + p.region_width as usize * 4]);
    }
    out
}
fn all(s: &Settings, w: u32, h: u32, input: &[f32]) -> Rendered {
    render(s, &geometry(w, h, 0, 0, w, h), input, MAX_WORK_BYTES, &mut || false).unwrap()
}

#[test]
fn declared_abi_layout_and_identity() {
    assert_eq!(mem::size_of::<Settings>(), 56);
    assert_eq!(mem::size_of::<Geometry>(), 32);
    assert_eq!(mem::size_of::<Plan>(), 72);
    assert_eq!(lrt_light_glow_abi(), 1);
    assert_eq!(lrt_light_glow_math(), 65537);
}

#[test]
fn neutral_is_bit_exact_and_needs_no_halo() {
    let s = Settings { strength: 0.0, radius_px: 512, scattering: 1.0, ..Settings::default() };
    let p = plan(&s, &geometry(1000, 700, 200, 200, 7, 5), MAX_WORK_BYTES).unwrap();
    assert_eq!((p.region_x, p.region_y, p.region_width, p.region_height, p.halo_px), (200, 200, 7, 5, 0));
    assert_eq!(p.scratch_bytes, 0);
    let mut input = source(7, 5);
    input[0] = -0.0;
    let out = render(&s, &geometry(1000, 700, 200, 200, 7, 5), &input, MAX_WORK_BYTES, &mut || false).unwrap();
    assert!(input.iter().zip(&out.rgba).all(|(a,b)| a.to_bits() == b.to_bits()));
    assert!(out.coverage.iter().all(|v| *v == 0.0));
}

#[test]
fn neutral_still_rejects_hdr_negative_and_invalid_alpha() {
    let s = Settings { strength: 0.0, ..Settings::default() };
    for p in [[1.01,0.0,0.0,1.0],[-0.01,0.0,0.0,1.0],
              [0.0,0.0,0.0,1.1],[0.01,0.0,0.0,0.0],
              [f32::NAN,0.0,0.0,1.0],[f32::INFINITY,0.0,0.0,1.0]] {
        assert!(matches!(render(&s, &geometry(1,1,0,0,1,1), &p, MAX_WORK_BYTES, &mut || false), Err(PIXEL_ERROR)));
    }
}

#[test]
fn rejects_future_math_and_bad_recipe_even_neutral() {
    let g = geometry(1,1,0,0,1,1);
    let mut s = Settings { strength: 0.0, ..Settings::default() };
    s.math_identity += 1;
    assert_eq!(plan(&s, &g, MAX_WORK_BYTES), Err(ABI_ERROR));
    s.math_identity = MATH_IDENTITY;
    s.threshold = f32::NAN;
    assert_eq!(plan(&s, &g, MAX_WORK_BYTES), Err(SETTINGS_ERROR));
    s.threshold = 0.65;
    s.radius_px = 513;
    assert_eq!(plan(&s, &g, MAX_WORK_BYTES), Err(SETTINGS_ERROR));
}

#[test]
fn source_grid_bounds_and_budget_fail_before_allocation() {
    let s = Settings::default();
    let g = geometry(8000,8000,1000,1000,256,256);
    let p = plan(&s,&g,MAX_WORK_BYTES).unwrap();
    assert_eq!(plan(&s,&g,p.required_bytes - 1),Err(BUDGET_ERROR));
    assert_eq!(plan(&s,&g,p.required_bytes).unwrap(),p);
    assert_eq!(plan(&s,&geometry(12000,12000,0,0,10,10),MAX_WORK_BYTES),Err(GEOMETRY_ERROR));
    assert_eq!(plan(&s,&geometry(8000,8000,7999,0,2,1),MAX_WORK_BYTES),Err(GEOMETRY_ERROR));
    assert_eq!(plan(&s,&geometry(8000,8000,0,0,512,512),MAX_WORK_BYTES),Err(GEOMETRY_ERROR));
}

#[test]
fn dispersion_expands_exact_finite_halo() {
    let s = Settings { radius_px: 512, scattering: 1.0, ..Settings::default() };
    let p = plan(&s,&geometry(5000,4000,1000,1000,256,256),MAX_WORK_BYTES).unwrap();
    assert_eq!(p.halo_px,640);
    assert_eq!((p.region_x,p.region_y,p.region_width,p.region_height),(360,360,1536,1536));
    assert_eq!(radii(&s),[640,512,384]);
    for reach in 0..=640 { assert_eq!((0..3).map(|pass|pass_radius(reach,pass)).sum::<usize>(),reach); }
}

#[test]
fn preserves_alpha_and_sdr_domain_for_every_mode_and_control_extreme() {
    let input = source(17,13);
    for mode in 0..3 {
        for sign in [-1.0,1.0] {
            let s = Settings { mode, strength: 1.0, radius_px: 7, threshold: 0.0,
                scattering: 1.0, exposure_ev: 4.0 * sign, hue_deg: 180.0 * sign,
                saturation: sign, lightness: sign, ..Settings::default() };
            let out = all(&s,17,13,&input);
            for (src,dst) in input.chunks_exact(4).zip(out.rgba.chunks_exact(4)) {
                assert_eq!(src[3].to_bits(),dst[3].to_bits());
                assert!(dst[..3].iter().all(|v| v.is_finite() && *v >= 0.0 && *v <= dst[3]));
                if src[3] == 0.0 { assert_eq!(src,dst); }
            }
        }
    }
}

#[test]
fn three_modes_are_not_strength_aliases() {
    let mut input = vec![0.1,0.1,0.1,1.0].repeat(25);
    input[12*4..12*4+3].copy_from_slice(&[0.95,0.95,0.95]);
    let s = Settings { radius_px: 4, threshold: 0.4, strength: 0.8, ..Settings::default() };
    let black = all(&s,25,1,&input);
    let white = all(&Settings { mode:1, ..s },25,1,&input);
    let glow = all(&Settings { mode:2, ..s },25,1,&input);
    assert!(black.rgba[12*4] < input[12*4]);
    assert!(glow.rgba[12*4] > input[12*4]);
    assert_ne!(white.rgba,glow.rgba);
    assert_ne!(black.rgba,white.rgba);
    assert!(glow.rgba[11*4] > input[11*4]);
}

#[test]
fn uniform_white_has_no_black_diffusion_delta() {
    let input = [1.0;4].repeat(25);
    let out = all(&Settings {radius_px:3,..Settings::default()},5,5,&input);
    assert_eq!(out.rgba,input);
    assert!(out.coverage.iter().all(|v|*v == 0.0));
}

#[test]
fn no_selected_light_is_unchanged_even_with_tint() {
    let input = [0.1,0.1,0.1,1.0].repeat(35);
    let s = Settings {mode:1,radius_px:3,threshold:0.8,lightness:1.0,saturation:1.0,..Settings::default()};
    let out = all(&s,7,5,&input);
    assert_eq!(out.rgba,input);
    assert!(out.coverage.iter().all(|v|*v == 0.0));
}

#[test]
fn reported_range_is_actual_effect_not_selection() {
    let input = source(11,9);
    let out = all(&Settings {mode:2,radius_px:3,threshold:0.3,..Settings::default()},11,9,&input);
    for (i,(src,dst)) in input.chunks_exact(4).zip(out.rgba.chunks_exact(4)).enumerate() {
        let expected = (0..3).map(|c|(dst[c]-src[c]).abs()).fold(0.0f32,f32::max);
        assert_eq!(out.coverage[i],expected);
    }
}

#[test]
fn full_source_tiles_match_monolithic_including_edges_and_alpha() {
    let (w,h) = (31,23);
    let input = source(w,h);
    for mode in 0..3 {
        let s = Settings {mode,radius_px:5,threshold:0.2,scattering:0.8,
            exposure_ev:0.5,hue_deg:35.0,saturation:-0.2,lightness:0.1,..Settings::default()};
        let full = all(&s,w,h,&input);
        for y in (0..h).step_by(5) {
            for x in (0..w).step_by(7) {
                let g = geometry(w,h,x,y,7.min(w-x),5.min(h-y));
                let p = plan(&s,&g,MAX_WORK_BYTES).unwrap();
                let tile = render(&s,&g,&extract(&input,w,&p),MAX_WORK_BYTES,&mut ||false).unwrap();
                for ty in 0..g.tile_height { for tx in 0..g.tile_width {
                    let fi = ((y+ty)*w+x+tx) as usize;
                    let ti = (ty*g.tile_width+tx) as usize;
                    for c in 0..4 { assert!((full.rgba[fi*4+c]-tile.rgba[ti*4+c]).abs() <= 3e-6); }
                    assert!((full.coverage[fi]-tile.coverage[ti]).abs() <= 3e-6);
                }}
            }
        }
    }
}

#[test]
fn finite_support_has_no_distant_tinted_halo() {
    let mut input = [0.0,0.0,0.0,1.0].repeat(81);
    input[40*4..40*4+3].copy_from_slice(&[1.0,1.0,1.0]);
    let s = Settings { mode:2,radius_px:5,scattering:1.0,lightness:0.7,threshold:0.2,..Settings::default() };
    let out = all(&s,81,1,&input);
    for x in 0usize..81 { if x.abs_diff(40) > 7 { assert_eq!(out.rgba[x*4],0.0); assert_eq!(out.coverage[x],0.0); } }
}

#[test]
fn cancellation_does_not_publish_any_c_output() {
    extern "C" fn stop(_: *mut c_void) -> i32 { 1 }
    let s = Settings::default();
    let g = geometry(3,2,0,0,3,2);
    let input = source(3,2);
    let mut output = [9.0f32;24];
    let mut coverage = [8.0f32;6];
    let code = unsafe { lrt_light_glow_render(&s,&g,input.as_ptr(),24,output.as_mut_ptr(),24,
        coverage.as_mut_ptr(),6,MAX_WORK_BYTES,Some(stop),ptr::null_mut()) };
    assert_eq!(code,CANCELLED);
    assert_eq!(output,[9.0;24]); assert_eq!(coverage,[8.0;6]);
}

#[test]
fn late_cancellation_is_error_not_partial_success() {
    let s = Settings {radius_px:3,..Settings::default()};
    let input = source(9,7);
    let mut calls = 0;
    let out = render(&s,&geometry(9,7,0,0,9,7),&input,MAX_WORK_BYTES,&mut || { calls+=1; calls>20 });
    assert!(matches!(out,Err(CANCELLED)));
}

#[test]
fn c_abi_invalid_length_and_pixel_leave_outputs_untouched() {
    let s = Settings::default();
    let g = geometry(1,1,0,0,1,1);
    let input = [2.0,0.0,0.0,1.0];
    for length in [3,4] {
        let mut output = [9.0f32;4]; let mut coverage = [8.0f32;1];
        let code = unsafe { lrt_light_glow_render(&s,&g,input.as_ptr(),length,output.as_mut_ptr(),4,
            coverage.as_mut_ptr(),1,MAX_WORK_BYTES,None,ptr::null_mut()) };
        assert_eq!(code,if length==3 {ABI_ERROR}else{PIXEL_ERROR});
        assert_eq!(output,[9.0;4]); assert_eq!(coverage,[8.0;1]);
    }
}

#[test]
fn c_abi_rejects_overlap_without_touching_input() {
    let s = Settings::default(); let g = geometry(1,1,0,0,1,1);
    let mut input = [0.5,0.5,0.5,1.0]; let mut coverage = [8.0f32;1];
    let code = unsafe { lrt_light_glow_render(&s,&g,input.as_ptr(),4,input.as_mut_ptr(),4,
        coverage.as_mut_ptr(),1,MAX_WORK_BYTES,None,ptr::null_mut()) };
    assert_eq!(code,ABI_ERROR); assert_eq!(input,[0.5,0.5,0.5,1.0]); assert_eq!(coverage,[8.0]);
}

#[test]
fn bounded_exposure_and_hsl_never_create_light_from_zero() {
    let s = Settings {exposure_ev:4.0,hue_deg:70.0,saturation:1.0,lightness:1.0,..Settings::default()};
    assert_eq!(tint([0.0;3],&s),[0.0;3]);
    for c in [[0.1,0.2,0.3],[1.0,1.0,1.0],[1.0,0.0,0.0]] {
        assert!(tint(c,&s).iter().all(|v|(-1e-12..=1.0+1e-12).contains(v)));
    }
}

#[test]
fn sliding_box_matches_independent_direct_window_oracle() {
    // This oracle deliberately does not reuse the rolling sum or its indexing.
    let (w,h) = (13usize,9usize);
    let mut input = vec![0.0;w*h*CHANNELS];
    for y in 0..h { for x in 0..w { for channel in 0..CHANNELS {
        input[(y*w+x)*CHANNELS+channel] = if (x+2*y+channel)%5 == 0 {0.0}
            else {((x*11+y*7+channel*3)%67) as f32/66.0};
    }}}
    for horizontal in [true,false] { for pass in 0..3 {
        let reaches = [7,5,3];
        let mut actual = vec![0.0;input.len()];
        blur_axis(&input,&mut actual,w,h,reaches,pass,horizontal,&mut ||false).unwrap();
        for y in 0..h { for x in 0..w { for channel in 0..CHANNELS {
            let radius = (reaches[channel%3]+pass)/3;
            let mut expected = 0.0f64;
            for offset in -(radius as isize)..=radius as isize {
                let xx = if horizontal {(x as isize+offset).max(0).min(w as isize-1) as usize}else{x};
                let yy = if horizontal {y}else{(y as isize+offset).max(0).min(h as isize-1) as usize};
                expected += input[(yy*w+xx)*CHANNELS+channel] as f64;
            }
            expected /= (2*radius+1) as f64;
            assert!((actual[(y*w+x)*CHANNELS+channel] as f64-expected).abs()<=1e-7);
        }}}
    }}
}
