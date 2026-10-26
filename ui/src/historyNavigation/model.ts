/** Metadata only. Ordinals are meaningful only inside this exact retained view. */
export type HistoryView={workspace:string;document_id:string;load_id:string;revision:string;digest:string;cursor:number;undo_steps:number;redo_steps:number;history_max:number};
export type HistoryRequest={cmd:'history_navigation';action:'state';request_id:string}|{cmd:'history_navigation';action:'navigate';request_id:string;view:HistoryView;target:number};
export type HistoryReceipt={event:'history_navigation_result';protocol:1;request_id:string;original_request:HistoryRequest;success:boolean;outcome_unknown:boolean;requires_reload:boolean;phase:'state'|'applied'|'no_change'|'partial'|'rejected'|'unknown'|'not_sent';completed_steps:number;reached:HistoryView|null;last_confirmed:HistoryView|null;view?:HistoryView;error?:string;authority?:string};
export const HISTORY_REQUEST_PREFIX='history-nav-v1:';
const viewKeys=['workspace','document_id','load_id','revision','digest','cursor','undo_steps','redo_steps','history_max'];
const bounded=(v:unknown):v is string=>typeof v==='string'&&v.length>0&&new TextEncoder().encode(v).length<=128&&!v.includes('\0');
const number=(v:unknown):v is number=>typeof v==='number'&&Number.isSafeInteger(v)&&v>=0;
export function validView(value:unknown):value is HistoryView {
  if(!value||typeof value!=='object')return false;const v=value as HistoryView;
  return Object.keys(v).length===viewKeys.length&&viewKeys.every(k=>Object.hasOwn(v,k))
    &&[v.workspace,v.document_id,v.load_id].every(bounded)&&typeof v.revision==='string'&&/^(0|[1-9][0-9]{0,19})$/.test(v.revision)&&BigInt(v.revision)<=18446744073709551615n
    &&typeof v.digest==='string'&&/^[0-9a-f]{64}$/.test(v.digest)&&number(v.history_max)&&v.history_max>=1&&v.history_max<=64
    &&number(v.undo_steps)&&number(v.redo_steps)&&v.undo_steps<=v.history_max&&v.redo_steps<=v.history_max&&v.cursor===v.undo_steps;
}
export function validRequest(value:unknown):value is HistoryRequest {
  if(!value||typeof value!=='object')return false;const r=value as HistoryRequest;
  if(r.cmd!=='history_navigation'||!bounded(r.request_id)||!r.request_id.startsWith(HISTORY_REQUEST_PREFIX)||r.request_id.length===HISTORY_REQUEST_PREFIX.length)return false;
  if(r.action==='state')return Object.keys(r).length===3;
  return r.action==='navigate'&&Object.keys(r).length===5&&validView(r.view)&&number(r.target)&&r.target<=r.view.undo_steps+r.view.redo_steps&&r.view.undo_steps+r.view.redo_steps<=r.view.history_max&&BigInt(r.view.revision)+BigInt(Math.abs(r.target-r.view.cursor))<=18446744073709551615n;
}
export function sameRequest(a:HistoryRequest,b:HistoryRequest):boolean {
  return a.cmd===b.cmd&&a.action===b.action&&a.request_id===b.request_id
    &&(a.action==='state'||(b.action==='navigate'&&a.target===b.target&&sameView(a.view,b.view)));
}
export function sameView(a:HistoryView,b:HistoryView):boolean {return viewKeys.every(k=>a[k as keyof HistoryView]===b[k as keyof HistoryView]);}
function reached(request:Extract<HistoryRequest,{action:'navigate'}>,v:unknown,done:number):v is HistoryView {
  if(!validView(v))return false;const before=request.view,steps=Math.abs(request.target-before.cursor);
  return ['workspace','document_id','load_id','history_max'].every(k=>v[k as keyof HistoryView]===before[k as keyof HistoryView])
    &&v.cursor===before.cursor+(request.target>before.cursor?done:-done)&&v.undo_steps+v.redo_steps===before.undo_steps+before.redo_steps
    &&BigInt(v.revision)>=BigInt(before.revision)&&BigInt(v.revision)<=BigInt(before.revision)+BigInt(steps);
}
export function validReceipt(value:unknown,request:HistoryRequest):value is HistoryReceipt {
  if(!value||typeof value!=='object')return false;const r=value as HistoryReceipt;
  if(r.event!=='history_navigation_result'||r.protocol!==1||r.request_id!==request.request_id||!validRequest(r.original_request)||!sameRequest(request,r.original_request)
    ||typeof r.success!=='boolean'||typeof r.outcome_unknown!=='boolean'||typeof r.requires_reload!=='boolean'||!number(r.completed_steps))return false;
  if(r.phase==='not_sent')return r.authority==='native-admission'&&!r.success&&!r.outcome_unknown&&!r.requires_reload&&r.completed_steps===0&&r.reached===null&&r.last_confirmed===null&&typeof r.error==='string';
  if(request.action==='state')return !r.outcome_unknown&&!r.requires_reload&&r.completed_steps===0&&r.reached===null&&r.last_confirmed===null
    &&((r.phase==='state'&&r.success&&validView(r.view))||(r.phase==='rejected'&&!r.success&&typeof r.error==='string'));
  const steps=Math.abs(request.target-request.view.cursor),done=r.completed_steps;
  if(done>steps)return false;
  if(r.phase==='unknown')return !r.success&&r.outcome_unknown&&r.requires_reload&&r.reached===null&&typeof r.error==='string'&&(r.last_confirmed===null||reached(request,r.last_confirmed,done));
  if(r.outcome_unknown||r.requires_reload)return false;
  if(r.phase==='rejected'&&done===0&&!r.success&&typeof r.error==='string'&&r.reached===null&&r.last_confirmed===null)return true;
  if(!reached(request,r.reached,done)||!validView(r.last_confirmed)||!sameView(r.reached,r.last_confirmed))return false;
  return ((r.phase==='applied'||r.phase==='no_change')&&r.success&&done===steps&&(r.phase==='no_change')===(steps===0)&&(r.phase!=='no_change'||sameView(r.reached,request.view)))
    ||(r.phase==='partial'&&!r.success&&done>0&&done<steps&&typeof r.error==='string')||(r.phase==='rejected'&&!r.success&&done===0&&typeof r.error==='string');
}
