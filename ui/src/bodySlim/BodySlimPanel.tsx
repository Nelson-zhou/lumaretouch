// SPDX-License-Identifier: GPL-3.0-or-later
import {useEffect,useRef,useState,useSyncExternalStore} from 'react';
import {BodySlimController} from './controller';
import {BodySlimSupportEditor} from './BodySlimSupportEditor';
import {OPERATION_ID,REQUIREMENT_ID,ANCHORS,adjust,neutral,refKey,viewKey,type BodyRef,type BodySlimRecipe,type BodySlimView} from './model';
import type {SourceImage} from './sourcePreview';
import './bodySlim.css';
export function BodySlimPanel({view,controller,sourceImage,onSelect,onOpenBodyAnalysis,coreAvailable=false,disabled=false}:{view:BodySlimView;controller:BodySlimController;sourceImage:SourceImage|null;onSelect:(ref:BodyRef)=>void;onOpenBodyAnalysis:()=>void;coreAvailable?:boolean;disabled?:boolean}){
 useEffect(()=>controller.update(view),[view,controller]);
 const state=useSyncExternalStore(controller.subscribe,controller.snapshot,controller.snapshot);
 const current=!!state.view&&viewKey(state.view)===viewKey(view)&&state.view.state_revision>=view.state_revision;
 const shown=current&&state.view?state.view:view,recipe=current?state.recipe:view.recipe,body=shown.bodies.find(b=>refKey(b.body_ref)===refKey(shown.selected_body_ref));
 const busy=disabled||state.phase!=='idle'||!current,canReset=!disabled&&current&&!!body&&state.phase!=='uncertain';
 const canEdit=canReset&&coreAvailable&&!!body?.enabled&&body.operation_enabled&&body.reviewed;
 const [error,setError]=useState(''),gesture=useRef<string|null>(null);
 useEffect(()=>{setError('');gesture.current=null;},[shown.binding.document_epoch,shown.binding.document_id,refKey(shown.selected_body_ref)]);
 function edit(change:(recipe:BodySlimRecipe)=>BodySlimRecipe,id=gesture.current??crypto.randomUUID()){try{controller.edit(change,id);setError('');}catch(e){setError(e instanceof Error?e.message:'调整未发送。');}}
 async function action(fn:()=>Promise<void>){try{await fn();setError('');}catch(e){setError(e instanceof Error?e.message:'操作未完成。');}}
 return <section className="body-slim-panel" aria-label="全身瘦身手动辅助 2D 调整" data-operation={OPERATION_ID} data-requirement-id={REQUIREMENT_ID}>
  <h3>全身瘦身 · 手动辅助 2D</h3>
  <p>仅支持近直立、完整可见的单人照片。根据手工实测完整轮廓，统一横向收窄或变宽头发、身体、双臂、双腿和脚；高度不变。不是腰或腿滑杆的组合，不推测隐藏身体。</p>
  <button type="button" disabled={busy} onClick={onOpenBodyAnalysis}>打开真实身体定位与人物关联</button>
  {!shown.bodies.length&&<p role="status">尚无真实身体定位，不会用人脸或关节框猜测全身轮廓。</p>}
  <div className="body-slim-body-choices">{shown.bodies.map((b,i)=><button type="button" key={refKey(b.body_ref)} disabled={busy} aria-pressed={refKey(b.body_ref)===refKey(shown.selected_body_ref)} onClick={()=>onSelect(b.body_ref)}>身体 {i+1}{b.reviewed?' · 全身已复核':' · 全身待复核'}{!b.enabled?' · 已停用':''}</button>)}</div>
  {body&&<><BodySlimSupportEditor key={`${refKey(body.body_ref)}:${body.points_sha256}`} body={body} image={sourceImage} reviewIdentity={`${shown.body_graph_sha256}:${shown.people_graph_sha256}:${shown.association_revision}:${shown.people_association_revision}`} disabled={busy||!body.enabled||!coreAvailable} onReview={data=>action(()=>controller.action('support_review',{data,points_sha256:body.points_sha256,visible_anchors:[...ANCHORS],ownership_confirmed:true}))}/>
   {!body.reviewed&&<p role="status">需手工独立描绘完整人物真实轮廓、明确背景过渡及单人归属；其他工具的复核不能授权此项。</p>}
   {(body.support||body.operation_enabled)&&<button type="button" disabled={busy||!body.operation_enabled&&!coreAvailable} onClick={()=>void action(()=>controller.action('operation_status',{enabled:!body.operation_enabled}))}>{body.operation_enabled?'停用全身瘦身，保留参数':'启用已复核的全身瘦身'}</button>}
  </>}
  <div className="body-slim-slider" data-control-id="PC-32473-C-bc54b9eb3c" data-requirement-id={REQUIREMENT_ID}><label>全身瘦身 <output>{Math.round(recipe.amount*100)}</output><input type="range" min={-100} max={100} step={1} value={Math.round(recipe.amount*100)} disabled={!canEdit} aria-label="全身瘦身" aria-valuetext={`${Math.round(recipe.amount*100)}，负值变宽，零保持原始，正值变窄`} onPointerDown={()=>{gesture.current=crypto.randomUUID();}} onPointerUp={()=>{gesture.current=null;}} onPointerCancel={()=>{gesture.current=null;}} onBlur={()=>{gesture.current=null;}} onChange={e=>{const amount=Number(e.currentTarget.value)/100;edit(r=>adjust(r,amount));}}/></label><span>向左变宽 ← 原始 0 → 向右变窄</span></div>
  <button type="button" disabled={!canReset} onClick={()=>edit(()=>neutral(),crypto.randomUUID())}>重置全身瘦身为 0</button>
  {state.phase==='working'&&<p role="status">正在应用；未发送的拖动只保留最新值。</p>}
  {state.phase==='uncertain'&&<button type="button" onClick={()=>void controller.reconcile()}>查询本次结果，不重发调整</button>}
  {[error,state.message,...shown.refusals.map(r=>r.reason)].filter(Boolean).map((message,i)=><p role="status" key={i}>{message}</p>)}
  <p className="body-slim-policy">这是全身横向、手动辅助的 2D 实现，不是自动 AI 塑形。-100 到 100、零默认和保守支撑阈值均为本产品原创策略，并非官方披露参数。不改写原文件；明确支撑内背景过渡、肢体间空隙和衣纹可能移动；支撑外固定。自然度及实机验收未运行。</p>
 </section>;
}
