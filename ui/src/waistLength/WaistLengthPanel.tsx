// SPDX-License-Identifier: GPL-3.0-or-later
import {useEffect,useRef,useState,useSyncExternalStore} from 'react';
import {WaistLengthController} from './controller';
import {WaistLengthSupportEditor} from './WaistLengthSupportEditor';
import {OPERATION_ID,REQUIREMENT_ID,ANCHORS,adjust,neutral,refKey,viewKey,type BodyRef,type WaistLengthRecipe,type WaistLengthView} from './model';
import type {SourceImage} from './sourcePreview';
import './waistLength.css';
export function WaistLengthPanel({view,controller,sourceImage,onSelect,onOpenBodyAnalysis,coreAvailable=false,disabled=false}:{view:WaistLengthView;controller:WaistLengthController;sourceImage:SourceImage|null;onSelect:(ref:BodyRef)=>void;onOpenBodyAnalysis:()=>void;coreAvailable?:boolean;disabled?:boolean}){
 useEffect(()=>controller.update(view),[view,controller]);
 const state=useSyncExternalStore(controller.subscribe,controller.snapshot,controller.snapshot);
 const current=!!state.view&&viewKey(state.view)===viewKey(view)&&state.view.state_revision>=view.state_revision;
 const shown=current&&state.view?state.view:view,recipe=current?state.recipe:view.recipe,body=shown.bodies.find(b=>refKey(b.body_ref)===refKey(shown.selected_body_ref));
 const busy=disabled||state.phase!=='idle'||!current,canReset=!disabled&&current&&!!body&&state.phase!=='uncertain';
 const canEdit=canReset&&coreAvailable&&!!body?.enabled&&body.operation_enabled&&body.reviewed;
 const [error,setError]=useState(''),gesture=useRef<string|null>(null);
 useEffect(()=>{setError('');gesture.current=null;},[shown.binding.document_epoch,shown.binding.document_id,refKey(shown.selected_body_ref)]);
 function edit(change:(recipe:WaistLengthRecipe)=>WaistLengthRecipe,id=gesture.current??crypto.randomUUID()){try{controller.edit(change,id);setError('');}catch(e){setError(e instanceof Error?e.message:'调整未发送。');}}
 async function action(fn:()=>Promise<void>){try{await fn();setError('');}catch(e){setError(e instanceof Error?e.message:'操作未完成。');}}
 return <section className="waist-length-panel" aria-label="腰部长度手动辅助 2D 调整" data-operation={OPERATION_ID} data-requirement-id={REQUIREMENT_ID}>
  <h3>腰部长度 · 手动辅助 2D</h3>
  {!coreAvailable&&<p role="status">原生形变核心未就绪。可保存当前来源图独立复核、查询、停用或归零；保存成功不代表效果已应用，非零调整及启用仍不可用。</p>}
  {shown.publication?.rendered===false&&<p role="status">当前已保存的参数或复核尚未应用：{shown.publication.unapplied_reason??'实际发布状态仍需核对。'}</p>}
  <p>局部手动辅助 2D：分别标出左右上腰、下腰端点，缩短或拉长标记腰段；下腰线以下固定，上方完整上躯干、肩颈和头部一起平移。跨过腰段的手臂局部随连续场衔接，不是整条手臂刚性平移。不是上身长度、瘦腰或全身 AI 塑形。</p>
  <button type="button" disabled={busy} onClick={onOpenBodyAnalysis}>打开真实身体定位与人物关联</button>
  {!shown.bodies.length&&<p role="status">尚无真实身体定位，不会用人脸框、肩髋或固定比例生成腰点。</p>}
  <div className="waist-length-body-choices">{shown.bodies.map((b,i)=><button type="button" key={refKey(b.body_ref)} disabled={busy} aria-pressed={refKey(b.body_ref)===refKey(shown.selected_body_ref)} onClick={()=>onSelect(b.body_ref)}>身体 {i+1}{b.reviewed?' · 腰长已复核':' · 腰长待复核'}{!b.enabled?' · 已停用':''}</button>)}</div>
  {body&&<><WaistLengthSupportEditor key={`${refKey(body.body_ref)}:${body.points_sha256}`} body={body} image={sourceImage} reviewIdentity={`${shown.body_graph_sha256}:${shown.people_graph_sha256}:${shown.association_revision}:${shown.people_association_revision}`} disabled={busy||!body.enabled} onReview={data=>action(()=>controller.action('support_review',{data,points_sha256:body.points_sha256,visible_anchors:[...ANCHORS],ownership_confirmed:true}))}/>
   {!body.reviewed&&<p role="status">需独立测量四个可见腰点并复核完整上躯干、头发、双臂及背景；瘦腰或上身长度的复核不能授权此项。</p>}
   {(body.support||body.operation_enabled)&&<button type="button" disabled={busy||!body.operation_enabled&&!coreAvailable} onClick={()=>void action(()=>controller.action('operation_status',{enabled:!body.operation_enabled}))}>{body.operation_enabled?'停用腰部长度，保留参数':'启用已复核的腰部长度'}</button>}
  </>}
  <div className="waist-length-slider" data-control-id="PC-32473-C-5d33f285bb" data-requirement-id={REQUIREMENT_ID}><label>腰部长度 <output>{Math.round(recipe.amount*100)}</output><input type="range" min={-100} max={100} step={1} value={Math.round(recipe.amount*100)} disabled={!canEdit} aria-label="腰部长度" aria-valuetext={`${Math.round(recipe.amount*100)}，负值缩短，零保持原始，正值拉长`} onPointerDown={()=>{gesture.current=crypto.randomUUID();}} onPointerUp={()=>{gesture.current=null;}} onPointerCancel={()=>{gesture.current=null;}} onBlur={()=>{gesture.current=null;}} onChange={e=>{const amount=Number(e.currentTarget.value)/100;edit(r=>adjust(r,amount));}}/></label><span>向左缩短 ← 原始 0 → 向右拉长</span></div>
  <button type="button" disabled={!canReset} onClick={()=>edit(()=>neutral(),crypto.randomUUID())}>重置腰部长度为 0</button>
  {state.phase==='working'&&<p role="status">正在应用；未发送的拖动只保留最新值。</p>}
  {state.phase==='uncertain'&&<button type="button" onClick={()=>void controller.reconcile()}>查询本次结果，不重发调整</button>}
  {[error,state.message,...shown.refusals.map(r=>r.reason)].filter(Boolean).map((message,i)=><p role="status" key={i}>{message}</p>)}
  <p className="waist-length-policy">这是局部、手动辅助的 2D 源码实现，不是自动 AI 塑形。-100 到 100、零默认和保守支撑阈值均为本产品原创策略，并非官方披露参数。不改写原文件；支撑范围内背景和衣纹可能移动。预设、同步、批量不借用当前照片的审核。自然度及实机验收未运行。</p>
 </section>;
}
