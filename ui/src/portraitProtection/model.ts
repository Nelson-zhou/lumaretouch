/** Source-only P0: one actually measured face; no inferred identity or quality score. */
export type ProtectedRegion = [number,number,number,number];
export interface ProtectionControls {
  enabled:boolean; strength:number; protect_identity_marks:boolean; analysis_enabled:boolean;
  overlay_visible:boolean; feather:number; protected_regions:ProtectedRegion[];
}
export interface ProtectionReport {
  controls:ProtectionControls; document_id:string; revision:string; active:boolean;
  /** Actual current single-face evidence or retained same-source evidence, not capability. */
  analysis_available:boolean; reason:string|null;
}
export interface ProtectionRequest {
  cmd:'portrait_protection'; request_id:string; document_id:string; revision:string; controls:ProtectionControls;
}
export const neutralControls=():ProtectionControls=>({enabled:false,strength:0,protect_identity_marks:true,
  analysis_enabled:false,overlay_visible:false,feather:0,protected_regions:[]});
const controlFields=['enabled','strength','protect_identity_marks','analysis_enabled','overlay_visible','feather','protected_regions'];
export function validControls(value:unknown):value is ProtectionControls {
  if(!value||typeof value!=='object'||Array.isArray(value))return false;
  const c=value as ProtectionControls;
  return Object.keys(c).length===controlFields.length&&controlFields.every(k=>Object.hasOwn(c,k))
    &&[c.enabled,c.protect_identity_marks,c.analysis_enabled,c.overlay_visible].every(v=>typeof v==='boolean')
    &&typeof c.strength==='number'&&Number.isFinite(c.strength)&&c.strength>=0&&c.strength<=1
    &&Number.isInteger(c.feather)&&c.feather>=0&&c.feather<=256
    &&Array.isArray(c.protected_regions)&&c.protected_regions.length<=64&&c.protected_regions.every(b=>
      Array.isArray(b)&&b.length===4&&b.every(n=>typeof n==='number'&&Number.isFinite(n)&&n>=0&&n<=1)&&b[0]<b[2]&&b[1]<b[3]);
}
export function validRevision(value:unknown):value is string {
  return typeof value==='string'&&value.length<=20&&/^(0|[1-9][0-9]*)$/.test(value)&&BigInt(value)<=18446744073709551615n;
}
export function validRequest(value:unknown):value is ProtectionRequest {
  if(!value||typeof value!=='object'||Array.isArray(value))return false;
  const r=value as ProtectionRequest, fields=['cmd','request_id','document_id','revision','controls'];
  return Object.keys(r).length===fields.length&&fields.every(k=>Object.hasOwn(r,k))&&r.cmd==='portrait_protection'
    &&typeof r.request_id==='string'&&r.request_id.length>0&&r.request_id.length<=128
    &&typeof r.document_id==='string'&&r.document_id!=='0'&&/^[A-Za-z0-9_-]{1,128}$/.test(r.document_id)
    &&validRevision(r.revision)&&validControls(r.controls);
}
export function sameControls(a:ProtectionControls,b:ProtectionControls):boolean {
  return a.enabled===b.enabled&&a.strength===b.strength&&a.protect_identity_marks===b.protect_identity_marks
    &&a.analysis_enabled===b.analysis_enabled&&a.overlay_visible===b.overlay_visible&&a.feather===b.feather
    &&a.protected_regions.length===b.protected_regions.length&&a.protected_regions.every((box,i)=>box.every((n,j)=>n===b.protected_regions[i][j]));
}
export function sameRequest(a:ProtectionRequest,b:ProtectionRequest):boolean {
  return a.cmd===b.cmd&&a.request_id===b.request_id&&a.document_id===b.document_id&&a.revision===b.revision&&sameControls(a.controls,b.controls);
}
export const needsAnalysis=(c:ProtectionControls)=>c.analysis_enabled||(c.enabled&&c.strength>0);
