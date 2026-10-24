// SPDX-License-Identifier: GPL-3.0-or-later
import {useEffect,useRef,useState,useSyncExternalStore} from 'react';
import {HeadSizeController} from './controller';
import {HeadSizeSupportEditor} from './HeadSizeSupportEditor';
import {OPERATION_ID,REQUIREMENT_ID,ANCHORS,adjust,neutral,refKey,viewKey,type BodyRef,type HeadSizeRecipe,type HeadSizeView} from './model';
import type {SourceImage} from './sourcePreview';
import './headSize.css';
export function HeadSizePanel({view,controller,sourceImage,onSelect,onOpenBodyAnalysis,coreAvailable=false,disabled=false}:{view:HeadSizeView;controller:HeadSizeController;sourceImage:SourceImage|null;onSelect:(ref:BodyRef)=>void;onOpenBodyAnalysis:()=>void;coreAvailable?:boolean;disabled?:boolean}){
 useEffect(()=>controller.update(view),[view,controller]);
 const state=useSyncExternalStore(controller.subscribe,controller.snapshot,controller.snapshot);
 const current=!!state.view&&viewKey(state.view)===viewKey(view)&&state.view.state_revision>=view.state_revision;
 const shown=current&&state.view?state.view:view,recipe=current?state.recipe:view.recipe,body=shown.bodies.find(b=>refKey(b.body_ref)===refKey(shown.selected_body_ref));
 const busy=disabled||state.phase!=='idle'||!current,canReset=!disabled&&current&&!!body&&state.phase!=='uncertain';
 const canEdit=canReset&&coreAvailable&&!!body?.enabled&&body.operation_enabled&&body.reviewed;
 const [error,setError]=useState(''),gesture=useRef<string|null>(null);
 useEffect(()=>{setError('');gesture.current=null;},[shown.binding.document_epoch,shown.binding.document_id,refKey(shown.selected_body_ref)]);
 function edit(change:(recipe:HeadSizeRecipe)=>HeadSizeRecipe,id=gesture.current??crypto.randomUUID()){try{controller.edit(change,id);setError('');}catch(e){setError(e instanceof Error?e.message:'调整未发送。');}}
 async function action(fn:()=>Promise<void>){try{await fn();setError('');}catch(e){setError(e instanceof Error?e.message:'操作未完成。');}}
 return <section className="head-size-panel" aria-label="小头含完整头发手动辅助 2D 调整" data-operation={OPERATION_ID} data-requirement-id={REQUIREMENT_ID}>
  <h3>小头 · 含完整头发 · 手动辅助 2D</h3>
  {!coreAvailable&&<p role="status">原生形变核心未就绪。可保存当前来源独立复核、查询、停用或归零；保存成功不代表效果已应用，非零调整及启用仍不可用。</p>}
  {shown.publication?.rendered===false&&<p role="status">当前已保存的参数或复核尚未应用：{shown.publication.unapplied_reason??'实际发布状态仍需核对。'}</p>}
  <p>围绕手工点选的中心，统一缩小完整头部、脸和全部头发，外围背景连续衔接。这不是人脸大小控制的复制，也不改变肩宽或全身比例。强度 0 保持原始，100 对应局部最多缩小 8%。</p>
  <button type="button" disabled={busy} onClick={onOpenBodyAnalysis}>打开真实身体定位与人物关联</button>
  {!shown.bodies.length&&<p role="status">尚无真实身体定位和本人脸部关系，不会仅凭人脸框猜测头发或建立虚假身体归属。</p>}
  <div className="head-size-body-choices">{shown.bodies.map((b,i)=><button type="button" key={refKey(b.body_ref)} disabled={busy} aria-pressed={refKey(b.body_ref)===refKey(shown.selected_body_ref)} onClick={()=>onSelect(b.body_ref)}>身体 {i+1}{b.reviewed?' · 小头已复核':' · 小头待复核'}{!b.enabled?' · 已停用':''}</button>)}</div>
  {body&&<><HeadSizeSupportEditor key={`${refKey(body.body_ref)}:${body.points_sha256}`} body={body} image={sourceImage} reviewIdentity={`${shown.binding.document_epoch}:${shown.body_graph_sha256}:${shown.people_graph_sha256}:${shown.association_revision}:${shown.people_association_revision}`} disabled={busy||!body.enabled} onReview={data=>action(()=>controller.action('support_review',{data,points_sha256:body.points_sha256,visible_anchors:[...ANCHORS],ownership_confirmed:true}))}/>
   {!body.reviewed&&<p role="status">需要本项独立复核：完整头发/头部框、清晰背景过渡框与手工中心。其他身体或人脸工具的复核不能授权此项。</p>}
   {(body.support||body.operation_enabled)&&<button type="button" disabled={busy||!body.operation_enabled&&(!coreAvailable||!body.reviewed||!body.enabled)} onClick={()=>void action(()=>controller.action('operation_status',{enabled:!body.operation_enabled}))}>{body.operation_enabled?'停用小头，保留参数':'启用已复核的小头'}</button>}
  </>}
  <div className="head-size-slider" data-control-id="PC-32473-C-dc1b0ba40a" data-requirement-id={REQUIREMENT_ID}><label>小头强度 <output>{Math.round(recipe.amount*100)}</output><input type="range" min={0} max={100} step={1} value={Math.round(recipe.amount*100)} disabled={!canEdit} aria-label="小头强度" aria-valuetext={`${Math.round(recipe.amount*100)}，零保持原始，越大越缩小完整头发与头部，最多百分之八`} onPointerDown={()=>{gesture.current=crypto.randomUUID();}} onPointerUp={()=>{gesture.current=null;}} onPointerCancel={()=>{gesture.current=null;}} onBlur={()=>{gesture.current=null;}} onChange={e=>{const amount=Number(e.currentTarget.value)/100;edit(r=>adjust(r,amount));}}/></label><span>原始 0 → 完整头发与头部缩小，100 为局部最多 8%</span></div>
  <button type="button" disabled={!canReset} onClick={()=>edit(()=>neutral(),crypto.randomUUID())}>重置小头为 0</button>
  {state.phase==='working'&&<p role="status">正在核对发布；尚未发送的拖动只保留最新值。</p>}
  {state.phase==='uncertain'&&<button type="button" onClick={()=>void controller.reconcile()}>查询本次结果，不重发调整</button>}
  {[error,state.message,...shown.refusals.map(r=>r.reason)].filter(Boolean).map((message,i)=><p role="status" key={i}>{message}</p>)}
  <p className="head-size-policy">这是局部、手动辅助的 2D 源码实现，不是自动 AI 发际检测或三维头型重建。0–100、最多 8% 和保守边界阈值均为本产品原创策略，不是官方披露参数。不改写原文件；外围背景可能移动。当前仅支持当前照片的独立参数，不宣称预设、同步或批量迁移已接入。自然度与实机验收未运行。</p>
 </section>;
}
