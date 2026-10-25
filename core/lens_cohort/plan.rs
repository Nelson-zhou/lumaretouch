// SPDX-License-Identifier: GPL-3.0-or-later
use std::mem;
use crate::{kernel::{self,Aperture},fft::{self,Complex},*};
pub(crate) const CORE:usize=254;
pub(crate) const MAX_DIRECT:u64=250_000_000;
pub(crate) const TILE_DIRECT:u64=8_388_608;
pub(crate) const MAX_BUTTERFLIES:u64=24_000_000_000;
pub(crate) const ALLOCATOR_ALLOWANCE:u64=1_048_576;
pub(crate) fn add(a:u64,b:u64)->Result<u64,i32>{a.checked_add(b).ok_or(RESOURCE_ERROR)}
pub(crate) fn mul(a:u64,b:u64)->Result<u64,i32>{a.checked_mul(b).ok_or(RESOURCE_ERROR)}
pub(crate) fn alloc<T:Clone>(n:usize,value:T)->Result<Vec<T>,i32>{
    let mut v=Vec::new();v.try_reserve_exact(n).map_err(|_|RESOURCE_ERROR)?;v.resize(n,value);Ok(v)
}
#[derive(Clone,Copy)]
pub(crate) struct Residual {pub i:usize,pub radius:f64}
pub(crate) struct Cohort {pub radius:f64,pub halo:usize,pub weights:Vec<f64>,pub spectrum:Vec<Complex>}
impl Cohort {
    pub(crate) fn weight(&self,dx:isize,dy:isize)->f64 {
        let h=self.halo as isize;
        if dx.abs()>h || dy.abs()>h {return 0.0;}
        self.weights[(dy+h) as usize*(2*self.halo+1)+(dx+h) as usize]
    }
}
pub(crate) fn cohort_radii(s:Settings)->Result<Vec<f64>,i32>{
    let mut radii=Vec::new();radii.try_reserve_exact(3).map_err(|_|RESOURCE_ERROR)?;
    for r in [kernel::radius(0.0,s),kernel::radius(-1.0,s),kernel::radius(1.0,s)] {
        if r>0.5 && !radii.iter().any(|v:&f64|v.to_bits()==r.to_bits()){radii.push(r);}
    }
    Ok(radii)
}
pub(crate) fn index(r:f64,rs:&[f64])->Option<usize>{rs.iter().position(|v|v.to_bits()==r.to_bits())}
pub(crate) fn clipped_pairs(i:usize,r:f64,w:usize,h:usize)->u64{
    let halo=kernel::halo(r);let x=i%w;let y=i/w;
    let nx=(x+halo).min(w-1)-x.saturating_sub(halo)+1;
    let ny=(y+halo).min(h-1)-y.saturating_sub(halo)+1;
    (nx*ny) as u64
}
pub(crate) fn make_plan<F:FnMut()->bool>(source:&[f32],refinement:Option<&[f32]>,
    width:usize,height:usize,s:Settings,b:Budget,cancel:&mut F)->Result<(Plan,Vec<f64>),i32>{
    s.validate()?;
    if s.abi_version!=2 || s.struct_size as usize!=mem::size_of::<Settings>()
        || b.abi_version!=2 || b.struct_size as usize!=mem::size_of::<Budget>(){return Err(ABI_ERROR);}
    if b.max_direct_pairs>MAX_DIRECT || b.reserved_repair_pairs>b.max_direct_pairs
        || b.max_fft_butterflies>MAX_BUTTERFLIES{return Err(RESOURCE_ERROR);}
    let n=width.checked_mul(height).filter(|n|*n>0 && *n<=100_000_000).ok_or(RESOURCE_ERROR)?;
    if source.len()!=n*4 || refinement.map_or(false,|q|q.len()!=n){return Err(ABI_ERROR);}
    let possible=cohort_radii(s)?;let mut counts=[0u64;3];
    let mut residuals=0u64;let mut residual_pairs=0u64;let mut hmax=0usize;
    for i in 0..n {
        if i%256==0{poll(cancel)?;}
        let p=&source[i*4..i*4+4];let q=q_at(refinement,i);
        if p[3]!=1.0 || p[..3].iter().any(|v|!kernel::unit(*v))
            || !q.is_finite() || !(-1.0..=1.0).contains(&q){return Err(PIXEL_ERROR);}
        let r=kernel::radius(q,s);hmax=hmax.max(kernel::halo(r));
        if r<=0.5 {continue;}
        if let Some(k)=index(r,&possible){counts[k]+=1;}else{
            residuals=add(residuals,1)?;
            residual_pairs=add(residual_pairs,clipped_pairs(i,r,width,height))?;
            if add(residual_pairs,b.reserved_repair_pairs)?>b.max_direct_pairs{return Err(RESOURCE_ERROR);}
        }
    }
    poll(cancel)?;
    let mut active=Vec::new();active.try_reserve_exact(3).map_err(|_|RESOURCE_ERROR)?;
    for (r,n) in possible.into_iter().zip(counts){if n>0{active.push(r);}}
    let c=active.len() as u64;let tw=width.min(CORE);let th=height.min(CORE);
    let cols=(width+tw-1)/tw;let rows=(height+th-1)/th;let tiles=mul(cols as u64,rows as u64)?;
    let fw=(tw+2*hmax).next_power_of_two();let fh=(th+2*hmax).next_power_of_two();
    let f=mul(fw as u64,fh as u64)?;let tn=mul(tw as u64,th as u64)?;
    let repeated=mul(mul(mul(tiles,f)?,3)?,c)?;
    let classification=add(add(mul(n as u64,3)?,repeated)?,mul(mul(residuals,tiles)?,2)?)?;
    let transforms=mul(c,add(1,mul(tiles,6)?)?)?;
    let per_fft=mul(f/2,(fw.trailing_zeros()+fh.trailing_zeros()) as u64)?;
    let butterflies=mul(transforms,per_fft)?;
    let support=if c==0 && residuals==0 {0}else{mul(n as u64,8)?};
    let direct=add(residual_pairs,b.reserved_repair_pairs)?;
    let mut spatial=0u64;
    for r in &active{let d=2*kernel::halo(*r)+1;spatial=add(spatial,mul(d as u64,d as u64)?)?;}
    // One quadrature evaluation means one transmission predicate. Include the
    // deliberately conservative direct-repair and residual-witness reservation.
    let quadrature=mul(add(add(spatial,direct)?,mul(residuals,8)?)?,16)?;
    let planbytes=add(add(mul(spatial,8)?,mul(mul(c,f)?,16)?)?,
        add(add(mul(residuals,mem::size_of::<Residual>() as u64)?,mul(tiles,8)?)?,ALLOCATOR_ALLOWANCE)?)?;
    let scratch=add(planbytes,add(add(mul(f,16)?,mul(fh as u64,16)?)?,mul(tn,56)?)?)?;
    let sink=mul(n as u64,16)?;
    if butterflies>b.max_fft_butterflies || quadrature>b.max_kernel_quadrature_evals
        || classification>b.max_classification_pixels || support>b.max_support_probes
        || direct>b.max_direct_pairs || scratch>b.max_scratch_bytes || sink>b.max_sink_bytes
        {return Err(RESOURCE_ERROR);}
    Ok((Plan{abi_version:2,struct_size:mem::size_of::<Plan>() as u32,math_identity:MATH_ID,
        non_delta_cohort_count:c as u32,width:width as u64,height:height as u64,source_pixels:n as u64,
        validation_pixels:n as u64,classification_pixels:classification,repeated_halo_classification_pixels:repeated,
        tile_width:tw as u64,tile_height:th as u64,tile_columns:cols as u64,tile_count:tiles,
        fft_width:fw as u64,fft_height:fh as u64,kernel_quadrature_evals:quadrature,
        fft_transform_count:transforms,fft_butterflies:butterflies,residual_emitters:residuals,
        residual_candidate_pairs:residual_pairs,residual_quadrature_upper_bound:mul(residual_pairs,16)?,
        support_probe_upper_bound:support,repair_candidate_reservation:b.reserved_repair_pairs,
        direct_pair_upper_bound:direct,owned_plan_bytes:planbytes,required_scratch_bytes:scratch,
        borrowed_source_bytes:sink,borrowed_refinement_bytes:if refinement.is_some(){mul(n as u64,4)?}else{0},
        sink_bytes:sink,output_tile_bytes:mul(tn,16)?},active))
}
pub(crate) fn prepare<F:FnMut()->bool>(radii:&[f64],p:Plan,s:Settings,cancel:&mut F)->Result<Vec<Cohort>,i32>{
    let aperture=Aperture::new(s);let fw=p.fft_width as usize;let fh=p.fft_height as usize;
    let mut cohorts=Vec::new();cohorts.try_reserve_exact(radii.len()).map_err(|_|RESOURCE_ERROR)?;
    let mut column=alloc(fh,Complex::default())?;
    for &radius in radii {
        let h=kernel::halo(radius);let d=2*h+1;
        let mut weights=alloc(d*d,0.0)?;let mut spectrum=alloc(fw*fh,Complex::default())?;
        for y in 0..d {
            poll(cancel)?;
            for x in 0..d {
                let dx=x as isize-h as isize;let dy=y as isize-h as isize;
                let weight=aperture.weight(dx as f64,dy as f64,radius);
                weights[y*d+x]=weight;
                // Positive signed offset placement: true K(destination-source).
                let xx=dx.rem_euclid(fw as isize) as usize;
                let yy=dy.rem_euclid(fh as isize) as usize;
                spectrum[yy*fw+xx].re+=weight;
            }
        }
        fft::transform(&mut spectrum,fw,fh,&mut column,false,cancel)?;
        cohorts.push(Cohort{radius,halo:h,weights,spectrum});
    }
    Ok(cohorts)
}
