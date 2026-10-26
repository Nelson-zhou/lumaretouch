// SPDX-License-Identifier: GPL-3.0-or-later
// Source only. Runtime, save durability and output acceptance UNRUN.
import {useEffect,useRef,useState} from 'react';
import {requestPortraitPresetGroup,readPortraitPresetGroup} from '../native';
import type {DestinationPolicy,DestinationPreview} from '../exportDestination/model';
import type {Reply} from './model';
export type GroupDelivery={preflight_token:string;batch_id:string;workspace_generation:string;delivery_targets:{document_id:string;revision:string}[];engineKey:string};
type Pending={id:string;action:string;options:Record<string,unknown>};
type Retained={group:GroupDelivery|null;pending:Pending|null;taskId:string|null;exportStatus:string;items:Reply[];message:string;exportMode:boolean};
// Navigation/dismissal does not authorize repeating an uncertain mutation.
const retained:Retained={group:null,pending:null,taskId:null,exportStatus:'',items:[],message:'',exportMode:false};
const record=(v:unknown):v is Reply=>!!v&&typeof v==='object'&&!Array.isArray(v);
const text=(v:unknown)=>typeof v==='string'?v:'';
const terminal=(s:string)=>['succeeded','failed','cancelled','partial'].includes(s);
export function checkedDelivery(r:Reply,engineKey:string):GroupDelivery {
  const approved=r.approved_document_ids;
  if(r.success!==true||r.outcome_unknown!==false||typeof r.preflight_token!=='string'||typeof r.batch_id!=='string'||!r.batch_id
    ||typeof r.workspace_generation!=='string'||!Array.isArray(r.delivery_targets)||!r.delivery_targets.length||r.delivery_targets.length>8
    ||!Array.isArray(approved)||r.delivery_targets.some((row,i)=>!record(row)||row.document_id!==approved[i]
      ||typeof row.revision!=='string'||!/^(0|[1-9][0-9]{0,19})$/.test(row.revision))
    ||approved.length!==r.delivery_targets.length)throw Error('整组成功回执缺少精确交付版本；不能自动交接。');
  return structuredClone({...r,engineKey}) as unknown as GroupDelivery;
}
async function bounded<T>(task:Promise<T>):Promise<T>{return new Promise((resolve,reject)=>{const timer=setTimeout(()=>reject(Error('原请求结果尚未确认，请查询原请求。')),120000);task.then(v=>{clearTimeout(timer);resolve(v);},e=>{clearTimeout(timer);reject(e);});});}
async function poll(p:Pending):Promise<Reply>{
  const deadline=Date.now()+120000;
  for(;;){const r=await bounded(readPortraitPresetGroup(p.id));
    if(r.request_id!==p.id)throw Error('交付回执请求身份不匹配。');
    if(r.phase==='done'){if(!r.result||r.result.request_id!==p.id||r.result.action!==p.action)throw Error('交付动作身份不匹配。');return r.result;}
    if(r.phase!=='pending'||Date.now()>deadline)throw Error(r.error||'原请求尚未确认，不重复提交。');
    await new Promise(resolve=>setTimeout(resolve,250));
  }
}
export function useGroupDelivery(engineKey:string){
  const [state,setState]=useState<Retained>({...retained}),[busy,setBusy]=useState(false);
  const mounted=useRef(true),flight=useRef(false),engine=useRef(engineKey);engine.current=engineKey;
  useEffect(()=>{mounted.current=true;return()=>{mounted.current=false;};},[]);
  const update=(patch:Partial<Retained>)=>{Object.assign(retained,patch);if(mounted.current)setState({...retained});};
  const available=!!state.group&&state.group.engineKey===engineKey;
  const binding=()=>{const g=retained.group;if(!g||g.engineKey!==engine.current)throw Error('引擎已变化；旧组交付不能沿用，请核对原任务。');return {preflightToken:g.preflight_token,batchId:g.batch_id};};
  function observe(r:Reply){
    const task=text(r.export_task_id);if(task){if(retained.taskId&&retained.taskId!==task)throw Error('任务身份已变化，不能接管另一个导出。');update({taskId:task});}
    if(typeof r.export_status==='string')update({exportStatus:r.export_status,items:Array.isArray(r.items)?r.items.filter(record):[]});
    if(r.save_status==='saved'){if(typeof r.saved_project_sha256!=='string'||!/^[a-f0-9]{64}$/.test(r.saved_project_sha256))throw Error('保存回执缺少工程校验证明，结果尚未确认。');update({message:'此组工程版本已保存；其他未保存编辑不会因此被认定已保存。'});}
    else if(r.save_status==='not_saved')update({message:`此组尚未保存：${text(r.error)||'保存 owner 未确认成功'}`});
    else if(r.export_status)update({message:`原导出任务：${String(r.export_status)}。逐项回执不等同于独立输出校验；跳过、部分失败和取消保持原状态。`});
  }
  async function settle(p:Pending,dispatch:boolean):Promise<Reply>{
    if(flight.current)throw Error('请等待原交付请求。');flight.current=true;if(mounted.current)setBusy(true);
    try{
      binding();
      if(dispatch){const q=await bounded(requestPortraitPresetGroup(p.action,{...p.options,requestId:p.id}));if(!q.requested)throw Error('交付入队结果未确认。');}
      const r=await poll(p),g=retained.group;
      if(!g||g.engineKey!==engine.current||r.preflight_token!==g.preflight_token||r.batch_id!==g.batch_id)throw Error('交付回执不属于此成功组。');
      observe(r);
      if(r.outcome_unknown===true||r.save_status==='unknown'||r.export_status==='unknown'){
        if(r.export_status==='unknown'&&retained.taskId)update({pending:null});
        throw Error(text(r.error)||'结果未知；仅查询原请求或其精确导出任务，不再次写入。');
      }
      if(r.success!==true){if(r.no_write===true||['portrait_preset_export_preview','portrait_preset_export_status'].includes(p.action))update({pending:null});throw Error(text(r.error)||'此组交付未完成。');}
      update({pending:null});return r;
    }catch(e){update({message:String(e)});throw e;}finally{flight.current=false;if(mounted.current)setBusy(false);}
  }
  async function run(action:string,options:Record<string,unknown>={}){
    if(retained.pending)throw Error('先查询原交付请求，不能重复提交。');
    const p={id:`portrait-delivery-${crypto.randomUUID()}`,action,options:{...binding(),...options}};
    update({pending:p});return settle(p,true);
  }
  async function status(){
    if(!retained.taskId||flight.current||retained.pending)return;
    await run('portrait_preset_export_status',{taskId:retained.taskId});
  }
  useEffect(()=>{
    if(!available||!state.taskId||state.pending||terminal(state.exportStatus))return;
    const timer=setInterval(()=>{void status().catch(()=>{});},2000);return()=>clearInterval(timer);
  },[available,state.taskId,state.pending,state.exportStatus]);
  return {state,busy,available,exportClaimed:!!state.taskId,blocked:busy||!!state.pending||!!state.taskId&&!terminal(state.exportStatus),
    accept:(r:Reply)=>{if(retained.pending||retained.taskId&&!terminal(retained.exportStatus))throw Error('原组交付仍未确认，请先核对原任务。');update({group:checkedDelivery(r,engine.current),pending:null,taskId:null,exportStatus:'',items:[],message:'整组应用已确认；保存和输出尚未执行。',exportMode:false});},
    save:()=>run('portrait_preset_save'),
    open:()=>{binding();update({exportMode:true});},
    leave:()=>{if(retained.pending||retained.taskId&&!terminal(retained.exportStatus))throw Error('原导出未终结，不能解除整组绑定。');update({exportMode:false});},
    preview:async(policy:DestinationPolicy,options:Record<string,unknown>,revision:number)=>{
      const r=await run('portrait_preset_export_preview',{policy,exportOptions:options,intentRevision:revision});
      const p=r.destination;if(!record(p)||p.schema_version!=='lrt.export-destination.v1'||typeof p.plan_id!=='string'||p.intent_revision!==revision||!Array.isArray(p.entries))throw Error('导出计划回执不完整。');
      return p as unknown as DestinationPreview;
    },
    start:(plan:DestinationPreview)=>run('portrait_preset_export_start',{planId:plan.plan_id,intentRevision:plan.intent_revision}),
    status,cancel:()=>run('portrait_preset_export_cancel',{taskId:retained.taskId}),
    reconcile:()=>retained.pending?settle(retained.pending,false):Promise.resolve(null),
  };
}
export type GroupDeliveryOwner=ReturnType<typeof useGroupDelivery>;
export function GroupDeliveryPanel({owner,onOpen}:{owner:GroupDeliveryOwner;onOpen:()=>void}){
  const {state:s,busy,available}=owner;if(!s.group)return null;
  const act=(f:()=>Promise<unknown>)=>{void f().catch(()=>{});};
  return <section aria-label="已应用整组的保存与输出"><h4>此成功组 · {s.group.delivery_targets.length} 张</h4>
    <p>绑定批次 {s.group.batch_id}；不会随底片条选择变化。工程保存与导出是分开的显式操作。此交接只导出单张文件；排版/PDF 请使用原独立流程。</p>
    {!available&&<p role="alert">引擎会话已变化：旧交付已锁定，不会重发保存或导出。请核对原任务。</p>}
    <button disabled={!available||owner.blocked} onClick={()=>act(owner.save)}>仅保存此成功组</button>
    <button disabled={!available||owner.blocked||owner.exportClaimed} onClick={()=>{try{onOpen();}catch{}}}>使用现有导出设置交付此组</button>
    {s.pending&&<button disabled={!available||busy} onClick={()=>act(owner.reconcile)}>查询原交付请求（不重发）</button>}
    {s.taskId&&<><p>原导出任务：{s.taskId} · {s.exportStatus||'未确认'}</p><button disabled={!available||busy||!!s.pending} onClick={()=>act(owner.status)}>刷新原任务状态</button>
      {!terminal(s.exportStatus)&&<button disabled={!available||busy||!!s.pending} onClick={()=>act(owner.cancel)}>请求取消原导出</button>}</>}
    {s.items.map((item,i)=><p key={String(item.id??item.document_id??i)}>{String(item.document_id??item.path??i+1)}：{String(item.state??'未知')}{item.out?` · 输出回执：${String(item.out)}`:''}{item.error?` · ${String(item.error)}`:''}</p>)}
    {s.message&&<p role="status">{s.message}</p>}
  </section>;
}
