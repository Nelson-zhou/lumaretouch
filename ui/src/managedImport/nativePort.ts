import {invoke} from '@tauri-apps/api/core';
import {open} from '@tauri-apps/plugin-dialog';
export type Progress = {phase:string;bytes:number;total:number};
export type State = {available:boolean;reason?:string;busy?:boolean;recovery_operation_id?:string|null;requires_readback?:boolean};
export type Result = {request_id:string;status:string;imported?:number;error?:string;notice?:string;progress?:Progress;state?:State;operation?:Result;verified_copies?:string[]};
export const request = (payload:Record<string,unknown>)=>invoke('managed_import_request',{request:{cmd:'managed_import',...payload}});
export async function query(requestId:string):Promise<Result> {
  const value=await invoke<{phase:string;result:Result|null}>('managed_import_status',{requestId});
  return value.result??{request_id:requestId,status:value.phase};
}
export const chooseFiles=()=>open({multiple:true,directory:false,title:'选择要导入的原图'});
export const chooseFolder=()=>open({multiple:false,directory:true,title:'选择原图目录'});
export const chooseRoot=()=>open({multiple:false,directory:true,title:'选择托管复制目录（不移动原图）'});
