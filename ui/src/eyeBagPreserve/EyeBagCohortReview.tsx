// SPDX-License-Identifier: GPL-3.0-or-later
import {useEffect, useLayoutEffect, useRef, useState} from 'react';
import type {SpillImage} from '../spillRemoval/model';
import {requestEyeBagCohortImage, readEyeBagCohortImage} from '../native';
import {verifyEyeBagCohortCoverage, type EyeBagCohortVisual, type EyeBagCohortCoverage} from './cohortModel';
import {fetchEyeBagCohortImage} from './cohortTransport';

type Side = 'before' | 'after';
type Pair = {attempt: number; before: SpillImage; after: SpillImage};
type Props = {value: EyeBagCohortVisual; coverage: EyeBagCohortCoverage; preflightToken: string; reviewKey: string;
  disabled?: boolean; onReady: (key: string, ready: boolean) => void};
/** Each target reads its own bounded image pages. Metadata never authorizes a write. */
export function EyeBagCohortReview(props: Props) {return <TargetReview key={JSON.stringify([props.reviewKey, props.coverage])} {...props}/>;}
function TargetReview({value, coverage, preflightToken, reviewKey, disabled = false, onReady}: Props) {
  const [attempt, setAttempt] = useState(0), [pair, setPair] = useState<Pair | null>(null);
  const [loaded, setLoaded] = useState<{attempt: number; before: boolean; after: boolean}>({attempt: 0, before: false, after: false});
  const [acknowledged, setAcknowledged] = useState(false), [error, setError] = useState(''), [zoom, setZoom] = useState(false);
  const notify = useRef(onReady); notify.current = onReady;
  const mounted = useRef(false), liveAttempt = useRef(attempt); liveAttempt.current = attempt;
  const coverageKey = JSON.stringify(coverage);
  useLayoutEffect(() => {
    mounted.current = true; notify.current(reviewKey, false);
    return () => {mounted.current = false; notify.current(reviewKey, false);};
  }, [reviewKey]);
  useEffect(() => {
    if (!attempt) return;
    let live = true;
    const current = () => live && mounted.current && liveAttempt.current === attempt;
    const api = {request: requestEyeBagCohortImage, read: readEyeBagCohortImage};
    const read = (side: Side) => fetchEyeBagCohortImage(api, {preflightToken, documentId: value.document_id,
      revision: value.revision, side, sha256: value[side].sha256, requestId: crypto.randomUUID()}, value[side], current);
    void (async () => {
      try {
        if (!await verifyEyeBagCohortCoverage(value, coverage)) throw Error('成员自己的卧蚕保护范围与冻结摘要不一致，请重新预检。');
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
    if (!good) {setAcknowledged(false); setError('本成员审核图未能完整显示或解码尺寸不匹配，不能确认。'); notify.current(reviewKey, false);}
  }
  return <section aria-label="本成员祛眼袋卧蚕保护真实前后审核" style={{flexBasis: '100%'}}>
    <strong>本成员完整编辑链的真实前后效果，包含本次全部共同参数及保留的显式效果</strong>
    <p>源成员与每个目标都用自身当前来源、分析和已审核的卧蚕保护，不复制任何其他成员的笔画、支持、恢复数据或关键点；不自动识别卧蚕。普通参数更新和解除关联同样必须检查启用的保留效果。</p>
    <p>{coverage.replace_legacy ? '此成员已明确允许：仅当候选新版启用时替换旧版眼袋。归零不清除旧版。' : '此成员不允许替换旧版眼袋；若候选新版与旧版冲突则拒绝。'}不会丢弃另行明确选择的非零旧版参数。</p>
    <ul>{(['before', 'after'] as const).map(side => <li key={side}>{side === 'before' ? '当前效果' : '本次完整候选'}：{coverage[side].scope === 'neutral-no-effect'
      ? '新版程度为零，不据此声明卧蚕保护有效，也不删除原保护。'
      : `使用本成员自己的已审核卧蚕保护，人物眼侧：${coverage[side].sides.map(eye => eye === 'left' ? '左眼' : '右眼').join('、')}。`}</li>)}</ul>
    <p>人脸显式参数优先，某些像素可能保持不变，仍须查看两图。解除关联只移除共同继承，不是删除每张照片的显式编辑；持久内容仍为 v1 标量意图，不迁移或推断配方。</p>
    <button type="button" disabled={disabled || attempt > 0 && !pair && !error} onClick={reload}>
      {pair ? '重新读取此成员的前后图' : '读取此成员的真实前后图'}</button>
    {error && <p role="alert">{error}</p>}
    {pair && <>
      <label><input type="checkbox" checked={zoom} onChange={event => setZoom(event.target.checked)}/>按审核图原尺寸显示并滚动检查</label>
      <div style={{display: 'flex', flexWrap: 'wrap', gap: 12, overflow: 'auto', maxHeight: 900}}>
        {(['before', 'after'] as const).map(side => <figure key={`${reviewKey}:${attempt}:${side}`} style={{margin: 0}}>
          <figcaption>{side === 'before' ? '当前真实效果' : '本次完整候选，尚未应用'} · 原输出 {value[side === 'before' ? 'before_output_size' : 'after_output_size'].join(' × ')} 像素</figcaption>
          <img src={`data:image/png;base64,${pair[side].base64}`} width={value[side].width} height={value[side].height}
            style={{maxWidth: zoom ? 'none' : '100%', height: 'auto'}} alt={`本成员整张照片${side === 'before' ? '修改前' : '祛眼袋及全部所选参数候选修改后'}的真实渲染审核图`}
            onLoad={event => displayed(side, event.currentTarget)} onError={() => displayed(side)}/>
        </figure>)}
      </div>
    </>}
    {!ready && !error && <p role="status">{attempt ? '正在读取、校验并显示此成员的两张真实图像…' : '请先读取并查看此成员的两张真实图像。'}</p>}
    <label><input type="checkbox" checked={confirmed} disabled={disabled || !ready}
      onChange={event => {if (ready && !disabled) setAcknowledged(event.target.checked);}}/>我已查看此成员卧蚕与眼袋、指定人脸、邻近人物和背景，以及全部所选参数的真实前后效果，同意本次共同参数或解除关联操作及此成员旧版处理策略</label>
    <p><small>审核图最长边最多 1024 像素，不替代全分辨率照片验收。每个成员必须单独查看和勾选；图像、人物状态、保护、参数或旧版处理策略变化后必须重新预检。</small></p>
  </section>;
}
