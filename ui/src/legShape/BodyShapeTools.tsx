import {HeadSizeWorkspace} from '../headSize/HeadSizeWorkspace';
import type {HeadSizeOwner} from '../headSize/useHeadSizeWorkflow';
import {NeckWorkspace} from '../neckShape/NeckWorkspace';
import type {NeckOwner} from '../neckShape/useNeckWorkflow';
// SPDX-License-Identifier: GPL-3.0-or-later
import {useState} from 'react';
import {LegLengthWorkspace} from '../legLength/LegLengthWorkspace';
import type {LegLengthOwner} from '../legLength/useLegLengthWorkflow';
import {TorsoLengthWorkspace} from '../torsoLength/TorsoLengthWorkspace';
import type {TorsoLengthOwner} from '../torsoLength/useTorsoLengthWorkflow';
import {WaistLengthWorkspace} from '../waistLength/WaistLengthWorkspace';
import type {WaistLengthOwner} from '../waistLength/useWaistLengthWorkflow';
import {WaistWorkspace} from '../waistShape/WaistWorkspace';
import type {WaistOwner} from '../waistShape/useWaistWorkflow';
import {ShoulderShapeTools} from '../shoulderShape/ShoulderShapeTools';
import type {ShoulderOwner} from '../shoulderShape/useShoulderWorkflow';
import {LegShapePanel} from './LegShapePanel';
import type {LegOwner} from './useLegWorkflow';
import {ArmShapePanel} from '../armShape/ArmShapePanel';
import type {ArmOwner} from '../armShape/useArmWorkflow';
/** Independent operation receipts and reviews share only the real body bank. */
export function BodyShapeTools({shoulders,legs,arms,waist,length,neck,torso,waistLength,headSize,blocked}:{shoulders:ShoulderOwner;legs:LegOwner;arms:ArmOwner;waist:WaistOwner;length:LegLengthOwner;neck:NeckOwner;torso:TorsoLengthOwner;waistLength:WaistLengthOwner;headSize:HeadSizeOwner;blocked:boolean}){
 const [workspace,setWorkspace]=useState<'shoulder'|'leg'|'arm'|'waist'|'length'|'neck'|'torso'|'waistLength'|'headSize'|null>(null),[error,setError]=useState('');
 const act=async(work:()=>Promise<unknown>)=>{setError('');try{await work();}catch(e){setError(e instanceof Error?e.message:'操作未完成');}};
 const openShoulders=()=>{setWorkspace('shoulder');void act(()=>shoulders.run('view'));};
 const openLegs=()=>{setWorkspace('leg');void act(()=>legs.run('view'));};
 const openArms=()=>{setWorkspace('arm');if(!arms.busy)void act(()=>arms.run('view'));};
 const openWaist=()=>{setWorkspace('waist');void act(()=>waist.run('view'));};
 const openLength=()=>{setWorkspace('length');void act(()=>length.run('view'));};
 const openNeck=()=>{setWorkspace('neck');void act(()=>neck.run('view'));};
 const openTorso=()=>{setWorkspace('torso');if(!torso.busy)void act(()=>torso.run('view'));};
 const openWaistLength=()=>{setWorkspace('waistLength');if(!waistLength.busy)void act(()=>waistLength.run('view'));};
 const openHeadSize=()=>{setWorkspace('headSize');if(!headSize.busy)void act(()=>headSize.run('view'));};
 const torsoBlocked=blocked||shoulders.busy||shoulders.acquisition.busy||legs.busy||arms.busy||waist.busy||length.busy||neck.busy||waistLength.busy||headSize.busy||!torso.enabled;
 const waistLengthBlocked=blocked||shoulders.busy||shoulders.acquisition.busy||legs.busy||arms.busy||waist.busy||length.busy||neck.busy||torso.busy||headSize.busy||!waistLength.enabled;
 const headSizeBlocked=blocked||shoulders.busy||shoulders.acquisition.busy||legs.busy||arms.busy||waist.busy||length.busy||neck.busy||torso.busy||waistLength.busy||!headSize.enabled;
 const neckBlocked=blocked||shoulders.busy||shoulders.acquisition.busy||legs.busy||arms.busy||waist.busy||length.busy||torso.busy||waistLength.busy||headSize.busy||!neck.enabled;
 const lengthBlocked=blocked||shoulders.busy||shoulders.acquisition.busy||legs.busy||arms.busy||waist.busy||neck.busy||torso.busy||waistLength.busy||headSize.busy||!length.enabled;
 const waistBlocked=blocked||shoulders.busy||shoulders.acquisition.busy||legs.busy||arms.busy||length.busy||neck.busy||torso.busy||waistLength.busy||headSize.busy||!waist.enabled;
 const legBlocked=blocked||shoulders.busy||shoulders.acquisition.busy||arms.busy||waist.busy||length.busy||neck.busy||torso.busy||waistLength.busy||headSize.busy||!legs.enabled;
 const armBlocked=blocked||shoulders.busy||shoulders.acquisition.busy||legs.busy||waist.busy||length.busy||neck.busy||torso.busy||waistLength.busy||headSize.busy||!arms.enabled;
 return <>
  <ShoulderShapeTools owner={shoulders} blocked={blocked||legs.busy||arms.busy||waist.busy||length.busy||neck.busy||torso.busy||waistLength.busy||headSize.busy} workspaceOpen={workspace==='shoulder'} onWorkspaceOpen={open=>setWorkspace(open?'shoulder':null)}/>
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
  <section data-leg-length-workflow aria-label="长腿" data-feature-id="PC-32473" data-control-id="PC-32473-C-d79658697a" data-requirement-id="LNX-REF-PC-32473-C-d79658697a" data-tool-anchor="长腿">
   <p>长腿：整体同时设置大腿和小腿长度，也可分项调整。独立复核髋、膝、踝和完整脚部，不是瘦腿宽度、增高或全身 AI 塑形。</p>
   <span data-tool-anchor="长腿/大腿"/><span data-tool-anchor="长腿/小腿"/>
   <button type="button" disabled={lengthBlocked||length.busy} onClick={openLength}>打开腿长与当前来源图过渡区复核</button>
   {!length.supported&&<p role="status">配套腿长原生核心未就绪，不能应用。</p>}
   {length.busy&&<p role="status">{length.uncertain||length.state.phase==='uncertain'?'腿长结果待核对，不会重发。':'正在处理腿长请求。'}</p>}
   {(length.uncertain||length.state.phase==='uncertain')&&<button type="button" onClick={()=>void act(length.check)}>查询原腿长请求</button>}
   {length.message&&<p role="status">{length.message}</p>}
  </section>
  <section data-torso-length-workflow aria-label="上身长度" data-feature-id="PC-32473" data-control-id="PC-32473-C-f1662d2dec" data-requirement-id="LNX-REF-PC-32473-C-f1662d2dec" data-tool-anchor="上身长度">
   <p>上身长度：手动辅助 2D 局部实现。髋固定，上身沿肩髋方向缩短或拉长；完整头部与手臂需独立复核。不是腰部长度、3D 或全身 AI 塑形。</p>
   <button type="button" disabled={torsoBlocked||torso.busy} onClick={openTorso}>打开上身长度与当前来源图复核</button>
   {!torso.supported&&<p role="status">当前引擎未提供上身长度通信协议，请使用配套版本。</p>}
   {torso.supported&&!torso.coreAvailable&&<p role="status">{torso.unavailableReason}</p>}
   {torso.busy&&<p role="status">{torso.uncertain||torso.state.phase==='uncertain'?'上身长度结果待核对，不会重发。':'正在处理上身长度请求。'}</p>}
   {(torso.uncertain||torso.state.phase==='uncertain')&&<button type="button" onClick={()=>void act(torso.check)}>查询原上身长度请求</button>}
   {torso.message&&<p role="status">{torso.message}</p>}
  </section>
  <section data-waist-length-workflow aria-label="腰部长度" data-feature-id="PC-32473" data-control-id="PC-32473-C-5d33f285bb" data-requirement-id="LNX-REF-PC-32473-C-5d33f285bb" data-tool-anchor="腰部长度">
   <p>腰部长度：局部手动辅助 2D。独立标记左右上腰、下腰四点，向左缩短、向右拉长；上方完整上躯干、肩颈和头部一起移动，下腰线以下固定。不是上身长度、瘦腰或全身 AI 塑形。</p>
   <button type="button" disabled={waistLengthBlocked||waistLength.busy||headSize.busy} onClick={openWaistLength}>打开腰部长度与当前来源图复核</button>
   {!waistLength.supported&&<p role="status">当前引擎未提供腰部长度通信协议，请使用配套版本。</p>}
   {waistLength.supported&&!waistLength.coreAvailable&&<p role="status">{waistLength.unavailableReason}</p>}
   {waistLength.busy&&<p role="status">{waistLength.uncertain||waistLength.state.phase==='uncertain'?'腰部长度结果待核对，不会重发。':'正在处理腰部长度请求。'}</p>}
   {(waistLength.uncertain||waistLength.state.phase==='uncertain')&&<button type="button" onClick={()=>void act(waistLength.check)}>查询原腰部长度请求</button>}
   {waistLength.message&&<p role="status">{waistLength.message}</p>}
  </section>
  <section data-head-size-workflow aria-label="小头" data-feature-id="PC-32473" data-control-id="PC-32473-C-dc1b0ba40a" data-requirement-id="LNX-REF-PC-32473-C-dc1b0ba40a" data-tool-anchor="小头">
   <p>小头：独立标记完整头部及头发范围、中心与清晰过渡区。局部手动辅助 2D 缩小，不是小脸、自动头发分割或 3D 重建；长发接触肩膀、裁切或遮挡会拒绝。</p>
   <button type="button" disabled={headSizeBlocked||headSize.busy} onClick={openHeadSize}>打开小头与当前来源图复核</button>
   {!headSize.supported&&<p role="status">当前引擎未提供小头通信协议，请使用配套版本。</p>}
   {headSize.supported&&!headSize.coreAvailable&&<p role="status">{headSize.unavailableReason}</p>}
   {headSize.busy&&<p role="status">{headSize.uncertain||headSize.state.phase==='uncertain'?'小头结果待核对，不会重发。':'正在处理小头请求。'}</p>}
   {(headSize.uncertain||headSize.state.phase==='uncertain')&&<button type="button" onClick={()=>void act(headSize.check)}>查询原小头请求</button>}
   {headSize.message&&<p role="status">{headSize.message}</p>}
  </section>
  <section data-neck-workflow aria-label="脖子长度与宽度" data-feature-id="PC-32473" data-tool-anchor="脖子长度">
   <span data-tool-anchor="瘦脖子"/><p>脖子长度与宽度：完整头部头发连贯移动，左右宽度可独立解锁。不是天鹅颈。</p>
   <button type="button" disabled={neckBlocked||neck.busy} onClick={openNeck}>打开颈部长宽与当前来源图复核</button>
   {!neck.supported&&<p role="status">配套颈部原生核心未就绪，不能应用。</p>}
   {neck.busy&&<p role="status">颈部请求处理中或待核对，不会重发。</p>}
   {(neck.uncertain||neck.state.phase==='uncertain')&&<button type="button" onClick={()=>void act(neck.check)}>查询原颈部请求</button>}{neck.message&&<p role="status">{neck.message}</p>}
  </section>
  {workspace==='torso'&&<TorsoLengthWorkspace owner={torso} blocked={torsoBlocked} onClose={()=>setWorkspace(null)} onOpenBodyAnalysis={openShoulders}/>}
  {workspace==='waistLength'&&<WaistLengthWorkspace owner={waistLength} blocked={waistLengthBlocked} onClose={()=>setWorkspace(null)} onOpenBodyAnalysis={openShoulders}/>}
  {workspace==='headSize'&&<HeadSizeWorkspace owner={headSize} blocked={headSizeBlocked} onClose={()=>setWorkspace(null)} onOpenBodyAnalysis={openShoulders}/>}
  {workspace==='neck'&&<NeckWorkspace owner={neck} blocked={neckBlocked} onClose={()=>setWorkspace(null)} onOpenBodyAnalysis={openShoulders}/>}
  {workspace==='length' &&<LegLengthWorkspace owner={length} blocked={lengthBlocked} onClose={()=>setWorkspace(null)} onOpenBodyAnalysis={openShoulders}/>}
  {workspace==='waist'&&<WaistWorkspace owner={waist} blocked={waistBlocked} onClose={()=>setWorkspace(null)} onOpenBodyAnalysis={openShoulders}/>}
  {workspace==='leg'&&<div className="legWorkspace" role="dialog" aria-modal="true" aria-label="当前来源图腿部定位与可见轮廓调整">
   <div className="leg-toolbar"><b>腿部可见轮廓复核</b><span>这里显示未修饰的全图参考缩略图；关闭后在主画布查看结果。</span><button type="button" onClick={()=>setWorkspace(null)}>关闭定位窗口</button></div>
   <div className="leg-workspace-content">
    <button type="button" disabled={legBlocked||legs.busy} onClick={()=>void act(()=>legs.run('view'))}>刷新身体状态与当前来源图参考</button>
    {legs.view?<LegShapePanel view={legs.view} controller={legs.controller} sourceImage={legs.source} disabled={legBlocked||!!legs.task} onSelect={ref=>void act(()=>legs.run('select',ref))} onOpenBodyAnalysis={openShoulders}/>:<><p role="status">等待真实文档的身体状态，不会生成示意骨架。</p><button type="button" disabled={blocked||legs.busy||!shoulders.enabled} onClick={openShoulders}>打开真实身体定位与人物关联</button></>}
    {[legs.message,error].filter(Boolean).map((text,i)=><p role="alert" key={i}>{text}</p>)}
    {(legs.uncertain||legs.state.phase==='uncertain')&&<button type="button" onClick={()=>void act(legs.check)}>查询原请求结果，不重发</button>}
   </div>
  </div>}
  {workspace==='arm'&&<div className="legWorkspace" data-arm-workflow role="dialog" aria-modal="true" aria-label="当前来源图手臂定位与可见轮廓调整">
   <div className="leg-toolbar"><b>手臂源图复核</b><span>未修饰的全图参考，不是效果图。关闭不撤销已提交调整。</span><button type="button" onClick={()=>setWorkspace(null)}>关闭复核窗口</button></div>
   <div className="leg-workspace-content">
    <button type="button" disabled={armBlocked||arms.busy} onClick={()=>void act(()=>arms.run('view'))}>刷新身体状态与当前来源图参考</button>
    <button type="button" disabled={blocked||arms.busy||legs.busy||!shoulders.enabled} onClick={openShoulders}>打开真实身体定位与人物关联</button>
    {arms.view?<ArmShapePanel controller={arms.controller} transport={arms.transport} source={arms.source} disabled={armBlocked||!!arms.task||arms.proposalBusy} onSelectBody={ref=>void act(()=>arms.run('select',ref))}/>:<p role="status">等待当前照片的真实身体状态，不会从人脸框伪造手臂骨架。</p>}
    {[arms.message,error].filter(Boolean).map((text,i)=><p role="alert" key={i}>{text}</p>)}
    {(arms.uncertain||arms.state.phase==='uncertain')&&<button type="button" onClick={()=>void act(arms.check)}>查询原手臂请求，不重发</button>}
   </div>
  </div>}
 </>;
}
