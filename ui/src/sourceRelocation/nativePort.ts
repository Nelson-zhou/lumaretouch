import {invoke} from '@tauri-apps/api/core';
import {open} from '@tauri-apps/plugin-dialog';
export type Missing = {document_id:string;revision:number;old_path:string;eligible:boolean;reason?:string};
export type Candidate = {path:string;sha256:string;bytes:number};
export type PreviewRow = Missing & {sha256:string;bytes:number;candidates:Candidate[]; affected_documents?:{document_id:string;copy_number:number;trashed:boolean}[];format?:string; width?:number;height?:number;orientation?:number};
export type Preview = {preview_id:string;rows:PreviewRow[];errors:{path:string;reason:string}[];files_hashed:number;bytes_hashed:number};
export type State = {available:boolean;rows:Missing[];reason?:string;busy?:boolean;requires_readback?:boolean;workspace?:string;project_path?:string;recovery_operation_id?:string};
export type Result = {event?:string;request_id:string;status:string;error?:string;preview?:Preview;state?:State;operation?:Result;relocated?:number;requires_readback?:boolean};
export const request = (payload:Record<string,unknown>) => invoke('source_relocation_request',{request:{cmd:'source_relocation',...payload}});
export async function query(requestId:string):Promise<Result> {
  const value=await invoke<{phase:string;result:Result|null}>('source_relocation_status',{requestId});
  return value.result??{request_id:requestId,status:value.phase};
}
export const chooseFiles=()=>open({multiple:true,directory:false,title:'选择原图的新位置（按完整内容核验）'});
export const chooseFolder=()=>open({multiple:false,directory:true,title:'选择要扫描的目录（不跟随符号链接）'});
