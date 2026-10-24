// SPDX-License-Identifier: GPL-3.0-or-later
import {useEffect,useRef,useState,useSyncExternalStore} from 'react';
import {TorsoLengthController} from './controller';
import {TorsoLengthSupportEditor} from './TorsoLengthSupportEditor';
import {OPERATION_ID,REQUIREMENT_ID,ANCHORS,adjust,neutral,refKey,viewKey,type BodyRef,type TorsoLengthRecipe,type TorsoLengthView} from './model';
import type {SourceImage} from './sourcePreview';
import './torsoLength.css';
export function TorsoLengthPanel({view,controller,sourceImage,onSelect,onOpenBodyAnalysis,coreAvailable=false,disabled=false}:{view:TorsoLengthView;controller:TorsoLengthController;sourceImage:SourceImage|null;onSelect:(ref:BodyRef)=>void;onOpenBodyAnalysis:()=>void;coreAvailable?:boolean;disabled?:boolean}){
 useEffect(()=>controller.update(view),[view,controller]);
 const state=useSyncExternalStore(controller.subscribe,controller.snapshot,controller.snapshot);
 const current=!!state.view&&viewKey(state.view)===viewKey(view)&&state.view.state_revision>=view.state_revision;
 const shown=current&&state.view?state.view:view,recipe=current?state.recipe:view.recipe,body=shown.bodies.find(b=>refKey(b.body_ref)===refKey(shown.selected_body_ref));
 const busy=disabled||state.phase!=='idle'||!current,canReset=!disabled&&current&&!!body&&state.phase!=='uncertain';
 const canEdit=canReset&&coreAvailable&&!!body?.enabled&&body.operation_enabled&&body.reviewed;
 const [error,setError]=useState(''),gesture=useRef<string|null>(null);
 useEffect(()=>{setError('');gesture.current=null;},[shown.binding.document_epoch,shown.binding.document_id,refKey(shown.selected_body_ref)]);
 function edit(change:(recipe:TorsoLengthRecipe)=>TorsoLengthRecipe,id=gesture.current??crypto.randomUUID()){try{controller.edit(change,id);setError('');}catch(e){setError(e instanceof Error?e.message:'调整未发送。');}}
 async function action(fn:()=>Promise<void>){try{await fn();setError('');}catch(e){setError(e instanceof Error?e.message:'操作未完成。');}}
 return <section className="torso-length-panel" aria-label="上身长度手动辅助 2D 调整" data-operation={OPERATION_ID} data-requirement-id={REQUIREMENT_ID}>
  <h3>上身长度 · 手动辅助 2D</h3>
  <p>仅支持近直立、近正面且完整可见的上身。髋部固定，肩髋之间纵向缩短或拉长；完整头部随上方区域移动，手臂沿同一连续形变衔接。不是腰部长度，不做 3D 重建或隐藏身体推测。</p>
  <button type="button" disabled={busy} onClick={onOpenBodyAnalysis}>打开真实身体定位与人物关联</button>
  {!shown.bodies.length&&<p role="status">尚无真实身体定位，不会用人脸框生成肩髋或完整头臂轮廓。</p>}
  <div className="torso-length-body-choices">{shown.bodies.map((b,i)=><button type="button" key={refKey(b.body_ref)} disabled={busy} aria-pressed={refKey(b.body_ref)===refKey(shown.selected_body_ref)} onClick={()=>onSelect(b.body_ref)}>身体 {i+1}{b.reviewed?' · 上身已复核':' · 上身待复核'}{!b.enabled?' · 已停用':''}</button>)}</div>
  {body&&<><TorsoLengthSupportEditor key={`${refKey(body.body_ref)}:${body.points_sha256}`} body={body} image={sourceImage} reviewIdentity={`${shown.body_graph_sha256}:${shown.people_graph_sha256}:${shown.association_revision}:${shown.people_association_revision}`} disabled={busy||!body.enabled||!coreAvailable} onReview={data=>action(()=>controller.action('support_review',{data,points_sha256:body.points_sha256,visible_anchors:[...ANCHORS],ownership_confirmed:true}))}/>
   {!body.reviewed&&<p role="status">需单独复核肩髋、完整头发与双臂及上下文背景；其他身体工具的复核不能授权此项。</p>}
   {(body.support||body.operation_enabled)&&<button type="button" disabled={busy||!body.operation_enabled&&!coreAvailable} onClick={()=>void action(()=>controller.action('operation_status',{enabled:!body.operation_enabled}))}>{body.operation_enabled?'停用上身长度，保留参数':'启用已复核的上身长度'}</button>}
  </>}
  <div className="torso-length-slider" data-control-id="PC-32473-C-f1662d2dec" data-requirement-id={REQUIREMENT_ID}><label>上身长度 <output>{Math.round(recipe.amount*100)}</output><input type="range" min={-100} max={100} step={1} value={Math.round(recipe.amount*100)} disabled={!canEdit} aria-label="上身长度" aria-valuetext={`${Math.round(recipe.amount*100)}，负值缩短，零保持原始，正值拉长`} onPointerDown={()=>{gesture.current=crypto.randomUUID();}} onPointerUp={()=>{gesture.current=null;}} onPointerCancel={()=>{gesture.current=null;}} onBlur={()=>{gesture.current=null;}} onChange={e=>{const amount=Number(e.currentTarget.value)/100;edit(r=>adjust(r,amount));}}/></label><span>向左缩短 ← 原始 0 → 向右拉长</span></div>
  <button type="button" disabled={!canReset} onClick={()=>edit(()=>neutral(),crypto.randomUUID())}>重置上身长度为 0</button>
  {state.phase==='working'&&<p role="status">正在应用；未发送的拖动只保留最新值。</p>}
  {state.phase==='uncertain'&&<button type="button" onClick={()=>void controller.reconcile()}>查询本次结果，不重发调整</button>}
  {[error,state.message,...shown.refusals.map(r=>r.reason)].filter(Boolean).map((message,i)=><p role="status" key={i}>{message}</p>)}
  <p className="torso-length-policy">这是局部、手动辅助的 2D 实现，不是自动 AI 塑形。-100 到 100、零默认和保守支撑阈值均为本产品原创策略，并非官方披露参数。不改写原文件；支撑范围内背景和衣纹可能移动。自然度及实机验收未运行。</p>
 </section>;
}
