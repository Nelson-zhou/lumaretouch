import {useEffect,useRef,useState} from 'react';
import {invoke} from '@tauri-apps/api/core';
import {INSPECTION_EDIT_INTENT,notifyInspectionEditIntent} from '../native';
import {settleCurveEdit} from '../curveEditBarrier';
import {spillApplyFields,spillNotSent,spillRequestFits,validSpillPaintSource,validSpillReview,type SpillFence,type SpillReview} from '../spillRemoval/model';
import {originalShadowApplyFields,originalShadowNotSent,originalShadowRequestFits,validOriginalShadowPreviewFields,validOriginalShadowReview,validOriginalShadowPaintSource,type OriginalShadowReview} from '../originalShadow/model';
import type {Reply,Report} from './model';
const pause=()=>new Promise<void>(resolve=>setTimeout(resolve,100));
type Kind='read'|'source'|'preview'|'mutation';
type Pending={id:string;document:string;kind:Kind;action:string;fence:SpillFence|null;reviewEpoch:number;shadowReviewEpoch:number;sourceEpoch:number};
const shadowAction=(action:string)=>action==='id_original_shadow_preview'||action==='id_original_shadow_apply'||action==='id_original_shadow_paint_source';
const spillAction=(action:string)=>action==='id_spill_preview'||action==='id_spill_apply'||action==='id_spill_paint_source';

export function useIdBackground(documentId:string,hostRevision:number,available:boolean,onChanged?:()=>void){
 const [report,setReport]=useState<Report|null>(null),[message,setMessage]=useState(''),[busy,setBusy]=useState(false),[uncertain,setUncertainState]=useState(false);
 const [spillReview,setSpillReview]=useState<SpillReview|null>(null),[shadowReview,setShadowReview]=useState<OriginalShadowReview|null>(null);
 const current=useRef(documentId);current.current=documentId;const reportRef=useRef(report);reportRef.current=report;
 const generation=useRef(0),flight=useRef(false),pending=useRef<Pending|null>(null),changed=useRef(onChanged);changed.current=onChanged;
 const reviewRef=useRef<SpillReview|null>(null),reviewEpoch=useRef(0),shadowReviewRef=useRef<OriginalShadowReview|null>(null),shadowReviewEpoch=useRef(0);
 const sourceEpoch=useRef(0),usedTokens=useRef(new Set<string>());
 const uncertainRef=useRef(false);
 function setUncertain(value:boolean){uncertainRef.current=value;setUncertainState(value);}
 function clearSpillReview(){reviewEpoch.current++;reviewRef.current=null;setSpillReview(null);}
 function clearShadowReview(){shadowReviewEpoch.current++;shadowReviewRef.current=null;setShadowReview(null);}
 function clearReviews(){clearSpillReview();clearShadowReview();}
 function clearPaintSource(){sourceEpoch.current++;const saved=reportRef.current;if(saved?.paint_source||saved?.shadow_paint_source){const {paint_source:_,shadow_paint_source:_shadow,...rest}=saved;reportRef.current=rest;setReport(rest);}}
 async function receipt(id:string):Promise<Reply|null>{
  const status=await invoke<{phase:string;result:Reply|null}>('id_background_status',{requestId:id});
  if(status.phase==='unknown')throw Error('原请求回执不可用。不会自动重发修改；请查询原操作核对。');
  return status.phase==='done'?status.result:null;
 }
 function accept(reply:Reply,p:Pending,token:number){
  if(current.current!==p.document||generation.current!==token)return;
  if(reply.event!=='id_background_result'||reply.request_id!==p.id||reply.document_id!==p.document||typeof reply.success!=='boolean')throw Error('回执身份或结果无效');
  const original=shadowAction(p.action),spill=spillAction(p.action),label=original?'原图阴影':'祛染';
  if((spill||original)&&(reply.protocol!==1||reply.action!==p.action))throw Error(`${label}回执协议或操作不匹配`);
  if(original&&(typeof reply.outcome_unknown!=='boolean'||typeof reply.requires_reload!=='boolean'))throw Error('原图阴影回执缺少明确结果状态');
  if(reply.outcome_unknown||reply.requires_reload){
   clearReviews();clearPaintSource();
   if(p.kind==='mutation'){setUncertain(true);setMessage('背景回滚结果未确认，已暂停编辑。请保存可恢复记录并重新打开应用核对，不要重复应用。');}
   else{pending.current=null;setMessage('只读审核未完成，未提交照片修改。请重新读取状态并生成新的审核。');}
   return;
  }
  if(p.kind==='source'&&reply.success){
   if(!p.fence||!(original?validOriginalShadowPaintSource(reply.shadow_paint_source,p.fence):validSpillPaintSource(reply.paint_source,p.fence))||!reply.report||reply.report.recipe_document_id!==p.fence.recipe_document_id||reply.report.recipe_revision!==p.fence.recipe_revision)throw Error('源图画笔回执缺少与当前配方相符的完整来源');
   if(p.sourceEpoch!==sourceEpoch.current||original&&p.shadowReviewEpoch!==shadowReviewEpoch.current||reportRef.current?.recipe_document_id!==p.fence.recipe_document_id||reportRef.current?.recipe_revision!==p.fence.recipe_revision){pending.current=null;setMessage('读取期间照片或编辑状态已变化，请重新读取源图。');return;}
  }
  if(p.kind==='preview'&&reply.success){
   if(!p.fence||!reply.report||reply.report.recipe_document_id!==p.fence.recipe_document_id||reply.report.recipe_revision!==p.fence.recipe_revision)throw Error(`${label}预览缺少当前配方版本`);
   const sameFence=reportRef.current?.recipe_document_id===p.fence.recipe_document_id&&reportRef.current?.recipe_revision===p.fence.recipe_revision;
   if(original){
    if(!validOriginalShadowReview(reply.shadow_review,p.fence))throw Error('原图阴影预览缺少独立、有效的冻结前后图像');
    if(p.shadowReviewEpoch!==shadowReviewEpoch.current||!sameFence){pending.current=null;setMessage('预览期间照片、蒙版或原图阴影草稿已变化，请重新生成审核。');return;}
    shadowReviewRef.current=reply.shadow_review;setShadowReview(reply.shadow_review);
   }else{
    if(!validSpillReview(reply.review,p.fence))throw Error('祛染预览缺少与当前配方相符的冻结图像');
    if(p.reviewEpoch!==reviewEpoch.current||!sameFence){pending.current=null;setMessage('预览期间照片或编辑状态已变化，请重新生成祛染审核。');return;}
    reviewRef.current=reply.review;setSpillReview(reply.review);
   }
  }
  if(reply.report){
   if(reviewRef.current&&(reviewRef.current.recipe_document_id!==reply.report.recipe_document_id||reviewRef.current.recipe_revision!==reply.report.recipe_revision))clearSpillReview();
   if(shadowReviewRef.current&&(shadowReviewRef.current.recipe_document_id!==reply.report.recipe_document_id||shadowReviewRef.current.recipe_revision!==reply.report.recipe_revision))clearShadowReview();
   const priorSource=reportRef.current?.paint_source;
   const paint_source=p.kind==='source'&&!original&&reply.success?reply.paint_source:priorSource&&priorSource.recipe_document_id===reply.report.recipe_document_id&&priorSource.recipe_revision===reply.report.recipe_revision?priorSource:undefined;
   // Transient pixel receipts never enter the durable recipe or gain trust via a nested report.
   const {paint_source:_untrusted,shadow_paint_source:_untrustedShadow,...received}=reply.report;
   const priorShadowSource=reportRef.current?.shadow_paint_source;
   const shadow_paint_source=p.kind==='source'&&original&&reply.success?reply.shadow_paint_source:priorShadowSource&&priorShadowSource.recipe_document_id===reply.report.recipe_document_id&&priorShadowSource.recipe_revision===reply.report.recipe_revision?priorShadowSource:undefined;
   const reportFence={recipe_document_id:reply.report.recipe_document_id,recipe_revision:reply.report.recipe_revision};
   const next:Report={...received,...(paint_source&&validSpillPaintSource(paint_source,reportFence)?{paint_source}:{}),...(shadow_paint_source&&validOriginalShadowPaintSource(shadow_paint_source,reportFence)?{shadow_paint_source}:{})};
   reportRef.current=next;setReport(next);
  }
  setMessage(reply.success?(p.kind==='preview'?`${label}候选已生成，请审核真实前后图像。`:p.kind==='source'?`已读取不可变源图，核验完成后可绘制${label}范围草稿。`:p.action==='id_original_shadow_apply'?'原图阴影修改已确认。':p.action==='id_spill_apply'?'祛染修改已确认。':'已确认当前背景状态。'):(reply.error||'证件照背景未应用'));
  setUncertain(false);pending.current=null;if(p.kind==='mutation'&&reply.success)changed.current?.();
 }
 async function request(action:string,fields:Record<string,unknown>={},read=false,frozenCaller?:{document_id:string;recipe_document_id:string;recipe_revision:string}){
  const kind:Kind=action==='id_spill_paint_source'||action==='id_original_shadow_paint_source'?'source':action==='id_spill_preview'||action==='id_original_shadow_preview'?'preview':read?'read':'mutation';
  if(flight.current||!available||(kind!=='read'&&uncertainRef.current))return;
  // An unresolved mutation must be reconciled by its original ID, never replaced with a new read.
  if(kind==='read'&&uncertainRef.current){
   if(pending.current?.kind==='mutation')await query();
   else setMessage('未确认的修改缺少可查询回执，请重新打开照片核对，不会发送新的编辑。');
   return;
  }
  const doc=current.current,token=generation.current,id=crypto.randomUUID(),original=shadowAction(action);
  const frozenReview=reviewRef.current,reviewAtStart=reviewEpoch.current,frozenShadow=shadowReviewRef.current,shadowAtStart=shadowReviewEpoch.current;
  if(action==='id_spill_apply'&&(!frozenReview||usedTokens.current.has(frozenReview.token)||Object.entries(spillApplyFields(frozenReview)).some(([key,value])=>fields[key]!==value))){setMessage('请先重新生成并审核当前祛染候选。');return;}
  if(action==='id_original_shadow_apply'&&(!frozenShadow||usedTokens.current.has(frozenShadow.token)||Object.entries(originalShadowApplyFields(frozenShadow)).some(([key,value])=>fields[key]!==value))){setMessage('请先重新生成并审核当前原图阴影候选。');return;}
  if(action==='id_original_shadow_preview'&&!validOriginalShadowPreviewFields(fields)){setMessage('请分别审核原图阴影的两组选区与均匀地面条件。');return;}
  flight.current=true;setBusy(true);setMessage(kind==='read'?'正在读取背景状态…':kind==='source'?`正在读取当前完整源图与${original?'原图阴影':'祛染'}范围…`:kind==='preview'?`正在生成真实${original?'原图阴影':'祛染'}前后审核…`:'正在处理背景…');
  try{
   if(kind!=='read'){await settleCurveEdit();if(doc!==current.current||token!==generation.current)return;}
   if(kind==='preview'&&(original?shadowAtStart!==shadowReviewEpoch.current:reviewAtStart!==reviewEpoch.current)){
    setMessage('准备预览时编辑或草稿已变化，请检查当前参数后重新生成审核。');return;
   }
   const saved=reportRef.current,fence=saved?{recipe_document_id:saved.recipe_document_id,recipe_revision:saved.recipe_revision}:null;
   if(frozenCaller&&(frozenCaller.document_id!==doc||frozenCaller.recipe_document_id!==fence?.recipe_document_id||frozenCaller.recipe_revision!==fence?.recipe_revision)){setMessage('背景素材选择时的照片配方已变化，未发送修改。');return;}
   if(kind!=='read'&&(!fence?.recipe_document_id||typeof fence.recipe_revision!=='string')){setMessage('缺少当前配方版本，请重新读取状态');return;}
   if(action==='id_spill_apply'&&(!frozenReview||reviewAtStart!==reviewEpoch.current||reviewRef.current!==frozenReview||frozenReview.recipe_document_id!==fence?.recipe_document_id||frozenReview.recipe_revision!==fence?.recipe_revision)){
    clearSpillReview();setMessage('准备应用时照片配方已变化，请重新生成祛染审核。');return;
   }
   if(action==='id_original_shadow_apply'&&(!frozenShadow||shadowAtStart!==shadowReviewEpoch.current||shadowReviewRef.current!==frozenShadow||frozenShadow.recipe_document_id!==fence?.recipe_document_id||frozenShadow.recipe_revision!==fence?.recipe_revision)){
    clearShadowReview();setMessage('准备应用时照片配方或草稿已变化，请重新生成原图阴影审核。');return;
   }
   const payload={...fields,cmd:'background',action,request_id:id,document_id:doc,...(kind!=='read'?fence:{})};
   if(!(original?originalShadowRequestFits(payload):spillRequestFits(payload))){setMessage(fields.paint?'源图草稿超过 64 KiB 请求上限，未发送且未修改照片。请撤销部分笔画后重试。':'背景请求超过 64 KiB 请求上限，未发送且未修改照片。');return;}
   if(kind==='mutation'){
    if(action==='id_spill_apply')usedTokens.current.add(frozenReview!.token);
    if(action==='id_original_shadow_apply')usedTokens.current.add(frozenShadow!.token);
    clearReviews();clearPaintSource();notifyInspectionEditIntent();
   }else if(kind==='preview'){if(original)clearShadowReview();else clearSpillReview();}
   else if(kind==='source'){clearReviews();clearPaintSource();}
   const p:Pending={id,document:doc,kind,action,fence,reviewEpoch:reviewEpoch.current,shadowReviewEpoch:shadowReviewEpoch.current,sourceEpoch:sourceEpoch.current};pending.current=p;
   const admission=await invoke<unknown>('id_background_request',{request:payload}),expected={action,request_id:id,document_id:doc};
   const notSent=original?originalShadowNotSent(admission,expected):spillNotSent(admission,expected);
   if(notSent){
    if(doc===current.current&&token===generation.current){pending.current=null;setUncertain(false);if(original)clearShadowReview();else clearSpillReview();setMessage(`未发送，照片未修改：${(admission as {error:string}).error}`);}return;
   }
   const until=Date.now()+30000;
   while(Date.now()<until){const reply=await receipt(id);if(reply){accept(reply,p,token);return;}if(doc!==current.current||token!==generation.current)return;await pause();}
   throw Error(kind==='mutation'?'修改仍未确认，请查询原操作；不要重复应用。':'只读请求仍未完成，可查询原请求或稍后重新生成审核，尚未提交照片修改。');
  }catch(error){if(doc===current.current&&token===generation.current){
   if(kind!=='preview'||pending.current?.id!==id){if(original)clearShadowReview();else clearSpillReview();}setMessage(String(error));
   // Preview/source/read failures cannot turn a read-only request into an unknown edit.
   if(kind==='mutation'&&pending.current?.id===id)setUncertain(true);
  }}
  finally{flight.current=false;if(doc===current.current&&token===generation.current)setBusy(false);}
 }
 async function query(){
  const p=pending.current;if(!p||p.document!==current.current||flight.current)return;
  const token=generation.current;flight.current=true;setBusy(true);
  try{const r=await receipt(p.id);if(r)accept(r,p,token);else if(token===generation.current)setMessage('原操作仍在处理中。');}
  catch(error){if(token===generation.current){setMessage(String(error));if(p.kind==='mutation')setUncertain(true);}}
  finally{flight.current=false;if(token===generation.current)setBusy(false);}
 }
 useEffect(()=>{
  generation.current++;pending.current=null;reportRef.current=null;setReport(null);clearReviews();usedTokens.current.clear();setUncertain(false);setBusy(false);setMessage(available?'':'当前引擎未提供证件照背景服务。');
  let live=true;void(async()=>{while(flight.current&&live)await pause();if(live&&available)await request('id_state',{},true);})();return()=>{live=false;generation.current++;};
 },[documentId,available]);
 useEffect(()=>{clearReviews();clearPaintSource();if(available&&!flight.current&&!uncertain)void request('id_state',{},true);},[hostRevision]);
 useEffect(()=>{const edit=()=>{clearReviews();clearPaintSource();};window.addEventListener(INSPECTION_EDIT_INTENT,edit);return()=>window.removeEventListener(INSPECTION_EDIT_INTENT,edit);},[]);
 return {report,message,busy,uncertain,request,query,spillReview,shadowReview,clearSpillReview,clearShadowReview,clearReviews,read:()=>request('id_state',{},true)};
}
