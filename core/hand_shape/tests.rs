// SPDX-License-Identifier: GPL-3.0-or-later
// AUTHORED / UNRUN: fixtures are not numerical or ABI acceptance evidence.
use super::*;

fn row()->[f64;7] { [128.,128.,0.,1.,24.,12.,0.12] }
fn call(rows:&[f64],points:&[f64],out:&mut[f64],jac:&mut[f64])->i32 {
    unsafe { lrt_hand_shape_evaluate(rows.as_ptr(),rows.len(),rows.len()/7,512,512,
        128.,points.as_ptr(),points.len(),points.len()/2,out.as_mut_ptr(),out.len(),jac.as_mut_ptr(),jac.len()) }
}
#[test]
fn neutral_and_empty_are_identity() {
    let mut primitive=row();primitive[6]=0.;
    let points=[132.1,130.7,3.2,9.1];let mut out=[99.;4];let mut jac=[99.;2];
    assert_eq!(call(&primitive,&points,&mut out,&mut jac),0);
    assert_eq!(out,[0.;4]);assert_eq!(jac,[1.;2]);
    assert_eq!(call(&[],&points,&mut out,&mut jac),0);
    assert_eq!(out,[0.;4]);assert_eq!(jac,[1.;2]);
    assert_eq!(unsafe{lrt_hand_shape_evaluate(std::ptr::null(),0,0,512,512,0.,
        std::ptr::null(),0,0,std::ptr::null_mut(),0,std::ptr::null_mut(),0)},0);
}
#[test]
fn palm_phalanx_and_knuckle_are_real_local_width_changes() {
    // Different independently reviewed visible sizes, not a body-width template.
    for (a,b) in [(24.,20.),(20.,6.),(6.,8.)] {
        let primitive=[128.,128.,0.,1.,a,b,0.12];
        let points=[128.+b*0.4,128.];let mut out=[99.;2];let mut jac=[99.;1];
        assert_eq!(call(&primitive,&points,&mut out,&mut jac),0);
        assert!(out[0]<0.);assert_eq!(out[1],0.);assert!(jac[0]>0.);
        let mut wider=primitive;wider[6]=-0.12;
        assert_eq!(call(&wider,&points,&mut out,&mut jac),0);assert!(out[0]>0.);
    }
}
#[test]
fn compact_boundary_and_exterior_are_exact_identity() {
    let primitive=row();let points=[140.,128.,128.,152.,0.,0.,511.,511.];
    let mut out=[99.;8];let mut jac=[99.;4];
    assert_eq!(call(&primitive,&points,&mut out,&mut jac),0);
    assert_eq!(out,[0.;8]);assert_eq!(jac,[1.;4]);
}
#[test]
fn analytic_off_grid_determinant_matches_differences() {
    let p=Primitive::read(&[128.,128.,0.6,0.8,24.,12.,0.12],512,512).unwrap();
    let q=[133.17,132.61];let epsilon=1e-5;
    let (s,j)=p.inverse(q);let(x,_)=p.inverse([q[0]+epsilon,q[1]]);
    let(y,_)=p.inverse([q[0],q[1]+epsilon]);
    let estimated=((x[0]-s[0])*(y[1]-s[1])-(x[1]-s[1])*(y[0]-s[0]))/(epsilon*epsilon);
    assert!((j-estimated).abs()<1e-5);
}
#[test]
fn composition_uses_actual_off_grid_intermediate_points() {
    let first=row();let second=[130.,129.,0.6,0.8,24.,12.,-0.08];
    let mut rows=first.to_vec();rows.extend_from_slice(&second);
    let q=[133.17,132.61];let mut out=[99.;2];let mut jac=[99.;1];
    let p1=Primitive::read(&first,512,512).unwrap();let p2=Primitive::read(&second,512,512).unwrap();
    let(a,j1)=p1.inverse(q);let(b,j2)=p2.inverse(a);
    assert_eq!(call(&rows,&q,&mut out,&mut jac),0);
    assert_eq!(out,[q[0]-b[0],q[1]-b[1]]);assert_eq!(jac,[j1*j2]);
    let independent=p2.inverse(q).0;
    let wrong=[2.*q[0]-a[0]-independent[0],2.*q[1]-a[1]-independent[1]];
    assert!((out[0]-wrong[0]).hypot(out[1]-wrong[1])>1e-6);
}
#[test]
fn invalid_last_point_preserves_both_complete_outputs() {
    let points=[132.,128.,f64::NAN,128.];let mut out=[91.;4];let mut jac=[92.;2];
    assert_eq!(call(&row(),&points,&mut out,&mut jac),3);
    assert_eq!(out,[91.;4]);assert_eq!(jac,[92.;2]);
    let points=[132.,128.,512.,128.];
    assert_eq!(call(&row(),&points,&mut out,&mut jac),3);
    assert_eq!(out,[91.;4]);assert_eq!(jac,[92.;2]);
}
#[test]
fn malformed_primitive_and_edges_are_refused_even_without_queries() {
    for (index,value,code) in [(0,2.,3),(2,0.1,2),(4,1.,2),(5,200.,2),(6,0.13,2),(6,f64::NAN,2)] {
        let mut primitive=row();primitive[index]=value;
        assert_eq!(call(&primitive,&[],&mut[],&mut[]),code);
    }
}
#[test]
fn explicit_budget_and_schema_refuse_without_writes() {
    let primitive=row();let points=[132.,128.];let mut out=[91.;2];let mut jac=[92.;1];
    assert_eq!(unsafe{lrt_hand_shape_evaluate(primitive.as_ptr(),7,1,512,512,0.1,
        points.as_ptr(),2,1,out.as_mut_ptr(),2,jac.as_mut_ptr(),1)},4);
    assert_eq!(out,[91.;2]);assert_eq!(jac,[92.;1]);
    assert_eq!(unsafe{lrt_hand_shape_evaluate(primitive.as_ptr(),6,1,512,512,128.,
        points.as_ptr(),2,1,out.as_mut_ptr(),2,jac.as_mut_ptr(),1)},1);
    assert_eq!(out,[91.;2]);assert_eq!(jac,[92.;1]);
}
#[test]
fn alias_null_alignment_and_address_overflow_are_refused() {
    let primitive=row();let mut points=[132.,128.];let original=points;let mut jac=[92.;1];
    assert_eq!(unsafe{lrt_hand_shape_evaluate(primitive.as_ptr(),7,1,512,512,128.,
        points.as_ptr(),2,1,points.as_mut_ptr(),2,jac.as_mut_ptr(),1)},1);
    assert_eq!(points,original);assert_eq!(jac,[92.;1]);
    assert!(span(0,1).is_err());assert!(span(1,1).is_err());
    assert!(span(usize::MAX-7,2).is_err());
    let mut out=[91.;2];
    assert_eq!(unsafe{lrt_hand_shape_evaluate(primitive.as_ptr(),7,1,512,512,128.,
        points.as_ptr(),2,1,out.as_mut_ptr(),2,out.as_mut_ptr(),1)},1);
    assert_eq!(out,[91.;2]);
}
#[test]
fn excessive_composed_jacobian_refuses_entire_candidate() {
    let mut rows=Vec::new();for _ in 0..32 { rows.extend_from_slice(&row()); }
    let points=[4.,4.,128.,128.];let mut out=[91.;4];let mut jac=[92.;2];
    assert_eq!(call(&rows,&points,&mut out,&mut jac),5);
    assert_eq!(out,[91.;4]);assert_eq!(jac,[92.;2]);
}
