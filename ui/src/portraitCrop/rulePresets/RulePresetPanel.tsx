// SPDX-License-Identifier: GPL-3.0-or-later
import {useEffect, useState, useSyncExternalStore} from 'react';
import {RulePresetCatalogue} from './controller';
import {draftFromRules, type Entry} from './model';
import {PORTRAIT_CROP_CONTROLS, type RuleDraft} from '../model';
export type RulePresetPanelProps = {catalogue: RulePresetCatalogue; draft: RuleDraft; loadDisabled: boolean; onLoad: (draft: RuleDraft) => void};
const summary = (entry: Entry) => `宽高比 ${entry.rules.aspect_ratio}；头顶留白 ${entry.rules.headroom_fraction}；头部占比 ${entry.rules.head_fraction}；水平位置 ${entry.rules.horizontal_position}`;
export function RulePresetPanel({catalogue, draft, loadDisabled, onLoad}: RulePresetPanelProps) {
  const state = useSyncExternalStore(catalogue.subscribe, catalogue.snapshot, catalogue.snapshot);
  const [selected, setSelected] = useState(''), [name, setName] = useState(''), [error, setError] = useState('');
  const [confirmation, setConfirmation] = useState<{action: 'delete' | 'update'; id: string; revision: number; draft: RuleDraft} | null>(null);
  useEffect(() => {void catalogue.refresh();}, [catalogue]);
  useEffect(() => {setConfirmation(null);}, [state.catalogue?.catalogue_id, state.catalogue?.revision, selected, draft]);
  const entry = state.catalogue?.entries.find(item => item.id === selected);
  const blocked = state.busy || !!state.uncertain || !state.catalogue;
  const action = (fn: () => unknown | Promise<unknown>) => {setError(''); try {void Promise.resolve(fn()).catch(error => setError(error instanceof Error ? error.message : '预设操作未完成。'));} catch (error) {setError(error instanceof Error ? error.message : '预设操作未完成。');}};
  function confirm() {
    const pending = confirmation; setConfirmation(null);
    if (!pending || !entry || pending.id !== entry.id || pending.revision !== state.catalogue?.revision) {setError('确认已失效，请重新选择预设。'); return;}
    action(() => pending.action === 'delete' ? catalogue.delete(pending.id) : catalogue.update(pending.id, pending.draft));
  }
  return <section className="portrait-crop-rule-presets" data-control-id={PORTRAIT_CROP_CONTROLS.presets} aria-label="人像构图规则预设">
    <h3>构图规则预设 · 本机目录</h3>
    <p>仅保存名称及四项构图比例。不保存照片、人脸身份、头顶/下巴锚点、裁剪框或已审核状态。载入只改草稿，不会裁剪照片；每张照片仍须实测真实锚点、重新生成并审核候选。</p>
    <button type="button" disabled={state.busy} onClick={() => action(() => catalogue.refresh())}>{state.busy ? '目录操作进行中…' : '刷新规则目录 / 核对原结果'}</button>
    {state.catalogue && <small>本机目录修订 {state.catalogue.revision} · {state.catalogue.entries.length}/256 项 · 不与普通裁剪预设互相转换</small>}
    <fieldset disabled={blocked}>
      <legend>选择规则，不自动载入</legend>
      <label>已保存预设<select value={entry ? selected : ''} onChange={event => {const id = event.currentTarget.value; setSelected(id); setName(state.catalogue?.entries.find(item => item.id === id)?.name ?? ''); setError('');}}>
        <option value="">请选择预设</option>{state.catalogue?.entries.map(item => <option key={item.id} value={item.id}>{item.name}</option>)}
      </select></label>
      {entry && <p>{summary(entry)}</p>}
      <label>新建或重命名名称<input type="text" value={name} maxLength={128} onChange={event => setName(event.currentTarget.value)} autoComplete="off"/><small>1–64 个可见字符，最多 192 UTF-8 字节；区分大小写，同名不覆盖。</small></label>
      <div className="portrait-crop-actions">
        <button type="button" onClick={() => action(() => catalogue.create(name, draft))}>将当前四项草稿另存为新规则</button>
        <button type="button" disabled={!entry} onClick={() => action(() => catalogue.rename(selected, name))}>仅重命名所选规则</button>
        <button type="button" disabled={!entry || loadDisabled} onClick={() => action(() => {if (entry) onLoad(draftFromRules(entry.rules));})}>载入为草稿，不应用</button>
        <button type="button" disabled={!entry} onClick={() => setConfirmation({action: 'update', id: selected, revision: state.catalogue!.revision, draft: structuredClone(draft)})}>用当前四项草稿更新所选规则…</button>
        <button type="button" disabled={!entry} onClick={() => setConfirmation({action: 'delete', id: selected, revision: state.catalogue!.revision, draft: structuredClone(draft)})}>删除所选规则…</button>
      </div>
      {confirmation && entry && <div role="group" aria-label="明确确认预设变更" className="portrait-crop-notice">
        <p>{confirmation.action === 'delete' ? `确认永久删除本机规则“${entry.name}”？只删除目录项目，不会撤销或改变照片。` : `确认用当前四项草稿替换“${entry.name}”的规则数值？不是另存为，也不会应用到照片。`}</p>
        {confirmation.action === 'update' && <p>宽高比 {confirmation.draft.aspect_ratio}；头顶留白 {confirmation.draft.headroom_fraction}；头部占比 {confirmation.draft.head_fraction}；水平位置 {confirmation.draft.horizontal_position}</p>}
        <button type="button" onClick={confirm}>{confirmation.action === 'delete' ? '确认删除此规则' : '确认更新此规则'}</button><button type="button" onClick={() => setConfirmation(null)}>取消，不修改目录</button>
      </div>}
    </fieldset>
    {state.message && <p role={state.uncertain ? 'alert' : 'status'}>{state.message}</p>}
    {error && <p role="alert">{error}</p>}
  </section>;
}
