// SPDX-License-Identifier: GPL-3.0-or-later
import {useState} from 'react';
import {HeadSizePanel} from './HeadSizePanel';
import type {HeadSizeOwner} from './useHeadSizeWorkflow';
export function HeadSizeWorkspace({owner,blocked,onClose,onOpenBodyAnalysis}:{owner:HeadSizeOwner;blocked:boolean;onClose:()=>void;onOpenBodyAnalysis:()=>void}){
 const [error,setError]=useState('');
 const act=(fn:()=>Promise<unknown>)=>{setError('');void fn().catch(e=>setError(e instanceof Error?e.message:'操作未完成。'));};
 return <div className="headSizeWorkspace" data-head-size-workflow role="dialog" aria-modal="true" aria-label="小头含完整头发的来源图人工复核">
  <div className="head-size-toolbar"><b>小头 · 含完整头发 · 手动辅助 2D</b><span>这里是未变形的全图参考缩略图，不是效果预览；关闭后在主画布查看已发布结果。</span><button type="button" onClick={onClose}>关闭复核窗口</button></div>
  <div className="head-size-workspace-content">
   {!owner.supported&&<p role="status">当前引擎未提供小头通信协议，请使用配套版本。</p>}
   {owner.supported&&!owner.coreAvailable&&<p role="status">{owner.unavailableReason}</p>}
   <button type="button" disabled={blocked||owner.busy||!owner.enabled} onClick={()=>act(()=>owner.run('view'))}>刷新身体、本人脸部与当前来源图参考</button>
   {owner.view?<HeadSizePanel view={owner.view} controller={owner.controller} sourceImage={owner.source} coreAvailable={owner.coreAvailable} disabled={blocked||!!owner.task||!owner.enabled} onSelect={ref=>act(()=>owner.run('select',ref))} onOpenBodyAnalysis={onOpenBodyAnalysis}/>:<><p role="status">需要真实身体定位与当前本人脸部关联，不会从人脸框生成头发范围或自动缩小中心。</p><button type="button" disabled={blocked||owner.busy} onClick={onOpenBodyAnalysis}>打开真实身体定位与人物关联</button></>}
   {error&&<p role="alert">{error}</p>}{owner.message&&<p role="alert">{owner.message}</p>}
   {(owner.uncertain||owner.state.phase==='uncertain')&&<button type="button" onClick={()=>act(owner.check)}>查询原小头请求，不重发</button>}
  </div>
 </div>;
}
