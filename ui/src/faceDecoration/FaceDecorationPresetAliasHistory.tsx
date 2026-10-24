// SPDX-License-Identifier: GPL-3.0-or-later
import {useState} from 'react';
import type {PeopleOwner} from '../people/usePeopleWorkflow';
export function FaceDecorationPresetAliasHistory({people}:{people:PeopleOwner}){
 const history=people.decorationPresetAliasHistory,[error,setError]=useState('');
 if(!history.batches.length)return null;
 async function run(work:()=>unknown){setError('');try{await work();}catch(cause){setError(String(cause));}}
 return <section aria-label="脸部装饰混合预设共享来源全成员历史"><h4>脸部装饰混合预设共享来源全成员历史</h4>
  <p>统一撤销或重做原当前照片的完整所选配方及全部共享来源成员的人像图。其他成员的裁切、色彩和修复保留，不使用当前照片本地撤销。缺少原成员、支持或准确台账时拒绝，不降级为单张恢复。</p>
  {history.batches.map(batch=><div key={batch.batch_id}><span>{batch.targets} 张 · {batch.undone?'已撤销':'已应用'} · {batch.batch_id}</span>
   <button type="button" disabled={!history.canUndo(batch.batch_id)} onClick={()=>void run(()=>history.undo(batch.batch_id))}>撤销完整批次</button>
   <button type="button" disabled={!history.canRedo(batch.batch_id)} onClick={()=>void run(()=>history.redo(batch.batch_id))}>重做完整批次</button>
  </div>)}
  {history.state.phase==='uncertain'&&<button type="button" onClick={()=>void run(history.query)}>查询原历史请求（不重发）</button>}
  {history.needsRefresh&&!history.refreshError&&<><p role="status">历史回执已确认，仍需核对全部成员的新状态。</p><button type="button" disabled={history.refreshing} onClick={()=>void run(history.refresh)}>读取完整历史成员状态（不重复撤销或重做）</button></>}
  {history.refreshError&&<><p role="alert">{history.refreshError}</p><button type="button" disabled={history.refreshing} onClick={()=>void run(history.refresh)}>刷新已确认的历史状态</button></>}
  {history.state.message&&<p role="status">{history.state.message}</p>}{error&&<p role="alert">{error}</p>}
 </section>;
}
