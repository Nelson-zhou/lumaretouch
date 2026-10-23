import {invoke} from '@tauri-apps/api/core';
import {notifyInspectionEditIntent} from '../native';
import {isCurveEditBusy,settleCurveEdit} from '../curveEditBarrier';
import type {HairAction,HairMailbox,HairPort,HairPortState,HairRequest} from './model';
import type {PeopleContext} from '../people/model';
const pause=(ms:number)=>new Promise<void>(resolve=>setTimeout(resolve,ms));
function bound<T>(promise:Promise<T>,ms:number):Promise<T> {
  return new Promise((resolve,reject)=>{const timer=setTimeout(()=>reject(Error('头发请求未及时确认；不会重发修改。')),Math.max(1,ms));
    promise.then(v=>{clearTimeout(timer);resolve(v);},e=>{clearTimeout(timer);reject(e);});});
}
/** Keep this owner alive across panel closure. Unknown writes stay fenced until recovery. */
export function createHairColourPort(canUse:()=>boolean,refresh:()=>Promise<void>):HairPort {
  let pending:HairRequest|null=null,unknown=false,preparing=false,reading:Promise<unknown>|null=null;
  let state:HairPortState={pending:false,uncertain:false,checking:false,message:''};
  const listeners=new Set<()=>void>();
  function publish(message=state.message){state={pending:!!pending,uncertain:unknown,checking:preparing||!!reading,message};listeners.forEach(listener=>listener());}
  async function poll():Promise<unknown> {
    const command=pending;if(!command)return null;
    const end=Date.now()+120000;
    while(pending===command){
      const box=await bound(invoke<HairMailbox>('hair_colour',{request:{action:'status',request_id:command.request_id}}),Math.min(10000,end-Date.now()));
      if(box.request_id!==command.request_id)throw Error('头发回执身份不匹配');
      if(box.phase==='done'){
        const r=box.result;
        if(!r||r.protocol!==1||r.request_id!==command.request_id||r.action!==command.action||r.document_id!==command.people_context.document_id||r.outcome_unknown)throw Error(r?.error||'头发请求结果未知，请查询原请求，勿重复提交');
        unknown=false;
        let message=!r.success?r.error||'头发修改被拒绝':'';
        // A refresh failure is not permission to resend the confirmed mutation.
        try{await bound(refresh(),10000);}catch{message+=' 结果已确认，但照片刷新失败，请刷新查看，勿重复提交。';}
        pending=null;publish(message);
        if(!r.success)throw new ConfirmedRefusal(message);
        return r.payload;
      }
      if(box.phase!=='pending')throw Error(box.error||'原头发请求不可查询，请核对照片，不要重复提交');
      if(Date.now()>=end)throw Error('头发请求仍未确认，请查询原请求');
      await pause(150);
    }
    return null;
  }
  function recover():Promise<unknown>{
    if(preparing)return Promise.reject(Error('正在等待曲线编辑结束，头发请求尚未发出。'));
    if(!reading){reading=poll().catch(error=>{if(!(error instanceof ConfirmedRefusal))unknown=true;publish(String(error));throw error;}).finally(()=>{reading=null;publish();});publish();}
    return reading;
  }
  return {pending:()=>pending!==null,uncertain:()=>unknown,recover,snapshot:()=>state,
    subscribe(listener){listeners.add(listener);return ()=>{listeners.delete(listener);};},
    async call<T>(action:HairAction,context:PeopleContext,payload:Record<string,unknown>):Promise<T>{
      if(pending||reading||preparing)throw Error('上一项头发请求未确认，请先查询结果');
      if(!canUse())throw Error('请等待当前照片与引擎就绪，并结束其他工具操作。');
      const command:HairRequest={request_id:`hair-${crypto.randomUUID()}`,action,people_context:structuredClone(context),payload:structuredClone(payload)};
      if(new TextEncoder().encode(JSON.stringify(command)).byteLength>512*1024)throw Error('头发范围草稿过大，尚未提交；请撤回多余笔迹后再审核。');
      // Reserve before awaiting the curve barrier: two clicks must never replace the original request.
      pending=command;unknown=false;preparing=true;publish('正在准备头发范围请求。');
      try{if(isCurveEditBusy())await settleCurveEdit();if(!canUse())throw Error('照片或编辑状态已变化，头发请求未提交。');}
      catch(error){pending=null;preparing=false;publish(String(error));throw error;}
      preparing=false;publish('正在等待头发请求结果；不会重复提交。');
      if(action.startsWith('commit_')||action.startsWith('clear_'))notifyInspectionEditIntent();
      try{await bound(invoke('hair_colour',{request:command}),10000);}catch{/* Query same ID. A lost enqueue reply never authorizes a resend. */}
      return await recover() as T;
    }};
}
class ConfirmedRefusal extends Error {}
