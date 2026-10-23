// SPDX-License-Identifier: GPL-3.0-or-later
import {useEffect,useRef,useState,useSyncExternalStore} from 'react';
import {WaistController} from './controller';
import {WaistSupportEditor,type SourceImage} from './WaistSupportEditor';
import {REQUIREMENT_ID,ANCHORS,neutral,refKey,viewKey,type BodyRef,type WaistRecipe,type WaistView} from './model';
import '../legShape/legShape.css';
export function WaistShapePanel({view,controller,sourceImage,onSelect,onOpenBodyAnalysis,disabled=false}:{view:WaistView;controller:WaistController;sourceImage:SourceImage|null;onSelect:(ref:BodyRef)=>void;onOpenBodyAnalysis:()=>void;disabled?:boolean}){
 useEffect(()=>controller.update(view),[view,controller]);
 const state=useSyncExternalStore(controller.subscribe,controller.snapshot,controller.snapshot);
 const current=!!state.view&&viewKey(state.view)===viewKey(view)&&state.view.state_revision>=view.state_revision;
 const shown=current&&state.view?state.view:view,recipe=current?state.recipe:view.recipe,body=shown.bodies.find(b=>refKey(b.body_ref)===refKey(shown.selected_body_ref));
 const busy=disabled||state.phase!=='idle'||!current,canEdit=!disabled&&current&&!!body&&body.enabled&&body.operation_enabled&&body.reviewed&&state.phase!=='uncertain';
 const [error,setError]=useState(''),gesture=useRef<string|null>(null);
 useEffect(()=>{setError('');gesture.current=null;},[shown.binding.document_epoch,shown.binding.document_id,refKey(shown.selected_body_ref)]);
 function edit(change:(r:WaistRecipe)=>WaistRecipe,id:string=crypto.randomUUID()){try{controller.edit(change,id);setError('');}catch(e){setError(e instanceof Error?e.message:'调整未发送。');}}
 async function action(fn:()=>Promise<void>){try{await fn();setError('');}catch(e){setError(e instanceof Error?e.message:'操作未完成。');}}
 return <section className="leg-shape-panel" aria-label="瘦腰可见轮廓调整" data-operation="lnx.waist_shape.v1" data-requirement-id={REQUIREMENT_ID}>
  <h3>瘦腰 · 向内收紧可见轮廓</h3><p>独立复核双侧腰部及上下界。仅变形真实可见的原图皮肤或衣物，不补全隐藏身体，也不改变腰长或上身长。本项是手动审核轮廓，不冒称 AI 腰部识别。</p>
  <button type="button" disabled={busy} onClick={onOpenBodyAnalysis}>打开真实身体定位与人物关联</button>
  {!shown.bodies.length&&<p role="status">尚无真实身体定位，请先分析当前源图。</p>}
  <div className="leg-body-choices">{shown.bodies.map((b,i)=><button key={refKey(b.body_ref)} type="button" disabled={busy} aria-pressed={refKey(b.body_ref)===refKey(shown.selected_body_ref)} onClick={()=>onSelect(b.body_ref)}>身体 {i+1}{b.reviewed?' · 瘦腰已复核':' · 瘦腰待复核'}{!b.enabled?' · 身体已停用':''}</button>)}</div>
  {body&&<><WaistSupportEditor key={`${refKey(body.body_ref)}:${body.points_sha256}`} body={body} image={sourceImage} disabled={busy||!body.enabled} onReview={support=>action(()=>controller.action('support_review',{data:support,points_sha256:body.points_sha256,visible_anchors:[...ANCHORS],ownership_confirmed:true}))}/>
   {!body.reviewed&&<p role="status">肩、腿或手臂复核不能授权瘦腰。遮挡、严重透视、归属不清或缺少一侧轮廓时拒绝应用。</p>}
   {body.support&&<button type="button" disabled={busy} onClick={()=>void action(()=>controller.action('operation_status',{enabled:!body.operation_enabled}))}>{body.operation_enabled?'停用瘦腰，保留参数':'启用已复核瘦腰'}</button>}
  </>}
  <div className="leg-slider" data-control-id="PC-32473-C-8268ea3e37"><label>瘦腰强度 <output>{Math.round(recipe.amount*100)}</output><input type="range" aria-label="瘦腰强度" min={0} max={100} step={1} value={Math.round(recipe.amount*100)} disabled={!canEdit} onPointerDown={()=>{gesture.current=crypto.randomUUID();}} onPointerUp={()=>{gesture.current=null;}} onPointerCancel={()=>{gesture.current=null;}} onBlur={()=>{gesture.current=null;}} onChange={e=>{const amount=Number(e.currentTarget.value)/100;edit(r=>({...r,amount}),gesture.current??crypto.randomUUID());}}/></label><span>原始轮廓 0 → 向内收紧 100</span></div>
  <button type="button" disabled={!canEdit} onClick={()=>edit(()=>neutral())}>重置瘦腰强度</button>
  {state.phase==='working'&&<p role="status">正在应用，未发送的拖动只保留最新值。</p>}{state.phase==='uncertain'&&<button type="button" onClick={()=>void controller.reconcile()}>查询原请求，不重发</button>}
  {[error,state.message,...shown.refusals.map(r=>r.reason)].filter(Boolean).map((message,i)=><p role="status" key={i}>{message}</p>)}
  <p className="leg-policy">0–100、单向强度、双侧共同应用与支撑阈值均为本产品原创策略，官方未公布范围或左右解锁。过渡区域内背景与衣纹可能移动；不能承诺背景无损或已经通过自然度实机验收。</p>
 </section>;
}
