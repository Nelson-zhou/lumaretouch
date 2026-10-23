import {invoke} from '@tauri-apps/api/core';
import {sampled,type Recipe,type SampleProof,type VerifiedSample} from './model';
/** Caller uses existing ColorCaptureController to display the capture descriptor
 * and acknowledges `presented` only after the exact captured frame is visible.
 * Never accept histogram readout, current canvas RGB or a final output sample. */
export async function sampleColour(request:SampleProof&{request_id:string;region:unknown},recipe:Recipe):Promise<Recipe>{
 await invoke('colour_editor_request',{request:{cmd:'colour_editor_sample',...request}});
 const end=Date.now()+5000;
 while(Date.now()<end){
  const r=await invoke<{phase:string;result?:{success:boolean;request_id:string;sample?:VerifiedSample;error?:string}}>('colour_editor_status',{requestId:request.request_id});
  if(r.phase==='done'){if(!r.result?.success||r.result.request_id!==request.request_id||!r.result.sample)throw Error(r.result?.error??'输入画面取色失败');return sampled(recipe,r.result.sample,request);}
  if(r.phase==='unknown')throw Error('取色请求未知；请重新取色');await new Promise(resolve=>setTimeout(resolve,60));
 }throw Error('输入画面取色超时');
}
