import {parseCaptureFrame,type VerifiedCapture} from '../captureFrame.ts';
import type {CaptureDescriptor} from '../captureModel';
import type {Point} from '../sourcePatch/geometry';
export interface HealStroke {points:Point[];size:number;hardness:number;opacity:number}

export const HEAL_BRUSH_LABEL='修复输入视图：当前来源及已有修补；不含磨皮/形变/调色，构图保持';
export interface HealBrushContext {enabled:boolean;canStart?:boolean;documentId:string;contextKey:string;samplingKey?:string;reason?:string}
export interface HealBrushRequest {
  request_id:string;capture_id:string;ticket:string;document_id:string;stroke:HealStroke;
}
export interface HealBrushCaptureStatus {
  phase:'arming'|'ready'|'copying'|'copied'|'eligible'|'redeemed'|'error'|'idle'|'stale';
  capture_id?:string;ticket?:string;descriptor?:CaptureDescriptor|null;error?:string|null;
}
export interface HealBrushTransport {
  arm:(captureId:string,documentId:string)=>Promise<{ticket:string}>;
  status:(captureId:string,ticket:string)=>Promise<HealBrushCaptureStatus>;
  frame:(captureId:string,ticket:string)=>Promise<ArrayBuffer>;
  presented:(captureId:string,ticket:string,documentId:string)=>Promise<{eligible:boolean}>;
  cancel:(captureId:string,ticket:string|null,documentId:string)=>Promise<unknown>;
  submit:(request:HealBrushRequest)=>Promise<unknown>;
  result:(requestId:string)=>Promise<unknown>;
}
export interface HealBrushState {
  phase:'idle'|'arming'|'painting'|'target'|'sending'|'waiting'|'success'|'failure'|'uncertain';
  frame:VerifiedCapture|null;size:number;hardness:number;opacity:number;request:HealBrushRequest|null;message:string;
}
interface CaptureOwner {id:string;ticket:string|null;documentId:string;contextKey:string;ack:Promise<boolean>|null}
const initial=():HealBrushState=>({phase:'idle',frame:null,size:.04,hardness:.7,opacity:1,request:null,message:''});
const object=(value:unknown):value is Record<string,unknown>=>!!value&&typeof value==='object'&&!Array.isArray(value);
const count=(value:unknown)=>Number.isSafeInteger(value)&&Number(value)>=0;
function bounded<T>(promise:Promise<T>,milliseconds:number):Promise<T>{
  let timer:ReturnType<typeof setTimeout>|undefined;
  return Promise.race([promise,new Promise<T>((_,reject)=>{timer=setTimeout(()=>reject(Error('等待超时')),Math.max(1,milliseconds));})])
    .finally(()=>{if(timer!==undefined)clearTimeout(timer);});
}

/** App owns this workflow. Collapsing a panel or switching tools never owns a receipt. */
export function createHealBrushWorkflow(api:HealBrushTransport,options:{refresh:()=>Promise<void>;id?:()=>string;sleep?:(ms:number)=>Promise<void>;timeoutMs?:number}={refresh:async()=>{}}){
  const id=options.id??(()=>crypto.randomUUID().replaceAll('-',''));
  const sleep=options.sleep??((ms:number)=>new Promise<void>(resolve=>setTimeout(resolve,ms)));
  const timeout=options.timeoutMs??15000;
  let state=initial(),context:HealBrushContext={enabled:false,documentId:'',contextKey:''};
  let owner:CaptureOwner|null=null,active=true,life=0,running=false;
  let submittedContext:string|null=null,continueAfterSuccess=false;
  let paintTimer:ReturnType<typeof setTimeout>|undefined;
  const listeners=new Set<(next:HealBrushState)=>void>();
  const publish=(patch:Partial<HealBrushState>)=>{state={...state,...patch};if(active)listeners.forEach(f=>f(state));};
  const pending=()=>['sending','waiting','uncertain'].includes(state.phase)&&!!state.request;
  const current=(o:CaptureOwner)=>active&&owner===o;
  const clearPaintTimer=()=>{if(paintTimer!==undefined)clearTimeout(paintTimer);paintTimer=undefined;};
  const release=(o:CaptureOwner)=>{void api.cancel(o.id,o.ticket,o.documentId).catch(()=>{/* Cancellation never submits a patch. */});};
  function discardCapture(){const old=owner;owner=null;clearPaintTimer();if(old)release(old);}
  function cancel(message='已取消，未提交修复笔',stopContinuation=true){
    if(stopContinuation){continueAfterSuccess=false;}
    if(!pending()){continueAfterSuccess=false;}
    if(pending()){
      // A submitted request owns the lease until its receipt. Do not race its commit.
      publish({frame:null,message:'修复笔已发送，不能作为未提交取消；仍在确认原操作结果'});
    }else{discardCapture();publish({...initial(),size:state.size,hardness:state.hardness,opacity:state.opacity,message});}
  }
  function failed(error:unknown){
    if(pending()){publish({message:`原操作仍待确认：${String(error)}`});return;}
    discardCapture();publish({...initial(),phase:'failure',message:String(error)});
  }
  function updateContext(next:HealBrushContext){
    if(next.documentId!==context.documentId||next.samplingKey!==context.samplingKey){continueAfterSuccess=false;}
    context=next;
    if(owner&&(!next.enabled||next.documentId!==owner.documentId||next.contextKey!==owner.contextKey))
      cancel(next.reason||'照片或编辑上下文已变化，未提交的笔划已取消',false);
  }
  async function start(){
    if(!active||running||pending()||owner)return;
    if(!context.enabled||context.canStart===false||!context.documentId){publish({phase:'failure',message:context.reason||'请等待照片与引擎就绪'});return;}
    const o:CaptureOwner={id:id(),ticket:null,documentId:context.documentId,contextKey:context.contextKey,ack:null};owner=o;
    publish({...initial(),size:state.size,hardness:state.hardness,opacity:state.opacity,phase:'arming',message:'正在冻结修复笔输入画面…'});
    const deadline=Date.now()+timeout;
    try{
      const arm=api.arm(o.id,o.documentId).then(receipt=>{
        o.ticket=receipt.ticket;
        if(!current(o))release(o);
        return receipt;
      });
      const receipt=await bounded(arm,deadline-Date.now());
      if(!current(o))return;
      if(!/^[1-9]\d*$/.test(receipt.ticket))throw Error('修复笔取样票据无效');
      while(current(o)){
        if(Date.now()>=deadline)throw Error('冻结修复笔输入画面超时');
        const report=await bounded(api.status(o.id,receipt.ticket),deadline-Date.now());
        if(!current(o))return;
        if(['error','stale','idle'].includes(report.phase))throw Error(report.error||'修复笔取样画面已失效');
        if(report.capture_id!==o.id||report.ticket!==receipt.ticket)throw Error('修复笔取样回执身份不匹配');
        if(report.phase==='ready'){
          const d=report.descriptor;
          if(!d||d.capture_id!==o.id||d.ticket!==receipt.ticket||d.document_id!==o.documentId||d.domain!=='repair-input')throw Error('修复笔输入来源不匹配');
          const buffer=await bounded(api.frame(o.id,receipt.ticket),deadline-Date.now());
          if(!current(o))return;
          const frame=parseCaptureFrame(buffer,d,'repair-input');
          publish({phase:'painting',frame,message:'正在显示冻结的修复笔取样视图…'});
          paintTimer=setTimeout(()=>{if(current(o)&&state.phase==='painting')failed('取样画面未完成显示，请重新开始');},timeout);
          return;
        }
        if(report.phase!=='arming')throw Error('修复笔取样状态不一致，请重新开始');
        await bounded(sleep(120),deadline-Date.now());
      }
    }catch(error){if(current(o))failed(error);}
  }
  function presented(descriptor:CaptureDescriptor):Promise<boolean>{
    const o=owner;
    if(!o||!current(o)||!o.ticket||!state.frame||state.frame.descriptor!==descriptor)return Promise.resolve(false);
    if(state.phase==='target')return Promise.resolve(true);
    if(state.phase!=='painting')return Promise.resolve(false);
    if(o.ack)return o.ack;
    o.ack=(async()=>{
      try{
        const reply=await bounded(api.presented(o.id,o.ticket!,o.documentId),timeout);
        if(!current(o))return false;
        if(reply.eligible!==true)throw Error('修复笔取样画面尚不能使用');
        clearPaintTimer();publish({phase:'target',message:'涂抹需修复的区域，松开提交一笔；Esc 取消未提交笔划'});return true;
      }catch(error){if(current(o))failed(error);return false;}
    })();return o.ack;
  }
  function settings(patch:Partial<Pick<HealBrushState,'size'|'hardness'|'opacity'>>){
    if(pending())return;
    const clean:typeof patch={};
    for(const key of ['size','hardness','opacity'] as const){
      const value=patch[key];if(value!==undefined&&Number.isFinite(value)&&value>=(key==='size' ? .001 : 0)&&value<=1)clean[key]=value;
    }
    publish(clean);
  }
  async function query(request:HealBrushRequest){
    if(!active||running)return;
    const token=life,deadline=Date.now()+timeout;running=true;
    publish({phase:'waiting',request,message:'正在确认原修复笔操作的历史回执…'});
    try{
      while(active&&token===life){
        if(Date.now()>=deadline)throw Error('等待原修复笔结果超时；不会重新提交');
        const packet=await bounded(api.result(request.request_id),deadline-Date.now());
        if(!active||token!==life)return;
        if(!object(packet)||packet.request_id!==request.request_id)throw Error('修复笔回执身份不匹配');
        if(packet.phase==='pending'){await bounded(sleep(150),deadline-Date.now());continue;}
        if(packet.phase!=='done'||!object(packet.result))throw Error('原修复笔结果未找到或引擎已重启；不会重新提交');
        const result=packet.result;
        if(result.protocol!==1||result.action!=='apply'||result.request_id!==request.request_id||result.document_id!==request.document_id||
          typeof result.success!=='boolean'||typeof result.outcome_unknown!=='boolean')throw Error('修复笔完成回执不完整');
        if(result.outcome_unknown)throw Error(typeof result.error==='string'?result.error:'修复笔结果尚未确认');
        if(!result.success){discardCapture();publish({phase:'failure',frame:null,message:typeof result.error==='string'?result.error:'修复笔未完成'});return;}
        if(result.kind!=='heal_vector'||result.capture_id!==request.capture_id||result.ticket!==request.ticket||result.requires_reload!==false||
          !object(result.history)||!count(result.history.undo_steps)||!count(result.history.redo_steps))throw Error('修复笔缺少匹配的提交后历史证据');
        discardCapture();publish({frame:null});
        let refreshFailed=false;
        try{await bounded(options.refresh(),Math.min(timeout,3000));}catch{refreshFailed=true;}
        if(!active||token!==life)return;
        if(refreshFailed)continueAfterSuccess=false;
        if(result.no_change===true)submittedContext=null;
        publish({phase:'success',message:(result.no_change===true?'所选修复笔未产生变化，未新增历史步骤':
          context.documentId===request.document_id?'修复笔已完成，可撤销':'上一张照片的修复笔已完成')+
          (refreshFailed?'；状态刷新失败，请稍后刷新':'')});return;
      }
    }catch(error){if(active&&token===life){continueAfterSuccess=false;discardCapture();publish({phase:'uncertain',frame:null,request,message:`结果未确认：${String(error)}`});}}
    finally{if(token===life)running=false;}
  }
  async function apply(points:Point[]){
    const o=owner;
    if(!active||running||pending()||!o||!o.ticket||state.phase!=='target')return;
    if(!context.enabled||context.documentId!==o.documentId||context.contextKey!==o.contextKey){cancel('照片或编辑上下文已变化，未提交修复笔');return;}
    if(points.length<1||points.length>1024||points.some(p=>p.some(v=>!Number.isFinite(v)||v<0||v>1))){publish({message:'笔划超出范围或过长，请分成多笔'});return;}
    if(state.opacity===0){publish({message:'不透明度为零，未提交修复笔'});return;}
    const request:HealBrushRequest={request_id:`heal-brush-${id()}`,capture_id:o.id,ticket:o.ticket,document_id:o.documentId,
      stroke:{points:points.map(p=>[...p] as Point),size:state.size,hardness:state.hardness,opacity:state.opacity}};
    submittedContext=context.contextKey;continueAfterSuccess=true;
    const token=life;running=true;publish({phase:'sending',request,message:'正在提交一次修复笔…'});
    try{await bounded(api.submit(request),timeout);}catch{/* Even a failed send can have executed. Query only this request. */}
    if(!active||token!==life)return;
    running=false;await query(request);
  }
  return {
    snapshot:()=>state,subscribe:(f:(next:HealBrushState)=>void)=>{listeners.add(f);return()=>{listeners.delete(f);};},
    context:updateContext,start,cancel,failed,presented,settings,apply,
    gestureCancelled(message:string){if(state.phase==='target')publish({message});},
    canContinue:()=>state.phase==='success'&&continueAfterSuccess&&context.enabled&&context.canStart!==false&&context.contextKey!==submittedContext,
    externalEdit(){continueAfterSuccess=false;if(owner&&!pending())cancel('照片正在调整，未提交的修复笔划已取消');},
    busy:pending,capturing:()=>!!owner,
    check:async()=>{if(active&&state.request&&!running&&['waiting','uncertain'].includes(state.phase))await query(state.request);},
    activate(){active=true;},
    stop(){
      continueAfterSuccess=false;discardCapture();active=false;++life;running=false;
      state=pending()?{...state,phase:'uncertain',frame:null,message:'等待被中断，请查询原修复笔结果；不会重发'}:initial();
    },
    acknowledgeAfterReload(){
      if(active&&!running&&state.phase==='uncertain'&&state.request&&context.enabled&&context.documentId!==state.request.document_id)
        publish({...initial(),message:'已换到重新打开的照片；旧修复笔不会重发'});
    },
  };
}
