// SPDX-License-Identifier: GPL-3.0-or-later
// AUTHORED / UNRUN. Analytic synthetic inputs are not photographic acceptance.
use super::*;
const W: usize = 48;
const N: usize = W*W;
fn landmarks() -> Vec<f32> {
    let mut lm = vec![0.5; LANDMARK_FLOATS];
    for p in lm.chunks_exact_mut(3) { p[2] = 0.0; }
    for (id, x, y) in [(10,0.5,0.12), (152,0.5,0.90), (127,0.18,0.25), (356,0.82,0.25), (234,0.20,0.58),
        (454,0.80,0.58), (168,0.50,0.32), (6,0.50,0.40), (197,0.50,0.46), (4,0.50,0.53)] {
        lm[3*id] = x; lm[3*id+1] = y;
    }
    for (ids, cx, cy) in [(&LEFT_EYE, 0.35, 0.35), (&RIGHT_EYE, 0.65, 0.35), (&LIPS, 0.5, 0.72)] {
        for (j, &id) in ids.iter().enumerate() {
            lm[3*id] = cx+if j%2 == 0 { -0.05 } else { 0.05 };
            lm[3*id+1] = cy+if j%3 == 0 { -0.02 } else { 0.02 };
        }
    }
    lm
}
struct Fixture {
    target: Vec<f32>, donor: Vec<f32>, tl: Vec<f32>, dl: Vec<f32>,
    allowed: Vec<f32>, protected: Vec<f32>, fusion: Vec<f32>, colour: Vec<f32>,
}
impl Fixture {
    fn new() -> Self {
        let target: Vec<f32> = [0.2,0.3,0.4,1.0].repeat(N);
        let donor: Vec<f32> = [0.7,0.5,0.1,1.0].repeat(N);
        let mut fusion = vec![0.0; N];
        for y in 10..38 { for x in 10..38 { fusion[y*W+x] = 1.0; } }
        Self { target, donor, tl: landmarks(), dl: landmarks(), allowed: vec![1.0; N],
            protected: vec![0.0; N], fusion, colour: vec![0.0; N] }
    }
    fn input(&self) -> Inputs<'_> {
        Inputs { target: &self.target, donor: &self.donor, target_landmarks: &self.tl,
            donor_landmarks: &self.dl, target_allowed: &self.allowed, donor_allowed: &self.allowed,
            target_protection: &self.protected, donor_protection: &self.protected,
            fusion: &self.fusion, colour_reference: &self.colour,
            tw: W, th: W, dw: W, dh: W, reviews: REQUIRED_REVIEWS, density: 1.0,
            colour_strength: 0.0, levels: 3, cancel: None }
    }
    unsafe fn ffi(&self, output: *mut f32, out_len: usize, receipt: *mut f32, cancel: Cancel) -> i32 {
        let mut effective = vec![7.0;N];
        let status = lrt_expression_blend_v1(self.target.as_ptr(),self.target.len(),W,W,
            self.donor.as_ptr(),self.donor.len(),W,W,self.tl.as_ptr(),self.tl.len(),
            self.dl.as_ptr(),self.dl.len(),self.allowed.as_ptr(),N,self.allowed.as_ptr(),N,
            self.protected.as_ptr(),N,self.protected.as_ptr(),N,self.fusion.as_ptr(),N,
            if self.colour.is_empty() { std::ptr::null() } else { self.colour.as_ptr() },
            self.colour.len(),REQUIRED_REVIEWS,1.0,0.0,3,
            output,out_len,effective.as_mut_ptr(),N,receipt,RECEIPT_FLOATS,cancel);
        if status != 0 { assert!(effective.iter().all(|&v|v==7.0)); }
        status
    }
}
#[test]
fn identity_anchor_fit_is_exact_and_does_not_fit_eyes_or_mouth() {
    let f = Fixture::new(); let mut donor = f.dl.clone();
    for id in LEFT_EYE.iter().chain(RIGHT_EYE.iter()).chain(LIPS.iter()) { donor[3*id+1] += 0.08; }
    let s = fit(&f.tl,&donor,W,W,W,W).unwrap();
    assert_eq!([s.a,s.b,s.tx,s.ty,s.rms,s.maximum], [1.0,0.0,0.0,0.0,0.0,0.0]);
}
#[test]
fn translation_is_recovered_and_expression_is_not_undone() {
    let f = Fixture::new(); let mut target = f.tl.clone();
    for p in target.chunks_exact_mut(3) { p[0] += 0.02; p[1] -= 0.03; }
    let s = fit(&target,&f.dl,W,W,W,W).unwrap();
    assert!((s.a-1.0).abs() < 1e-6 && s.b.abs() < 1e-6);
    assert!((s.tx-0.94).abs() < 1e-5 && (s.ty+1.41).abs() < 1e-5);
    let p = Point { x: 13.2, y: 20.6 }; let r = s.inverse(s.forward(p));
    assert!((r.x-p.x).abs() < 1e-10 && (r.y-p.y).abs() < 1e-10);
}
#[test]
fn reflection_and_degenerate_landmarks_refuse() {
    let f = Fixture::new(); let mut reflected = f.dl.clone();
    for p in reflected.chunks_exact_mut(3) { p[0] = 1.0-p[0]; }
    assert_eq!(fit(&f.tl,&reflected,W,W,W,W).unwrap_err(), BAD_ALIGNMENT);
    let flat = vec![0.5; LANDMARK_FLOATS];
    assert_eq!(fit(&flat,&flat,W,W,W,W).unwrap_err(), BAD_ALIGNMENT);
}
#[test]
fn unknown_reviews_and_incompatible_2d_geometry_fail_closed() {
    assert_eq!(validate_reviews(126), Err(REVIEW_REQUIRED));
    assert_eq!(validate_reviews(127|128), Err(REVIEW_REQUIRED));
    let f = Fixture::new();
    assert_eq!(compatible_2d(&f.tl,&f.dl,W,W,W,W), Ok(()));
    let mut turned = f.dl.clone(); turned[3*4] = 0.72;
    assert_eq!(profile_2d(&turned,W,W).err(),Some(BAD_POSE));
    let flat = vec![0.5;LANDMARK_FLOATS];
    assert_eq!(profile_2d(&flat,W,W).err(),Some(BAD_POSE));
}
#[test]
fn neutral_density_and_erased_mask_are_bit_exact() {
    let mut f = Fixture::new(); f.target[0] = -0.0;
    let mut input = f.input(); input.density = 0.0;
    let (out, _, _) = render(&input).unwrap();
    assert!(out.iter().zip(&f.target).all(|(a,b)| a.to_bits()==b.to_bits()));
    f.fusion.fill(0.0);
    assert_eq!(render(&f.input()).unwrap().0, f.target);
}
#[test]
fn identical_pixels_are_exact_even_with_many_bands() {
    let mut f = Fixture::new(); f.donor.copy_from_slice(&f.target);
    let mut input = f.input(); input.levels = 5;
    let (out, _, report) = render(&input).unwrap();
    assert_eq!(out, f.target); assert_eq!(report[11],0.0);
}
#[test]
fn fractional_density_is_linear_and_zero_coverage_does_not_bleed() {
    let f = Fixture::new(); let mut input = f.input();
    let (full, _, _) = render(&input).unwrap(); input.density = 0.5;
    let (half, _, _) = render(&input).unwrap();
    assert!(full != f.target);
    for i in 0..N {
        for c in 0..3 {
            let j = 4*i+c;
            assert!((half[j] as f64-(f.target[j] as f64+full[j] as f64)*0.5).abs() < 1e-7);
            if f.fusion[i] == 0.0 { assert_eq!(full[j].to_bits(),f.target[j].to_bits()); }
        }
        assert_eq!(half[4*i+3],1.0);
    }
}
#[test]
fn even_tiny_positive_protection_is_a_hard_veto() {
    let mut f = Fixture::new(); let i = 24*W+24; f.protected[i] = f32::MIN_POSITIVE;
    let (out, _, _) = render(&f.input()).unwrap();
    assert_eq!(&out[4*i..4*i+4],&f.target[4*i..4*i+4]);
}
#[test]
fn fusion_cannot_expand_reviewed_target_eligibility() {
    let mut f = Fixture::new(); f.allowed[24*W+24] = 0.5;
    assert_eq!(render(&f.input()).err(), Some(BAD_SUPPORT));
}
#[test]
fn unavailable_donor_tap_is_not_clamped_filled_or_generated() {
    let f = Fixture::new(); let mut donor_cap = f.allowed.clone(); donor_cap[24*W+24] = 0.0;
    let mut input = f.input(); input.donor_allowed = &donor_cap;
    assert_eq!(render(&input).err(),Some(BAD_SUPPORT));
    assert_eq!(taps(Point{x:-0.00001,y:0.0},W,W).err(),Some(BAD_SUPPORT));
    assert_eq!(taps(Point{x:W as f64,y:0.0},W,W).err(),Some(BAD_SUPPORT));
}
#[test]
fn transparent_hdr_and_nonfinite_sources_are_not_silently_converted() {
    for value in [f32::NAN,f32::INFINITY,-0.01,1.01] {
        let mut f = Fixture::new(); f.donor[0] = value;
        assert_eq!(render(&f.input()).err(),Some(BAD_DATA));
    }
    let mut f = Fixture::new(); f.target[3] = 0.5;
    assert_eq!(render(&f.input()).err(),Some(BAD_DATA));
}
#[test]
fn colour_matching_needs_sufficient_nonexpressive_reviewed_skin() {
    let mut f = Fixture::new(); let mut input = f.input(); input.colour_strength = 1.0;
    assert_eq!(render(&input).err(),Some(BAD_COLOUR));
    for y in 31..36 { for x in 21..27 { f.colour[y*W+x] = 1.0; } }
    let mut input = f.input(); input.colour_strength = 1.0;
    assert_eq!(render(&input).err(),Some(BAD_COLOUR));
}
#[test]
fn binomial_downsample_preserves_constant_and_reconstruction_is_bounded() {
    let l = Level { width: 5, height: 3, channels: 1, data: vec![0.25;15] };
    let down = blur_down(&l,None).unwrap();
    assert_eq!((down.width,down.height),(3,2)); assert!(down.data.iter().all(|&v|v==0.25));
    let target = vec![0.25;15*3]; let donor = vec![0.75;15*3]; let mask = vec![1.0;15];
    let out = multiband(target,donor,mask,5,3,2,None).unwrap();
    assert!(out.iter().all(|&v|(v-0.75).abs()<1e-7));
}
extern "C" fn stop() -> i32 { 1 }
#[test]
fn ffi_failures_and_cancellation_leave_all_outputs_unchanged() {
    let f = Fixture::new(); let mut output = vec![9.0;N*4]; let mut receipt = [8.0;16];
    assert_eq!(unsafe{f.ffi(output.as_mut_ptr(),N*4-1,receipt.as_mut_ptr(),None)},BAD_ABI);
    assert_eq!(unsafe{f.ffi(output.as_mut_ptr(),N*4,receipt.as_mut_ptr(),Some(stop))},CANCELLED);
    assert!(output.iter().all(|&v|v==9.0)); assert_eq!(receipt,[8.0;16]);
    assert_eq!(unsafe{f.ffi(output.as_mut_ptr(),N*4,output.as_mut_ptr(),None)},BAD_ABI);
    assert_eq!(unsafe{f.ffi(f.target.as_ptr() as *mut f32,N*4,receipt.as_mut_ptr(),None)},BAD_ABI);
    assert!(output.iter().all(|&v|v==9.0)); assert_eq!(receipt,[8.0;16]);
}
#[test]
fn explicit_resource_limits_and_receipt_are_versioned() {
    assert_eq!(count(1025,32),Err(BAD_ABI)); assert_eq!(count(1,32),Err(BAD_ABI));
    assert_eq!(count(usize::MAX,2),Err(BAD_ABI)); assert_eq!(lrt_expression_blend_abi(),1);
    let f = Fixture::new(); let (out, _, receipt) = render(&f.input()).unwrap();
    assert_eq!(out.len(),N*4); assert_eq!(receipt[4],1.0);
    assert_eq!(&receipt[13..],[3.0,1.0,0.0]);
    assert!(out.chunks_exact(4).all(|p|p[3]==1.0 && p[..3].iter().copied().all(unit)));
}

#[test]
fn absent_colour_reference_and_authentic_effective_mask() {
    let mut f = Fixture::new(); f.fusion[24*W+24] = 0.5;
    let mut input = f.input(); input.colour_reference = &[]; input.density = 0.5;
    let (_, mask, _) = render(&input).unwrap();
    assert_eq!(mask[24*W+24],0.25); assert_eq!(mask[0],0.0);
    input.colour_strength = 0.1;
    assert_eq!(render(&input).err(),Some(BAD_ABI));
    f.colour.clear();
    let mut out = vec![9.0;N*4]; let mut report = [8.0;16];
    assert_eq!(unsafe { f.ffi(out.as_mut_ptr(),out.len(),report.as_mut_ptr(),None) },0);
}
