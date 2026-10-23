// SPDX-License-Identifier: GPL-3.0-or-later
import {useRef,useState,useSyncExternalStore} from 'react';
import {SEGMENTS,LABELS,REQUIREMENT_ID,canApply,refKey,reviewKey,targets,type Segment,type Strategy,type Transport,type BodyRef} from './model';
import {type ArmController} from './controller';
import {ArmSupportEditor,type SourcePreview} from './ArmSupportEditor';
import './armShape.css';
/** The app owns controller and receipts; closing this panel only cancels proposals. */
export function ArmShapePanel({controller,transport,source,onSelectBody,disabled=false}:{controller:ArmController;transport:Transport;source:SourcePreview|null;onSelectBody:(ref:BodyRef)=>void;disabled?:boolean}){
 const gesture=useRef<string|null>(null);
 const state=useSyncExternalStore(controller.subscribe,controller.snapshot),view=state.view;
 const [segment,setSegment]=useState<Segment>('left_upper'),[linked,setLinked]=useState(false),[whole,setWhole]=useState(false),[strategy,setStrategy]=useState<Strategy>('reviewed-contour'),[message,setMessage]=useState('');
 if(!view)return <section className="arm-shape"><p>等待实际身体状态；未伪造可用能力。</p></section>;
 const body=view.bodies.find(b=>refKey(b.body_ref)===refKey(view.selected_body_ref)),keys=targets(segment,linked,whole),recipe=state.recipe[segment];
 const ready=!disabled&&!!body&&canApply(body,keys,strategy),uncertain=state.phase==='uncertain',busy=disabled||state.phase!=='idle';
 function edit(amount:number,gestureId:string=crypto.randomUUID()){try{if(disabled)throw Error('请先等待当前工具请求完成。');controller.edit(keys,linked,strategy,amount,gestureId);setMessage('');}catch(e){setMessage(e instanceof Error?e.message:'未应用');}}
 return <section className="arm-shape" aria-label="AI瘦手臂与瘦手臂" data-operation="lnx.arm_shape.v1" data-control-id={REQUIREMENT_ID}><h3>AI瘦手臂 / 瘦手臂</h3><p>普通可见轮廓与待复核分割候选分开记录，不是全自动识别。本地运行与画质验收未完成。</p>
 <label>实际身体<select value={refKey(view.selected_body_ref)} disabled={busy} onChange={e=>{const choice=view.bodies.find(b=>refKey(b.body_ref)===e.target.value);if(choice)onSelectBody(choice.body_ref);}}><option value="none">请选择</option>{view.bodies.map((b,i)=><option key={refKey(b.body_ref)} value={refKey(b.body_ref)}>身体 {i+1} · {b.body_ref.body_instance_id.slice(0,8)}</option>)}</select></label>
 <label>策略<select disabled={busy} value={strategy} onChange={e=>setStrategy(e.target.value as Strategy)}><option value="reviewed-contour">普通：复核可见轮廓</option><option value="sam2-prompted-contour">AI：SAM2 待复核分割候选</option></select></label>
 <label>分段<select value={segment} disabled={busy} onChange={e=>setSegment(e.target.value as Segment)}>{SEGMENTS.map(k=><option value={k} key={k}>{LABELS[k]}</option>)}</select></label>
 <div className="arm-row"><label><input type="checkbox" checked={linked} disabled={busy} onChange={e=>setLinked(e.target.checked)}/>左右联动</label><label><input type="checkbox" checked={whole} disabled={busy} onChange={e=>setWhole(e.target.checked)}/>同时设置上臂和前臂</label></div>
 <p>目标：{keys.map(k=>LABELS[k]).join('、')}。联动是一次性同时设置，不叠加额外强度；任何一段缺少有效证据就整次拒绝。</p>
 <p>当前已保存：{recipe.strategy==='reviewed-contour'?'普通可见轮廓':'SAM2 图像辅助轮廓'}，{Math.round(recipe.amount*100)}。切换选择策略不会偷偷重标或重算已有效果。</p>
 <label>收细强度 {Math.round(recipe.amount*100)}<input aria-label="手臂收细强度" type="range" min="0" max="100" step="1" value={Math.round(recipe.amount*100)} disabled={!ready||uncertain} onPointerDown={()=>{gesture.current=crypto.randomUUID();}} onPointerUp={()=>{gesture.current=null;}} onPointerCancel={()=>{gesture.current=null;}} onKeyDown={()=>{gesture.current??=crypto.randomUUID();}} onKeyUp={()=>{gesture.current=null;}} onBlur={()=>{gesture.current=null;}} onChange={e=>edit(Number(e.target.value)/100,gesture.current??(gesture.current=crypto.randomUUID()))}/></label>
 <p>0 为真实中性。0–100、正向收细、默认解锁、分段模式与普通模式的左右独立控制均为本产品选择，不是官方数值规格。</p>
 <button disabled={disabled||!body||uncertain} onClick={()=>edit(0)}>将所选目标归零</button>{body&&<button disabled={busy} onClick={()=>void controller.action('operation_status',{segment,enabled:!body.operations[segment].enabled}).catch(e=>setMessage(String(e)))}>{body.operations[segment].enabled?'停用':'启用'}该分段</button>}
 {!ready&&<p>先完成每个目标分段对应策略的可见源图复核。只有一只手臂可见时保持解锁，并只选有证据的分段。</p>}
 {uncertain&&<button onClick={()=>void controller.reconcile()}>查询原请求结果（不重发）</button>}
 <p role="status">{state.message||message}</p>{view.refusals.map((r,i)=><p role="alert" key={i}>{r.reason}</p>)}
 {body&&source?<ArmSupportEditor key={`${reviewKey(view,segment)}:${strategy}`} body={body} view={view} segment={segment} strategy={strategy} source={source} controller={controller} transport={transport} disabled={busy}/>:<p>需要与当前照片绑定的标准当前来源图，才能查看真实选区并复核。</p>}
 <small>{REQUIREMENT_ID} · 关联 PORTRAIT-008 不代表本项已验收。过渡范围中的背景与衣物纹理可能随形变移动。</small></section>;
}
