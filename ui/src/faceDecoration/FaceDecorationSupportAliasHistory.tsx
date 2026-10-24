// SPDX-License-Identifier: GPL-3.0-or-later
import {useState} from 'react';
import type {PeopleOwner} from '../people/usePeopleWorkflow';
export function FaceDecorationSupportAliasHistory({people}: {people: PeopleOwner}) {
  const history = people.decorationSupportAliasHistory, [error, setError] = useState('');
  if (!history.batches.length) return null;
  async function run(work: () => unknown) {setError(''); try {await work();} catch (cause) {setError(String(cause));}}
  return <section aria-label="共享来源装饰范围原子历史"><h4>共享来源装饰范围历史</h4>
    <p>这不是图案或程度历史。撤销、重做同时恢复原批次全部成员的人物图指针和完整支持状态；缺少成员、旧支持或准确台账时拒绝，不回退到单张。</p>
    {history.batches.map(batch => <div key={batch.batch_id}><span>{batch.targets} 张 · {batch.undone ? '范围已撤销' : '范围已应用'} · {batch.batch_id}</span>
      <button type="button" disabled={!history.canUndo(batch.batch_id)} onClick={() => void run(() => history.undo(batch.batch_id))}>撤销完整范围批次</button>
      <button type="button" disabled={!history.canRedo(batch.batch_id)} onClick={() => void run(() => history.redo(batch.batch_id))}>重做完整范围批次</button>
    </div>)}
    {history.state.phase === 'uncertain' && <button type="button" onClick={() => void run(history.query)}>查询原范围历史请求（不重发）</button>}
    {history.refreshError && <><p role="alert">{history.refreshError}</p><button type="button" disabled={history.refreshing} onClick={() => void run(history.refresh)}>刷新已确认的范围历史</button></>}
    {history.state.message && <p role="status">{history.state.message}</p>}{error && <p role="alert">{error}</p>}
  </section>;
}
