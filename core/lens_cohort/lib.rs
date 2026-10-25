// SPDX-License-Identifier: GPL-3.0-or-later
//! Original exact-radius cohort/overlap-save lens core, AUTHORED / UNRUN.
//! ABI2 intentionally does not reinterpret ABI1 recipes. No I/O, image rescale,
//! inference, threading, external FFT dependency, source copy or full output.
mod contract;
mod kernel;
mod fft;
mod plan;
mod render;
pub use contract::{Settings,Budget,Plan};
pub use render::{Job,NORMALIZED_ROUNDOFF};
use std::{ffi::c_void,mem,panic,ptr,slice};
pub const MATH_ID:u32=0x0002_0001;
pub const ABI_ERROR:i32=1;
pub const SETTINGS_ERROR:i32=2;
pub const PIXEL_ERROR:i32=3;
pub const CANCELLED:i32=4;
pub const RESOURCE_ERROR:i32=5;
pub const PANIC_ERROR:i32=6;
pub const RESULT_ERROR:i32=7;
pub const STATE_ERROR:i32=8;
pub type Cancel=Option<extern "C" fn(*mut c_void)->i32>;
pub(crate) fn poll<F:FnMut()->bool>(cancel:&mut F)->Result<(),i32>{if cancel(){Err(CANCELLED)}else{Ok(())}}
pub(crate) fn q_at(q:Option<&[f32]>,i:usize)->f32{q.map_or(0.0,|q|q[i])}
fn span<T>(p:*const T,len:usize)->Result<(usize,usize),i32>{
    let start=p as usize;let bytes=len.checked_mul(mem::size_of::<T>()).ok_or(ABI_ERROR)?;
    if p.is_null()||start%mem::align_of::<T>()!=0||bytes>isize::MAX as usize{return Err(ABI_ERROR);}
    Ok((start,start.checked_add(bytes).ok_or(ABI_ERROR)?))
}
fn overlap(a:(usize,usize),b:(usize,usize))->bool{a.0<b.1&&b.0<a.1}
fn caught(result:Result<Result<(),i32>,Box<dyn std::any::Any+Send>>)->i32{
    match result{Ok(Ok(()))=>0,Ok(Err(e))=>e,Err(_)=>PANIC_ERROR}
}
#[no_mangle]
pub extern "C" fn lrt_lens_cohort_abi()->u32{2}
#[no_mangle]
pub extern "C" fn lrt_lens_cohort_math_identity()->u32{MATH_ID}
/// # Safety
/// All pointer spans are valid live allocations. Inputs remain immutable for the
/// entire job lifetime. Outputs cannot alias inputs/each other. Callback must not
/// mutate, free, reenter or unwind. Flags are not provenance authentication.
#[no_mangle]
pub unsafe extern "C" fn lrt_lens_cohort_create_v2(
    source:*const f32,source_len:usize,refinement:*const f32,refinement_len:usize,
    width:usize,height:usize,settings:Settings,budget:Budget,
    out_job:*mut *mut Job<'static>,out_plan:*mut Plan,cancel:Cancel,context:*mut c_void)->i32{
    caught(panic::catch_unwind(panic::AssertUnwindSafe(||{
        let n=width.checked_mul(height).filter(|n|*n>0&&*n<=100_000_000).ok_or(RESOURCE_ERROR)?;
        if source_len!=n*4{return Err(ABI_ERROR);}
        let srcspan=span(source,source_len)?;let jobspan=span(out_job,1)?;let planspan=span(out_plan,1)?;
        if overlap(jobspan,planspan)||overlap(srcspan,jobspan)||overlap(srcspan,planspan){return Err(ABI_ERROR);}
        let refinement=if refinement.is_null(){
            if refinement_len!=0{return Err(ABI_ERROR);}None
        }else{
            if refinement_len!=n{return Err(ABI_ERROR);}let qs=span(refinement,refinement_len)?;
            if overlap(qs,jobspan)||overlap(qs,planspan){return Err(ABI_ERROR);}
            Some(slice::from_raw_parts(refinement,refinement_len))
        };
        let job=Job::create(slice::from_raw_parts(source,source_len),refinement,width,height,
            settings,budget,||cancel.map_or(false,|f|f(context)!=0))?;
        let plan=job.plan;
        // Fallible small handle allocation; unlike Box::new no allocation-error
        // abort is requested here. Vec payloads likewise use try_reserve_exact.
        let layout=std::alloc::Layout::new::<Job<'static>>();
        let handle=std::alloc::alloc(layout) as *mut Job<'static>;
        if handle.is_null(){return Err(RESOURCE_ERROR);}
        ptr::write(handle,job);
        ptr::write(out_plan,plan);ptr::write(out_job,handle);Ok(())
    })))
}
/// # Safety
/// Valid live handle from create, single caller, no reentrancy; writable output
/// allocation disjoint from handle and all borrowed inputs; callback as above.
#[no_mangle]
pub unsafe extern "C" fn lrt_lens_cohort_render_next_v2(job:*mut Job<'static>,index:u64,
    output:*mut f32,output_len:usize,cancel:Cancel,context:*mut c_void)->i32{
    let result=panic::catch_unwind(panic::AssertUnwindSafe(||{
        let js=span(job,1)?;let out=span(output,output_len)?;
        if overlap(js,out){return Err(ABI_ERROR);}
        let j=&mut *job;
        let src=span(j.source.as_ptr(),j.source.len())?;
        if overlap(src,out)||j.refinement.map_or(false,|q|{
            // Already validated source span; still checked rather than guessed.
            span(q.as_ptr(),q.len()).map_or(true,|qs|overlap(qs,out))
        }){j.failed=true;return Err(ABI_ERROR);}
        if index!=j.next{j.failed=true;return Err(STATE_ERROR);}
        let (_,_,w,h)=match j.tile_rect(index){Ok(rect)=>rect,Err(e)=>{j.failed=true;return Err(e);}};
        if output_len!=w*h*4{j.failed=true;return Err(ABI_ERROR);}
        j.render_next(index,slice::from_raw_parts_mut(output,output_len),
            ||cancel.map_or(false,|f|f(context)!=0))
    }));
    if result.is_err() && !job.is_null() && (job as usize)%mem::align_of::<Job<'static>>()==0{
        // Caller guarantees a valid handle; panic recovery cannot repair a bad
        // foreign pointer or callback fault. No external output has been copied.
        (*job).failed=true;
    }
    caught(result)
}
#[no_mangle]
pub unsafe extern "C" fn lrt_lens_cohort_finish_v2(job:*const Job<'static>)->i32{
    caught(panic::catch_unwind(panic::AssertUnwindSafe(||{span(job,1)?;(&*job).finish()})))
}
/// # Safety
/// Null or unique live handle; never double-destroy or race another operation.
#[no_mangle]
pub unsafe extern "C" fn lrt_lens_cohort_destroy_v2(job:*mut Job<'static>){
    if !job.is_null(){ptr::drop_in_place(job);std::alloc::dealloc(job.cast(),std::alloc::Layout::new::<Job<'static>>());}
}
#[cfg(test)]
mod tests;
