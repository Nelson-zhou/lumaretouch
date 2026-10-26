// SPDX-License-Identifier: GPL-3.0-or-later
import {useEffect, useState} from 'react';
import {semanticIntent, type SemanticArchive} from './semanticArchive';

export function SemanticArchiveSummary({archive}: {archive?: SemanticArchive}) {
  const intent = archive ? semanticIntent(archive) : null;
  if (!archive || !intent) return <p>尚未取得完整 .lrtcolour 的宿主验证身份；不能授权启动。</p>;
  return <div>
    <p>{archive.path}<br/>归档 {archive.file_sha256} · {archive.file_bytes} 字节<br/>便携意图 {archive.intent_sha256}</p>
    <p>样片资产 {intent.reference.asset_id}<br/>原始渲染 {intent.reference.render_sha256}<br/>源图 {intent.reference.source.sha256}</p>
    <p>{intent.mode === 'extreme' ? '极致' : '和谐'} · 总开关 {intent.enabled ? '开启' : '关闭'} · 整体／影调／色彩 {intent.strengths.join(' / ')}</p>
    <p>明确请求分组：{intent.groups.map(group => `${group.id}（${group.enabled ? '开启' : '关闭'}）`).join('、')}。关闭组也必须在每张目标中具备真实共同支持；不自动丢弃分组。</p>
    <details><summary>完整冻结便携意图与全部样片身份（含逐组手动偏移）</summary>
      <pre className="local-workflow-profile">{JSON.stringify(intent, null, 2)}</pre>
    </details>
  </div>;
}
export function SemanticArchivePicker({archive, onSelect}: {archive?: SemanticArchive; onSelect: (path: string) => void}) {
  const [path, setPath] = useState(archive?.path ?? '');
  useEffect(() => {setPath(archive?.path ?? '');}, [archive?.path]);
  return <section aria-label="选择自动语义追色归档">
    <label>已导出的 .lrtcolour 文件（绝对路径）<input value={path} spellCheck={false}
      placeholder="/presets/reference.lrtcolour" onChange={event => setPath(event.currentTarget.value)}/></label>
    <button type="button" disabled={!path.startsWith('/') || !/\.lrtcolour$/i.test(path)} onClick={() => onSelect(path)}>验证并选择完整归档</button>
    <small>包含完整样片照片。这里只验证文件及便携意图，不推理或应用；修改路径输入本身不会替换已选归档。检测时保留精确归档字节，启动授权后才分析。</small>
    <SemanticArchiveSummary archive={archive}/>
  </section>;
}
