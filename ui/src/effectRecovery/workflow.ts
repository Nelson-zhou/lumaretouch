import {parseCaptureFrame,type VerifiedCapture} from '../captureFrame';
import type {CaptureDescriptor} from '../captureModel';
import type {CloneStampCaptureStatus} from '../cloneStamp/workflow';
import {requiresRecoveryConfirmation} from './model';
import type {RecoveryTarget,RecoveryMutation,RecoveryImage,RecoveryRequest,RecoveryStroke} from './model';
import {validRecoveryAliasReview,verifyRecoveryAliasReview,recoveryAliasAck,sameRecoveryAliasAck,recoveryAliasMemberKey,recoveryAliasMarker,validRecoveryAliasMembers,type RecoveryAliasReview,type RecoveryAliasAck} from './aliasModel';
import {fetchRecoveryAliasImage,type RecoveryAliasImageTransport} from './aliasTransport';
import {recoveryAliasWorkspace,recoveryAliasWritePending,setRecoveryAliasWritePending,registerRecoveryAliasReceipt,sameRecoveryAliasMarker,subscribeRecoveryAliasWorkspace,type RecoveryWorkspaceReplacement} from './aliasHistoryRegistry';

export interface RecoveryContext {enabled:boolean;canStart?:boolean;documentId:string;contextKey:string;reason?:string}
export interface RecoveryTransport {
  arm:(id:string,document:string)=>Promise<{ticket:string}>;
  status:(id:string,ticket:string)=>Promise<CloneStampCaptureStatus>;
  frame:(id:string,ticket:string)=>Promise<ArrayBuffer>;
  presented:(id:string,ticket:string,document:string)=>Promise<{eligible:boolean}>;
  cancel:(id:string,ticket:string|null,document:string)=>Promise<unknown>;
  preview:(action:'preview'|'presented'|'cancel',id:string,capture:string,ticket:string,mutation?:RecoveryMutation,ack?:RecoveryAliasAck)=>Promise<unknown>;
  previewStatus:(id:string)=>Promise<unknown>;
  aliasImage?:RecoveryAliasImageTransport;
  submit:(request:RecoveryRequest)=>Promise<unknown>;
  result:(id:string)=>Promise<unknown>;
}
type Phase='idle'|'arming'|'painting'|'drawing'|'previewing'|'sending'|'waiting'|'success'|'failure'|'uncertain';
export interface RecoveryState {
  phase:Phase;target:RecoveryTarget;frame:VerifiedCapture|null;image:RecoveryImage|null;previewId:string|null;
  request:RecoveryRequest|null;message:string;strokeActive:boolean;ending:boolean;open:boolean;awaitingConfirmation:boolean;aliasReview:RecoveryAliasReview|null;receiptBatchId:string|null;
}
interface Owner {id:string;ticket:string|null;documentId:string;contextKey:string;workspace:string|null;ack:Promise<boolean>|null}
interface Candidate {id:string;mutation:RecoveryMutation;final:boolean;serial:number;reviewed?:boolean;alias?:RecoveryAliasReview;memberAcks?:Set<string>;presenting?:boolean}
const initial=():RecoveryState=>({phase:'idle',target:'skin_smoothing',frame:null,image:null,previewId:null,
  request:null,message:'',strokeActive:false,ending:false,open:false,awaitingConfirmation:false,aliasReview:null,receiptBatchId:null});
const object=(v:unknown):v is Record<string,unknown>=>!!v&&typeof v==='object'&&!Array.isArray(v);
/** A valid legacy recovery preview is not consent for the separate ID stage. */
export const recoveryTargetMatches=(value:unknown,target:RecoveryTarget):boolean=>object(value)&&value.target===target;
const count=(v:unknown)=>Number.isSafeInteger(v)&&Number(v)>=0;
function bounded<T>(promise:Promise<T>,ms:number):Promise<T>{
  let timer:ReturnType<typeof setTimeout>|undefined;
  return Promise.race([promise,new Promise<T>((_,reject)=>{timer=setTimeout(()=>reject(Error('等待超时')),Math.max(1,ms));})])
    .finally(()=>{if(timer!==undefined)clearTimeout(timer);});
}
export function recoveryReview(value:unknown,target:RecoveryTarget):RecoveryImage {
  if(!object(value)||value.domain!=='production-output'||value.quality!==(target==='eye_bag_preserve'?'full-source-render-srgb8':'proxy-render-srgb8')||
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
  let latest:Candidate|null=null,shown:Candidate|null=null,continueDrawing=false,aliasWorkspace=false;
  // Read the live queue after awaits: a newer gesture may have replaced it.
  const queuedCandidate=():Candidate|null=>latest;
  let submittedContext:string|null=null,resumeReady=false;
  let paintTimer:ReturnType<typeof setTimeout>|undefined;
  const listeners=new Set<(value:RecoveryState)=>void>();
  const publish=(patch:Partial<RecoveryState>)=>{state={...state,...patch};if(active)listeners.forEach(f=>f(state));};
  const pending=()=>!!state.request&&['sending','waiting','uncertain'].includes(state.phase);
  const current=(o:Owner)=>active&&owner===o;
  const workspaceReplaced=(replacement:RecoveryWorkspaceReplacement)=>{
    if(!active||state.request?.protocol!==2||state.request.workspace!==replacement.previous)return;
    continueDrawing=false;resumeReady=false;discard();publish({...initial(),target:'eye_bag_preserve',phase:'failure',message:'已确认进入新的项目工作区；原恢复写入结果仍未知，不认定成功。请核对全部成员后使用当前准确批次台账。'});
  };
  let stopWorkspaceRecovery:(()=>void)|null=subscribeRecoveryAliasWorkspace(workspaceReplaced);
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
    continueDrawing=false;discard();publish({phase:'failure',frame:null,image:null,aliasReview:null,previewId:null,strokeActive:false,ending:false,awaitingConfirmation:false,message:String(error)});
  }
  async function start(target:RecoveryTarget,continuation=false){
    if(!active||owner||pending()||recoveryAliasWritePending())return;
    if(!context.enabled||context.canStart===false||!context.documentId){failed(context.reason||'请等待照片可编辑');return;}
    options.prepare?.();
    if(!continuation)aliasWorkspace=false;
    const o:Owner={id:id(),ticket:null,documentId:context.documentId,contextKey:context.contextKey,workspace:recoveryAliasWorkspace(),ack:null};owner=o;
    continueDrawing=true;resumeReady=false;
    publish({phase:'arming',target,open:true,frame:null,previewId:null,request:null,receiptBatchId:null,strokeActive:false,ending:false,awaitingConfirmation:false,
      image:continuation?state.image:null,aliasReview:null,message:continuation?'此笔已完成，正在准备下一笔…':'正在冻结源图定位画面…'});
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
    publish({phase:state.strokeActive?'drawing':'previewing',ending:final,awaitingConfirmation:false,aliasReview:null,message:final?(requiresRecoveryConfirmation(state.target)?'正在生成本笔完整源图渲染，确认后才保存…':'正在显示本笔最终效果，随后自动提交一次…'):'全效果预览更新中…'});
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
        if(raw.state!=='ready'||raw.success!==true||!recoveryTargetMatches(raw,candidate.mutation.target))throw Error(typeof raw.error==='string'?raw.error:'恢复预览没有完成或效果目标不匹配');
        if(raw.protocol===2){
          const descriptor=state.frame?.descriptor as (CaptureDescriptor&{full_source?:[number,number]})|undefined;
          if(candidate.mutation.target!=='eye_bag_preserve'||!object(raw.result)||raw.result.domain!=='production-output'||raw.result.quality!=='full-source-render-srgb8'
            ||!descriptor?.recipe_document_id||!validRecoveryAliasReview(raw.result.review,descriptor.recipe_document_id)
            ||raw.recipe_document_id!==descriptor.recipe_document_id||raw.recipe_revision!==descriptor.recipe_revision||raw.generation!==descriptor.generation
            ||raw.result.review.visual.revision!==descriptor.recipe_revision||!Array.isArray(descriptor.full_source)
            ||JSON.stringify(raw.result.review.visual.source_size)!==JSON.stringify(descriptor.full_source)||!o.workspace||o.workspace!==recoveryAliasWorkspace()
            ||!await verifyRecoveryAliasReview(raw.result.review))throw Error('共享来源恢复审核缺少准确全成员、来源或摘要证明');
          if(!current(o)||token!==life||candidate.serial!==serial||latest)return;
          candidate.alias=structuredClone(raw.result.review);candidate.memberAcks=new Set();shown=candidate;aliasWorkspace=true;
          publish({image:null,aliasReview:candidate.alias,previewId:candidate.id,phase:state.strokeActive?'drawing':'previewing',message:candidate.mutation.action==='view'&&!candidate.final
            ?'这是绘制前的只读基线。先读取并确认第 1 张当前照片即可开始绘制；不会提交。每次实际修改仍须逐张审核全部成员。'
            :'请逐张读取并比较所有共享来源成员的完整前后图；每张保留自己的裁剪、修补和其他编辑。'});return;
        }
        if(raw.protocol!==undefined&&raw.protocol!==1)throw Error('恢复审核协议不匹配');
        const image=recoveryReview(raw.result,candidate.mutation.target);
        shown=candidate;
        publish({image,aliasReview:null,previewId:candidate.id,phase:state.strokeActive?'drawing':'previewing',message:latest?'全效果预览更新中…':candidate.final?'正在显示本笔最终效果…':'左侧定位原图，右侧是真实全效果；可继续涂抹'});
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
    const alias=candidate.alias,ack=alias?recoveryAliasAck(alias):undefined;
    // Baseline viewing grants drawing availability only, never native presentation or write authority.
    if(alias&&candidate.mutation.action==='view')return;
    if(candidate.presenting||candidate.reviewed||alias&&!alias.members.every(member=>candidate.memberAcks?.has(recoveryAliasMemberKey(preview,alias,member))))return;
    candidate.presenting=true;
    try{
      await bounded(api.preview('presented',candidate.id,o.id,o.ticket,undefined,ack),timeout);
      if(!current(o)||token!==life||shown!==candidate||latest||candidate.serial!==serial)return;
      const deadline=Date.now()+timeout;
      while(current(o)&&token===life&&shown===candidate&&!latest&&candidate.serial===serial){
        const raw=await bounded(api.previewStatus(candidate.id),deadline-Date.now());
        if(!current(o)||token!==life||shown!==candidate||latest||candidate.serial!==serial)return;
        if(!object(raw)||raw.preview_id!==candidate.id||!recoveryTargetMatches(raw,candidate.mutation.target))throw Error('恢复显示证明身份或效果目标变化');
        if(raw.state==='presented'){
          if(alias&&(raw.protocol!==2||raw.review_sha256!==alias.review_sha256||raw.document_id!==o.documentId||raw.capture_id!==o.id||raw.ticket!==o.ticket
            ||raw.generation!==state.frame?.descriptor.generation||raw.recipe_document_id!==state.frame?.descriptor.recipe_document_id
            ||raw.recipe_revision!==state.frame?.descriptor.recipe_revision))throw Error('共享来源恢复显示证明不匹配');
          if(alias&&!alias.members.every(member=>candidate.memberAcks?.has(recoveryAliasMemberKey(preview,alias,member)))){
            publish({awaitingConfirmation:false,message:'有成员撤回了确认，请重新比较并确认；尚未保存。'});return;
          }
          candidate.reviewed=true;
          if(candidate.final&&!state.strokeActive){
            if(requiresRecoveryConfirmation(candidate.mutation.target))publish({phase:'previewing',awaitingConfirmation:true,message:alias?`全部 ${alias.members.length} 张成员已逐图确认。最后确认后将只发布共享的本效果恢复笔迹，并进入全成员批次历史。`:'本笔完整源图渲染已显示。请比较前后，确认后才保存；结束画笔可丢弃。'});
            else await apply(candidate,o);
          }
          else publish({phase:'drawing',message:requiresRecoveryConfirmation(state.target)?'左侧源图捕获定位，右侧完整源图渲染；松手预览，确认后才保存':'左侧原图定位，右侧全效果即时反馈；松手自动保存一笔，Esc 结束'});
          return;
        }
        if(raw.state!=='ready')throw Error(typeof raw.error==='string'?raw.error:'恢复效果显示未确认');
        await bounded(sleep(80),deadline-Date.now());
      }
    }catch(error){if(current(o)&&token===life&&shown===candidate&&candidate.serial===serial&&!latest)failed(error);}
    finally{candidate.presenting=false;}
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
        if(r.protocol!==(request.protocol??1)||r.action!=='apply'||r.request_id!==request.request_id||r.preview_id!==request.preview_id||
          r.document_id!==request.document_id||r.capture_id!==request.capture_id||r.ticket!==request.ticket||
          typeof r.success!=='boolean'||typeof r.outcome_unknown!=='boolean')throw Error('恢复提交回执不完整');
        const alias=request.alias_review;
        if(request.protocol===2){
          if(!alias||!request.ack||!request.workspace||!sameRecoveryAliasAck(r.ack,request.ack)||r.generation!==request.generation
            ||r.recipe_document_id!==request.recipe_document_id||r.recipe_revision!==request.recipe_revision)throw Error('共享来源恢复回执未关联原全成员确认');
          if(r.batch_id!=null){
            if(typeof r.batch_id!=='string'||!r.batch_id.trim()||new TextEncoder().encode(r.batch_id).length>128||/[\u0000-\u001f\u007f]/.test(r.batch_id))throw Error('共享来源恢复回执批次身份无效');
            publish({receiptBatchId:r.batch_id});
          }
          if(r.eye_bag_recovery_alias_review!=null){
            if(typeof r.batch_id!=='string'||!sameRecoveryAliasMarker(r.eye_bag_recovery_alias_review,recoveryAliasMarker(alias))
              ||JSON.stringify(r.module_scope)!==JSON.stringify(['lnx.people_graph.v1'])
              ||!registerRecoveryAliasReceipt(request.workspace,r.batch_id,recoveryAliasMarker(alias)))throw Error('共享来源恢复批次标记不匹配');
          }
        }
        if(r.outcome_unknown)throw Error(typeof r.error==='string'?r.error:'原请求执行结果未知');
        if(!r.success){
          if(alias&&(r.requires_reload!==false||typeof r.error!=='string'||!r.error.trim()
            ||!(r.no_write===true&&r.rolled_back!==true||r.no_write===false&&r.rolled_back===true)
            ||['batch_id','eye_bag_recovery_alias_review','alias_members','doc_state','module_scope','before','after'].some(field=>r[field]!=null)
            ||r.committed===true||r.operation_committed===true||['applied','restored'].some(field=>r[field]!==undefined&&(!Array.isArray(r[field])||(r[field] as unknown[]).length!==0))))throw Error('共享来源恢复失败回执不能证明未发布或完整补偿，只能查询原请求');
          if(alias)setRecoveryAliasWritePending(request.request_id,false);
          continueDrawing=false;discard();const failedLife=life;
          publish({phase:'failure',frame:null,image:null,aliasReview:null,previewId:null,request:null,ending:false,message:typeof r.error==='string'?r.error:'本笔未完成'});
          if(alias&&r.rolled_back===true){try{await bounded(options.refresh(),Math.min(timeout,5000));
            if(active&&life===failedLife)publish({message:`${String(r.error)}。已补偿共享图和向量；成员版本可能推进，必须从当前状态重新审核。`});}
            catch{if(active&&life===failedLife)publish({message:`${String(r.error)}。已补偿，但状态刷新失败；请先刷新全部成员，再重新审核。`});}}
          return;
        }
        if(alias){
          const next=object(r.doc_state)?r.doc_state:null,people=object(next?.people)?next.people:null,binding=object(people?.binding)?people.binding:null;
          if(r.requires_reload!==false||r.no_change!==false||r.no_write!==false||typeof r.batch_id!=='string'
            ||!sameRecoveryAliasMarker(r.eye_bag_recovery_alias_review,recoveryAliasMarker(alias))||!validRecoveryAliasMembers(r.alias_members,alias)
            ||JSON.stringify(r.module_scope)!==JSON.stringify(['lnx.people_graph.v1'])||next?.document_id!==request.document_id
            ||binding?.document_id!==alias.visual.document_id||binding.document_epoch!==request.workspace||binding.asset_sha256!==alias.face_ref.asset_sha256
            ||binding.document_revision!==Number(BigInt(alias.visual.revision)+1n)||!object(r.history)||!count(r.history.undo_steps)||!count(r.history.redo_steps))throw Error('共享来源恢复缺少完整成员原子发布证明');
          setRecoveryAliasWritePending(request.request_id,false);
        }else if(r.requires_reload!==false||typeof r.no_change!=='boolean'||!object(r.history)||!count(r.history.undo_steps)||!count(r.history.redo_steps))throw Error('恢复提交缺少完成后的历史证据');
        const again=continueDrawing&&context.documentId===request.document_id;
        discard();const completedLife=life;publish({frame:null,request:null,ending:false,aliasReview:null});
        let refreshFailed=false;
        try{await bounded(options.refresh(),Math.min(timeout,5000));}catch{refreshFailed=true;}
        if(!active||life!==completedLife)return;
        resumeReady=again&&continueDrawing&&!refreshFailed&&context.documentId===request.document_id;
        if(r.no_change)submittedContext=null;
        publish({phase:'success',message:(alias?`全部 ${alias.members.length} 张成员已确认发布；请在人物面板的共享来源恢复批次历史中整体撤销或重做。`:r.no_change?'本笔未改变效果，未新增历史':'本笔已完成，可撤销')+
          (refreshFailed?'；状态刷新失败，已暂停续画，请刷新后继续':'')});
        return;
      }
    }catch(error){if(active&&token===life){publish({phase:'uncertain',frame:null,ending:false,message:`结果未确认：${String(error)}`});}}
    finally{querying=false;}
  }
  async function apply(candidate:Candidate,o:Owner){
    if(!current(o)||!o.ticket||pending()||candidate.mutation.action==='view'||!context.enabled||context.documentId!==o.documentId||context.contextKey!==o.contextKey)return;
    const alias=candidate.alias;
    if(alias&&(!candidate.reviewed||!o.workspace||o.workspace!==recoveryAliasWorkspace()||recoveryAliasWritePending()
      ||!alias.members.every(member=>candidate.memberAcks?.has(recoveryAliasMemberKey(candidate.id,alias,member)))))return;
    const request:RecoveryRequest={request_id:`recovery-${id()}`,preview_id:candidate.id,capture_id:o.id,ticket:o.ticket,document_id:o.documentId};
    if(alias){const descriptor=state.frame?.descriptor;if(!descriptor||descriptor.recipe_document_id!==alias.visual.document_id||descriptor.recipe_revision!==alias.visual.revision)return;
      request.protocol=2;request.ack=recoveryAliasAck(alias);request.workspace=o.workspace!;request.alias_review=structuredClone(alias);
      request.generation=descriptor.generation;request.recipe_document_id=descriptor.recipe_document_id;request.recipe_revision=descriptor.recipe_revision;}
    submittedContext=context.contextKey;resumeReady=false;
    publish({phase:'sending',request,strokeActive:false,awaitingConfirmation:false,message:requiresRecoveryConfirmation(state.target)?'正在提交已确认的恢复笔迹…':'正在自动提交一笔恢复…'});
    if(alias)setRecoveryAliasWritePending(request.request_id,true,o.workspace!);
    try{await bounded(api.submit(request),timeout);}catch{/* A transport failure can follow execution. Query, never resubmit. */}
    if(active)await query(request);
  }
  return {snapshot:()=>state,subscribe:(f:(value:RecoveryState)=>void)=>{listeners.add(f);return()=>{listeners.delete(f);};},
    start,cancel,failed,sourcePresented,imagePresented,
    async readAliasImage(preview:string,review:RecoveryAliasReview,index:number,side:'before'|'after',live:()=>boolean){
      const candidate=shown,o=owner,member=review.members[index],source=state.frame?.descriptor;
      const valid=()=>live()&&!!candidate&&shown===candidate&&candidate.id===preview&&candidate.alias===review&&candidate.serial===serial&&!latest
        &&!!o?.ticket&&current(o)&&!pending()&&state.aliasReview===review&&!!source&&state.frame?.descriptor===source;
      if(!valid()||!source||!member||!api.aliasImage)throw Error('共享来源恢复图像读取已失效');
      return fetchRecoveryAliasImage(api.aliasImage,{previewId:preview,captureId:o!.id,ticket:o!.ticket!,requestId:`recovery-image-${id()}`,
        reviewSha256:review.review_sha256,memberDocumentId:member.visual.document_id,memberRevision:member.visual.revision,side,sha256:member.visual[side].sha256},member.visual[side],valid,
        {document_id:o!.documentId,generation:source.generation,recipe_document_id:review.visual.document_id,recipe_revision:review.visual.revision});
    },
    aliasMemberReviewed(preview:string,key:string,ready:boolean){
      const candidate=shown,alias=candidate?.alias;
      if(!candidate||!alias||candidate.id!==preview||candidate.serial!==serial||latest||pending()||state.aliasReview!==alias
        ||!alias.members.some(member=>recoveryAliasMemberKey(preview,alias,member)===key))return;
      if(ready)candidate.memberAcks?.add(key);else {candidate.memberAcks?.delete(key);candidate.reviewed=false;publish({awaitingConfirmation:false});}
      if(candidate.mutation.action==='view'&&candidate.final===false){
        if(key===recoveryAliasMemberKey(preview,alias,alias.members[0]))publish({phase:ready?'drawing':'previewing',awaitingConfirmation:false,
          message:ready?'当前照片的只读基线已显示，可开始绘制；这不是保存确认。松手后必须逐张比较全部成员的新效果，再明确保存。':'请先重新读取并确认当前照片只读基线；尚未允许绘制或保存。'});
        return;
      }
      if(alias.members.every(member=>candidate.memberAcks?.has(recoveryAliasMemberKey(preview,alias,member))))void imagePresented(preview);
    },
    async confirmReviewed(){
      const candidate=shown,o=owner;
      if(!state.awaitingConfirmation||!candidate?.reviewed||!candidate.final||candidate.mutation.action==='view'||
        !requiresRecoveryConfirmation(candidate.mutation.target)||!o||!current(o)||latest||inflight||pending()||
        state.strokeActive||candidate.serial!==serial||state.previewId!==candidate.id)return;
      await apply(candidate,o);
    },
    context(next:RecoveryContext){if(context.documentId!==next.documentId){continueDrawing=false;resumeReady=false;}context=next;if(owner&&!pending()&&(!next.enabled||next.documentId!==owner.documentId||next.contextKey!==owner.contextKey))cancel(next.reason||'编辑状态变化，未提交笔迹已取消');},
    beginStroke(){if(state.phase!=='drawing'||state.ending||state.awaitingConfirmation||(!state.image&&!state.aliasReview)||pending())return false;publish({strokeActive:true});return true;},
    stroke(stroke:RecoveryStroke,final=false){if(!state.strokeActive||state.awaitingConfirmation||pending())return;if(final)publish({strokeActive:false});schedule({action:'stroke',target:state.target,stroke},final);},
    mutate(mutation:RecoveryMutation){if(!owner||pending()||state.strokeActive||state.ending||state.awaitingConfirmation)return;schedule(mutation,true);},
    gestureCancelled(message:string){if(pending())return;latest=null;shown=null;++serial;publish({strokeActive:false,ending:false,message});if(owner?.ticket)schedule({action:'view',target:state.target},false);},
    canContinue:()=>state.phase==='success'&&resumeReady&&continueDrawing&&context.enabled&&context.canStart!==false&&context.contextKey!==submittedContext,
    resume:()=>start(state.target,true),
    busy:pending,capturing:()=>!!owner,usesAliasHistory:()=>aliasWorkspace,externalEdit(){continueDrawing=false;resumeReady=false;if(owner&&!pending())cancel('照片正在调整，未提交笔迹已取消');},
    check:async()=>{if(state.request&&!querying&&['waiting','uncertain'].includes(state.phase))await query(state.request);},
    activate(){active=true;if(!stopWorkspaceRecovery)stopWorkspaceRecovery=subscribeRecoveryAliasWorkspace(workspaceReplaced);
      const previous=state.request?.workspace,current=recoveryAliasWorkspace();if(state.request?.protocol===2&&previous&&current&&previous!==current)workspaceReplaced({previous,current,retiredWrites:[]});},
    stop(){continueDrawing=false;const wasPending=pending();discard();active=false;querying=false;stopWorkspaceRecovery?.();stopWorkspaceRecovery=null;
      state=wasPending?{...state,phase:'uncertain',frame:null,message:'原操作等待中断，请查询结果；不会重发'}:initial();},
    acknowledgeAfterReload(){if(state.request?.protocol===2)return;if(active&&!querying&&state.phase==='uncertain'&&state.request&&context.enabled&&context.documentId!==state.request.document_id){discard();publish(initial());}},
  };
}
