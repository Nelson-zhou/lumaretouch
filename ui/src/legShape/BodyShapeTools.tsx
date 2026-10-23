// SPDX-License-Identifier: GPL-3.0-or-later
import {useState} from 'react';
import {ShoulderShapeTools} from '../shoulderShape/ShoulderShapeTools';
import type {ShoulderOwner} from '../shoulderShape/useShoulderWorkflow';
import {LegShapePanel} from './LegShapePanel';
import type {LegOwner} from './useLegWorkflow';
/** Both operations retain independent receipts but share the real body bank. */
export function BodyShapeTools({shoulders,legs,blocked}:{shoulders:ShoulderOwner;legs:LegOwner;blocked:boolean}){
 const [workspace,setWorkspace]=useState<'shoulder'|'leg'|null>(null),[error,setError]=useState('');
 const act=async(work:()=>Promise<unknown>)=>{setError('');try{await work();}catch(e){setError(e instanceof Error?e.message:'操作未完成');}};
 const openShoulders=()=>{setWorkspace('shoulder');void act(()=>shoulders.run('view'));};
 const openLegs=()=>{setWorkspace('leg');void act(()=>legs.run('view'));};
 const legBlocked=blocked||shoulders.busy||shoulders.acquisition.busy||!legs.enabled;
 return <>
  <ShoulderShapeTools owner={shoulders} blocked={blocked||legs.busy} workspaceOpen={workspace==='shoulder'} onWorkspaceOpen={open=>setWorkspace(open?'shoulder':null)}/>
  <section aria-label="瘦腿、大腿和小腿" data-feature-id="PC-32473">
   <p>瘦腿：独立复核可见大腿和小腿轮廓，与肩部共享真实身体定位，但不借用肩部复核权限。</p>
   <button type="button" disabled={legBlocked||legs.busy} onClick={openLegs}>打开腿部调整与轮廓复核</button>
   {!legs.supported&&<p role="status">当前引擎未声明腿部协议，请使用配套版本。</p>}
   {legs.busy&&<p role="status">{legs.uncertain||legs.state.phase==='uncertain'?'腿部结果待核对，不会重新提交。':'腿部请求正在处理。'}</p>}
   {(legs.uncertain||legs.state.phase==='uncertain')&&<button type="button" onClick={()=>void act(legs.check)}>查询原请求结果</button>}
   {[legs.message,error].filter(Boolean).map((text,i)=><p role="status" key={i}>{text}</p>)}
  </section>
  {workspace==='leg'&&<div className="legWorkspace" role="dialog" aria-modal="true" aria-label="原图腿部定位与可见轮廓调整">
   <div className="leg-toolbar"><b>腿部可见轮廓复核</b><span>这里显示未修饰的全图参考缩略图；关闭后在主画布查看结果。</span><button type="button" onClick={()=>setWorkspace(null)}>关闭定位窗口</button></div>
   <div className="leg-workspace-content">
    <button type="button" disabled={legBlocked||legs.busy} onClick={()=>void act(()=>legs.run('view'))}>刷新身体状态与原图参考</button>
    {legs.view?<LegShapePanel view={legs.view} controller={legs.controller} sourceImage={legs.source} disabled={legBlocked||!!legs.task} onSelect={ref=>void act(()=>legs.run('select',ref))} onOpenBodyAnalysis={openShoulders}/>:<><p role="status">等待真实文档的身体状态，不会生成示意骨架。</p><button type="button" disabled={blocked||legs.busy||!shoulders.enabled} onClick={openShoulders}>打开真实身体定位与人物关联</button></>}
    {[legs.message,error].filter(Boolean).map((text,i)=><p role="alert" key={i}>{text}</p>)}
    {(legs.uncertain||legs.state.phase==='uncertain')&&<button type="button" onClick={()=>void act(legs.check)}>查询原请求结果，不重发</button>}
   </div>
  </div>}
 </>;
}
