import {invoke} from '@tauri-apps/api/core';
import {bounded} from '../virtualCopies/nativePort';
import {isReport,type GuideReport} from './model';
export interface GuideResult {event:'canvas_guides_result';request_id:string;success:boolean;canvas_guides?:GuideReport;error?:string}
export const send=(request:Record<string,unknown>)=>bounded(invoke('canvas_guides_request',{request:{cmd:'canvas_guides',...request}}),10000);
export async function receipt(requestId:string):Promise<GuideResult|null>{
  const r=await bounded(invoke<{phase:string;result:GuideResult|null}>('canvas_guides_status',{requestId}),10000);
  if(!r||!['done','pending','unknown'].includes(r.phase))throw Error('参考线回执格式无效');
  if(r.phase!=='done')return null;
  if(!r.result||r.result.event!=='canvas_guides_result'||r.result.request_id!==requestId||typeof r.result.success!=='boolean')throw Error('参考线回执身份不符');
  if(r.result.success&&!isReport(r.result.canvas_guides))throw Error('参考线状态格式无效');
  return r.result;
}
export async function awaitReceipt(id:string){
  const until=Date.now()+10000;
  while(Date.now()<until){const r=await receipt(id);if(r)return r;await new Promise(resolve=>setTimeout(resolve,100));}
  throw Error('参考线结果待确认，请查询原操作；不会自动重发');
}
