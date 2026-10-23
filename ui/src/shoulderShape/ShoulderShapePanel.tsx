// SPDX-License-Identifier: GPL-3.0-or-later
import {useLayoutEffect,useRef,useState,useSyncExternalStore} from 'react';
import {ANCHORS,IDS,LABELS,adjust,canReview,link,neutral,refKey,type BodyRef,type Key,type ShoulderView,type Side} from './model';
import type {ShoulderController} from './controller';
import type {ModelStatus} from './nativePort';
interface Props{view:ShoulderView;controller:ShoulderController;disabled:boolean;model:ModelStatus;reviewAvailable?:boolean;onSelect:(ref:BodyRef)=>void;onAnalyse:()=>Promise<void>;onInstall:()=>Promise<void>;}
export function ShoulderShapePanel({view,controller,disabled,model,reviewAvailable=false,onSelect,onAnalyse,onInstall}:Props){
 const value=useSyncExternalStore(controller.subscribe,controller.snapshot,controller.snapshot);
 const [task,setTask]=useState(false),[error,setError]=useState(''),[person,setPerson]=useState('');
 const gestures=useRef(new Map<string,string>());
 useLayoutEffect(()=>{controller.update(view);},[controller,view]);
 const shown=value.view??view;const body=shown.bodies.find(b=>refKey(b.body_ref)===refKey(shown.selected_body_ref));
 const busy=disabled||task||value.phase!=='idle';const canEdit=!disabled&&!task&&value.phase!=='uncertain'&&!!body?.reviewed&&body.enabled&&body.shoulder_enabled!==false;
 const act=async(fn:()=>Promise<unknown>)=>{setTask(true);setError('');try{await fn();}catch(e){setError(e instanceof Error?e.message:'操作未完成');}finally{setTask(false);}};
 const gesture=(key:string)=>{let id=gestures.current.get(key);if(!id){id=crypto.randomUUID();gestures.current.set(key,id);}return id;};
 const edit=(fn:Parameters<ShoulderController['edit']>[0],id:string)=>{try{controller.edit(fn,id);setError('');}catch(e){setError(e instanceof Error?e.message:'调整未发送');}};
 const slider=(key:Key,side:Side)=>{const id=`${key}:${side}`,label=`${LABELS[key]} · 人物${side==='left'?'左':'右'}`,min=key==='square'?0:-100;const n=value.recipe[key][side];
  const change=(next:number)=>{if(Number.isFinite(next))edit(r=>adjust(r,key,side,Math.min(100,Math.max(min,next))/100),gesture(id));};
  return <div key={id} className="pslider"><label className="prow">{label}<input type="number" aria-label={`${label}数值`} min={min} max={100} step={1} value={Math.round(n*100)} disabled={!canEdit} onChange={e=>change(e.currentTarget.valueAsNumber)} onBlur={()=>gestures.current.delete(id)}/></label>
   <input type="range" aria-label={label} min={min} max={100} step={1} value={Math.round(n*100)} disabled={!canEdit} onPointerDown={e=>{gesture(id);e.currentTarget.setPointerCapture(e.pointerId);}} onChange={e=>change(e.currentTarget.valueAsNumber)} onPointerUp={()=>gestures.current.delete(id)} onPointerCancel={()=>gestures.current.delete(id)} onKeyUp={()=>gestures.current.delete(id)} onBlur={()=>gestures.current.delete(id)}/>
   <button type="button" disabled={!canEdit} onClick={()=>edit(r=>adjust(r,key,side,0),crypto.randomUUID())}>归零</button></div>;};
 return <section aria-label="肩部美型" data-operation="lnx.shoulder_shape.v1">
  <p>肩部美型只移动已有二维像素，附近背景也可能移动。左右指人物自身。</p>
  {!model.installed&&<div role="status"><p>{model.reason??'需先取得并校验可选身体定位模型。'}首次获取尚不等于画质验收。</p><button type="button" disabled={busy||['pin-pending','unknown'].includes(model.state)} onClick={()=>void act(onInstall)}>获取可选身体定位模型{model.download_bytes?`（约 ${(model.download_bytes/1e6).toFixed(1)} MB）`:''}</button></div>}
  {model.installed&&<p role="status">仅模型文件已完成校验，不代表 MediaPipe 运行环境就绪或定位质量通过。检测会真实验证；不会自动安装运行库。</p>}
  <button type="button" disabled={busy||!model.installed} onClick={()=>void act(onAnalyse)}>在原始图像上检测真实身体定位</button>
  <div role="group" aria-label="身体目标">{shown.bodies.map((b,i)=><button key={refKey(b.body_ref)} type="button" disabled={busy} aria-pressed={refKey(b.body_ref)===refKey(shown.selected_body_ref)} onClick={()=>onSelect(b.body_ref)}>身体 {i+1}{b.reviewed?' · 已复核':' · 待复核'}{b.enabled?'':' · 已停用'}</button>)}</div>
  {shown.analysis_run?.limit_reached&&<p role="status">已达到 {shown.analysis_run.detector_limit} 个检测上限，仍可能有未检测到的人物。</p>}
  {body&&<>
   {!!body.unapplied_operations?.length&&<p role="alert">此身体还保留本界面不能应用的操作：{body.unapplied_operations.join('、')}。它们未被丢弃，启用时将阻止导出，不能把未应用意图当作成功结果。</p>}
   {body.unapplied_operations?.map(operation_id=><button key={operation_id} type="button" disabled={busy} onClick={()=>void act(()=>controller.action('operation_status',{operation_id,enabled:false}))}>保留参数并停用未应用操作 {operation_id}</button>)}
   <p>请在原图定位叠层中核对头部、双肩、双肘和髋部可见点均属于此身体。低置信度或遮挡点不能通过手动确认强行启用。</p>
   <button type="button" disabled={busy||!reviewAvailable||!canReview(body)} onClick={()=>void act(()=>controller.action('review',{points_sha256:body.points_sha256,visible_anchors:[...ANCHORS],ownership_confirmed:true}))}>确认这些锚点清晰可见且归属此身体</button>
   {!reviewAvailable&&<p role="status">请先显示当前身体的原图定位叠层，再确认锚点。</p>}
   {!canReview(body)&&<p role="status">至少一个必要锚点无法可靠确认，请换用清晰完整视角或重新分析，不会重建不可见部位。</p>}
   <label>明确关联到已确认的匿名人物<select value={person} disabled={busy} onChange={e=>setPerson(e.currentTarget.value)}><option value="">请选择，不按最近人脸猜测</option>{Object.keys(shown.persons).map((id,i)=><option key={id} value={id}>匿名人物 {i+1}</option>)}</select></label>
   <button type="button" disabled={busy||!person||!shown.persons[person]} onClick={()=>void act(()=>controller.action('associate',{person_id:person,user_confirmed:true}))}>确认身体与人物关联</button>
   {body.association&&<button type="button" disabled={busy} onClick={()=>void act(()=>controller.action('unlink',{}))}>解除人物关联（保留肩形参数）</button>}
   <button type="button" disabled={busy||!body.reviewed} onClick={()=>void act(()=>controller.action('operation_status',{operation_id:'lnx.shoulder_shape.v1',enabled:body.shoulder_enabled===false}))}>{body.shoulder_enabled===false?'启用肩部调整':'仅停用肩部调整'}</button>
   <button type="button" disabled={busy} onClick={()=>void act(()=>controller.action('body_status',{enabled:!body.enabled}))}>{body.enabled?'停用此身体调整':'启用此身体调整'}</button>
  </>}
  {(['square','width'] as const).map(key=><div key={key} data-control-id={IDS[key]}><p>{LABELS[key]}：{key==='square'?'向头部方向适度抬升可见肩部，使肩线更平直。':'负值收窄，正值拓宽。'}</p>
   <button type="button" disabled={!canEdit} aria-pressed={value.recipe[key].linked} onClick={()=>edit(r=>link(r,key,!r[key].linked),crypto.randomUUID())}>{value.recipe[key].linked?'已联动，点击解锁':'已解锁，点击联动'}</button>
   {value.recipe[key].linked&&value.recipe[key].left!==value.recipe[key].right&&<p>原有左右差异保留，下次调整才同步。</p>}{slider(key,'left')}{slider(key,'right')}</div>)}
  <button type="button" disabled={!canEdit} onClick={()=>edit(()=>neutral(),crypto.randomUUID())}>重置两项肩形</button>
  {value.phase==='working'&&<p role="status">正在应用；拖动保留最新意图。</p>}{value.phase==='uncertain'&&<button type="button" onClick={()=>void controller.reconcile()}>查询本次结果，不重发调整</button>}
  {[error,value.message,...shown.refusals.map(r=>r.reason)].filter(Boolean).map((text,i)=><p role="status" key={i}>{text}</p>)}
  <p className="muted">直角肩 0–100、肩宽 -100–100 和可见性阈值均为本产品实现策略，官方未披露数值。MediaPipe 模型卡主要面向单人完整身体；多人、遮挡、裁边、极端姿态需逐例核对，接口支持多个定位不代表多人塑形质量已验收。</p>
 </section>;
}
