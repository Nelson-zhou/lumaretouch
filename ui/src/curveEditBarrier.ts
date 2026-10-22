/** External mutations must not overtake a pending native curve inverse solve.
 * Ownership tokens prevent an old editor's cleanup unregistering a new editor. */
let active:{owner:symbol;settle:()=>Promise<void>;busy:()=>boolean}|null=null;
export function registerCurveEditBarrier(settle:()=>Promise<void>,busy:()=>boolean=()=>true):()=>void{
  const owner=Symbol('curve-editor');active={owner,settle,busy};
  return ()=>{if(active?.owner===owner)active=null;};
}
export async function settleCurveEdit():Promise<void>{
  const current=active;if(current)await current.settle();
}
export function curveBarrierRequired(command:string,action:unknown,isMutation:boolean):boolean{
  if(!isMutation||command==='curves')return false;
  return !['state','list','status','info','get'].includes(typeof action==='string'?action:'');
}

export function isCurveEditBusy():boolean{return active?.busy()??false;}
