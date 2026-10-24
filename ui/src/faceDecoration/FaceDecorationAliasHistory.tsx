// SPDX-License-Identifier: GPL-3.0-or-later
import {useState} from 'react';
import type {PeopleOwner} from '../people/usePeopleWorkflow';
export function FaceDecorationAliasHistory({people}:{people:PeopleOwner}){
 const history=people.decorationAliasHistory,[error,setError]=useState('');
 if(!history.batches.length)return null;
 async function run(work:()=>unknown){setError('');try{await work();}catch(cause){setError(String(cause));}}
 return <section aria-label="共享来源装饰原子历史"><h4>共享来源装饰历史</h4>
  <p>撤销、重做包含原批次全部共享来源成员，不只当前照片。依赖、成员或未打开历史不完整时仍拒绝，不能改为单张覆盖。</p>
  {history.batches.map(batch=><div key={batch.batch_id}><span>{batch.targets} 张 · {batch.undone?'已撤销':'已应用'} · {batch.batch_id}</span>
   <button type="button" disabled={!history.canUndo(batch.batch_id)} onClick={()=>void run(()=>history.undo(batch.batch_id))}>撤销完整批次</button>
   <button type="button" disabled={!history.canRedo(batch.batch_id)} onClick={()=>void run(()=>history.redo(batch.batch_id))}>重做完整批次</button>
  </div>)}
  {history.state.phase==='uncertain'&&<button type="button" onClick={()=>void run(history.query)}>查询原历史请求（不重发）</button>}
  {history.refreshError&&<><p role="alert">{history.refreshError}</p><button type="button" disabled={history.refreshing} onClick={()=>void run(history.refresh)}>刷新已确认的历史状态</button></>}
  {history.state.message&&<p role="status">{history.state.message}</p>}{error&&<p role="alert">{error}</p>}
 </section>;
}
