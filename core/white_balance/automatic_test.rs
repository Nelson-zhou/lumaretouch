//! AUTHORED / UNRUN. These assertions have not been compiled or executed.
use super::*;
fn sample(rgb:[f64;3])->Sample {Sample {rgb,coverage:1.0,risk:0.0}}
fn grid(rgb:[f64;3])->Vec<Sample>{vec![sample(rgb);SAMPLES]}

#[test] fn exact_neutral_noop_and_determinism(){
    let rows=grid([0.2;3]);let a=estimate(&rows,[1.0;3]).unwrap();
    assert_eq!(a.gains,[1.0;3]);assert_eq!(a.accepted,1024);assert_eq!(a.stable_tiles,16);
    assert_eq!(a,estimate(&rows,[1.0;3]).unwrap());
}
#[test] fn manual_compensation_replaces_and_does_not_accumulate(){
    let rows:Vec<_>=(0..SAMPLES).map(|i|{let v=0.10+(i%13) as f64*0.01;sample([v*0.7,v,v*1.25])}).collect();
    let manual=[0.9,1.0,1.1];let a=estimate(&rows,manual).unwrap();
    let q=[a.illuminant[0]*manual[0],a.illuminant[1]*manual[1],a.illuminant[2]*manual[2]];
    let y=q.iter().zip(Y_WEIGHTS).map(|(v,w)|v*w).sum::<f64>();
    for i in 0..3 {assert!((q[i]*a.gains[i]-y).abs()<1e-12);}
    // There is deliberately no previous-picked-gains argument.
    assert_eq!(a,estimate(&rows,manual).unwrap());
}
#[test] fn clipped_source_cannot_be_laundered_by_projected_rgb(){
    let mut rows=grid([0.2;3]);for s in &mut rows{s.risk=1e-20;}
    assert_eq!(estimate(&rows,[1.0;3]),Err(Error::Insufficient));
    for s in &mut rows{s.risk=0.0;s.rgb=[0.99,0.2,0.2];}
    assert_eq!(estimate(&rows,[1.0;3]),Err(Error::Insufficient));
}
#[test] fn exclusion_is_spatial_and_not_first_n_bright_pixels(){
    let mut rows=grid([0.18,0.2,0.22]);
    for (i,s) in rows.iter_mut().enumerate(){if i%4==0{s.risk=1.0;}else if i%4==1{s.rgb=[0.001;3];}}
    let a=estimate(&rows,[1.0;3]).unwrap();assert_eq!(a.accepted,512);assert_eq!(a.stable_tiles,16);
    for s in &mut rows[..GRID*16]{s.coverage=0.5;}
    assert_eq!(estimate(&rows,[1.0;3]),Err(Error::Insufficient));
}
#[test] fn contrasting_spatial_illuminants_are_rejected(){
    let rows:Vec<_>=(0..SAMPLES).map(|i|if i%GRID<16{sample([0.1,0.2,0.3])}else{sample([0.3,0.2,0.1])}).collect();
    assert_eq!(estimate(&rows,[1.0;3]),Err(Error::Unstable));
    let mut rows=grid([0.2;3]);
    for (i,s) in rows.iter_mut().enumerate(){if i/GRID<16&&i%GRID<16{s.rgb=[0.4,0.2,0.1];}}
    assert_eq!(estimate(&rows,[1.0;3]),Err(Error::Unstable));
}
#[test] fn missing_quadrant_and_dark_input_cannot_claim_success(){
    let mut rows=grid([0.2;3]);
    for (i,s) in rows.iter_mut().enumerate(){if i/GRID<16&&i%GRID<16{s.coverage=0.0;}}
    assert_eq!(estimate(&rows,[1.0;3]),Err(Error::Unstable));
    assert_eq!(estimate(&grid([0.001;3]),[1.0;3]),Err(Error::Insufficient));
}
#[test] fn excessive_effective_or_replacement_gain_rejects_without_clamping(){
    assert_eq!(estimate(&grid([0.003,0.5,0.5]),[1.0;3]),Err(Error::Gain));
    assert_eq!(estimate(&grid([0.2;3]),[17.0;3]),Err(Error::Gain));
    assert_eq!(estimate(&grid([0.2;3]),[0.0,1.0,1.0]),Err(Error::Gain));
}
#[test] fn malformed_nonfinite_and_wrong_size_fail_closed(){
    assert_eq!(estimate(&[],[1.0;3]),Err(Error::Size));
    for value in [f64::NAN,f64::INFINITY]{let mut rows=grid([0.2;3]);rows[50].rgb[1]=value;assert_eq!(estimate(&rows,[1.0;3]),Err(Error::Invalid));}
    let mut rows=grid([0.2;3]);rows[5].risk=-0.1;assert_eq!(estimate(&rows,[1.0;3]),Err(Error::Invalid));
}
#[test] fn dominant_colour_limitation_is_explicit_not_false_recognition(){
    // Stable uniform warm paint is indistinguishable from a cast in this
    // classical policy. Passing stability is NOT physical-light recognition.
    assert!(estimate(&grid([0.3,0.2,0.15]),[1.0;3]).is_ok());
}
