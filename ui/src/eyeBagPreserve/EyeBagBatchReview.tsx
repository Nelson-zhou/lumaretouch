// SPDX-License-Identifier: GPL-3.0-or-later
import {useEffect, useLayoutEffect, useRef, useState} from 'react';
import type {SpillImage} from '../spillRemoval/model';
import {requestEyeBagBatchImage, readEyeBagBatchImage} from '../native';
import {verifyEyeBagBatchCoverage, type EyeBagBatchVisual, type EyeBagBatchCoverage, type EyeBagTargetPolicy} from './batchModel';
import {fetchEyeBagBatchImage} from './batchTransport';

type Side = 'before' | 'after';
type Pair = {attempt: number; before: SpillImage; after: SpillImage};
type Props = {value: EyeBagBatchVisual; coverage: EyeBagBatchCoverage; policy: EyeBagTargetPolicy; preflightToken: string; reviewKey: string;
  disabled?: boolean; onReady: (key: string, ready: boolean) => void};
/** Each target reads its own bounded image pages. Metadata never authorizes a write. */
export function EyeBagBatchReview(props: Props) {return <TargetReview key={JSON.stringify([props.reviewKey, props.coverage, props.policy])} {...props}/>;}
function TargetReview({value, coverage, policy, preflightToken, reviewKey, disabled = false, onReady}: Props) {
  const [attempt, setAttempt] = useState(0), [pair, setPair] = useState<Pair | null>(null);
  const [loaded, setLoaded] = useState<{attempt: number; before: boolean; after: boolean}>({attempt: 0, before: false, after: false});
  const [acknowledged, setAcknowledged] = useState(false), [error, setError] = useState(''), [zoom, setZoom] = useState(false);
  const notify = useRef(onReady); notify.current = onReady;
  const mounted = useRef(false), liveAttempt = useRef(attempt); liveAttempt.current = attempt;
  const coverageKey = JSON.stringify([coverage, policy]);
  useLayoutEffect(() => {
    mounted.current = true; notify.current(reviewKey, false);
    return () => {mounted.current = false; notify.current(reviewKey, false);};
  }, [reviewKey]);
  useEffect(() => {
    if (!attempt) return;
    let live = true;
    const current = () => live && mounted.current && liveAttempt.current === attempt;
    const api = {request: requestEyeBagBatchImage, read: readEyeBagBatchImage};
    const read = (side: Side) => fetchEyeBagBatchImage(api, {preflightToken, documentId: value.document_id,
      revision: value.revision, side, sha256: value[side].sha256, requestId: crypto.randomUUID()}, value[side], current);
    void (async () => {
      try {
        if (!await verifyEyeBagBatchCoverage(value, coverage)) throw Error('目标自己的卧蚕保护范围与冻结摘要不一致，请重新预检。');
        if (!current()) return;
        const before = await read('before'), after = await read('after');
        if (current()) setPair({attempt, before, after});
      } catch (cause) {if (current()) {setError(String(cause)); setAcknowledged(false); notify.current(reviewKey, false);}}
    })();
    return () => {live = false;};
  }, [attempt, preflightToken, reviewKey, coverageKey]);
  const ready = !!pair && pair.attempt === attempt && loaded.attempt === attempt && loaded.before && loaded.after && !error;
  const confirmed = ready && acknowledged;
  useEffect(() => {notify.current(reviewKey, confirmed);}, [reviewKey, confirmed]);
  function reload() {
    if (disabled || attempt > 0 && !pair && !error) return;
    const next = attempt + 1;
    liveAttempt.current = next; notify.current(reviewKey, false);
    setAcknowledged(false); setPair(null); setError(''); setLoaded({attempt: next, before: false, after: false}); setAttempt(next);
  }
  function displayed(side: Side, element?: HTMLImageElement) {
    if (!mounted.current || liveAttempt.current !== attempt || pair?.attempt !== attempt) return;
    const good = !!element && element.naturalWidth === value[side].width && element.naturalHeight === value[side].height;
    setLoaded(old => old.attempt === attempt ? {...old, [side]: good} : old);
    if (!good) {setAcknowledged(false); setError('本目标审核图未能完整显示或解码尺寸不匹配，不能确认。'); notify.current(reviewKey, false);}
  }
  return <section aria-label="本目标祛眼袋卧蚕保护真实前后审核" style={{flexBasis: '100%'}}>
    <strong>本目标完整编辑链的真实前后效果，包含本次同时选择的全部参数</strong>
    <p>只同步明确勾选的新版祛眼袋程度与卧蚕保留值。各目标使用自己已手绘并审核的卧蚕保护，不复制来源保护笔画、支持缓存、恢复数据、关键点或人物关联；不自动识别卧蚕，也不补全不可见的眼睛。</p>
    <p>{policy.replace_legacy ? '本目标已明确允许：仅当候选新版祛眼袋处于启用状态时，替换旧版眼袋效果。新版归零不会清除旧版。' : '本目标不允许替换旧版眼袋效果。候选新版启用且目标旧版仍生效时会拒绝，不能静默关闭任何已选参数。'}选择同时传递非零旧版眼袋和启用新版会拒绝，即使允许替换也不会丢弃所选旧版值。</p>
    <p>归零可能移除目标已有的新版调整，仍需查看前后图；归零不代表卧蚕保护已有效或删除保护，不因本项归零清除旧版；另行明确选中的旧版参数仍按选项应用。</p>
    <ul>{coverage.targets.map(row => <li key={row.face_ref.face_instance_id}>目标人脸 {row.face_ref.face_instance_id}：{row.scope === 'neutral-no-effect'
      ? '候选新版程度为零，不据此声明保护有效；原有作用仍显示在前图。'
      : `使用本目标自己的已审核卧蚕保护，人物眼侧：${row.sides.map(side => side === 'left' ? '左眼' : '右眼').join('、')}。`}</li>)}</ul>
    <button type="button" disabled={disabled || attempt > 0 && !pair && !error} onClick={reload}>
      {pair ? '重新读取此目标的前后图' : '读取此目标的真实前后图'}</button>
    {error && <p role="alert">{error}</p>}
    {pair && <>
      <label><input type="checkbox" checked={zoom} onChange={event => setZoom(event.target.checked)}/>按审核图原尺寸显示并滚动检查</label>
      <div style={{display: 'flex', flexWrap: 'wrap', gap: 12, overflow: 'auto', maxHeight: 900}}>
        {(['before', 'after'] as const).map(side => <figure key={`${reviewKey}:${attempt}:${side}`} style={{margin: 0}}>
          <figcaption>{side === 'before' ? '当前真实效果' : '本次完整候选，尚未应用'} · 原输出 {value[side === 'before' ? 'before_output_size' : 'after_output_size'].join(' × ')} 像素</figcaption>
          <img src={`data:image/png;base64,${pair[side].base64}`} width={value[side].width} height={value[side].height}
            style={{maxWidth: zoom ? 'none' : '100%', height: 'auto'}} alt={`本目标整张照片${side === 'before' ? '修改前' : '祛眼袋及全部所选参数候选修改后'}的真实渲染审核图`}
            onLoad={event => displayed(side, event.currentTarget)} onError={() => displayed(side)}/>
        </figure>)}
      </div>
    </>}
    {!ready && !error && <p role="status">{attempt ? '正在读取、校验并显示此目标的两张真实图像…' : '请先读取并查看此目标的两张真实图像。'}</p>}
    <label><input type="checkbox" checked={confirmed} disabled={disabled || !ready}
      onChange={event => {if (ready && !disabled) setAcknowledged(event.target.checked);}}/>我已查看此目标卧蚕与眼袋、指定人脸、邻近人物和背景，以及全部所选参数的真实前后效果，同意本次同步及该目标旧版处理策略</label>
    <p><small>审核图最长边最多 1024 像素，不替代全分辨率照片验收。每张目标必须单独查看和勾选；图像、人物状态、保护、参数或旧版处理策略变化后必须重新预检。</small></p>
  </section>;
}
