// SPDX-License-Identifier: GPL-3.0-or-later
import {useLayoutEffect,useRef,useState} from 'react';
import type {PeopleOwner} from '../people/usePeopleWorkflow';
import type {PeopleAction} from '../people/model';
import type {SpillImage} from '../spillRemoval/model';
import {PATTERNS,bindingKey,canonical,command,type Recipe} from './model';
import {DecorationTransferReview} from './TransferReview';
import {aliasAck,aliasReceiptCurrent,decorationAliasImage,decorationAliasKey,validAliasReview,verifyDecorationAliasReview,type DecorationAliasReview} from './aliasModel';
/** A draft is not a graph patch. Publish only the complete immutable affected set. */
export function FaceDecorationAliasEditor({people,recipe,disabled}:{people:PeopleOwner;recipe:Recipe;disabled:boolean}){
 const view=people.value,binding=bindingKey(view),report=view?.face_decoration;
 const [draft,setDraft]=useState(recipe),[review,setReview]=useState<DecorationAliasReview|null>(null),[ready,setReady]=useState<Record<string,boolean>>({}),[error,setError]=useState('');
 const mounted=useRef(false),generation=useRef(0),busy=useRef(false);
 const pendingImage=useRef<{id:string;resolve:(image:SpillImage)=>void;reject:(error:Error)=>void;timer:ReturnType<typeof setTimeout>;review:DecorationAliasReview;document:string;side:'before'|'after';live:()=>boolean}|null>(null);
 const latest=useRef({view,binding,disabled,review,draft});latest.current={view,binding,disabled,review,draft};
 useLayoutEffect(()=>{mounted.current=true;return()=>{mounted.current=false;generation.current++;const p=pendingImage.current;if(p){clearTimeout(p.timer);p.reject(Error('审核界面已关闭；已发送请求仍由原队列确认'));pendingImage.current=null;}};},[]);
 useLayoutEffect(()=>{generation.current++;setDraft(recipe);setReview(null);setReady({});setError('');const p=pendingImage.current;if(p){clearTimeout(p.timer);p.reject(Error('来源或人物状态已变化'));pendingImage.current=null;}},[binding]);
 useLayoutEffect(()=>{
  const receipt=people.state.lastDecorationAliasResult;if(!receipt)return;
  const {command:request,result}=receipt;
  if(!aliasReceiptCurrent(request,result,latest.current.view))return;
  if(request.action==='face_decoration_alias_preview'){
   const payload=result.payload as {review?:unknown;kind?:unknown}|undefined;
   if(payload?.kind!=='face_decoration_alias_preview'||!validAliasReview(payload.review,latest.current.view,latest.current.draft))return;
   const candidate=payload.review,sequence=++generation.current;
   void verifyDecorationAliasReview(candidate).then(valid=>{if(!mounted.current||sequence!==generation.current)return;if(!valid){setError('完整审核摘要不一致，不能提交');return;}setReview(candidate);setReady({});}).catch(cause=>{if(mounted.current&&sequence===generation.current)setError(String(cause));});
  }
  if(request.action==='face_decoration_alias_image'){
   const p=pendingImage.current;if(!p||p.id!==request.request_id)return;
   clearTimeout(p.timer);pendingImage.current=null;
   void decorationAliasImage(result.payload,p.review,p.document,p.side).then(image=>{if(!mounted.current||!p.live()||latest.current.review!==p.review)p.reject(Error('图像审核已失效'));else p.resolve(image);},cause=>p.reject(Error(String(cause))));
  }
 },[people.state.lastDecorationAliasResult]);
 const canEdit=!disabled&&!people.state.pending&&!people.state.uncertain&&!!view&&view.editing_target?.scope==='face'&&view.editing_target.target_id===view.selected_face_id&&!report?.alias_reason;
 function change(value:Recipe){if(!canEdit)return;generation.current++;setDraft(value);setReview(null);setReady({});setError('');}
 async function preview(){
  if(!canEdit||busy.current||!view)return;busy.current=true;setReview(null);setReady({});setError('');
  try{await people.submitCaptured(command(view,'face_decoration_alias_preview',crypto.randomUUID(),{recipe:structuredClone(draft)}));}catch(cause){if(mounted.current)setError(String(cause));}finally{busy.current=false;}
 }
 function readImage(member:DecorationAliasReview['members'][number],side:'before'|'after',live:()=>boolean):Promise<SpillImage>{
  if(!review||!view||latest.current.review!==review||latest.current.binding!==binding||pendingImage.current||people.state.pending||people.state.uncertain)return Promise.reject(Error('上一请求尚未确认或审核已失效，请查询原请求。'));
  const request:PeopleAction=command(view,'face_decoration_alias_image',crypto.randomUUID(),{token:review.token,document_id:member.visual.document_id,side,sha256:member.visual[side].sha256});
  return new Promise((resolve,reject)=>{
   const timer=setTimeout(()=>{if(pendingImage.current?.id===request.request_id){pendingImage.current=null;reject(Error('图像读取等待超时；请先查询原请求，不能重发未知请求。'));}},130000);
   pendingImage.current={id:request.request_id,resolve,reject,timer,review,document:member.visual.document_id,side,live};
   void people.submitCaptured(request).catch(cause=>{if(pendingImage.current?.id===request.request_id){clearTimeout(timer);pendingImage.current=null;reject(Error(String(cause)));}});
  });
 }
 const allReady=!!review&&review.members.every(m=>ready[decorationAliasKey(review,m.visual)]===true);
 async function confirm(){
  if(!canEdit||!allReady||!review||!view||busy.current||!validAliasReview(review,view,draft))return;busy.current=true;setError('');
  try{if(!await verifyDecorationAliasReview(review)||latest.current.review!==review||latest.current.binding!==binding)throw Error('审核已变化，请重新预览');await people.submitCaptured(command(view,'face_decoration_alias_confirm',crypto.randomUUID(),{token:review.token,ack:aliasAck(review)}));}catch(cause){if(mounted.current)setError(String(cause));}finally{busy.current=false;}
 }
 return <section aria-label="共享来源脸部装饰逐照片审核">
  <h4>共享来源：必须审核全部受影响照片后一起应用</h4>
  <p>这里只起草当前人物的图案和程度，不立即改变任何照片。每个成员保留自己的裁切、色彩、修复和其他效果；不复制可见皮肤笔迹。初次或重新绘制范围请使用下方独立的范围事务，不能借用本通道提交。</p>
  <label>候选图案 <select disabled={!canEdit} value={draft.pattern} onChange={e=>change({...draft,pattern:e.target.value as Recipe['pattern']})}>{PATTERNS.map(p=><option key={p.id} value={p.id}>{p.label}</option>)}</select></label>
  <label>候选程度 {Math.round(draft.strength*100)} / 100 <input type="range" min={0} max={100} step={1} disabled={!canEdit} value={Math.round(draft.strength*100)} onChange={e=>change({...draft,strength:Number(e.target.value)/100})}/></label>
  <button type="button" disabled={!canEdit} onClick={()=>change({...draft,strength:0})}>起草归零（仍须审核全部照片）</button>
  <button type="button" disabled={!canEdit||canonical(draft)===canonical(recipe)} onClick={()=>void preview()}>生成全部受影响照片的完整前后审核</button>
  {view?.editing_target?.scope!=='face'&&<p role="status">请先切换到当前人物独立范围；共享来源别名通道不修改分组、跨人或全体默认值。</p>}
  {report?.alias_reason&&<p role="status">{report.alias_reason}</p>}
  {review&&<><p>本次共 {review.members.length} 张。未打开、不可用或依赖不完整的成员不会被忽略；需要重新预检。显示图不是全分辨率验收。</p>{review.members.map((m,index)=><section key={m.visual.document_id}>
   <strong>{index===0?'当前照片':'共享来源成员'}：{m.path}</strong>
   <DecorationTransferReview value={m.visual} coverage={m.coverage} token={review.token} reviewKey={decorationAliasKey(review,m.visual)} disabled={!canEdit} readImage={(side,live)=>readImage(m,side,live)} onReady={(key,value)=>setReady(old=>old[key]===value?old:{...old,[key]:value})}/>
  </section>)}<button type="button" disabled={!canEdit||!allReady} onClick={()=>void confirm()}>确认全部图像并原子应用</button></>}
  {error&&<p role="alert">{error}</p>}
 </section>;
}
