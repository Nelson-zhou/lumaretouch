/** App-lifetime exact request owner; closing a panel never cancels/retries work. */
import {useEffect,useSyncExternalStore} from 'react';
import {historyNavigationRequest,historyNavigationStatus,historyNavigationAbandon} from '../native';
import {sameRequest,sameView,validReceipt,validRequest,isMutation,validCatalog,type NamedCatalog,type NamedMutation,HISTORY_REQUEST_PREFIX,type HistoryRequest,type HistoryView} from './model';
const storageKey='lrt.retained-history.pending.v1';
function restore():HistoryRequest|null {try{const raw=sessionStorage.getItem(storageKey);if(!raw)return null;const r:unknown=JSON.parse(raw);return validRequest(r)&&isMutation(r)?r:null;}catch{return null;}}
type Snapshot={context:string;view:HistoryView|null;catalog:NamedCatalog|null;pending:HistoryRequest|null;busy:boolean;message:string;recoveryAvailable:boolean;notice:boolean};
let state:Snapshot={context:'',view:null,catalog:null,pending:restore(),busy:false,message:'',recoveryAvailable:false,notice:false};
const listeners=new Set<()=>void>();
function update(patch:Partial<Snapshot>){state={...state,...patch};listeners.forEach(fn=>fn());}
export function historyNavigationLocked(){return state.busy||state.pending!==null;}
export function useHistoryNavigation(context:string){
  const snapshot=useSyncExternalStore(fn=>{listeners.add(fn);return()=>{listeners.delete(fn);};},()=>state);
  useEffect(()=>{if(state.context!==context)update({context,view:null,catalog:null});},[context]);
  return {...snapshot,view:snapshot.context===context?snapshot.view:null,catalog:snapshot.context===context?snapshot.catalog:null};
}
const deadline=<T,>(promise:Promise<T>):Promise<T>=>{let timer:ReturnType<typeof setTimeout>;return Promise.race([promise,new Promise<T>((_,reject)=>{timer=setTimeout(()=>reject(Error('历史结果仍未确认；保留原请求，只能查询，不会重发')),12000);})]).finally(()=>clearTimeout(timer));};
function accept(raw:unknown,request:HistoryRequest,context:string):boolean {
  if(!validReceipt(raw,request))throw Error('历史回执身份或到达证明无效；请查询原操作');
  if(raw.outcome_unknown){const known=raw.last_confirmed?`最后确认在保留第 ${raw.last_confirmed.cursor} 步，但这不是当前状态证明。`:'';throw Error(`${raw.error} ${known} 不会继续跳转或重发。`);}
  if(request.action==='state'||request.action==='named_state'){
    if(raw.phase==='state'&&raw.view&&state.context===context)update({view:raw.view,catalog:request.action==='named_state'&&validCatalog(raw)?{catalog_digest:raw.catalog_digest,versions:raw.versions}:null,message:request.action==='named_state'?'已读取命名版本；选择会作为新编辑恢复到工作版本。':'已读取当前实际保留历史；点击某一步按相邻历史恢复。'});
    else if(!raw.success)update({message:raw.error??'历史读取被拒绝'});
    return false;
  }
  sessionStorage.removeItem(storageKey);
  const message=request.action!=='navigate'?(raw.success?'命名版本操作已确认；请保存工程以持久化。':raw.error??'命名版本操作未提交'):raw.phase==='applied'||raw.phase==='no_change'?`已确认到达保留第 ${raw.reached!.cursor} 步。`
    :raw.phase==='partial'?`仅到达保留第 ${raw.reached!.cursor} 步，未到请求的第 ${request.target} 步；${raw.error}。不会自动继续。`
    :raw.error??'历史跳转未提交';
  // Terminal describes the original document only. Never apply its metadata or
  // doc state to a replacement canvas; reread after every mutation terminal.
  update({pending:null,view:null,catalog:null,recoveryAvailable:false,notice:true,message});
  return raw.completed_steps>0;
}
type Reply={request_id:string;phase:string;result?:unknown;original_request?:unknown;previous_outcome?:string;recovery_available?:boolean;reason?:string;recovery_hint?:string};
function abandoned(raw:Reply,request:HistoryRequest){
  if(raw.phase!=='abandoned'||raw.request_id!==request.request_id||raw.previous_outcome!=='unknown'||!validRequest(raw.original_request)||!sameRequest(raw.original_request,request))throw Error('新工作区恢复证明不匹配');
  sessionStorage.removeItem(storageKey);update({pending:null,view:null,catalog:null,recoveryAvailable:false,notice:true,message:'已按验证的新工作区放弃旧等待；旧结果仍未知，没有重发。请重新读取历史。'});
}
async function queryOnce(request:HistoryRequest,context:string):Promise<boolean|null>{
  const raw=await deadline(historyNavigationStatus<Reply>(request));
  if(raw.request_id!==request.request_id)throw Error('历史查询身份不匹配');
  if(isMutation(request))update({recoveryAvailable:raw.recovery_available===true});
  if(raw.phase==='abandoned'){abandoned(raw,request);return false;}
  if(raw.phase==='done'){try{return accept(raw.result,request,context);}catch(e){throw Error(`${String(e)} ${raw.recovery_hint??''}`);}}
  if(!['pending','unknown'].includes(raw.phase))throw Error('历史查询状态无效');
  update({message:`${raw.reason??'仍在等待历史终态'} ${isMutation(request)?(raw.recovery_hint??'只能查询原操作，不会重发'):''}`});
  return null;
}
async function run(request:HistoryRequest,context:string):Promise<boolean>{
  const ack=await deadline(historyNavigationRequest<{requested:boolean;request_id:string;phase?:string;result?:unknown}>(request));
  if(ack.request_id!==request.request_id||typeof ack.requested!=='boolean')throw Error('历史原生入队回执无效');
  if(!ack.requested&&ack.phase==='done')return accept(ack.result,request,context);
  if(!ack.requested)throw Error('历史入队结果未确认');
  // A bounded wait ONLY queries the original native mailbox; no undo/redo or
  // desired-target submission occurs in this loop. Queue ACK is never success.
  const end=Date.now()+10000;
  while(Date.now()<end){const result=await queryOnce(request,context);if(result!==null)return result;await new Promise(r=>setTimeout(r,120));}
  throw Error(!isMutation(request)?'只读历史查询超时；可重新读取，不会修改照片':'历史终态等待超时；原请求保留，请查询，不会自动重发');
}
export async function readHistory(context:string):Promise<void>{
  if(historyNavigationLocked())return;update({busy:true,view:null,catalog:null,message:'正在读取实际保留历史'});
  try{await run({cmd:'history_navigation',action:'state',request_id:HISTORY_REQUEST_PREFIX+crypto.randomUUID()},context);}
  catch(e){update({message:String(e)});}finally{update({busy:false});}
}
export async function navigateHistory(view:HistoryView,target:number,context:string):Promise<boolean>{
  if(historyNavigationLocked()||state.context!==context||!state.view||!sameView(state.view,view))return false;
  const request:HistoryRequest={cmd:'history_navigation',action:'navigate',request_id:HISTORY_REQUEST_PREFIX+crypto.randomUUID(),view,target};
  if(!validRequest(request)){update({message:'历史目标或保留范围无效；未发送'});return false;}
  try{sessionStorage.setItem(storageKey,JSON.stringify(request));}catch{update({message:'无法保留原请求身份；未发送'});return false;}
  update({pending:request,busy:true,view:null,catalog:null,notice:true,recoveryAvailable:false,message:`等待到达保留第 ${target} 步的实际回执；不自动重试`});
  try{return await run(request,context);}catch(e){update({message:String(e)});return false;}finally{update({busy:false});}
}
export async function queryHistory():Promise<boolean>{
  const request=state.pending;if(!request||state.busy)return false;update({busy:true});
  try{return await queryOnce(request,state.context)===true;}catch(e){update({message:String(e)});return false;}finally{update({busy:false});}
}
export async function abandonHistory():Promise<boolean>{
  const request=state.pending;if(!request||state.busy||!state.recoveryAvailable)return false;update({busy:true});
  try{abandoned(await deadline(historyNavigationAbandon<Reply>(request)),request);return true;}catch(e){update({message:String(e)});return false;}finally{update({busy:false});}
}
export function historyMessage(message:string){update({message});}
export function dismissHistoryNotice(){if(!state.pending&&!state.busy)update({notice:false});}

/** Named versions share the same pending request, native mailbox and recovery fence. */
export async function readNamedVersions(context:string):Promise<void>{
  if(historyNavigationLocked())return;update({busy:true,view:null,catalog:null,message:'正在读取命名版本'});
  try{await run({cmd:'history_navigation',action:'named_state',request_id:HISTORY_REQUEST_PREFIX+crypto.randomUUID()},context);}
  catch(e){update({message:String(e)});}finally{update({busy:false});}
}
export async function mutateNamedVersion(action:({action:'named_create';name:string}|{action:'named_rename';version_id:string;name:string}|{action:'named_select';version_id:string}),context:string):Promise<boolean>{
  if(historyNavigationLocked()||state.context!==context||!state.view||!state.catalog)return false;
  const request:NamedMutation={cmd:'history_navigation',request_id:HISTORY_REQUEST_PREFIX+crypto.randomUUID(),view:state.view,catalog_digest:state.catalog.catalog_digest,...action};
  if(!validRequest(request)){update({message:'版本名称或绑定无效；未发送'});return false;}
  try{sessionStorage.setItem(storageKey,JSON.stringify(request));}catch{update({message:'无法保留原请求身份；未发送'});return false;}
  update({pending:request,busy:true,view:null,catalog:null,notice:true,recoveryAvailable:false,message:'等待命名版本操作的准确回执；不会自动重发'});
  try{return await run(request,context);}catch(e){update({message:String(e)});return false;}finally{update({busy:false});}
}
