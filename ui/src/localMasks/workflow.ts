import {parseCaptureFrame,type VerifiedCapture} from '../captureFrame.ts';
import type {CaptureDescriptor} from '../captureModel';
import type {CloneStampCaptureStatus} from '../cloneStamp/workflow';
import type {MaskMutation,MaskObject,PromptAcceptance} from './model';
import {mutationGroupId,objectMutation,withObjectMutation} from './model.ts';
import type {Point} from '../sourcePatch/geometry';
import type {RangePatch} from './RangeControls';
import {luminanceMapUnavailableReason,sourceLuminanceFromSrgb8} from './display.ts';
export interface LocalMaskContext {enabled:boolean;canStart?:boolean;documentId:string;contextKey:string;reason?:string}
export interface LocalMaskRequest {request_id:string;capture_id:string;ticket:string;document_id:string;mutation:MaskMutation}
export interface LocalMaskTransport {
  arm:(captureId:string,documentId:string,groupId:string|null)=>Promise<{ticket:string}>;
  status:(captureId:string,ticket:string)=>Promise<CloneStampCaptureStatus>;
  frame:(captureId:string,ticket:string)=>Promise<ArrayBuffer>;
  presented:(captureId:string,ticket:string,documentId:string)=>Promise<{eligible:boolean}>;
  cancel:(captureId:string,ticket:string|null,documentId:string)=>Promise<unknown>;
  submit:(request:LocalMaskRequest)=>Promise<unknown>;
  result:(requestId:string)=>Promise<unknown>;
}
export interface LocalMaskState {
  phase:'idle'|'arming'|'painting'|'target'|'sending'|'waiting'|'success'|'failure'|'uncertain';
  groupId:string|null;showOverlay:boolean;showLuminanceMap:boolean;frame:VerifiedCapture|null;mutation:MaskMutation|null;draw:boolean;geometryReady:boolean;request:LocalMaskRequest|null;message:string;
}
interface CaptureOwner {id:string;ticket:string|null;documentId:string;contextKey:string;groupId:string|null;ack:Promise<boolean>|null}
const initial=():LocalMaskState=>({phase:'idle',groupId:null,showOverlay:true,showLuminanceMap:false,frame:null,mutation:null,draw:false,geometryReady:false,request:null,message:''});
const object=(v:unknown):v is Record<string,unknown>=>!!v&&typeof v==='object'&&!Array.isArray(v);
const count=(v:unknown)=>Number.isSafeInteger(v)&&Number(v)>=0;
function bounded<T>(promise:Promise<T>,milliseconds:number):Promise<T>{
  let timer:ReturnType<typeof setTimeout>|undefined;
  return Promise.race([promise,new Promise<T>((_,reject)=>{timer=setTimeout(()=>reject(Error('等待超时')),Math.max(1,milliseconds));})])
    .finally(()=>{if(timer!==undefined)clearTimeout(timer);});
}
/** Retained edits stay in the engine report. This owns only an uncommitted mutation. */
export function createLocalMaskWorkflow(api:LocalMaskTransport,options:{refresh:()=>Promise<void>;id?:()=>string;sleep?:(ms:number)=>Promise<void>;timeoutMs?:number}){
  const id=options.id??(()=>crypto.randomUUID().replaceAll('-',''));
  const sleep=options.sleep??((ms:number)=>new Promise<void>(resolve=>setTimeout(resolve,ms)));
  const timeout=options.timeoutMs??15000;
  let state=initial(),context:LocalMaskContext={enabled:false,documentId:'',contextKey:''};
  let owner:CaptureOwner|null=null,active=true,life=0,running=false;
  let paintTimer:ReturnType<typeof setTimeout>|undefined;
  const listeners=new Set<(next:LocalMaskState)=>void>();
  const publish=(patch:Partial<LocalMaskState>)=>{state={...state,...patch};if(active)listeners.forEach(f=>f(state));};
  const pending=()=>['sending','waiting','uncertain'].includes(state.phase)&&!!state.request;
  const current=(o:CaptureOwner)=>active&&owner===o;
  const clearTimer=()=>{if(paintTimer!==undefined)clearTimeout(paintTimer);paintTimer=undefined;};
  const release=(o:CaptureOwner)=>{void api.cancel(o.id,o.ticket,o.documentId).catch(()=>{/* A cancellation never mutates a mask. */});};
  function discard(){const old=owner;owner=null;clearTimer();if(old)release(old);}
  function cancel(message='已取消，未修改蒙版'){
    if(pending())publish({frame:null,message:'操作已发送，仍需确认原操作结果；不会重复提交'});
    else{discard();publish({...initial(),message});}
  }
  function failed(error:unknown){
    if(pending()){publish({message:`原操作仍待确认：${String(error)}`});return;}
    discard();publish({...initial(),phase:'failure',message:String(error)});
  }
  function updateContext(next:LocalMaskContext){
    context=next;
    if(owner&&(!next.enabled||next.documentId!==owner.documentId||next.contextKey!==owner.contextKey))
      cancel(next.reason||'照片或编辑状态变化，未提交蒙版已取消');
  }
  function selectGroup(groupId:string|null){
    if(pending()||running)return false;
    if(owner&&owner.groupId!==groupId)cancel('已切换蒙版组，原组的冻结画面与未提交修改已取消');
    return true;
  }
  async function start(mutation:MaskMutation|null,draw=false,groupId:string|null=null){
    if(!active||running||pending())return;
    const targetGroup=mutation?mutationGroupId(mutation):groupId;
    if(groupId!==null&&groupId!==targetGroup){failed('请求的蒙版组与修改目标不一致');return;}
    if(!selectGroup(targetGroup)||owner)return;
    if(!context.enabled||context.canStart===false||!context.documentId){publish({phase:'failure',message:context.reason||'请等待照片与引擎就绪'});return;}
    const o:CaptureOwner={id:id(),ticket:null,documentId:context.documentId,contextKey:context.contextKey,groupId:targetGroup,ack:null};owner=o;
    publish({...initial(),groupId:targetGroup,phase:'arming',mutation:structuredClone(mutation),draw,geometryReady:!draw,message:targetGroup?'正在冻结原始源图与所选组的已保存范围…':'正在冻结原始源图…'});
    const deadline=Date.now()+timeout;
    try{
      const arm=api.arm(o.id,o.documentId,o.groupId).then(receipt=>{o.ticket=receipt.ticket;if(!current(o))release(o);return receipt;});
      const receipt=await bounded(arm,deadline-Date.now());if(!current(o))return;
      if(!/^[1-9]\d*$/.test(receipt.ticket))throw Error('蒙版取样票据无效');
      while(current(o)){
        if(Date.now()>=deadline)throw Error('冻结原始源图超时');
        const report=await bounded(api.status(o.id,receipt.ticket),deadline-Date.now());if(!current(o))return;
        if(['error','stale','idle'].includes(report.phase))throw Error(report.error||'源图画面已失效');
        if(report.capture_id!==o.id||report.ticket!==receipt.ticket)throw Error('源图回执身份不匹配');
        if(report.phase==='ready'){
          const d=report.descriptor;
          if(!d||d.capture_id!==o.id||d.ticket!==receipt.ticket||d.document_id!==o.documentId||d.domain!=='source-input'||d.mask_overlay!==true)throw Error('蒙版必须使用原始源图');
          if((d.mask_group_id??null)!==o.groupId)throw Error('冻结范围不属于所选蒙版组，请重新捕获');
          const buffer=await bounded(api.frame(o.id,receipt.ticket),deadline-Date.now());if(!current(o))return;
          const frame=parseCaptureFrame(buffer,d,'source-input');
          publish({phase:'painting',frame,message:'正在显示原始源图…'});
          paintTimer=setTimeout(()=>{if(current(o)&&state.phase==='painting')failed('源图未完成显示，请重新开始');},timeout);return;
        }
        if(report.phase!=='arming')throw Error('源图取样状态不一致，请重新开始');
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
        const reply=await bounded(api.presented(o.id,o.ticket!,o.documentId),timeout);if(!current(o))return false;
        if(reply.eligible!==true)throw Error('源图尚未完成显示');
        clearTimer();publish({phase:'target',message:state.draw?'请在源图上拖动绘制；释放后可检查，再应用':state.mutation?'原始源图已显示，请确认本次蒙版修改':'原始源图与已保存组合范围已显示；本次仅查看'});return true;
      }catch(error){if(current(o))failed(error);return false;}
    })();return o.ack;
  }
  function geometry(mask:MaskObject){
    if(state.phase!=='target'||!state.draw||objectMutation(state.mutation)?.object.id!==mask.id)return;
    publish({mutation:withObjectMutation(state.mutation!,{action:'upsert',coordinate_space:'capture',object:structuredClone(mask)}),geometryReady:true,message:'几何已准备；可重新拖动替换，点击应用后保留为可编辑对象'});
  }
  function range(patch:RangePatch){
    const inner=objectMutation(state.mutation);
    if(state.phase!=='target'||!inner)return;
    const object=inner.object;
    let next:MaskObject;
    if(object.kind==='color_range'){
      const color=patch.color??object.color,tolerance=patch.tolerance??object.tolerance,invert=patch.invert??object.invert??false;
      if(color.length!==3||!color.every(n=>Number.isFinite(n)&&n>=0&&n<=1)||!Number.isFinite(tolerance)||tolerance<0||tolerance>1||typeof invert!=='boolean')return;
      next={...object,color:[...color],tolerance,invert};
    }else if(object.kind==='luminance_range'){
      const low=patch.low??object.low,high=patch.high??object.high;
      if(!Number.isFinite(low)||!Number.isFinite(high)||low<0||high>1||low>high)return;
      next={...object,low,high};
    }else return;
    publish({mutation:withObjectMutation(state.mutation!,{...inner,object:next}),geometryReady:true});
  }
  function sample(point:Point){
    const inner=objectMutation(state.mutation);
    if(state.phase!=='target'||!state.frame||!inner||point.some(n=>!Number.isFinite(n)||n<0||n>1))return;
    const object=inner.object,d=state.frame.descriptor;
    const x=Math.min(d.width-1,Math.floor(point[0]*d.width)),y=Math.min(d.height-1,Math.floor(point[1]*d.height)),offset=(y*d.width+x)*4;
    const row=d.sample_valid_rows?.[y];
    if(!row||row.length!==2||!row.every(Number.isSafeInteger)||row[0]<0||row[1]>d.width||x<row[0]||x>=row[1]){
      publish({message:!d.sample_valid_rows?'此画面没有可用采样有效域；请手动设定范围':'点击位置是构图填充边缘，不是有效源图像素；请选择图像内部'});return;
    }
    const color=[0,1,2].map(i=>state.frame!.rgba[offset+i]/255) as [number,number,number];
    if(object.kind==='color_range')range({color});
    else if(object.kind==='luminance_range'){
      const rgb=state.frame.rgba;
      const value=sourceLuminanceFromSrgb8(rgb[offset],rgb[offset+1],rgb[offset+2]),width=object.high-object.low;
      const low=Math.max(0,Math.min(1-width,value-width/2));range({low,high:low+width});
    }else return;
    publish({message:'已用显示用 8 位源图代理取样（近似）；可调整范围参数，确认后应用'});
  }
  async function query(request:LocalMaskRequest){
    if(!active||running)return;const token=life,deadline=Date.now()+timeout;running=true;
    publish({phase:'waiting',request,message:'正在确认蒙版修改的历史回执…'});
    try{
      while(active&&token===life){
        if(Date.now()>=deadline)throw Error('等待原操作结果超时；不会重新提交');
        const packet=await bounded(api.result(request.request_id),deadline-Date.now());if(!active||token!==life)return;
        if(!object(packet)||packet.request_id!==request.request_id)throw Error('蒙版回执身份不匹配');
        if(packet.phase==='pending'){await bounded(sleep(150),deadline-Date.now());continue;}
        if(packet.phase!=='done'||!object(packet.result))throw Error('原操作结果未找到或引擎已重启；不会重新提交');
        const result=packet.result;
        if(result.protocol!==1||result.action!=='apply'||result.request_id!==request.request_id||result.document_id!==request.document_id||
          result.capture_id!==request.capture_id||result.ticket!==request.ticket||typeof result.success!=='boolean'||typeof result.outcome_unknown!=='boolean')throw Error('蒙版完成回执不完整');
        if(result.outcome_unknown)throw Error(typeof result.error==='string'?result.error:'结果未确认');
        if(!result.success){discard();publish({phase:'failure',frame:null,message:typeof result.error==='string'?result.error:'蒙版修改未完成'});return;}
        if(result.requires_reload!==false||typeof result.no_change!=='boolean'||!object(result.history)||!count(result.history.undo_steps)||!count(result.history.redo_steps))throw Error('缺少提交后的历史证据');
        discard();publish({frame:null});
        let refreshFailed=false;try{await bounded(options.refresh(),Math.min(timeout,3000));}catch{refreshFailed=true;}
        if(!active||token!==life)return;
        publish({phase:'success',mutation:null,draw:false,message:(result.no_change?'蒙版未变化，未新增历史步骤':context.documentId===request.document_id?'蒙版修改已完成，可撤销':'上一张照片的蒙版修改已完成，可撤销')+(refreshFailed?'；状态刷新失败，请稍后刷新':'')});return;
      }
    }catch(error){if(active&&token===life){discard();publish({phase:'uncertain',frame:null,request,message:`结果未确认：${String(error)}`});}}
    finally{if(token===life)running=false;}
  }
  function acceptPrompted(mutation:PromptAcceptance){
    if(!active||running||pending()||!owner||owner.groupId!==null||state.phase!=='target')return false;
    publish({mutation:structuredClone(mutation),draw:false,geometryReady:true,message:'已审核 AI 提示选区，正在提交一次修改'});return true;
  }
  async function apply(){
    const o=owner;
    if(!active||running||pending()||!o||!o.ticket||state.phase!=='target'||!state.mutation||!state.geometryReady)return;
    if(mutationGroupId(state.mutation)!==o.groupId||(state.frame?.descriptor.mask_group_id??null)!==o.groupId){failed('蒙版组与已显示范围不一致，请重新捕获');return;}
    if(!context.enabled||context.documentId!==o.documentId||context.contextKey!==o.contextKey){cancel('照片或编辑状态已变化，未提交蒙版');return;}
    const request:LocalMaskRequest={request_id:`local-masks-${id()}`,capture_id:o.id,ticket:o.ticket,document_id:o.documentId,mutation:structuredClone(state.mutation)};
    const token=life;running=true;publish({phase:'sending',request,message:'正在提交一次蒙版修改…'});
    try{await bounded(api.submit(request),timeout);}catch{/* Transport failure may follow execution. Query the original request only. */}
    if(!active||token!==life)return;running=false;await query(request);
  }
  return {snapshot:()=>state,subscribe:(f:(s:LocalMaskState)=>void)=>{listeners.add(f);return()=>{listeners.delete(f);};},context:updateContext,start,selectGroup,cancel,failed,presented,geometry,range,sample,acceptPrompted,apply,
    overlay(showOverlay:boolean){publish({showOverlay});},
    luminanceMap(showLuminanceMap:boolean){
      if(state.phase!=='target'||!state.frame)return;
      const reason=showLuminanceMap?luminanceMapUnavailableReason(state.frame.descriptor):null;
      if(reason){publish({message:reason});return;}
      // Display-only: no mutation, receipt, presentation proof, or history edit.
      publish({showLuminanceMap});
    },
    beginGeometry(){if(state.phase==='target'&&state.draw)publish({geometryReady:false});},
    gestureCancelled(message:string){if(state.phase==='target')publish({message});},busy:pending,capturing:()=>!!owner,
    externalEdit(){if(owner&&!pending())cancel('照片正在调整，未提交蒙版已取消');},
    check:async()=>{if(active&&state.request&&!running&&['waiting','uncertain'].includes(state.phase))await query(state.request);},
    activate(){active=true;},stop(){discard();active=false;++life;running=false;state=pending()?{...state,phase:'uncertain',frame:null,message:'等待被中断，请查询原蒙版操作；不会重发'}:initial();},
    acknowledgeAfterReload(){if(active&&!running&&state.phase==='uncertain'&&state.request&&context.enabled&&context.documentId!==state.request.document_id)publish(initial());},
  };
}
