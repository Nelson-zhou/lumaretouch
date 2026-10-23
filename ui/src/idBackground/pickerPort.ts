import {invoke} from '@tauri-apps/api/core';
import {pickerStages,type RGB,type PickerMode} from './model';
type Proof={document_id:string;capture_id:string;ticket:string;generation:string;recipe_document_id:string;recipe_revision:string};
export async function sampleOriginal(request:Proof&{request_id:string;region:unknown;picker_mode:PickerMode;source_binding:unknown}):Promise<RGB>{
 await invoke('id_background_request',{request:{cmd:'background',action:'id_sample',...request}});
 const deadline=Date.now()+10000;
 while(Date.now()<deadline){
  const r=await invoke<{phase:string;result?:{success:boolean;request_id:string;error?:string;sample?:{rgb:RGB;proof:Proof;source_stage:string;quality:string;picker_mode:PickerMode;source_binding:unknown}}}>('id_background_status',{requestId:request.request_id});
  if(r.phase==='done'){
   const result=r.result,s=result?.sample;if(!result?.success||result.request_id!==request.request_id||!s)throw Error(result?.error??'当前源图取色失败');
   for(const key of ['document_id','capture_id','ticket','generation','recipe_document_id','recipe_revision'] as const)if(s.proof[key]!==request[key])throw Error('当前源图取色身份已变化');
   if(s.source_stage!==pickerStages[request.picker_mode]||s.picker_mode!==request.picker_mode||JSON.stringify(s.source_binding)!==JSON.stringify(request.source_binding)||s.quality!=='proxy-float-input'||s.rgb.length!==3||s.rgb.some(n=>!Number.isInteger(n)||n<0||n>255))throw Error('当前源图取色结果无效');return s.rgb;
  }
  if(r.phase==='unknown')throw Error('取色结果未知，请关闭取色后重新进入');await new Promise(resolve=>setTimeout(resolve,100));
 }
 throw Error('当前源图取色超时；未修改背景配方');
}
