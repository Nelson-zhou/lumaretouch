import {parseCaptureFrame,type VerifiedCapture} from '../captureFrame';
import type {CaptureDescriptor} from '../captureModel';
import type {CloneStampCaptureStatus} from '../cloneStamp/workflow';
import type {RecoveryTarget,RecoveryMutation,RecoveryImage,RecoveryRequest,RecoveryStroke} from './model';

export interface RecoveryContext {enabled:boolean;canStart?:boolean;documentId:string;contextKey:string;reason?:string}
export interface RecoveryTransport {
  arm:(id:string,document:string)=>Promise<{ticket:string}>;
  status:(id:string,ticket:string)=>Promise<CloneStampCaptureStatus>;
  frame:(id:string,ticket:string)=>Promise<ArrayBuffer>;
  presented:(id:string,ticket:string,document:string)=>Promise<{eligible:boolean}>;
  cancel:(id:string,ticket:string|null,document:string)=>Promise<unknown>;
  preview:(action:'preview'|'presented'|'cancel',id:string,capture:string,ticket:string,mutation?:RecoveryMutation)=>Promise<unknown>;
  previewStatus:(id:string)=>Promise<unknown>;
  submit:(request:RecoveryRequest)=>Promise<unknown>;
  result:(id:string)=>Promise<unknown>;
}
type Phase='idle'|'arming'|'painting'|'drawing'|'previewing'|'sending'|'waiting'|'success'|'failure'|'uncertain';
export interface RecoveryState {
  phase:Phase;target:RecoveryTarget;frame:VerifiedCapture|null;image:RecoveryImage|null;previewId:string|null;
  request:RecoveryRequest|null;message:string;strokeActive:boolean;ending:boolean;open:boolean;
}
interface Owner {id:string;ticket:string|null;documentId:string;contextKey:string;ack:Promise<boolean>|null}
interface Candidate {id:string;mutation:RecoveryMutation;final:boolean;serial:number}
const initial=():RecoveryState=>({phase:'idle',target:'skin_smoothing',frame:null,image:null,previewId:null,
  request:null,message:'',strokeActive:false,ending:false,open:false});
const object=(v:unknown):v is Record<string,unknown>=>!!v&&typeof v==='object'&&!Array.isArray(v);
const count=(v:unknown)=>Number.isSafeInteger(v)&&Number(v)>=0;
function bounded<T>(promise:Promise<T>,ms:number):Promise<T>{
  let timer:ReturnType<typeof setTimeout>|undefined;
  return Promise.race([promise,new Promise<T>((_,reject)=>{timer=setTimeout(()=>reject(Error('等待超时')),Math.max(1,ms));})])
    .finally(()=>{if(timer!==undefined)clearTimeout(timer);});
}
function review(value:unknown):RecoveryImage {
  if(!object(value)||value.domain!=='production-output'||value.quality!=='proxy-render-srgb8'||
    ![value.width,value.height].every(n=>Number.isSafeInteger(n)&&Number(n)>0&&Number(n)<=800)||
    ![value.before,value.after].every(s=>typeof s==='string'&&s.startsWith('data:image/png;base64,')&&s.length<=4*1024*1024))
    throw Error('恢复预览不是有效的全效果渲染');
  return value as unknown as RecoveryImage;
}

/** One in-flight preview plus one replaceable latest gesture candidate. Only the
 * final, actually displayed candidate can produce a single history mutation. */
export function createRecoveryWorkflow(api:RecoveryTransport,options:{refresh:()=>Promise<void>;prepare?:()=>void;id?:()=>string;timeoutMs?:number}){
  const id=options.id??(()=>crypto.randomUUID().replaceAll('-','')),timeout=options.timeoutMs??60000;
  const sleep=(ms:number)=>new Promise<void>(resolve=>setTimeout(resolve,ms));
  let state=initial(),context:RecoveryContext={enabled:false,documentId:'',contextKey:''};
  let owner:Owner|null=null,active=true,life=0,serial=0,inflight=false,querying=false;
  let latest:Candidate|null=null,shown:Candidate|null=null,continueDrawing=false;
  // Read the live queue after awaits: a newer gesture may have replaced it.
  const queuedCandidate=():Candidate|null=>latest;
  let submittedContext:string|null=null,resumeReady=false;
  let paintTimer:ReturnType<typeof setTimeout>|undefined;
  const listeners=new Set<(value:RecoveryState)=>void>();
  const publish=(patch:Partial<RecoveryState>)=>{state={...state,...patch};if(active)listeners.forEach(f=>f(state));};
  const pending=()=>!!state.request&&['sending','waiting','uncertain'].includes(state.phase);
  const current=(o:Owner)=>active&&owner===o;
  function discard(){
    const old=owner;owner=null;latest=null;shown=null;++life;inflight=false;
    if(paintTimer!==undefined)clearTimeout(paintTimer);paintTimer=undefined;
    if(old)void api.cancel(old.id,old.ticket,old.documentId).catch(()=>{});
  }
  function cancel(message='已结束恢复画笔，未提交的笔迹已丢弃'){
    continueDrawing=false;resumeReady=false;
    if(pending()){publish({open:false,frame:null,message:'原操作已发送，仍需查询结果；不会重复提交'});return;}
    discard();publish({...initial(),target:state.target,message});
  }
  function failed(error:unknown){
    if(pending()){publish({phase:'uncertain',message:`原操作结果待确认：${String(error)}`});return;}
    continueDrawing=false;discard();publish({phase:'failure',frame:null,image:null,previewId:null,strokeActive:false,ending:false,message:String(error)});
  }
  async function start(target:RecoveryTarget,continuation=false){
    if(!active||owner||pending())return;
    if(!context.enabled||context.canStart===false||!context.documentId){failed(context.reason||'请等待照片可编辑');return;}
    options.prepare?.();
    const o:Owner={id:id(),ticket:null,documentId:context.documentId,contextKey:context.contextKey,ack:null};owner=o;
    continueDrawing=true;resumeReady=false;
    publish({phase:'arming',target,open:true,frame:null,previewId:null,request:null,strokeActive:false,ending:false,
      image:continuation?state.image:null,message:continuation?'此笔已完成，正在准备下一笔…':'正在冻结源图定位画面…'});
    const deadline=Date.now()+timeout;
    try{
      const receipt=await bounded(api.arm(o.id,o.documentId).then(r=>{o.ticket=r.ticket;if(!current(o))void api.cancel(o.id,o.ticket,o.documentId).catch(()=>{});return r;}),timeout);
      if(!current(o))return;
      if(!/^[1-9]\d*$/.test(receipt.ticket))throw Error('恢复源图票据无效');
      while(current(o)){
        const packet=await bounded(api.status(o.id,receipt.ticket),deadline-Date.now());if(!current(o))return;
        if(packet.capture_id!==o.id||packet.ticket!==receipt.ticket)throw Error(packet.error||'恢复源图身份变化');
        if(packet.phase==='ready'){
          const d=packet.descriptor;
          if(!d||d.domain!=='source-input'||d.document_id!==o.documentId||d.capture_id!==o.id||d.ticket!==o.ticket)throw Error('恢复定位画面必须属于当前源图');
          const frame=parseCaptureFrame(await bounded(api.frame(o.id,receipt.ticket),deadline-Date.now()),d,'source-input');
          if(!current(o))return;
          publish({phase:'painting',frame,message:'正在显示源图定位画面与全效果图…'});
          paintTimer=setTimeout(()=>{if(current(o)&&state.phase==='painting')failed('源图未完成显示，请重新开始');},timeout);return;
        }
        if(packet.phase!=='arming')throw Error(packet.error||'恢复源图已失效');
        await bounded(sleep(100),deadline-Date.now());
      }
    }catch(error){if(current(o))failed(error);}
  }
  function sourcePresented(descriptor:CaptureDescriptor):Promise<boolean>{
    const o=owner;
    if(!o||!o.ticket||!current(o)||state.frame?.descriptor!==descriptor)return Promise.resolve(false);
    if(state.phase!=='painting')return Promise.resolve(true);
    if(o.ack)return o.ack;
    o.ack=(async()=>{try{
      const receipt=await bounded(api.presented(o.id,o.ticket!,o.documentId),timeout);if(!current(o))return false;
      if(receipt.eligible!==true)throw Error('恢复源图尚未显示');
      if(paintTimer!==undefined)clearTimeout(paintTimer);paintTimer=undefined;
      schedule({action:'view',target:state.target},false);return true;
    }catch(error){if(current(o))failed(error);return false;}})();return o.ack;
  }
  function schedule(mutation:RecoveryMutation,final:boolean){
    if(!owner?.ticket||pending())return;
    latest={id:id(),mutation:structuredClone(mutation),final,serial:++serial};
    publish({phase:state.strokeActive?'drawing':'previewing',ending:final,message:final?'正在显示本笔最终效果，随后自动提交一次…':'全效果预览更新中…'});
    void pump();
  }
  async function pump(){
    if(inflight||!latest||!owner?.ticket||pending()||!active)return;
    const candidate=latest,o=owner,token=life;latest=null;inflight=true;
    try{
      await bounded(api.preview('preview',candidate.id,o.id,o.ticket!,candidate.mutation),timeout);
      const deadline=Date.now()+timeout;
      while(current(o)&&token===life){
        const raw=await bounded(api.previewStatus(candidate.id),deadline-Date.now());if(!current(o)||token!==life)return;
        if(!object(raw)||raw.preview_id!==candidate.id||raw.document_id!==o.documentId||raw.capture_id!==o.id||raw.ticket!==o.ticket)throw Error('恢复效果预览身份变化');
        if(raw.state==='running'){await bounded(sleep(100),deadline-Date.now());continue;}
        if(raw.state!=='ready'||raw.success!==true)throw Error(typeof raw.error==='string'?raw.error:'恢复预览没有完成');
        const image=review(raw.result);
        shown=candidate;
        publish({image,previewId:candidate.id,phase:state.strokeActive?'drawing':'previewing',message:latest?'全效果预览更新中…':candidate.final?'正在显示本笔最终效果…':'左侧定位原图，右侧是真实全效果；可继续涂抹'});
        return;
      }
    }catch(error){
      const queued=queuedCandidate();
      if(current(o)&&token===life&&(!queued||queued.serial<=candidate.serial))failed(error);
    }
    finally{if(token===life){inflight=false;if(latest)void pump();}}
  }
  async function imagePresented(preview:string){
    const candidate=shown,o=owner,token=life;
    if(!candidate||candidate.id!==preview||!o?.ticket||!current(o)||pending()||latest||inflight||candidate.serial!==serial)return;
    try{
      await bounded(api.preview('presented',candidate.id,o.id,o.ticket),timeout);
      if(!current(o)||token!==life||shown!==candidate||latest||candidate.serial!==serial)return;
      const deadline=Date.now()+timeout;
      while(current(o)&&token===life&&shown===candidate&&!latest&&candidate.serial===serial){
        const raw=await bounded(api.previewStatus(candidate.id),deadline-Date.now());
        if(!current(o)||token!==life||shown!==candidate||latest||candidate.serial!==serial)return;
        if(!object(raw)||raw.preview_id!==candidate.id)throw Error('恢复显示证明身份变化');
        if(raw.state==='presented'){
          if(candidate.final&&!state.strokeActive)await apply(candidate,o);
          else publish({phase:'drawing',message:'左侧原图定位，右侧全效果即时反馈；松手自动保存一笔，Esc 结束'});
          return;
        }
        if(raw.state!=='ready')throw Error(typeof raw.error==='string'?raw.error:'恢复效果显示未确认');
        await bounded(sleep(80),deadline-Date.now());
      }
    }catch(error){if(current(o)&&token===life&&shown===candidate&&candidate.serial===serial&&!latest)failed(error);}
  }
  async function query(request:RecoveryRequest){
    if(!active||querying)return;querying=true;const token=life,deadline=Date.now()+timeout;
    publish({phase:'waiting',request,message:'正在确认本笔的撤销历史回执…'});
    try{
      while(active&&token===life){
        const packet=await bounded(api.result(request.request_id),deadline-Date.now());if(!active||token!==life)return;
        if(!object(packet)||packet.request_id!==request.request_id)throw Error('恢复历史回执身份不匹配');
        if(packet.phase==='pending'){await bounded(sleep(100),deadline-Date.now());continue;}
        if(packet.phase!=='done'||!object(packet.result))throw Error('原请求结果未找到；不会重发');
        const r=packet.result;
        if(r.protocol!==1||r.action!=='apply'||r.request_id!==request.request_id||r.preview_id!==request.preview_id||
          r.document_id!==request.document_id||r.capture_id!==request.capture_id||r.ticket!==request.ticket||
          typeof r.success!=='boolean'||typeof r.outcome_unknown!=='boolean')throw Error('恢复提交回执不完整');
        if(r.outcome_unknown)throw Error(typeof r.error==='string'?r.error:'原请求执行结果未知');
        if(!r.success){discard();publish({phase:'failure',frame:null,image:null,previewId:null,ending:false,message:typeof r.error==='string'?r.error:'本笔未完成'});return;}
        if(r.requires_reload!==false||typeof r.no_change!=='boolean'||!object(r.history)||!count(r.history.undo_steps)||!count(r.history.redo_steps))throw Error('恢复提交缺少完成后的历史证据');
        const again=continueDrawing&&context.documentId===request.document_id;
        discard();const completedLife=life;publish({frame:null,request:null,ending:false});
        let refreshFailed=false;
        try{await bounded(options.refresh(),Math.min(timeout,5000));}catch{refreshFailed=true;}
        if(!active||life!==completedLife)return;
        resumeReady=again&&continueDrawing&&!refreshFailed&&context.documentId===request.document_id;
        if(r.no_change)submittedContext=null;
        publish({phase:'success',message:(r.no_change?'本笔未改变效果，未新增历史':'本笔已完成，可撤销')+
          (refreshFailed?'；状态刷新失败，已暂停续画，请刷新后继续':'')});
        return;
      }
    }catch(error){if(active&&token===life){publish({phase:'uncertain',frame:null,ending:false,message:`结果未确认：${String(error)}`});}}
    finally{querying=false;}
  }
  async function apply(candidate:Candidate,o:Owner){
    if(!current(o)||!o.ticket||pending()||candidate.mutation.action==='view'||!context.enabled||context.documentId!==o.documentId||context.contextKey!==o.contextKey)return;
    const request:RecoveryRequest={request_id:`recovery-${id()}`,preview_id:candidate.id,capture_id:o.id,ticket:o.ticket,document_id:o.documentId};
    submittedContext=context.contextKey;resumeReady=false;
    publish({phase:'sending',request,strokeActive:false,message:'正在自动提交一笔恢复…'});
    try{await bounded(api.submit(request),timeout);}catch{/* A transport failure can follow execution. Query, never resubmit. */}
    if(active)await query(request);
  }
  return {snapshot:()=>state,subscribe:(f:(value:RecoveryState)=>void)=>{listeners.add(f);return()=>{listeners.delete(f);};},
    start,cancel,failed,sourcePresented,imagePresented,
    context(next:RecoveryContext){if(context.documentId!==next.documentId){continueDrawing=false;resumeReady=false;}context=next;if(owner&&!pending()&&(!next.enabled||next.documentId!==owner.documentId||next.contextKey!==owner.contextKey))cancel(next.reason||'编辑状态变化，未提交笔迹已取消');},
    beginStroke(){if(state.phase!=='drawing'||state.ending||!state.image||pending())return false;publish({strokeActive:true});return true;},
    stroke(stroke:RecoveryStroke,final=false){if(!state.strokeActive||pending())return;if(final)publish({strokeActive:false});schedule({action:'stroke',target:state.target,stroke},final);},
    mutate(mutation:RecoveryMutation){if(!owner||pending()||state.strokeActive||state.ending)return;schedule(mutation,true);},
    gestureCancelled(message:string){if(pending())return;latest=null;shown=null;++serial;publish({strokeActive:false,ending:false,message});if(owner?.ticket)schedule({action:'view',target:state.target},false);},
    canContinue:()=>state.phase==='success'&&resumeReady&&continueDrawing&&context.enabled&&context.canStart!==false&&context.contextKey!==submittedContext,
    resume:()=>start(state.target,true),
    busy:pending,capturing:()=>!!owner,externalEdit(){continueDrawing=false;resumeReady=false;if(owner&&!pending())cancel('照片正在调整，未提交笔迹已取消');},
    check:async()=>{if(state.request&&!querying&&['waiting','uncertain'].includes(state.phase))await query(state.request);},
    activate(){active=true;},stop(){continueDrawing=false;const wasPending=pending();discard();active=false;querying=false;
      state=wasPending?{...state,phase:'uncertain',frame:null,message:'原操作等待中断，请查询结果；不会重发'}:initial();},
    acknowledgeAfterReload(){if(active&&!querying&&state.phase==='uncertain'&&state.request&&context.enabled&&context.documentId!==state.request.document_id){discard();publish(initial());}},
  };
}
