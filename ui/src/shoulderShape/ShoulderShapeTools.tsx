// SPDX-License-Identifier: GPL-3.0-or-later
import {useEffect,useState} from 'react';
import {BodyPoseOverlay} from './BodyPoseOverlay';
import {ShoulderShapePanel} from './ShoulderShapePanel';
import {refKey,type BodyRef} from './model';
import type {ShoulderOwner} from './useShoulderWorkflow';
import './shoulderShape.css';
/** Isolated original-source workspace: never place canonical points on an edited frame. */
export function ShoulderShapeTools({owner,blocked=false,workspaceOpen,onWorkspaceOpen}:{owner:ShoulderOwner;blocked?:boolean;workspaceOpen?:boolean;onWorkspaceOpen?:(open:boolean)=>void}){
 const [localOpen,setLocalOpen]=useState(false),[loaded,setLoaded]=useState(false),[candidate,setCandidate]=useState<BodyRef|null>(null),[confirmed,setConfirmed]=useState(false),[error,setError]=useState('');
 const source=owner.source,view=owner.view;
 const open=workspaceOpen??localOpen;
 const setOpen=(value:boolean)=>{setLocalOpen(value);onWorkspaceOpen?.(value);};
 const sourceKey=source?`${view?.binding.document_epoch}:${view?.binding.document_id}:${source.source_sha256}`:'';
 useEffect(()=>{setLoaded(false);setCandidate(null);setConfirmed(false);},[sourceKey]);
 useEffect(()=>{setCandidate(null);setConfirmed(false);},[owner.candidates?.run_id]);
 const act=async(work:()=>Promise<unknown>)=>{setError('');try{await work();}catch(e){setError(e instanceof Error?e.message:'操作未完成');}};
 const available=owner.enabled&&!blocked;
 const launch=()=>{setOpen(true);void act(()=>owner.run('view'));};
 const choose=(ref:BodyRef)=>void act(()=>owner.run('select',ref));
 const candidateVisible=!!owner.candidates?.bodies.length;
 return <section aria-label="直角肩与肩膀宽度" data-feature-id="PC-32473">
  <p>直角肩与肩膀宽度：在原图上检测并逐一复核身体，不借用人脸身份。</p>
  <button type="button" disabled={!available||owner.busy} onClick={launch}>打开肩部调整与原图定位</button>
  {!owner.supported&&<p role="status">当前引擎未声明肩部协议，请使用配套引擎。</p>}
  {owner.acquisition.busy&&<p role="status">{owner.acquisition.task?.result.downloaded_bytes!==undefined?`已接收 ${owner.acquisition.task.result.downloaded_bytes} / ${owner.acquisition.task.result.total_bytes??'?'} 字节，完成校验前不能使用。`:'正在获取可选模型，尚未验证完成。'}</p>}
  {owner.acquisition.message&&<p role="status">{owner.acquisition.message}</p>}
  {owner.acquisition.busy&&<button type="button" onClick={()=>void act(owner.acquisition.cancel)}>取消可选模型获取</button>}
  {owner.acquisition.uncertain&&<button type="button" onClick={()=>void act(owner.acquisition.check)}>查询模型获取状态</button>}
  {owner.busy&&<p role="status">{owner.uncertain?'肩部结果待确认，不会重发。':owner.task==='analyse'?'正在原图上检测身体定位。':'肩部请求正在处理。'}</p>}
  {(owner.uncertain||owner.state.phase==='uncertain')&&<button type="button" onClick={()=>void act(owner.check)}>查询原请求结果</button>}
  {[owner.message,error].filter(Boolean).map((text,index)=><p role="status" key={index}>{text}</p>)}
  {open&&<div className="shoulderWorkspace" role="dialog" aria-modal="true" aria-label="原图肩部定位与调整">
   <div className="shoulderToolbar"><b>原图定位复核</b><span>下方是未修饰的原图定位参考；关闭后在主画布查看变形结果。</span><button type="button" onClick={()=>setOpen(false)}>关闭定位窗口</button></div>
   <div className="shoulderContent"><div className="shoulderSourcePane">
    {source&&view?<div className="shoulderSource" style={{aspectRatio:`${source.width} / ${source.height}`}}>
     <img key={sourceKey} alt="当前照片未经修饰的原图定位参考" src={`data:${source.mime};base64,${source.base64}`} onLoad={()=>setLoaded(true)} onError={()=>{setLoaded(false);setError('原图定位参考无法显示，不能确认锚点。');}}/>
     {loaded&&<BodyPoseOverlay bodies={candidateVisible?owner.candidates!.bodies:view.bodies} selected={candidateVisible?candidate:view.selected_body_ref} onSelect={ref=>{if(owner.busy||!available)return;if(candidateVisible){setCandidate(ref);setConfirmed(false);}else choose(ref);}}/>}
    </div>:<p role="status">尚未取得与当前照片匹配的原图定位参考。</p>}
    {candidateVisible&&<div className="shoulderCandidates"><p>这是本次重新检测得到的实际候选，不会按距离自动对应旧身体。先在右侧选择保留配方的旧目标，再选择此图中对应的新定位。</p>
     <button type="button" disabled={owner.busy} onClick={owner.dismissCandidates}>取消本次定位替换，查看现有身体</button>
     {owner.candidates!.bodies.map((body,index)=><button type="button" key={refKey(body.body_ref)} disabled={!available||owner.busy||!loaded} aria-pressed={refKey(candidate)===refKey(body.body_ref)} onClick={()=>{setCandidate(body.body_ref);setConfirmed(false);}}>新定位 {index+1}</button>)}
     <label><input type="checkbox" checked={confirmed} disabled={!candidate||!view?.selected_body_ref||owner.busy} onChange={e=>setConfirmed(e.currentTarget.checked)}/>我确认所选新定位属于右侧选中的旧身体；保留参数，并清除旧锚点复核及人物关联。</label>
     <button type="button" disabled={!available||owner.busy||!loaded||!confirmed||!candidate||!view?.selected_body_ref} onClick={()=>void act(()=>owner.run('reanalyse',view!.selected_body_ref!,candidate!))}>用所选新定位替换当前身体观察</button>
    </div>}
   </div><aside className="shoulderControls">
    {owner.acquisition.busy&&<div role="status"><p>可选模型正在获取和校验，完成前不会启用检测。{owner.acquisition.task?.result.downloaded_bytes!==undefined?` 已接收 ${owner.acquisition.task.result.downloaded_bytes} 字节。`:''}</p><button type="button" onClick={()=>void act(owner.acquisition.cancel)}>取消可选模型获取</button></div>}
    {owner.acquisition.message&&<p role="status">{owner.acquisition.message}</p>}
    {owner.acquisition.uncertain&&<button type="button" onClick={()=>void act(owner.acquisition.check)}>查询模型获取状态</button>}
    <button type="button" disabled={!available||owner.busy} onClick={()=>void act(()=>owner.run('view'))}>刷新当前身体状态与原图</button>
    {view&&<ShoulderShapePanel view={view} controller={owner.controller} disabled={!available||!!owner.task||owner.acquisition.busy} model={owner.model} reviewAvailable={loaded&&!candidateVisible} onSelect={choose} onAnalyse={()=>owner.run('analyse')} onInstall={owner.acquisition.install}/>}
    {!view&&<p role="status">等待真实文档身体状态，不会生成示意骨架。</p>}
    {[owner.message,error].filter(Boolean).map((text,index)=><p role="alert" key={index}>{text}</p>)}
    {(owner.uncertain||owner.state.phase==='uncertain')&&<button type="button" onClick={()=>void act(owner.check)}>查询原请求结果，不重发</button>}
   </aside></div>
  </div>}
 </section>;
}
