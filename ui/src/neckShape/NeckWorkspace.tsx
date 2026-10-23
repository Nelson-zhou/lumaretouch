// SPDX-License-Identifier: GPL-3.0-or-later
import {useState} from 'react';
import {NeckShapePanel} from './NeckShapePanel';
import type {NeckOwner} from './useNeckWorkflow';
export function NeckWorkspace({owner,blocked,onClose,onOpenBodyAnalysis}:{owner:NeckOwner;blocked:boolean;onClose:()=>void;onOpenBodyAnalysis:()=>void}){
 const [error,setError]=useState('');
 const act=(fn:()=>Promise<unknown>)=>{setError('');void fn().catch(e=>setError(e instanceof Error?e.message:'操作未完成。'));};
 return <div className="legLengthWorkspace" data-neck-workflow role="dialog" aria-modal="true" aria-label="当前来源图颈部长宽定位与可见轮廓调整">
  <div className="leg-length-toolbar"><b>颈部长宽源图复核</b><span>这里是未修饰的当前来源图参考，关闭后在主画布查看结果。</span><button type="button" onClick={onClose}>关闭复核窗口</button></div>
  <div className="leg-length-workspace-content">
   <button type="button" disabled={blocked||owner.busy} onClick={()=>act(()=>owner.run('view'))}>刷新身体状态与当前来源图参考</button>
   {owner.view?<NeckShapePanel view={owner.view} controller={owner.controller} sourceImage={owner.source} disabled={blocked||!!owner.task} onSelect={ref=>act(()=>owner.run('select',ref))} onOpenBodyAnalysis={onOpenBodyAnalysis}/>:<><p role="status">等待实际身体定位，不会生成示意颈部长宽。</p><button type="button" disabled={blocked||owner.busy} onClick={onOpenBodyAnalysis}>打开真实身体定位</button></>}
   {error&&<p role="alert">{error}</p>}
   {owner.message&&<p role="alert">{owner.message}</p>}{(owner.uncertain||owner.state.phase==='uncertain')&&<button type="button" onClick={()=>act(owner.check)}>查询原颈部长宽请求，不重发</button>}
  </div>
 </div>;
}
