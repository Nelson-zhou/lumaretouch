// Source-only queue controls. Dispatch acknowledgement is NOT a task outcome.
import {useEffect,useRef,useState} from 'react';
import {runTask} from '../native';
import type {EngineStatus,TaskState} from '../native';
type Action = 'pause'|'resume'|'cancel'|'retry'|'delete';
type Receipt = {task_id:string;token:string;project_id:string|null;workspace_generation:string;session_id:string;request_id:string;action:string;success:boolean;error?:string};
type Control = {protocol:1;token:string;revision:string;project_id:string|null;workspace_generation:string;session_id:string;available:boolean;allowed:Action[];result?:Receipt|null};
type Row = TaskState & {control?:Control};
type Pending = {request:string;action:Action;taskId:string;token:string;project:string|null;workspace:string;session:string;message:string};
// Survives export-workspace dismissal. Never silently resend an uncertain action.
const pending = new Map<string,Pending>();
const deleted = new Map<string,Receipt>();
const matches=(p:Pending,r:Receipt)=>r.task_id===p.taskId&&r.token===p.token&&r.project_id===p.project&&r.workspace_generation===p.workspace&&r.session_id===p.session&&r.request_id===p.request&&r.action===p.action;
const labels:Record<Action,string>={pause:'请求暂停',resume:'继续',cancel:'请求取消',retry:'按冻结输入重试',delete:'删除记录（保留文件）'};
async function bounded<T>(promise:Promise<T>):Promise<T>{
 return new Promise((resolve,reject)=>{const timer=setTimeout(()=>reject(Error('回执未确认')),15000);
  promise.then(value=>{clearTimeout(timer);resolve(value);},error=>{clearTimeout(timer);reject(error);});});
}
const actions:Action[]=['pause','resume','cancel','retry','delete'];
export function ExportTaskControls({status}:{status:EngineStatus|null}){
 const [,render]=useState(0),mounted=useRef(true),flight=useRef(false);
 const project=status?.project?.project_id??null;
 const rows=(status?.tasks??[]) as Row[];
 const latest=useRef({status,project,rows});latest.current={status,project,rows};
 const update=()=>{if(mounted.current)render(n=>n+1);};
 useEffect(()=>{mounted.current=true;return()=>{mounted.current=false;};},[]);
 useEffect(()=>{
  let changed=false;
  for(const row of rows){const c=row.control,p=c&&pending.get(c.token),r=c?.result;
   if(p&&r&&p.project===project&&matches(p,r)){
    // Confirmation is of this command, not of boundary completion or output quality.
    pending.delete(p.token);changed=true;
   }
  }
  for(const r of status?.task_control_results??[]){const p=pending.get(r.token);
   if(p&&p.project===project&&matches(p,r)&&r.action==='delete'&&r.success===true){
    deleted.set(r.token,r);pending.delete(r.token);changed=true;
   }
  }
  if(changed)update();
 },[status?.task_rev,project]);
 async function refresh(){if(flight.current)return;flight.current=true;try{await bounded(runTask('list'));}catch{/* Read-only failure never unlocks a mutation. */}finally{flight.current=false;update();}}
 async function act(row:Row,action:Action){
  const c=row.control,now=latest.current;
  if(!c||!c.available||flight.current||!now.status?.engine_alive||c.project_id!==now.project||pending.has(c.token))return;
  const current=now.rows.find(t=>t.task_id===row.task_id&&t.control?.token===c.token);
  if(!current?.control?.allowed.includes(action))return;
  const p:Pending={request:crypto.randomUUID(),action,taskId:row.task_id,token:c.token,project:now.project,workspace:c.workspace_generation,session:c.session_id,message:'请求已发出；等待精确任务回执，不重复提交。'};
  pending.set(c.token,p);flight.current=true;update();
  try{
   const ref='lrt-task-control:'+JSON.stringify({task_id:row.task_id,token:c.token,project_id:c.project_id,workspace_generation:c.workspace_generation,session_id:c.session_id,revision:c.revision,request_id:p.request});
   const ack=await bounded(runTask(action,ref));
   if(!ack.requested)throw Error('调度未确认');
   // This read cannot start work. Acknowledgement alone must not clear pending.
   await bounded(runTask('list'));
  }catch{p.message='结果未知；仅刷新原任务状态，不自动重发。';}
  finally{flight.current=false;update();}
 }
 return <section aria-label="普通导出任务控制"><h3>任务台账</h3>
  <p>暂停/取消在条目边界生效，当前原子提交不会中断。删除只移除记录；原图与已导出文件保留。</p>
  <button disabled={!status?.engine_alive||flight.current} onClick={()=>void refresh()}>刷新任务状态（不重发）</button>
  {rows.map(row=>{const c=row.control,p=c&&pending.get(c.token),bound=c?.protocol===1&&c.available&&c.project_id===project;
   return <div key={row.task_id}><strong>{row.task_id}</strong> · {row.state} · 第 {row.attempt} 次重试
    <p>{row.counts.succeeded} 已成功 / {row.counts.failed} 失败 / {row.counts.skipped} 跳过 / {row.counts.total} 总项</p>
    {actions.map(action=><button key={action} disabled={!bound||!status?.engine_alive||!!p||flight.current||!c?.allowed.includes(action)} onClick={()=>void act(row,action)}>{labels[action]}</button>)}
    {!bound&&<p role="status">此记录缺少当前工程/会话控制身份，不能操作。</p>}
    {row.blocked_reason&&<p role="status">{row.blocked_reason}</p>}
    {p&&<p role="status">{labels[p.action]}：{p.message}</p>}
    {c?.result?.success===false&&<p role="alert">请求被拒绝：{c.result.error}</p>}
   </div>;
  })}
  {[...deleted.values()].filter(r=>r.project_id===project).map(r=><p role="status" key={r.token}>任务 {r.task_id} 的记录已确认删除；原图与导出文件保留。</p>)}
  {!rows.length&&<p>暂无任务记录。重开工程的任务不能用当前配方冒充原输入恢复。</p>}
 </section>;
}
