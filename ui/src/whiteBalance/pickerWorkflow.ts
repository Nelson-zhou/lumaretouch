import {parseCaptureFrame,type VerifiedCapture} from '../captureFrame.ts';
import type {CaptureDescriptor} from '../captureModel';
import type {CaptureRegion} from '../captureModel';

export const WB_PICKER_LABEL='白平衡输入视图：冻结的线性白平衡前输入，保持裁剪与旋转；不是最终调色画面';
export interface WhiteBalancePickerContext {enabled:boolean;canStart?:boolean;documentId:string;contextKey:string;reason?:string}
export interface WhiteBalancePickerRequest {
  request_id:string;capture_id:string;ticket:string;document_id:string;region:CaptureRegion;
}
export interface WhiteBalancePickerCaptureStatus {
  phase:'arming'|'ready'|'copying'|'copied'|'eligible'|'redeemed'|'error'|'idle'|'stale';
  capture_id?:string;ticket?:string;descriptor?:CaptureDescriptor|null;error?:string|null;
}
export interface WhiteBalancePickerTransport {
  arm:(captureId:string,documentId:string)=>Promise<{ticket:string}>;
  status:(captureId:string,ticket:string)=>Promise<WhiteBalancePickerCaptureStatus>;
  frame:(captureId:string,ticket:string)=>Promise<ArrayBuffer>;
  presented:(captureId:string,ticket:string,documentId:string)=>Promise<{eligible:boolean}>;
  cancel:(captureId:string,ticket:string|null,documentId:string)=>Promise<unknown>;
  submit:(request:WhiteBalancePickerRequest)=>Promise<unknown>;
  result:(requestId:string)=>Promise<unknown>;
}
export interface WhiteBalancePickerState {
  phase:'idle'|'arming'|'painting'|'ready'|'sending'|'waiting'|'success'|'failure'|'uncertain';
  frame:VerifiedCapture|null;request:WhiteBalancePickerRequest|null;message:string;
}
interface CaptureOwner {id:string;ticket:string|null;documentId:string;contextKey:string;ack:Promise<boolean>|null}
const initial=():WhiteBalancePickerState=>({phase:'idle',frame:null,request:null,message:''});
const object=(value:unknown):value is Record<string,unknown>=>!!value&&typeof value==='object'&&!Array.isArray(value);
const count=(value:unknown)=>Number.isSafeInteger(value)&&Number(value)>=0;
function bounded<T>(promise:Promise<T>,milliseconds:number):Promise<T>{
  let timer:ReturnType<typeof setTimeout>|undefined;
  return Promise.race([promise,new Promise<T>((_,reject)=>{timer=setTimeout(()=>reject(Error('等待超时')),Math.max(1,milliseconds));})])
    .finally(()=>{if(timer!==undefined)clearTimeout(timer);});
}

/** App owns this workflow. Collapsing a panel or switching tools never owns a receipt. */
export function createWhiteBalancePickerWorkflow(api:WhiteBalancePickerTransport,options:{refresh:()=>Promise<void>;id?:()=>string;sleep?:(ms:number)=>Promise<void>;timeoutMs?:number}={refresh:async()=>{}}){
  const id=options.id??(()=>crypto.randomUUID().replaceAll('-',''));
  const sleep=options.sleep??((ms:number)=>new Promise<void>(resolve=>setTimeout(resolve,ms)));
  const timeout=options.timeoutMs??15000;
  let state=initial(),context:WhiteBalancePickerContext={enabled:false,documentId:'',contextKey:''};
  let owner:CaptureOwner|null=null,active=true,life=0,running=false;
  let paintTimer:ReturnType<typeof setTimeout>|undefined;
  const listeners=new Set<(next:WhiteBalancePickerState)=>void>();
  const publish=(patch:Partial<WhiteBalancePickerState>)=>{state={...state,...patch};if(active)listeners.forEach(f=>f(state));};
  const pending=()=>['sending','waiting','uncertain'].includes(state.phase)&&!!state.request;
  const current=(o:CaptureOwner)=>active&&owner===o;
  const clearPaintTimer=()=>{if(paintTimer!==undefined)clearTimeout(paintTimer);paintTimer=undefined;};
  const release=(o:CaptureOwner)=>{void api.cancel(o.id,o.ticket,o.documentId).catch(()=>{/* Cancellation never submits a WB action. */});};
  function discardCapture(){const old=owner;owner=null;clearPaintTimer();if(old)release(old);}
  function cancel(message='已取消，未提交白平衡取样'){
    if(pending()){
      // A submitted request owns the lease until its receipt. Do not race its commit.
      publish({frame:null,message:'白平衡取样已发送，不能作为未提交取消；仍在确认原操作结果'});
    }else{discardCapture();publish({...initial(),message});}
  }
  function failed(error:unknown){
    if(pending()){publish({message:`原操作仍待确认：${String(error)}`});return;}
    discardCapture();publish({...initial(),phase:'failure',message:String(error)});
  }
  function updateContext(next:WhiteBalancePickerContext){
    context=next;
    if(owner&&(!next.enabled||next.documentId!==owner.documentId||next.contextKey!==owner.contextKey))
      cancel(next.reason||'照片或编辑上下文已变化，未提交的取样已取消');
  }
  async function start(){
    if(!active||running||pending()||owner)return;
    if(!context.enabled||context.canStart===false||!context.documentId){publish({phase:'failure',message:context.reason||'请等待照片与引擎就绪'});return;}
    const o:CaptureOwner={id:id(),ticket:null,documentId:context.documentId,contextKey:context.contextKey,ack:null};owner=o;
    publish({...initial(),phase:'arming',message:'正在冻结白平衡取样输入画面…'});
    const deadline=Date.now()+timeout;
    try{
      const arm=api.arm(o.id,o.documentId).then(receipt=>{
        o.ticket=receipt.ticket;
        if(!current(o))release(o);
        return receipt;
      });
      const receipt=await bounded(arm,deadline-Date.now());
      if(!current(o))return;
      if(!/^[1-9]\d*$/.test(receipt.ticket))throw Error('白平衡取样票据无效');
      while(current(o)){
        if(Date.now()>=deadline)throw Error('冻结白平衡取样输入画面超时');
        const report=await bounded(api.status(o.id,receipt.ticket),deadline-Date.now());
        if(!current(o))return;
        if(['error','stale','idle'].includes(report.phase))throw Error(report.error||'白平衡取样画面已失效');
        if(report.capture_id!==o.id||report.ticket!==receipt.ticket)throw Error('白平衡取样回执身份不匹配');
        if(report.phase==='ready'){
          const d=report.descriptor;
          if(!d||d.capture_id!==o.id||d.ticket!==receipt.ticket||d.document_id!==o.documentId||d.domain!=='wb-input')throw Error('白平衡取样输入来源不匹配');
          const buffer=await bounded(api.frame(o.id,receipt.ticket),deadline-Date.now());
          if(!current(o))return;
          const frame=parseCaptureFrame(buffer,d,'wb-input');
          publish({phase:'painting',frame,message:'正在显示冻结的白平衡取样视图…'});
          paintTimer=setTimeout(()=>{if(current(o)&&state.phase==='painting')failed('取样画面未完成显示，请重新开始');},timeout);
          return;
        }
        if(report.phase!=='arming')throw Error('白平衡取样状态不一致，请重新开始');
        await bounded(sleep(120),deadline-Date.now());
      }
    }catch(error){if(current(o))failed(error);}
  }
  function presented(descriptor:CaptureDescriptor):Promise<boolean>{
    const o=owner;
    if(!o||!current(o)||!o.ticket||!state.frame||state.frame.descriptor!==descriptor)return Promise.resolve(false);
    if(state.phase==='ready')return Promise.resolve(true);
    if(state.phase!=='painting')return Promise.resolve(false);
    if(o.ack)return o.ack;
    o.ack=(async()=>{
      try{
        const reply=await bounded(api.presented(o.id,o.ticket!,o.documentId),timeout);
        if(!current(o))return false;
        if(reply.eligible!==true)throw Error('白平衡取样画面尚不能使用');
        clearPaintTimer();publish({phase:'ready',message:'点击应为中性的灰色或白色区域，取样周围 5×5 像素；避免高光与暗部'});return true;
      }catch(error){if(current(o))failed(error);return false;}
    })();return o.ack;
  }
  async function query(request:WhiteBalancePickerRequest){
    if(!active||running)return;
    const token=life,deadline=Date.now()+timeout;running=true;
    publish({phase:'waiting',request,message:'正在确认原白平衡操作的历史回执…'});
    try{
      while(active&&token===life){
        if(Date.now()>=deadline)throw Error('等待原白平衡结果超时；不会重新提交');
        const packet=await bounded(api.result(request.request_id),deadline-Date.now());
        if(!active||token!==life)return;
        if(!object(packet)||packet.request_id!==request.request_id)throw Error('白平衡取样回执身份不匹配');
        if(packet.phase==='pending'){await bounded(sleep(150),deadline-Date.now());continue;}
        if(packet.phase!=='done'||!object(packet.result))throw Error('原白平衡结果未找到或引擎已重启；不会重新提交');
        const result=packet.result;
        if(result.protocol!==1||result.action!=='pick'||result.request_id!==request.request_id||result.document_id!==request.document_id||
          typeof result.success!=='boolean'||typeof result.outcome_unknown!=='boolean')throw Error('白平衡取样完成回执不完整');
        if(result.outcome_unknown)throw Error(typeof result.error==='string'?result.error:'白平衡取样结果尚未确认');
        if(!result.success){discardCapture();publish({phase:'failure',frame:null,message:typeof result.error==='string'?result.error:'白平衡取样未完成'});return;}
        if(result.capture_id!==request.capture_id||result.ticket!==request.ticket||result.requires_reload!==false||
          !object(result.history)||!count(result.history.undo_steps)||!count(result.history.redo_steps)||!object(result.after)||!object(result.after.options))throw Error('白平衡取样缺少匹配的提交后历史证据');
        discardCapture();publish({frame:null});
        let refreshFailed=false;
        try{await bounded(options.refresh(),Math.min(timeout,3000));}catch{refreshFailed=true;}
        if(!active||token!==life)return;
        publish({phase:'success',message:(result.no_change===true?'所选白平衡取样未产生变化，未新增历史步骤':
          context.documentId===request.document_id?'白平衡取样已完成，可撤销':'上一张照片的白平衡取样已完成')+
          (refreshFailed?'；状态刷新失败，请稍后刷新':'')});return;
      }
    }catch(error){if(active&&token===life){discardCapture();publish({phase:'uncertain',frame:null,request,message:`结果未确认：${String(error)}`});}}
    finally{if(token===life)running=false;}
  }
  async function apply(region:CaptureRegion){
    const o=owner;
    if(!active||running||pending()||!o||!o.ticket||state.phase!=='ready')return;
    if(!context.enabled||context.documentId!==o.documentId||context.contextKey!==o.contextKey){cancel('照片或编辑上下文已变化，未提交白平衡取样');return;}
    const d=state.frame?.descriptor;
    if(!d||![region.x,region.y,region.width,region.height].every(Number.isInteger)||region.x<0||region.y<0||region.width<1||region.height<1||region.width*region.height>121||region.x+region.width>d.width||region.y+region.height>d.height){publish({message:'取样范围无效，未提交'});return;}
    const request:WhiteBalancePickerRequest={request_id:`wb-pick-${id()}`,capture_id:o.id,ticket:o.ticket,document_id:o.documentId,
      region:{...region}};
    const token=life;running=true;publish({phase:'sending',request,message:'正在提交一次白平衡取样…'});
    try{await bounded(api.submit(request),timeout);}catch{/* Even a failed send can have executed. Query only this request. */}
    if(!active||token!==life)return;
    running=false;await query(request);
  }
  return {
    snapshot:()=>state,subscribe:(f:(next:WhiteBalancePickerState)=>void)=>{listeners.add(f);return()=>{listeners.delete(f);};},
    context:updateContext,start,cancel,failed,presented,apply,
    busy:pending,capturing:()=>!!owner,
    check:async()=>{if(active&&state.request&&!running&&['waiting','uncertain'].includes(state.phase))await query(state.request);},
    activate(){active=true;},
    stop(){
      discardCapture();active=false;++life;running=false;
      state=pending()?{...state,phase:'uncertain',frame:null,message:'等待被中断，请查询原白平衡结果；不会重发'}:initial();
    },
    acknowledgeAfterReload(){
      if(active&&!running&&state.phase==='uncertain'&&state.request&&context.enabled&&context.documentId!==state.request.document_id)
        publish({...initial(),message:'已换到重新打开的照片；旧白平衡取样不会重发'});
    },
  };
}
