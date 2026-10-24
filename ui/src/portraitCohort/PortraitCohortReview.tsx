// SPDX-License-Identifier: GPL-3.0-or-later
import {useEffect, useLayoutEffect, useRef, useState} from 'react';
import type {SpillImage} from '../spillRemoval/model';
import {requestPortraitCohortImage, readPortraitCohortImage} from '../native';
import {FACE_STYLE_LABELS, type FaceStyleRecipe} from '../faceStyle/model';
import type {PortraitCohortVisual} from './model';
import {fetchPortraitCohortImage} from './visualTransport';

type Side = 'before' | 'after';
type Pair = {attempt: number; before: SpillImage; after: SpillImage};
type Props = {value: PortraitCohortVisual; recipe?: FaceStyleRecipe; preflightToken: string; reviewKey: string;
  disabled?: boolean; onReady: (key: string, ready: boolean) => void};
/** Each target reads its own bounded image pages. Metadata never authorizes a write. */
export function PortraitCohortReview(props: Props) {return <TargetReview key={props.reviewKey} {...props}/>;}
function TargetReview({value, recipe, preflightToken, reviewKey, disabled = false, onReady}: Props) {
  const [attempt, setAttempt] = useState(0), [pair, setPair] = useState<Pair | null>(null);
  const [loaded, setLoaded] = useState<{attempt: number; before: boolean; after: boolean}>({attempt: 0, before: false, after: false});
  const [acknowledged, setAcknowledged] = useState(false), [error, setError] = useState(''), [zoom, setZoom] = useState(false);
  const notify = useRef(onReady); notify.current = onReady;
  const mounted = useRef(false), liveAttempt = useRef(attempt); liveAttempt.current = attempt;
  const recipeKey = JSON.stringify(recipe);
  useLayoutEffect(() => {
    mounted.current = true; notify.current(reviewKey, false);
    return () => {mounted.current = false; notify.current(reviewKey, false);};
  }, [reviewKey]);
  useEffect(() => {
    if (!attempt) return;
    let live = true;
    const current = () => live && mounted.current && liveAttempt.current === attempt;
    const api = {request: requestPortraitCohortImage, read: readPortraitCohortImage};
    const read = (side: Side) => fetchPortraitCohortImage(api, {preflightToken, documentId: value.document_id,
      revision: value.revision, side, sha256: value[side].sha256, requestId: crypto.randomUUID()}, value[side], current);
    void (async () => {
      try {
        if (!current()) return;
        const before = await read('before'), after = await read('after');
        if (current()) setPair({attempt, before, after});
      } catch (cause) {if (current()) {setError(String(cause)); setAcknowledged(false); notify.current(reviewKey, false);}}
    })();
    return () => {live = false;};
  }, [attempt, preflightToken, reviewKey, recipeKey]);
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
  return <section aria-label="本成员新版脸型真实前后审核" style={{flexBasis: '100%'}}>
    {recipe ? <strong>{FACE_STYLE_LABELS[recipe.style]} · 配方 v{recipe.version} · 共同程度 {Number((recipe.amount * 100).toFixed(6))}</strong> : <strong>已有共同参数的完整成员审核，不推断命名配方</strong>}
    <p>这是此成员完整编辑链的真实前后效果。源成员和每个目标都必须独立读取、显示并确认；不是来源与目标外貌对比，不复制关键点、蒙版或局部素材。</p>
    <p>共同参数在人物层继承。每张人脸更高优先级的显式参数保留，可能使部分像素完全不变，仍须审核；解除关联也不能跳过。0 是中性替换，不是恢复旧值。</p>
    <button type="button" disabled={disabled || attempt > 0 && !pair && !error} onClick={reload}>
      {pair ? '重新读取此成员的前后图' : '读取此成员的真实前后图'}</button>
    {error && <p role="alert">{error}</p>}
    {pair && <>
      <label><input type="checkbox" checked={zoom} onChange={event => setZoom(event.target.checked)}/>按审核图原尺寸显示并滚动检查</label>
      <div style={{display: 'flex', flexWrap: 'wrap', gap: 12, overflow: 'auto', maxHeight: 900}}>
        {(['before', 'after'] as const).map(side => <figure key={`${reviewKey}:${attempt}:${side}`} style={{margin: 0}}>
          <figcaption>{side === 'before' ? '当前真实效果' : '本次关联操作候选，尚未应用'} · 原输出 {value[side === 'before' ? 'before_output_size' : 'after_output_size'].join(' × ')} 像素</figcaption>
          <img src={`data:image/png;base64,${pair[side].base64}`} width={value[side].width} height={value[side].height}
            style={{maxWidth: zoom ? 'none' : '100%', height: 'auto'}} alt={`本成员整张照片${side === 'before' ? '修改前' : '关联操作候选修改后'}的真实渲染审核图`}
            onLoad={event => displayed(side, event.currentTarget)} onError={() => displayed(side)}/>
        </figure>)}
      </div>
    </>}
    {!ready && !error && <p role="status">{attempt ? '正在读取、校验并显示此成员的两张真实图像…' : '请先读取并查看此成员的两张真实图像。'}</p>}
    <label><input type="checkbox" checked={confirmed} disabled={disabled || !ready}
      onChange={event => {if (ready && !disabled) setAcknowledged(event.target.checked);}}/>我已查看此成员指定人脸、邻近人物和背景的真实前后效果，同意本次共同参数或解除关联操作</label>
    <p><small>审核图最长边最多 1024 像素，不替代全分辨率照片验收。每个成员必须单独查看和勾选；图像、人物状态或配方变化后必须重新预检。</small></p>
  </section>;
}
