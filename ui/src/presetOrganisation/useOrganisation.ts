import {useEffect,useRef,useState} from 'react';
import {invoke} from '@tauri-apps/api/core';
import {catalog,validateReply,type Catalog,type Edit,type Reply} from './model';
export function useOrganisation(enabled:boolean,onChanged:()=>void|Promise<void>,sourceVersion:unknown){
  const [view,setView]=useState<Catalog|null>(null),[busy,setBusy]=useState(false),[message,setMessage]=useState('');
  const [uncertain,setUncertain]=useState<string|null>(null);
  const owner=useRef({live:true,locked:false,pending:null as Record<string,unknown>|null});
  const latest=useRef({enabled,onChanged});latest.current={enabled,onChanged};
  useEffect(()=>{owner.current.live=true;return()=>{owner.current.live=false;};},[]);
  async function exchange(request:Record<string,unknown>){
    const deadline=Date.now()+15000;
    function bound<T>(p:Promise<T>):Promise<T>{return new Promise((resolve,reject)=>{
      const timer=setTimeout(()=>reject(Error('等待超时；不会自动重提操作')),Math.max(1,deadline-Date.now()));
      p.then(v=>{clearTimeout(timer);resolve(v);},e=>{clearTimeout(timer);reject(e);});
    });}
    const accepted=await bound(invoke<{requested:boolean}>('preset_organisation',{request}));
    if(!accepted.requested)throw Error('未确认入队，不能判断是否执行');
    for(;;){
      const row=await bound(invoke<{phase:string;request_id:string;result?:Reply}>('preset_organisation_result',{requestId:request.request_id}));
      if(row.request_id!==request.request_id)throw Error('目录查询身份不匹配');
      if(row.phase==='done'&&row.result){validateReply(row.result,request);return row.result;}
      if(row.phase!=='pending'||Date.now()>=deadline)throw Error('目录结果未确认，可查询原操作');
      await new Promise(resolve=>setTimeout(resolve,120));
    }
  }
  async function snapshot(){
    const reply=await exchange({action:'snapshot',request_id:crypto.randomUUID()});
    if(!reply.success||reply.outcome_unknown)throw Error(reply.error??'无法读取分类');
    const next=catalog(reply.catalog);
    if(owner.current.live&&latest.current.enabled)setView(next);
    return next;
  }
  async function locked(work:()=>Promise<void>){
    if(owner.current.locked||!latest.current.enabled)return;
    owner.current.locked=true;if(owner.current.live)setBusy(true);
    try{await work();}catch(error){if(owner.current.live)setMessage(String(error));}
    finally{owner.current.locked=false;if(owner.current.live)setBusy(false);}
  }
  async function refresh(){await locked(async()=>{await snapshot();setMessage('已从持久化目录刷新；尚未确认的操作仍须单独查询。');});}
  async function edit(value:Edit){
    if(owner.current.pending||!view||view.errors.length)return;
    await locked(async()=>{
      const request={...value,request_id:crypto.randomUUID(),expected_revision:view.revision};
      owner.current.pending=request;setMessage('正在保存目录，尚未确认完成…');
      try{
        const reply=await exchange(request);
        if(reply.outcome_unknown)throw Error(reply.error??'目录写入结果未确认');
        owner.current.pending=null;setUncertain(null);
        if(!reply.success){setMessage(reply.error??'操作被拒绝，未更改目录');await snapshot();return;}
        setMessage('目录操作已持久化；正在刷新列表。');
      }catch(error){
        setUncertain(String(request.request_id));setMessage(`${String(error)}。不要重复操作，可查询原请求。`);return;
      }
      await snapshot();await latest.current.onChanged();setMessage('目录操作已确认并刷新。');
    });
  }
  async function query(){
    const pending=owner.current.pending;if(!pending)return;
    await locked(async()=>{
      const reply=await exchange({action:'receipt',request_id:crypto.randomUUID(),target_request_id:pending.request_id});
      if(!reply.success||reply.outcome_unknown)throw Error(reply.error??'回执查询失败');
      if(!reply.found){setMessage('未找到持久化回执，不代表没有执行；请刷新核对。不会自动重试。');return;}
      if(reply.receipt?.action!==pending.action)throw Error('原操作回执动作不匹配');
      owner.current.pending=null;setUncertain(null);setMessage('已确认原操作持久化成功。');
      await snapshot();await latest.current.onChanged();
    });
  }
  function inspected(){if(owner.current.locked)return;owner.current.pending=null;setUncertain(null);setMessage('已结束等待；未重提旧操作。后续操作仍以当前目录版本为准。');}
  useEffect(()=>{if(enabled)void refresh();else setView(null);},[enabled,sourceVersion]);
  return {view,busy,uncertain,message,refresh,edit,query,inspected};
}
