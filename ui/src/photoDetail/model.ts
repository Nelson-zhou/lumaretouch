export const names=['sharpen_amount','sharpen_radius','sharpen_detail','luma_amount','luma_detail','luma_contrast','chroma_amount','chroma_detail','chroma_smoothness'] as const;
export type Control=typeof names[number];
export type Spec=Record<Control,number>&{version:1;algorithm:'lrt-photo-detail-v1';enabled:boolean};
export const neutral=():Spec=>({version:1,algorithm:'lrt-photo-detail-v1',enabled:true,sharpen_amount:0,sharpen_radius:1,sharpen_detail:50,luma_amount:0,luma_detail:50,luma_contrast:50,chroma_amount:0,chroma_detail:50,chroma_smoothness:50});
export const labels:Record<Control,string>={sharpen_amount:'程度',sharpen_radius:'半径（原图像素）',sharpen_detail:'细节',luma_amount:'程度',luma_detail:'细节',luma_contrast:'对比度',chroma_amount:'程度',chroma_detail:'细节',chroma_smoothness:'平滑度'};
export const requirements:Record<Control,string>={sharpen_amount:'e9c7dd33a1',sharpen_radius:'d0f17720d3',sharpen_detail:'583a2e6a82',luma_amount:'16888f9a2b',luma_detail:'39567e3766',luma_contrast:'220c6c8d23',chroma_amount:'f91cc0b7ee',chroma_detail:'dbd69ac908',chroma_smoothness:'5b97b902d4'};
export const groups:{id:string;label:string;help:string;controls:Control[]}[]=[
{id:'89d0a0d750',label:'锐化',help:'程度控制边缘增强，半径控制范围，细节越高越增强细小结构；可能同时增强噪声。',controls:['sharpen_amount','sharpen_radius','sharpen_detail']},
{id:'8a30a7dc6e',label:'噪点消除',help:'细节值越高降噪越强，较低值保留更多细节；对比度调节噪点与周围亮度的融合，并非全局对比度。',controls:['luma_amount','luma_detail','luma_contrast']},
{id:'a7d79be72d',label:'减少杂色',help:'细节越高越保留色彩边缘，也可能留下色斑；平滑度越高颜色过渡越柔和，也可能损失细节。',controls:['chroma_amount','chroma_detail','chroma_smoothness']}];
export const limits=(k:Control)=>k==='sharpen_radius'?{min:0.1,max:3,step:0.1}:{min:0,max:100,step:1};
export function check(value:unknown):Spec{
 if(!value||typeof value!=='object'||Array.isArray(value))throw Error('细节配方格式错误');const v=value as Record<string,unknown>;
 if(Object.keys(v).length!==12||v.version!==1||v.algorithm!=='lrt-photo-detail-v1'||typeof v.enabled!=='boolean'||names.some(k=>typeof v[k]!=='number'||!Number.isFinite(v[k])||Number(v[k])<limits(k).min||Number(v[k])>limits(k).max))throw Error('细节配方无效');return {...v} as Spec;
}
export const same=(a:Spec,b:Spec)=>a.enabled===b.enabled&&names.every(k=>a[k]===b[k]);
export type Request={cmd:'photo_detail';request_id:string;document_id:string;revision:number;action:'set'|'reset';spec:Spec|null};
export type Receipt={event:'photo_detail_result';protocol:1;request_id:string;document_id:string;success:boolean;outcome_unknown:boolean;requires_reload:boolean;spec?:Spec;error?:string};
export function receipt(value:unknown,request:Request):Receipt{
 if(!value||typeof value!=='object')throw Error('细节回执缺失');const r=value as Receipt;
 if(r.event!=='photo_detail_result'||r.protocol!==1||r.request_id!==request.request_id||r.document_id!==request.document_id||typeof r.success!=='boolean'||typeof r.outcome_unknown!=='boolean'||typeof r.requires_reload!=='boolean')throw Error('细节回执身份不匹配');
 if(r.success&&(!r.spec||!same(check(r.spec),request.spec??neutral())))throw Error('细节回执配方不匹配');return r;
}
