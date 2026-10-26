// SPDX-License-Identifier: GPL-3.0-or-later
import {useLayoutEffect, useState, useSyncExternalStore, type MouseEvent} from 'react';
import {PortraitCropController} from './controller';
import {PortraitCropImage} from './PortraitCropImage';
import {RulePresetPanel} from './rulePresets/RulePresetPanel';
import type {RulePresetCatalogue} from './rulePresets/controller';
import {PORTRAIT_CROP_CONTROLS, imageKey, type AnchorName, type RuleDraft} from './model';
import './portraitCrop.css';
const ANCHORS: AnchorName[] = ['crown', 'chin', 'face_center'];
const NAMES: Record<AnchorName, string> = {crown: '真实头顶（含完整头发）', chin: '真实下巴底部', face_center: '所选人脸中心'};
const CONFIRMATIONS: Record<AnchorName, string> = {
  crown: '我已在本张照片上确认完整头发的真实头顶，不是额头点、脸框顶部或自动猜测。',
  chin: '我已在本张照片上确认真实下巴底部；检测提议仅作参考。',
  face_center: '我已确认中心属于我明确选择的这张人脸。',
};
const RULES: {key: keyof RuleDraft; label: string; min: number; max: number; control?: string; detail: string}[] = [
  {key: 'aspect_ratio', label: '画幅宽 ÷ 高', min: 0.001, max: 1000, detail: '例如 0.75 表示 3:4。本地输入范围 0.001–1000。'},
  {key: 'headroom_fraction', label: '头顶留白 ÷ 画幅高度', min: 0, max: 1, control: PORTRAIT_CROP_CONTROLS.headroom, detail: '从画幅顶边到真实头顶的垂直距离。'},
  {key: 'head_fraction', label: '头部高度 ÷ 画幅高度', min: 0, max: 1, control: PORTRAIT_CROP_CONTROLS.headFraction, detail: '真实头顶到下巴的垂直高度；必须大于 0。'},
  {key: 'horizontal_position', label: '人脸中心水平位置 ÷ 画幅宽度', min: 0, max: 1, control: PORTRAIT_CROP_CONTROLS.facePosition, detail: '0 为左侧，0.5 为居中，1 为右侧。'},
];
export type PortraitCropPanelProps = {controller: PortraitCropController; catalogue: RulePresetCatalogue; disabled?: boolean; onClose?: () => void};
/** Current-photo manual-assisted composition with rules-only preset drafts. */
export function PortraitCropPanel({controller, catalogue, disabled = false, onClose}: PortraitCropPanelProps) {
  const state = useSyncExternalStore(controller.subscribe, controller.snapshot, controller.snapshot);
  const [target, setTarget] = useState<AnchorName>('crown'), [coordinates, setCoordinates] = useState<[string, string]>(['', '']);
  const [error, setError] = useState('');
  const current = state.current, preview = state.preview;
  const context = current ? `${current.session_id}:${current.capture_sha256}:${state.selectedFace ?? ''}` : '';
  useLayoutEffect(() => {setCoordinates(['', '']); setTarget('crown'); setError('');}, [context]);
  const blocked = disabled || !state.enabled || state.phase !== 'idle';
  const measuring = !blocked && !!current && state.sourceReady && !!state.selectedFace;
  const inputPending = coordinates.some(value => value.trim() !== '');
  const action = (fn: () => unknown | Promise<unknown>) => {setError(''); try {void Promise.resolve(fn()).catch(e => setError(e instanceof Error ? e.message : '操作未完成。'));} catch (e) {setError(e instanceof Error ? e.message : '操作未完成。');}};
  const close = () => {controller.dismiss(); onClose?.();};
  function chooseTarget(name: AnchorName) {setTarget(name); setCoordinates(['', '']); setError('');}
  function pick(event: MouseEvent<SVGSVGElement>) {
    if (!measuring || !current) return;
    action(() => {
      const matrix = event.currentTarget.getScreenCTM(); if (!matrix) throw Error('图片映射尚未就绪。');
      const point = new DOMPoint(event.clientX, event.clientY).matrixTransform(matrix.inverse());
      controller.mark(target, [point.x, point.y]); setCoordinates(['', '']);
    });
  }
  function useCoordinates() {
    action(() => {
      if (coordinates.some(value => value.trim() === '' || value.length > 32)) throw Error('请填写 X、Y 两项有限来源像素坐标。');
      const x = Number(coordinates[0]), y = Number(coordinates[1]);
      if (!Number.isFinite(x) || !Number.isFinite(y)) throw Error('坐标必须是有限数字。');
      controller.mark(target, [x, y]); setCoordinates(['', '']);
    });
  }
  const sourceKey = current ? `${current.session_id}:${imageKey(current.source.image)}` : '';
  const face = current?.source.faces.find(item => item.face_id === state.selectedFace);
  const radius = current ? Math.max(current.source.width, current.source.height) * 0.008 : 1;
  return <section className="portrait-crop-panel" data-portrait-crop-workflow data-control-id={PORTRAIT_CROP_CONTROLS.workspace}
    aria-label="当前照片人像构图人工辅助裁剪" onKeyDown={event => {if (event.key === 'Escape' && onClose) {event.stopPropagation(); close();}}}>
    <header className="portrait-crop-toolbar"><strong>人像构图 · 当前照片 · 人工辅助</strong>{onClose && <button type="button" onClick={close}>关闭</button>}</header>
    <p>使用当前完整编辑照片的真实人脸分析。人脸网格不检测头发顶部，必须手工标记并确认头顶和下巴。不会自动应用，也不承诺证件照合规。</p>
    <p className="portrait-crop-notice">此处采用本地明确约定：头部高度及头顶留白均除以画幅高度，人脸位置只控制水平方向。垂直位置由前两项决定，不另设互相冲突的目标。非零旋转须先在普通裁剪中处理，本工具不会重置旋转。</p>
    <div className="portrait-crop-actions">
      <button type="button" disabled={blocked} onClick={() => action(() => controller.acquire())}>{current ? '重新捕获当前完整照片' : '捕获当前完整编辑照片'}</button>
      <button type="button" disabled={!current && !state.pending} onClick={() => action(() => controller.cancel())}>{state.pending?.action === 'apply' ? '保留原应用请求，勿重发' : '放弃本次候选，不应用'}</button>
      {state.pending && <button type="button" disabled={state.checking} onClick={() => action(() => controller.reconcile())}>{state.checking ? '正在查询原请求…' : '查询原请求，不重复提交'}</button>}
    </div>
    {current && <>
      <p className="portrait-crop-proof">文档 {current.binding.document_id} · 修订 {current.binding.revision} · 当前来源 {current.source.width} × {current.source.height} px · 仅此捕获有效</p>
      <div className="portrait-crop-layout">
        <section aria-label="真实当前完整照片及来源像素锚点">
          <h3>1. 明确选择人脸，在真实照片上测量</h3>
          <label>本次构图的人脸<select disabled={blocked || !state.sourceReady} value={state.selectedFace ?? ''} onChange={event => action(() => controller.selectFace(event.currentTarget.value))}>
            <option value="" disabled>请选择，不会默认采用第一张人脸</option>
            {current.source.faces.map((item, index) => <option key={item.face_id} value={item.face_id}>人脸 {index + 1} · {item.face_id}</option>)}
          </select></label>
          {current.source.faces.length === 0 && <p role="status">没有可用的真实人脸分析。不会以照片中心或历史人脸替代。</p>}
          <PortraitCropImage value={current.source.image} identity={sourceKey} alt="未裁剪的当前完整编辑照片，供手工确认真实头顶、下巴和所选人脸中心" onReady={(key, ready) => controller.sourceImageReady(key, ready)}>
            <svg viewBox={`0 0 ${current.source.width} ${current.source.height}`} preserveAspectRatio="none" onClick={pick} aria-label="在完整来源像素坐标中点选锚点" className={measuring ? 'is-measuring' : ''}>
              {face && <rect x={face.bbox[0]} y={face.bbox[1]} width={face.bbox[2] - face.bbox[0]} height={face.bbox[3] - face.bbox[1]} fill="none" stroke="#bdc8d6" strokeWidth={radius / 5} strokeDasharray={`${radius} ${radius / 2}`}/>}
              {ANCHORS.map(name => {const p = state.anchors[name]; return p ? <g key={name}>
                <circle cx={p[0]} cy={p[1]} r={radius} fill={name === target ? '#ffc764' : '#75dfcc'} stroke="#111820" strokeWidth={radius / 5}/>
                <text x={p[0] + radius * 1.6} y={p[1] - radius * 1.2} fontSize={radius * 2.2} fill="#fff" stroke="#111820" strokeWidth={radius / 10} paintOrder="stroke">{name === 'crown' ? '头顶' : name === 'chin' ? '下巴' : '中心'}</text>
              </g> : null;})}
              {state.anchors.crown && state.anchors.chin && <line x1={state.anchors.crown[0]} y1={state.anchors.crown[1]} x2={state.anchors.chin[0]} y2={state.anchors.chin[1]} stroke="#ffc764" strokeWidth={radius / 4} strokeDasharray={`${radius} ${radius}`}/>}
            </svg>
          </PortraitCropImage>
          <p>灰色虚线仅为已选人脸提议框，不是完整头部或头发边界。图上的三点采用 {current.source.width} × {current.source.height} 全图边界像素，绝不保存缩略图坐标。</p>
        </section>
        <section aria-label="锚点复核和构图数值">
          <fieldset disabled={!measuring}>
            <legend>2. 标记并确认真实锚点</legend>
            <button type="button" onClick={() => action(() => {controller.useFaceProposal(); setCoordinates(['', '']);})}>采用所选人脸的下巴及中心提议，仍须确认</button>
            <label>点击照片要标记的位置<select value={target} onChange={event => chooseTarget(event.currentTarget.value as AnchorName)}>{ANCHORS.map(name => <option value={name} key={name}>{state.anchors[name] ? '✓ ' : ''}{NAMES[name]}</option>)}</select></label>
            <div className="portrait-crop-coordinates">{(['X', 'Y'] as const).map((axis, index) => <label key={axis}>{axis} 来源像素<input type="number" min={0} max={index === 0 ? current.source.width : current.source.height} step="any" value={coordinates[index]} onChange={event => {
              const value = event.currentTarget.value;
              action(() => {controller.invalidateMeasurement(); setCoordinates(old => index === 0 ? [value, old[1]] : [old[0], value]);});
            }}/></label>)}</div>
            <div className="portrait-crop-actions"><button type="button" disabled={!inputPending} onClick={useCoordinates}>采用手工像素坐标</button><button type="button" onClick={() => setCoordinates(['', ''])}>取消未完成输入</button><button type="button" onClick={() => action(() => {controller.clearAnchors(); setCoordinates(['', '']);})}>清除全部锚点</button></div>
            <ul>{ANCHORS.map(name => <li key={name}>{NAMES[name]}：{state.anchors[name]?.map(n => `${n.toFixed(2)} px`).join('，') ?? '未测量'}</li>)}</ul>
            {ANCHORS.map(name => <label className="portrait-crop-confirm" key={name}><input type="checkbox" disabled={inputPending || !state.anchors[name]} checked={state.confirmations[name]} onChange={event => action(() => controller.confirmAnchor(name, event.currentTarget.checked))}/>{CONFIRMATIONS[name]}</label>)}
          </fieldset>
          <fieldset disabled={blocked}>
            <legend>3. 明确输入构图规则</legend>
            {RULES.map(rule => <label key={rule.key} data-control-id={rule.control}>{rule.label}<input type="number" min={rule.min} max={rule.max} step="any" value={state.rules[rule.key]} onChange={event => action(() => controller.setRules({...state.rules, [rule.key]: event.currentTarget.value}))}/><small>{rule.detail}</small></label>)}
            <p>不预填隐藏默认值。0.1 表示 10%。超出照片范围、裁掉已确认锚点或数值冲突时拒绝，不会悄悄夹紧、移中、缩放或补造像素。</p>
          </fieldset>
          <button type="button" disabled={!measuring || inputPending || ANCHORS.some(name => !state.confirmations[name])} onClick={() => action(() => controller.prepare())}>生成真实完整前后候选，暂不应用</button>
        </section>
      </div>
      {preview && <section className="portrait-crop-review" aria-label="实际完整候选前后审核">
        <h3>4. 查看实际完整前后图，再明确应用</h3>
        <div className="portrait-crop-comparison">
          <figure><figcaption>之前：当前已编辑、现有裁剪后的完整照片</figcaption><PortraitCropImage value={preview.before} identity={`${preview.preview_token}:before`} alt="本次候选前的真实完整当前照片" onReady={(_, ready) => controller.previewImageReady(preview.preview_token, 'before', imageKey(preview.before), ready)}/></figure>
          <figure><figcaption>之后：完整编辑链实际渲染的裁剪候选，尚未应用</figcaption><PortraitCropImage value={preview.after} identity={`${preview.preview_token}:after`} alt="本次实际裁剪后的完整候选照片，非 CSS 模拟裁剪" onReady={(_, ready) => controller.previewImageReady(preview.preview_token, 'after', imageKey(preview.after), ready)}/></figure>
        </div>
        <p>实际整数边界 [左，上，右，下]：{preview.plan.pixel_bounds.join('，')} px · 输出 {preview.plan.output_size.join(' × ')} px · 旋转 0°。</p>
        <ul>
          <li>实际头顶留白：{(preview.plan.achieved.headroom_fraction * 100).toFixed(3)}%；实际头部占比：{(preview.plan.achieved.head_fraction * 100).toFixed(3)}%。</li>
          <li>实际人脸水平位置：{(preview.plan.achieved.horizontal_position * 100).toFixed(3)}%；随上述规则得到的垂直位置：{(preview.plan.achieved.vertical_position * 100).toFixed(3)}%。</li>
          <li>实际宽高比：{preview.plan.achieved.aspect_ratio.toFixed(6)}。整数像素舍入可与请求产生微小差异。</li>
        </ul>
        <label className="portrait-crop-confirm"><input type="checkbox" checked={state.reviewConfirmed} disabled={blocked || !state.beforeReady || !state.afterReady} onChange={event => action(() => controller.confirmReview(event.currentTarget.checked))}/>我已查看本次完整前后照片与实际像素边界，确认采用此候选。</label>
        <button type="button" disabled={blocked || !state.beforeReady || !state.afterReady || !state.reviewConfirmed} onClick={() => action(() => controller.apply())}>应用已核对候选</button>
        <p>应用通过现有裁剪与历史记录通道完成。来源、修复、分析或任何编辑状态变化都会使此候选失效。</p>
      </section>}
    </>}
    <RulePresetPanel catalogue={catalogue} draft={state.rules} loadDisabled={blocked} onLoad={draft => controller.loadRulePreset(draft)}/>
    {state.historicalUnknown && <p className="portrait-crop-notice">历史{state.historicalUnknown.action === 'apply' ? '裁剪应用' : '来源/候选准备或会话清理'}请求 {state.historicalUnknown.request_id} 的结果仍未知。工程已确认重新打开，但这不证明原操作成功、失败或取消；不会重发原请求。{state.historicalUnknown.action !== 'apply' && '该请求不是裁剪应用。'}</p>}
    {state.message && <p role={state.phase === 'uncertain' ? 'alert' : 'status'}>{state.message}</p>}
    {state.pending && <small>原请求：{state.pending.request_id}</small>}
    {error && <p role="alert">{error}</p>}
  </section>;
}
