import {invoke} from '@tauri-apps/api/core';
import {notifyInspectionEditIntent} from '../native';
import {checked,type Recipe} from './model';
import type {Reply} from './workflow';
export type Readback={document_id:string;revision:number;recipe:Recipe;available:boolean;requires_reload?:boolean};
const delay=()=>new Promise<void>(resolve=>setTimeout(resolve,60));
export async function query(id:string):Promise<Reply>{
  const p=await invoke<{phase:string;result:Reply|null}>('primary_calibration_status',{requestId:id});
  if(p.phase==='done'&&p.result)return p.result;
  return {event:'primary_calibration_result',request_id:id,status:p.phase};
}
export async function send(p:Record<string,unknown>):Promise<Reply>{
  if(p.action==='status')return query(String(p.request_id));
  if(p.action==='commit')notifyInspectionEditIntent();
  await invoke('primary_calibration_request',{request:p});
  const until=Date.now()+15000;
  while(Date.now()<until){const r=await query(String(p.request_id));if(r.status!=='pending'&&r.status!=='unknown'){
    if(r.status==='failed'||r.status==='cancelled')throw Error((r as Reply&{error?:string}).error??'RGB 原色校准未应用');
    return {...r,frame:r.frame?{...(r.frame as object),request_id:r.request_id}:undefined};
  }if(r.status==='unknown')throw Error('引擎重启或结果未知；请回读状态，不会重发');await delay();}
  throw Error('RGB 原色校准结果超时；请查询原操作');
}
export async function readback():Promise<Readback>{
  const id=crypto.randomUUID();const r=await send({cmd:'primary_calibration_state',request_id:id}) as Reply&{result?:Readback;success?:boolean};
  if(!r.success||!r.result||typeof r.result.document_id!=='string'||!Number.isSafeInteger(r.result.revision))throw Error('RGB 原色校准状态读取失败');
  return {...r.result,recipe:checked(r.result.recipe)};
}
export async function show(frame:unknown,isCurrent:()=>boolean):Promise<void>{
  const f=frame as {seq:number;slot:number;request_id:string};
  if(!Number.isSafeInteger(f.seq)||!Number.isInteger(f.slot)||typeof f.request_id!=='string')throw Error('共享帧身份缺失');
  const until=Date.now()+5000;
  while(Date.now()<until){
    if(!isCurrent())throw Error('RGB 原色校准显示请求已失效');
    const seen=await invoke<boolean>('primary_calibration_frame_status',{requestId:f.request_id,seq:f.seq,slot:f.slot});
    if(!isCurrent())throw Error('RGB 原色校准显示请求已失效');
    if(seen)return;await delay();
  }
  throw Error('RGB 原色校准帧尚未确认呈现，不能提交该预览');
}

export const abort=(id:string)=>invoke<void>('primary_calibration_abort',{requestId:id});
