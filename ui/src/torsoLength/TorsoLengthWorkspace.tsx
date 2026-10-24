// SPDX-License-Identifier: GPL-3.0-or-later
import {useState} from 'react';
import {TorsoLengthPanel} from './TorsoLengthPanel';
import type {TorsoLengthOwner} from './useTorsoLengthWorkflow';
export function TorsoLengthWorkspace({owner,blocked,onClose,onOpenBodyAnalysis}:{owner:TorsoLengthOwner;blocked:boolean;onClose:()=>void;onOpenBodyAnalysis:()=>void}){
 const [error,setError]=useState('');
 const act=(fn:()=>Promise<unknown>)=>{setError('');void fn().catch(e=>setError(e instanceof Error?e.message:'操作未完成。'));};
 return <div className="torsoLengthWorkspace" data-torso-length-workflow role="dialog" aria-modal="true" aria-label="上身长度当前来源图独立复核">
  <div className="torso-length-toolbar"><b>上身长度 · 手动辅助 2D</b><span>未修饰的全图参考缩略图，不是效果图；关闭后在主画布查看结果。</span><button type="button" onClick={onClose}>关闭复核窗口</button></div>
  <div className="torso-length-workspace-content">
   {!owner.supported&&<p role="status">当前引擎未提供上身长度通信协议，请使用配套版本。</p>}
   {owner.supported&&!owner.coreAvailable&&<p role="status">{owner.unavailableReason}</p>}
   <button type="button" disabled={blocked||owner.busy||!owner.enabled} onClick={()=>act(()=>owner.run('view'))}>刷新身体状态与当前来源图参考</button>
   {owner.view?<TorsoLengthPanel view={owner.view} controller={owner.controller} sourceImage={owner.source} coreAvailable={owner.coreAvailable} disabled={blocked||!!owner.task||!owner.enabled} onSelect={ref=>act(()=>owner.run('select',ref))} onOpenBodyAnalysis={onOpenBodyAnalysis}/>:<><p role="status">等待实际肩髋定位，不会用人脸框生成躯干或补齐隐藏轮廓。</p><button type="button" disabled={blocked||owner.busy} onClick={onOpenBodyAnalysis}>打开真实身体定位与人物关联</button></>}
   {error&&<p role="alert">{error}</p>}{owner.message&&<p role="alert">{owner.message}</p>}
   {(owner.uncertain||owner.state.phase==='uncertain')&&<button type="button" onClick={()=>act(owner.check)}>查询原上身长度请求，不重发</button>}
  </div>
 </div>;
}
