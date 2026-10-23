// SPDX-License-Identifier: GPL-3.0-or-later
import {useState} from 'react';
import {WaistWorkspace} from '../waistShape/WaistWorkspace';
import type {WaistOwner} from '../waistShape/useWaistWorkflow';
import {ShoulderShapeTools} from '../shoulderShape/ShoulderShapeTools';
import type {ShoulderOwner} from '../shoulderShape/useShoulderWorkflow';
import {LegShapePanel} from './LegShapePanel';
import type {LegOwner} from './useLegWorkflow';
import {ArmShapePanel} from '../armShape/ArmShapePanel';
import type {ArmOwner} from '../armShape/useArmWorkflow';
/** Independent operation receipts and reviews share only the real body bank. */
export function BodyShapeTools({shoulders,legs,arms,waist,blocked}:{shoulders:ShoulderOwner;legs:LegOwner;arms:ArmOwner;waist:WaistOwner;blocked:boolean}){
 const [workspace,setWorkspace]=useState<'shoulder'|'leg'|'arm'|'waist'|null>(null),[error,setError]=useState('');
 const act=async(work:()=>Promise<unknown>)=>{setError('');try{await work();}catch(e){setError(e instanceof Error?e.message:'操作未完成');}};
 const openShoulders=()=>{setWorkspace('shoulder');void act(()=>shoulders.run('view'));};
 const openLegs=()=>{setWorkspace('leg');void act(()=>legs.run('view'));};
 const openArms=()=>{setWorkspace('arm');if(!arms.busy)void act(()=>arms.run('view'));};
 const openWaist=()=>{setWorkspace('waist');void act(()=>waist.run('view'));};
 const waistBlocked=blocked||shoulders.busy||shoulders.acquisition.busy||legs.busy||arms.busy||!waist.enabled;
 const legBlocked=blocked||shoulders.busy||shoulders.acquisition.busy||arms.busy||waist.busy||!legs.enabled;
 const armBlocked=blocked||shoulders.busy||shoulders.acquisition.busy||legs.busy||waist.busy||!arms.enabled;
 return <>
  <ShoulderShapeTools owner={shoulders} blocked={blocked||legs.busy||arms.busy||waist.busy} workspaceOpen={workspace==='shoulder'} onWorkspaceOpen={open=>setWorkspace(open?'shoulder':null)}/>
  <section aria-label="AI瘦手臂与瘦手臂" data-feature-id="PC-32473" data-control-id="PC-32473-C-5d25f1744f" data-requirement-id="LNX-REF-PC-32473-C-5d25f1744f" data-tool-anchor="AI瘦手臂&瘦手臂" data-arm-workflow>
   <p>AI瘦手臂 / 瘦手臂：上臂、前臂与左右独立选择。AI 只提供待复核分割候选，不借用肩部或腿部复核权限。</p>
   <button type="button" disabled={armBlocked} onClick={openArms}>打开手臂调整与源图复核</button>
   {!arms.supported&&<p role="status">当前引擎未声明手臂协议，请使用配套版本。</p>}
   {arms.busy&&<p role="status">{arms.uncertain||arms.state.phase==='uncertain'?'手臂结果待核对，不会重新提交。':arms.proposalBusy?'选区任务正在处理；关闭复核窗口会请求取消。':'手臂请求正在处理。'}</p>}
   {(arms.uncertain||arms.state.phase==='uncertain')&&<button type="button" onClick={()=>void act(arms.check)}>查询原手臂请求结果</button>}
   {arms.message&&<p role="status">{arms.message}</p>}
  </section>
  <section data-waist-workflow aria-label="瘦腰" data-feature-id="PC-32473" data-control-id="PC-32473-C-8268ea3e37" data-requirement-id="LNX-REF-PC-32473-C-8268ea3e37" data-tool-anchor="瘦腰">
   <p>瘦腰：独立审核上下界和双侧可见轮廓，向内收紧。不是腰长、上身长或全身 AI 塑形。</p>
   <button type="button" disabled={waistBlocked||waist.busy} onClick={openWaist}>打开瘦腰调整与源图复核</button>
   {!waist.supported&&<p role="status">当前引擎未声明瘦腰协议，请使用配套版本。</p>}
   {waist.busy&&<p role="status">{waist.uncertain||waist.state.phase==='uncertain'?'瘦腰结果待核对，不会重发。':'正在处理瘦腰请求。'}</p>}
   {(waist.uncertain||waist.state.phase==='uncertain')&&<button type="button" onClick={()=>void act(waist.check)}>查询原瘦腰请求</button>}
   {waist.message&&<p role="status">{waist.message}</p>}
  </section>
  <section aria-label="瘦腿、大腿和小腿" data-feature-id="PC-32473">
   <p>瘦腿：独立复核可见大腿和小腿轮廓，与肩部共享真实身体定位，但不借用肩部复核权限。</p>
   <button type="button" disabled={legBlocked||legs.busy} onClick={openLegs}>打开腿部调整与轮廓复核</button>
   {!legs.supported&&<p role="status">当前引擎未声明腿部协议，请使用配套版本。</p>}
   {legs.busy&&<p role="status">{legs.uncertain||legs.state.phase==='uncertain'?'腿部结果待核对，不会重新提交。':'腿部请求正在处理。'}</p>}
   {(legs.uncertain||legs.state.phase==='uncertain')&&<button type="button" onClick={()=>void act(legs.check)}>查询原请求结果</button>}
   {[legs.message,error].filter(Boolean).map((text,i)=><p role="status" key={i}>{text}</p>)}
  </section>
  {workspace==='waist'&&<WaistWorkspace owner={waist} blocked={waistBlocked} onClose={()=>setWorkspace(null)} onOpenBodyAnalysis={openShoulders}/>}
  {workspace==='leg'&&<div className="legWorkspace" role="dialog" aria-modal="true" aria-label="原图腿部定位与可见轮廓调整">
   <div className="leg-toolbar"><b>腿部可见轮廓复核</b><span>这里显示未修饰的全图参考缩略图；关闭后在主画布查看结果。</span><button type="button" onClick={()=>setWorkspace(null)}>关闭定位窗口</button></div>
   <div className="leg-workspace-content">
    <button type="button" disabled={legBlocked||legs.busy} onClick={()=>void act(()=>legs.run('view'))}>刷新身体状态与原图参考</button>
    {legs.view?<LegShapePanel view={legs.view} controller={legs.controller} sourceImage={legs.source} disabled={legBlocked||!!legs.task} onSelect={ref=>void act(()=>legs.run('select',ref))} onOpenBodyAnalysis={openShoulders}/>:<><p role="status">等待真实文档的身体状态，不会生成示意骨架。</p><button type="button" disabled={blocked||legs.busy||!shoulders.enabled} onClick={openShoulders}>打开真实身体定位与人物关联</button></>}
    {[legs.message,error].filter(Boolean).map((text,i)=><p role="alert" key={i}>{text}</p>)}
    {(legs.uncertain||legs.state.phase==='uncertain')&&<button type="button" onClick={()=>void act(legs.check)}>查询原请求结果，不重发</button>}
   </div>
  </div>}
  {workspace==='arm'&&<div className="legWorkspace" data-arm-workflow role="dialog" aria-modal="true" aria-label="原图手臂定位与可见轮廓调整">
   <div className="leg-toolbar"><b>手臂源图复核</b><span>未修饰的全图参考，不是效果图。关闭不撤销已提交调整。</span><button type="button" onClick={()=>setWorkspace(null)}>关闭复核窗口</button></div>
   <div className="leg-workspace-content">
    <button type="button" disabled={armBlocked||arms.busy} onClick={()=>void act(()=>arms.run('view'))}>刷新身体状态与原图参考</button>
    <button type="button" disabled={blocked||arms.busy||legs.busy||!shoulders.enabled} onClick={openShoulders}>打开真实身体定位与人物关联</button>
    {arms.view?<ArmShapePanel controller={arms.controller} transport={arms.transport} source={arms.source} disabled={armBlocked||!!arms.task||arms.proposalBusy} onSelectBody={ref=>void act(()=>arms.run('select',ref))}/>:<p role="status">等待当前照片的真实身体状态，不会从人脸框伪造手臂骨架。</p>}
    {[arms.message,error].filter(Boolean).map((text,i)=><p role="alert" key={i}>{text}</p>)}
    {(arms.uncertain||arms.state.phase==='uncertain')&&<button type="button" onClick={()=>void act(arms.check)}>查询原手臂请求，不重发</button>}
   </div>
  </div>}
 </>;
}
