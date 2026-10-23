// SPDX-License-Identifier: GPL-3.0-or-later
import {useEffect,useRef,useState,useSyncExternalStore} from 'react';
import {LegController} from './controller';
import {LegSupportEditor,type SourceImage} from './LegSupportEditor';
import {IDS,LABELS,ANCHORS,adjust,neutral,refKey,viewKey,type BodyRef,type Key,type LegRecipe,type LegView} from './model';
import './legShape.css';
/** Standalone real interactive panel. Host supplies its native controller and
 * verified source mapping; registration and mailbox are owned by the host workflow. */
export function LegShapePanel({view,controller,sourceImage,onSelect,onOpenBodyAnalysis,disabled=false}:{view:LegView;controller:LegController;sourceImage:SourceImage|null;onSelect:(ref:BodyRef)=>void;onOpenBodyAnalysis:()=>void;disabled?:boolean}){
 useEffect(()=>controller.update(view),[view,controller]);
 const state=useSyncExternalStore(controller.subscribe,controller.snapshot,controller.snapshot);
 const contextCurrent=!!state.view&&viewKey(state.view)===viewKey(view)&&state.view.state_revision>=view.state_revision;
 const shown=contextCurrent&&state.view?state.view:view;const recipe=contextCurrent?state.recipe:view.recipe;const body=shown.bodies.find(b=>refKey(b.body_ref)===refKey(shown.selected_body_ref));
 const busy=disabled||state.phase!=='idle'||!contextCurrent;const canEdit=!disabled&&contextCurrent&&!!body&&body.enabled&&body.operation_enabled&&body.reviewed&&state.phase!=='uncertain';
 const [error,setError]=useState('');const gesture=useRef<string|null>(null);
 useEffect(()=>{setError('');gesture.current=null;},[shown.binding.document_epoch,shown.binding.document_id,refKey(shown.selected_body_ref)]);
 function edit(change:(recipe:LegRecipe)=>LegRecipe,id=crypto.randomUUID()){try{controller.edit(change,id);setError('');}catch(e){setError(e instanceof Error?e.message:'调整未发送。');}}
 async function action(fn:()=>Promise<void>){try{await fn();setError('');}catch(e){setError(e instanceof Error?e.message:'操作未完成。');}}
 const mixed=recipe.thigh!==recipe.calf;
 return <section className="leg-shape-panel" aria-label="可见腿部线条调整" data-operation="lnx.leg_shape.v1"><h3>瘦腿 · 大腿 / 小腿</h3>
  <p>左滑变宽，右滑收紧。大腿为髋到膝，小腿为膝到踝。只变形可见原图像素，不生成被遮挡部位，不改变腿长。</p>
  <button type="button" disabled={busy} onClick={onOpenBodyAnalysis}>打开真实身体定位与人物关联</button>
  {!shown.bodies.length&&<p role="status">尚无实际身体定位结果，不会用人脸框生成腿部骨架。</p>}
  <div className="leg-body-choices">{shown.bodies.map((b,i)=><button type="button" key={refKey(b.body_ref)} disabled={busy} aria-pressed={refKey(b.body_ref)===refKey(shown.selected_body_ref)} onClick={()=>onSelect(b.body_ref)}>身体 {i+1}{b.reviewed?' · 腿部已复核':' · 腿部待复核'}{!b.enabled?' · 身体已停用':''}</button>)}</div>
  {body&&<><LegSupportEditor key={`${refKey(body.body_ref)}:${body.points_sha256}`} body={body} image={sourceImage} disabled={busy||!body.enabled} onReview={support=>action(()=>controller.action('support_review',{data:support,points_sha256:body.points_sha256,visible_anchors:[...ANCHORS],ownership_confirmed:true}))}/>
   {!body.reviewed&&<p role="status">先单独复核本张原图的腿部轮廓；肩部复核不能授权腿部变形。</p>}
   {body.support&&<button type="button" disabled={busy} onClick={()=>void action(()=>controller.action('operation_status',{enabled:!body.operation_enabled}))}>{body.operation_enabled?'停用腿部调整，保留参数':'启用已复核腿部调整'}</button>}
  </>}
  {(['overall','thigh','calf'] as Key[]).map(key=>{const amount=key==='overall'?(mixed?0:recipe.thigh):recipe[key];return <div key={key} data-control-id={IDS[key]} className="leg-slider"><label>{LABELS[key]} <output>{key==='overall'&&mixed?'分项不同':Math.round(amount*100)}</output><input type="range" min={-100} max={100} step={1} value={Math.round(amount*100)} disabled={!canEdit} aria-label={LABELS[key]} aria-valuetext={key==='overall'&&mixed?'分项数值不同，调节整体会同时设置两项':String(Math.round(amount*100))} onPointerDown={()=>{gesture.current=crypto.randomUUID();}} onPointerUp={()=>{gesture.current=null;}} onPointerCancel={()=>{gesture.current=null;}} onBlur={()=>{gesture.current=null;}} onChange={e=>{const n=Number(e.currentTarget.value)/100;edit(r=>adjust(r,key,n),gesture.current??crypto.randomUUID());}}/></label><span>变宽 ← 0 → 收紧</span>{key==='overall'&&<p>同时将大腿和小腿设为选定值，不叠加第三个强度。仅展开或查看不会覆盖分项差异。</p>}</div>;})}
  <button type="button" disabled={!canEdit} onClick={()=>edit(()=>neutral())}>重置腿部两项</button>
  {state.phase==='working'&&<p role="status">正在应用；未发送的拖动只保留最新值。</p>}{state.phase==='uncertain'&&<button type="button" onClick={()=>void controller.reconcile()}>查询本次结果，不重发调整</button>}
  {[error,state.message,...shown.refusals.map(r=>r.reason)].filter(Boolean).map((message,i)=><p role="status" key={i}>{message}</p>)}
  <p className="leg-policy">-100–100、零默认、两条腿同步及支撑阈值均为本产品原创策略，官方未披露数值或腿部左右解锁。本项不改写原文件，仅在支撑区域内变形；渐隐范围内的邻近背景可能弯曲。数值防折叠不代表自然度已经验收。</p>
 </section>;
}
