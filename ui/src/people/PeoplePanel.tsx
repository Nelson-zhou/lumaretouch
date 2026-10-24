// SPDX-License-Identifier: GPL-3.0-or-later
import {useEffect, useRef, useState} from 'react';
import {PEOPLE_CONTROL_IDS as IDS, sourceLabel, restoreInheritance, canSelectFace, targetLabel, operationLabel,
  type FaceChoice, type FaceRef, type LinkState, type PeopleAction, type PeopleScope, type PeopleTarget} from './model';
import type {PeopleOwner} from './usePeopleWorkflow';
import {OPERATION_ID as EYE_BAGS} from '../eyeBagPreserve/model';
import './people.css';

type Props = {owner: PeopleOwner; busy: boolean; thumb?: string; onFaceAdd: () => void; faceAdding: boolean};
function FaceAvatar({face, thumb}: {face: FaceChoice; thumb?: string}) {
  if (!thumb) return <i className="faceAv ph">人</i>;
  const [x0, y0, x1, y1] = face.box;
  const width = Math.max(.06, Math.min(1, x1 - x0)), height = Math.max(.06, Math.min(1, y1 - y0));
  const x = width < .999 ? Math.max(0, Math.min(100, x0 / (1 - width) * 100)) : 50;
  const y = height < .999 ? Math.max(0, Math.min(100, y0 / (1 - height) * 100)) : 50;
  return <i className="faceAv" style={{backgroundImage: `url(data:image/jpeg;base64,${thumb})`,
    backgroundSize: `${100 / width}% ${100 / height}%`, backgroundPosition: `${x}% ${y}%`}}/>;
}

/** Engine-selected cursor and scope, with unsaved form drafts kept separate. */
export function PeoplePanel({owner, busy, thumb, onFaceAdd, faceAdding}: Props) {
  const value = owner.value;
  const [error, setError] = useState('');
  const [label, setLabel] = useState(''), [groupName, setGroupName] = useState('');
  const [groupPriority, setGroupPriority] = useState(0), [members, setMembers] = useState<string[]>([]);
  const [box, setBox] = useState<[number, number, number, number]>([.25, .25, .75, .75]);
  const [person, setPerson] = useState(''), [editingGroup, setEditingGroup] = useState('');
  const context = `${value?.binding.document_id ?? ''}:${value?.binding.document_epoch ?? ''}`;
  const current = useRef(context); current.current = context;
  useEffect(() => {
    setError(''); setMembers([]); setPerson(''); setLabel(''); setEditingGroup(''); setGroupName(''); setGroupPriority(0);
  }, [context]);
  const face = value?.faces.find(item => item.face_ref.face_instance_id === value.selected_face_id);
  useEffect(() => {setLabel(String(face?.labels?.user_group ?? ''));}, [face?.face_ref.face_instance_id, face?.labels?.user_group]);
  if (!value) return <section className="peoplePanel" aria-label="人物与分组">
    <p role="status">{owner.supported ? '打开照片并完成人物分析后，此处显示引擎确认的人物状态。' : '当前引擎未提供人物编辑协议，请使用配套版本。'}</p>
  </section>;
  const target = (scope: PeopleScope, id: string | null, ref: FaceRef | null = null): PeopleTarget => ({scope, target_id: id, face_ref: ref});
  const faceTarget = face ? target('face', face.face_ref.face_instance_id, face.face_ref) : null;
  const allTarget = target('all_people', value.binding.asset_sha256);
  const disabled = busy || owner.state.pending || owner.state.uncertain || !owner.enabled;
  const submit = async (action: PeopleAction['action'], payload: Record<string, unknown>, to: PeopleTarget | null = faceTarget) => {
    if (disabled || !to) return;
    const captured = current.current; setError('');
    try {await owner.submit(action, payload, to);}
    catch (reason) {if (captured === current.current) setError(String(reason));}
  };
  const link = (state: LinkState, personId = person) => face && void submit('link', {
    face_instance_id: face.face_ref.face_instance_id, person_id: personId, state, user_confirmed: true});
  const validBox = box.every(n => Number.isFinite(n) && n >= 0 && n <= 1) && box[0] < box[2] && box[1] < box[3];
  const isTarget = (scope: PeopleScope, id: string | null) => value.editing_target?.scope === scope && value.editing_target.target_id === id;
  return <section aria-label="人物与分组" className="peoplePanel">
    <div className="faceHead"><span>人物与分组</span><em>{value.faces.length} 人</em></div>
    <p>人物选择只改变编辑光标；所有已启用人脸保留各自效果。分组标签不是身份事实。</p>
    <div data-control-id={IDS.single} className="faceChips" role="group" aria-label="选择人物">
      {value.faces.map((item, index) => <button type="button" key={item.face_ref.face_instance_id}
        className={`faceChip${item.face_ref.face_instance_id === value.selected_face_id ? ' on' : ''}`}
        disabled={!canSelectFace(item, disabled)} aria-pressed={item.face_ref.face_instance_id === value.selected_face_id}
        onClick={() => void submit('select', {}, target('face', item.face_ref.face_instance_id, item.face_ref))}>
        <FaceAvatar face={item} thumb={thumb}/><span>人物 {index + 1}{item.manual ? ' · 人工' : ''}
          {!item.enabled ? ' · 已禁用' : ''}{item.analysis_status !== 'verified' ? ' · 待分析' : ''}</span>
      </button>)}
    </div>
    <button type="button" data-control-id={IDS.all} disabled={disabled} aria-pressed={isTarget('all_people', value.binding.asset_sha256)}
      onClick={() => void submit('target', {}, allTarget)}>编辑本照片全部人物默认</button>
    <p role="status">当前编辑范围：{targetLabel(value)}。仅改动明确调整的参数，不清除已有逐项覆盖。</p>
    {value.editing_target?.scope !== 'face' && <p>下方人像滑块显示所选人脸的有效预览值，并非共享默认值。调整某一项会写入当前编辑范围，其他项保留继承。</p>}
    {face && <details data-guide-category-editor data-control-id={IDS.detectionCorrection}><summary>纠正检测与人工标签</summary>
      <button type="button" data-control-id={IDS.addDisableFace} disabled={disabled}
        onClick={() => void submit('face_status', {enabled: !face.enabled})}>{face.enabled ? '禁用误检（保留历史）' : '重新启用此脸'}</button>
      {face.analysis_status !== 'verified' && <button type="button" disabled={disabled}
        onClick={() => void submit('analyse_face', {})}>分析此人脸区域</button>}
      <label data-control-id={IDS.editableLabels}>用户分组标签<input value={label} maxLength={128}
        onChange={event => setLabel(event.currentTarget.value)} disabled={disabled}/></label>
      <button type="button" disabled={disabled} onClick={() => void submit('face_status', {labels: {...face.labels, user_group: label}})}>保存标签</button>
      <label>人工年龄分组<select value={String(face.labels?.age_band ?? '未标注')} disabled={disabled}
        onChange={event => void submit('face_status', {labels: {...face.labels, age_band: event.currentTarget.value}})}>
        {['未标注', '成人', '儿童'].map(name => <option key={name}>{name}</option>)}</select></label>
      <label>人工性别分组<select value={String(face.labels?.gender_label ?? '未标注')} disabled={disabled}
        onChange={event => void submit('face_status', {labels: {...face.labels, gender_label: event.currentTarget.value}})}>
        {['未标注', '男', '女'].map(name => <option key={name}>{name}</option>)}</select></label>
      <p>这些是用户自定修图标签，不是自动年龄、性别或身份判断，也不会自行确认跨照片关联。</p>
    </details>}
    <details data-control-id={IDS.labels}><summary>用户分组与联动默认</summary><fieldset disabled={disabled}>
      {Object.entries(value.groups).map(([id, group]) => <button type="button" key={id} aria-pressed={isTarget('group', id)}
        onClick={() => void submit('target', {}, target('group', id))}>{group.label} · 优先级 {group.priority}</button>)}
      <label>编辑已有分组<select value={editingGroup} onChange={event => {
        const id = event.currentTarget.value, group = value.groups[id]; setEditingGroup(id);
        setGroupName(group?.label ?? ''); setGroupPriority(group?.priority ?? 0);
        const currentFaces = new Set(value.faces.map(item => item.face_ref.face_instance_id));
        setMembers((group?.face_ids ?? []).filter(id => currentFaces.has(id)));
      }}><option value="">建立新分组</option>{Object.entries(value.groups).map(([id, group]) => <option key={id} value={id}>{group.label}</option>)}</select></label>
      <label>分组名称<input value={groupName} onChange={event => setGroupName(event.currentTarget.value)} maxLength={128}/></label>
      <label>优先级<input type="number" value={groupPriority} onChange={event => setGroupPriority(event.currentTarget.valueAsNumber)}/></label>
      {value.faces.map((item, index) => <label key={item.face_ref.face_instance_id}><input type="checkbox" checked={members.includes(item.face_ref.face_instance_id)}
        onChange={event => {const checked = event.currentTarget.checked;
          setMembers(old => checked ? [...old, item.face_ref.face_instance_id] : old.filter(id => id !== item.face_ref.face_instance_id));}}/>人物 {index + 1}</label>)}
      <button type="button" data-control-id={IDS.linkedGroups} disabled={!groupName.trim() || !Number.isSafeInteger(groupPriority)}
        onClick={() => void submit('group', {group_id: editingGroup || crypto.randomUUID(), label: groupName.trim(), priority: groupPriority,
          face_ids: [...(value.groups[editingGroup]?.face_ids ?? []).filter(id => !value.faces.some(item => item.face_ref.face_instance_id === id)), ...members]}, allTarget)}>
        {editingGroup ? '保存成员和优先级' : '建立联动分组'}</button>
      <p>组默认只影响明确加入组的脸，包括其他照片。此处保留其他照片成员。同优先级冲突暂停该项，不按创建顺序猜测。</p>
    </fieldset></details>
    <details><summary>匿名跨照片关联</summary><fieldset disabled={disabled}>
      <button type="button" onClick={() => void submit('create_person', {}, allTarget)}>建立匿名人物关联</button>
      <label>选择匿名人物<select value={person} onChange={event => setPerson(event.currentTarget.value)}><option value="">请选择</option>
        {Object.keys(value.persons).map((id, index) => <option key={id} value={id}>匿名人物 {index + 1}</option>)}</select></label>
      <button type="button" disabled={!person} onClick={() => void submit('target', {}, target('person', person))}>编辑此匿名人物默认（仅确认关联生效）</button>
      <button type="button" disabled={!face || !person} onClick={() => link('confirmed')}>确认此脸属于所选匿名人物</button>
      {value.links.filter(item => item.face_instance_id === value.selected_face_id).map(item => <div key={item.person_id}>
        <span>匿名人物 {Object.keys(value.persons).indexOf(item.person_id) + 1} · {item.state === 'confirmed' ? '已确认' : item.state === 'candidate' ? '待确认候选' : item.state === 'rejected' ? '已拒绝' : '未确定'}</span>
        {item.state === 'candidate' && <button type="button" onClick={() => link('confirmed', item.person_id)}>确认候选</button>}
        <button type="button" onClick={() => link('rejected', item.person_id)}>拒绝关联</button>
        <button type="button" onClick={() => link('unresolved', item.person_id)}>解除关联，保留历史</button>
      </div>)}
      <p>候选不会同步参数。解除关联保留本地覆盖和历史，但停止继承该匿名人物的默认值。</p>
    </fieldset></details>
    <details><summary>补充漏检人脸区域</summary><fieldset disabled={disabled}>
      <button type="button" disabled={faceAdding} onClick={onFaceAdd}>{faceAdding ? '正在画面中框选…' : '在画面中框选人脸并分析'}</button>
      {(['左', '上', '右', '下'] as const).map((name, index) => <label key={name}>{name}（0–1）<input type="number" min={0} max={1} step={.01} value={box[index]}
        onChange={event => {const number = event.currentTarget.valueAsNumber; setBox(old => old.map((item, i) => i === index ? number : item) as typeof box);}}/></label>)}
      <button type="button" disabled={!validBox} onClick={() => void submit('manual_add', {box}, allTarget)}>添加待分析区域</button>
      <p>区域本身不含关键点；必须完成真实分析后才能应用面部效果。无可靠分析时保留区域并说明原因。</p>
    </fieldset></details>
    <details><summary>当前范围逐项覆盖</summary>
      <p>{targetLabel(value)}。未列出的参数保留继承；不同人脸的继承结果可以不同。</p>
      {Object.entries(value.editing_overrides ?? {}).flatMap(([operation, parameters]) => Object.entries(parameters).map(([path, number]) => <div className="peopleValue" key={`${operation}:${path}`}>
        <span>{operationLabel(operation)} {path}：{String(number)}</span>
        {operation === EYE_BAGS ? <span className="muted">新版卧蚕保护只能在专用逐眼审核中启用或改变，不能在此恢复可能激活的继承。</span>
          : <button type="button" disabled={disabled || !value.editing_target} onClick={() => void submit('patch', {patches: [restoreInheritance(operation, path)]}, value.editing_target)}>恢复此范围该项继承</button>}
      </div>))}
    </details>
    {value.resolved && <details><summary>所选人脸有效参数与来源</summary>
      {value.resolved.operations[EYE_BAGS] && <div>
        <p>新版祛眼袋与保留卧蚕参数在这里仅供检查。正向调整、恢复继承、跨脸分组或同步都不能绕过逐眼源图与真实前后图审核；请前往「面部祛瑕疵 → 祛眼袋」。当前不支持活跃新版效果跨来源复制。</p>
        <button type="button" disabled={disabled || !faceTarget} onClick={() => void submit('patch', {patches: [{operation_id: EYE_BAGS, parameter_path: '/amount', unset: false, value: 0}]}, faceTarget)}>仅归零当前脸新版祛眼袋，保留保护设置</button>
      </div>}
      {Object.entries(value.resolved.operations).flatMap(([operation, parameters]) => Object.entries(parameters).map(([path, number]) => <div className="peopleValue" key={`${operation}:${path}`}>
        <span>{operationLabel(operation)} {path}：{String(number.value)} · {sourceLabel(number)}</span>
        {number.overridden && operation !== EYE_BAGS && <button type="button" disabled={disabled || !faceTarget}
          onClick={() => void submit('patch', {patches: [restoreInheritance(operation, path)]}, faceTarget)}>恢复此脸该项继承</button>}
      </div>))}
    </details>}
    {value.resolved?.conflicts.map(conflict => <p role="alert" key={`${conflict.operation_id}:${conflict.parameter_path}`}>
      {operationLabel(conflict.operation_id)} {conflict.parameter_path}：分组优先级冲突，请修改组优先级或明确此脸覆盖。</p>)}
    {!!value.legacy_unresolved?.length && <details open><summary>旧版编辑归属需要确认</summary>
      <p>旧效果与历史原样保留。只有明确选择归属才应用可移植参数；来源蒙版不会自动分配给新人物。</p>
      {value.legacy_unresolved.map(record => <div className="peopleValue" key={record.id}>
        <span>{record.legacy_key}</span>
        <details><summary>查看保留的参数记录</summary><p>{JSON.stringify(record.intent)}</p></details>
        <button type="button" disabled={disabled || !record.bindable || !faceTarget}
          onClick={() => void submit('resolve_legacy', {archive_id: record.id, mode: 'apply_parameters'}, faceTarget)}>确认应用到所选人脸</button>
        <button type="button" disabled={disabled || !record.bindable}
          onClick={() => void submit('resolve_legacy', {archive_id: record.id, mode: 'apply_parameters'}, allTarget)}>确认作为本照片全部人物默认</button>
        <button type="button" disabled={disabled}
          onClick={() => void submit('resolve_legacy', {archive_id: record.id, mode: 'retain_inactive'}, faceTarget ?? allTarget)}>保留记录与历史，不参与当前渲染</button>
        {!record.bindable && <p>此记录没有可安全重分配的参数，来源绑定不能猜测。</p>}
      </div>)}
    </details>}
    {value.analysis_notice && <p role="status">{value.analysis_notice}</p>}
    {value.refusals?.map(refusal => <p role="alert" key={`${refusal.face_instance_id}:${refusal.reason}`}>{refusal.reason}</p>)}
    {owner.state.message && <p role="status">{owner.state.message}</p>}
    {owner.state.uncertain && <button type="button" onClick={() => void owner.check().catch(() => {})}>查询本次结果（不重发修改）</button>}
    {error && error !== owner.state.message && <p role="alert">{error}</p>}
  </section>;
}
