export type ScopeStage='original'|'levels-input'|'curves-input'|'output';
export interface ScopeHistogram {bins:number[];underflow:number;overflow:number}
export interface ScopeAnalysis {
  version:1;bins:256;samples:number;finite_samples:number;nonfinite_samples:number;
  rgb:[ScopeHistogram,ScopeHistogram,ScopeHistogram];linear_y:ScopeHistogram;
  mean_srgb:[number,number,number]|null;mean_lab_d65:[number,number,number]|null;
}
export interface ScopeResult {
  request_id:string;document_id:string;host_doc_rev:number;stage:ScopeStage;success:boolean;error:string|null;
  quality?:'sampled-proxy-float';profile?:'working-srgb';analysis?:ScopeAnalysis;
  width?:number;height?:number;grid_width?:number;grid_height?:number;
  eligible_pixels?:number;sampled_pixels?:number;
}
export function matchesScope(result:ScopeResult|null|undefined,request:string|undefined,
  document:string,revision:number,stage:ScopeStage):result is ScopeResult {
  return !!request&&!!result&&!!document&&result.request_id===request&&result.document_id===document&&
    result.host_doc_rev===revision&&result.stage===stage;
}
export function histogramPoints(hist:ScopeHistogram,maximum:number,logarithmic:boolean):string {
  const scale=(n:number)=>logarithmic?Math.log1p(n):n;
  const top=scale(maximum)||1;
  return hist.bins.map((n,i)=>`${i},${100-100*scale(n)/top}`).join(' ');
}
