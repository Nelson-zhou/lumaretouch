import {invoke} from '@tauri-apps/api/core';
import {notifyInspectionEditIntent} from '../native';
import {check,Request,Spec} from './model';
export type Readback={document_id:string;revision:number;spec:Spec;available:boolean;history:unknown};
export const detailQuery=(id:string)=>invoke<{request_id:string;phase:string;result:unknown}>('photo_detail_status',{requestId:id});
async function wait(id:string){const end=Date.now()+10000;while(Date.now()<end){const packet=await detailQuery(id);if(packet.phase==='done')return packet.result;if(packet.phase==='unknown')throw Error('引擎已重启或回执未知，请读取当前状态核对；不会重发');await new Promise(r=>setTimeout(r,100));}throw Error('细节回执等待超时，请查询原操作');}
export async function detailSend(r:Request){notifyInspectionEditIntent();await invoke('photo_detail_request',{request:r});return wait(r.request_id);}
export async function detailReadback():Promise<Readback>{const id=crypto.randomUUID();await invoke('photo_detail_request',{request:{cmd:'photo_detail_state',request_id:id}});const raw=await wait(id) as {success?:boolean;result?:Readback};if(raw.success!==true||!raw.result||typeof raw.result.document_id!=='string'||!Number.isSafeInteger(raw.result.revision)||typeof raw.result.available!=='boolean')throw Error('细节当前状态回读失败');return {...raw.result,spec:check(raw.result.spec)};}
export const detailCancel=(id:string)=>invoke<void>('photo_detail_cancel',{requestId:id});
