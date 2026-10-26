/** Metadata only. Ordinals are meaningful only inside this exact retained view. */
export type HistoryView={workspace:string;document_id:string;load_id:string;revision:string;digest:string;cursor:number;undo_steps:number;redo_steps:number;history_max:number};
export type NamedCatalog={catalog_digest:string;versions:{id:string;name:string}[]};
export type NamedMutation={cmd:'history_navigation';request_id:string;view:HistoryView;catalog_digest:string}&({action:'named_create';name:string}|{action:'named_rename';version_id:string;name:string}|{action:'named_select';version_id:string});
export type HistoryRequest={cmd:'history_navigation';action:'state';request_id:string}|{cmd:'history_navigation';action:'named_state';request_id:string}|NamedMutation|{cmd:'history_navigation';action:'navigate';request_id:string;view:HistoryView;target:number};
export type HistoryReceipt={event:'history_navigation_result';protocol:1;request_id:string;original_request:HistoryRequest;success:boolean;outcome_unknown:boolean;requires_reload:boolean;phase:'state'|'applied'|'no_change'|'partial'|'rejected'|'unknown'|'not_sent';completed_steps:number;reached:HistoryView|null;last_confirmed:HistoryView|null;view?:HistoryView;catalog_digest?:string;versions?:{id:string;name:string}[];error?:string;authority?:string};
export const HISTORY_REQUEST_PREFIX='history-nav-v1:';
export const isMutation=(r:HistoryRequest)=>!['state','named_state'].includes(r.action);
export const validName=(v:unknown):v is string=>typeof v==='string'&&v.length>0&&v.trim()===v&&new TextEncoder().encode(v).length<=160&&!/[\x00-\x1f\x7f]/.test(v);
const digest=(v:unknown):v is string=>typeof v==='string'&&/^[0-9a-f]{64}$/.test(v);
export function validCatalog(v:unknown):v is NamedCatalog {
  if(!v||typeof v!=='object')return false;const c=v as NamedCatalog;
  return digest(c.catalog_digest)&&Array.isArray(c.versions)&&c.versions.length<=128&&new Set(c.versions.map(v=>v?.id)).size===c.versions.length
    &&c.versions.every(v=>!!v&&typeof v==='object'&&Object.keys(v).length===2&&bounded(v.id)&&validName(v.name));
}
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
  if(r.action==='state'||r.action==='named_state')return Object.keys(r).length===3;
  if(r.action==='named_create'||r.action==='named_rename'||r.action==='named_select')return Object.keys(r).length===(r.action==='named_rename'?7:6)&&validView(r.view)&&digest(r.catalog_digest)
    &&BigInt(r.view.revision)<18446744073709551615n&&(r.action==='named_select'||validName(r.name))&&(r.action==='named_create'||bounded(r.version_id));
  return r.action==='navigate'&&Object.keys(r).length===5&&validView(r.view)&&number(r.target)&&r.target<=r.view.undo_steps+r.view.redo_steps&&r.view.undo_steps+r.view.redo_steps<=r.view.history_max&&BigInt(r.view.revision)+BigInt(Math.abs(r.target-r.view.cursor))<=18446744073709551615n;
}
export function sameRequest(a:HistoryRequest,b:HistoryRequest):boolean {
  if(a.cmd!==b.cmd||a.action!==b.action||a.request_id!==b.request_id)return false;
  if(a.action==='state'||a.action==='named_state')return true;
  if(b.action==='state'||b.action==='named_state'||!sameView(a.view,b.view))return false;
  if(a.action==='navigate')return b.action==='navigate'&&a.target===b.target;
  if(b.action==='navigate'||a.catalog_digest!==b.catalog_digest)return false;
  return (a.action==='named_select'||('name' in b&&a.name===b.name))&&(a.action==='named_create'||('version_id' in b&&a.version_id===b.version_id));
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
  if(request.action.startsWith('named_')){
    const keys=['event','protocol','request_id','original_request','success','outcome_unknown','requires_reload','phase','completed_steps','reached','last_confirmed'];
    if(r.phase==='state'&&request.action==='named_state')keys.push('view','catalog_digest','versions');
    else if(r.phase==='applied'&&request.action!=='named_state')keys.push('catalog_digest','versions');
    else if(r.phase==='rejected'||r.phase==='unknown')keys.push('error');
    else if(r.phase==='not_sent')keys.push('authority','error');
    else return false;
    if(Object.keys(r).length!==keys.length||keys.some(k=>!Object.hasOwn(r,k)))return false;
  }
  if(r.phase==='not_sent')return r.authority==='native-admission'&&!r.success&&!r.outcome_unknown&&!r.requires_reload&&r.completed_steps===0&&r.reached===null&&r.last_confirmed===null&&typeof r.error==='string';
  if(request.action==='named_state')return !r.outcome_unknown&&!r.requires_reload&&r.completed_steps===0&&r.reached===null&&r.last_confirmed===null
    &&((r.phase==='state'&&r.success&&validView(r.view)&&validCatalog(r))||(r.phase==='rejected'&&!r.success&&typeof r.error==='string'));
  if(request.action==='named_create'||request.action==='named_rename'||request.action==='named_select'){
    if(r.view!==undefined)return false;
    if(r.phase==='unknown')return !r.success&&r.outcome_unknown&&r.requires_reload&&r.completed_steps===0&&r.reached===null&&r.last_confirmed===null&&typeof r.error==='string';
    if(r.outcome_unknown||r.requires_reload)return false;
    if(r.phase==='rejected')return !r.success&&r.completed_steps===0&&r.reached===null&&r.last_confirmed===null&&typeof r.error==='string';
    if(r.phase!=='applied'||!r.success||r.completed_steps!==1||!validView(r.reached)||!validView(r.last_confirmed)||!sameView(r.reached,r.last_confirmed)||!validCatalog(r))return false;
    if(request.action==='named_create'&&(r.catalog_digest===request.catalog_digest||!r.versions.some(v=>v.name===request.name)))return false;
    if(request.action==='named_rename'&&!r.versions.some(v=>v.id===request.version_id&&v.name===request.name))return false;
    if(request.action==='named_select'&&(r.catalog_digest!==request.catalog_digest||!r.versions.some(v=>v.id===request.version_id)))return false;
    const v=r.reached,b=request.view;
    return ['workspace','document_id','load_id','history_max'].every(k=>v[k as keyof HistoryView]===b[k as keyof HistoryView])&&BigInt(v.revision)===BigInt(b.revision)+1n
      &&(request.action==='named_select'||['cursor','undo_steps','redo_steps'].every(k=>v[k as keyof HistoryView]===b[k as keyof HistoryView]));
  }
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
