export const names = ['brightness','whites','blacks','texture','clarity','dehaze','vibrance'] as const;
export type Control = typeof names[number];
export type Spec = Record<Control, number> & { version: 1; algorithm: 'lrt-extended-tone-v1'; enabled: boolean; monochrome:boolean };
export const labels: Record<Control,string> = {brightness:'亮度',whites:'白色',blacks:'黑色',texture:'纹理',clarity:'清晰度',dehaze:'祛雾',vibrance:'鲜艳度'};
export const requirements: Record<Control,string> = {brightness:'935d133b92',whites:'ef0ecc2e31',blacks:'b6a3a387f1',texture:'df1b3249dd',clarity:'9dc1af72b2',dehaze:'0b1f30c7f5',vibrance:'e25d667189'};
export const neutral = (): Spec => ({version:1,algorithm:'lrt-extended-tone-v1',enabled:true,monochrome:false,brightness:0,whites:0,blacks:0,texture:0,clarity:0,dehaze:0,vibrance:0});
export function check(value:unknown):Spec {
  if (!value || typeof value!=='object' || Array.isArray(value)) throw Error('影调配方格式错误');
  const v=value as Record<string,unknown>;
  if (Object.keys(v).length!==11 || v.version!==1 || v.algorithm!=='lrt-extended-tone-v1' || typeof v.enabled!=='boolean'||typeof v.monochrome!=='boolean' || names.some(k=>typeof v[k]!=='number'||!Number.isFinite(v[k])||Number(v[k]) < -100||Number(v[k])>100)) throw Error('影调配方参数无效');
  return {...v} as Spec;
}
export const same=(a:Spec,b:Spec)=>a.enabled===b.enabled&&a.monochrome===b.monochrome&&names.every(k=>a[k]===b[k]);
export type Request={cmd:'extended_tone';request_id:string;document_id:string;revision:number;action:'set'|'reset';spec:Spec|null};
export type Receipt={event:'extended_tone_result';protocol:1;request_id:string;document_id:string;success:boolean;outcome_unknown:boolean;requires_reload:boolean;spec?:Spec;error?:string};
export function receipt(value:unknown,request:Request):Receipt {
  if(!value||typeof value!=='object')throw Error('影调回执缺失');
  const r=value as Receipt;
  if(r.event!=='extended_tone_result'||r.protocol!==1||r.request_id!==request.request_id||r.document_id!==request.document_id||typeof r.success!=='boolean'||typeof r.outcome_unknown!=='boolean'||typeof r.requires_reload!=='boolean')throw Error('影调回执身份不匹配');
  if(r.success && (!r.spec || !same(check(r.spec), request.spec??neutral())))throw Error('影调回执与请求配方不匹配');
  return r;
}
