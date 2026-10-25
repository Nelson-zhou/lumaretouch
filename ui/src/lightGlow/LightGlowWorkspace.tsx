// SPDX-License-Identifier: GPL-3.0-or-later
import {useEffect, useState, useSyncExternalStore} from 'react';
import {GLOW_MODES, GLOW_MODE_LABELS, GLOW_PRESET_LABELS, GLOW_REFERENCE, glowPresets, glowReviewKey, matchingGlowPreset,
  type GlowRecipe} from './model';
import {glowImageUrl} from './imagery';
import type {LightGlowController} from './controller';
import './lightGlow.css';

function Scalar({label, value, min, max, step, unit = '', change}: {
  label: string; value: number; min: number; max: number; step: number; unit?: string; change: (value: number) => void;
}) {
  return <label className="lightGlowScalar"><span>{label}<output>{Number(value.toFixed(3))}{unit}</output></span>
    <input type="range" min={min} max={max} step={step} value={value} onChange={event => change(Number(event.target.value))}/>
  </label>;
}

/** Only renders authoritative source/review assets. No canvas approximations of glow. */
export function LightGlowWorkspace({controller, disabled = false}: {controller: LightGlowController; disabled?: boolean}) {
  const state = useSyncExternalStore(controller.subscribe, controller.snapshot, controller.snapshot);
  const [showRange, setShowRange] = useState(false);
  const context = state.context, recipe = state.recipe, review = state.review;
  const locked = disabled || !controller.editable();
  const reviewKey = review ? glowReviewKey(review) : '';
  const preset = recipe ? matchingGlowPreset(recipe) : null;
  const canAcknowledge = !disabled && controller.canPreview() && state.phase === 'review' && !!review
    && state.before_loaded && state.after_loaded && state.coverage_loaded;
  useEffect(() => () => controller.releasePresentation(), [controller]);
  useEffect(() => {setShowRange(false);}, [context?.session_id, reviewKey]);
  const edit = (patch: Partial<Omit<GlowRecipe, 'version' | 'operation_id' | 'math_identity' | 'mode'>>) => {
    if (recipe) controller.edit({...recipe, ...patch});
  };
  const tint = (patch: Partial<GlowRecipe['tint']>) => {if (recipe) edit({tint: {...recipe.tint, ...patch}});};
  return <section className="lightGlowWorkspace" aria-label="发光 · 当前完整照片复核">
    <p className="lightGlowBoundary">黑柔、白柔、辉光使用三种独立本地算法，不是 AI 受光面识别，也不宣称等同实物滤镜或像素蛋糕专有算法。</p>
    <p className="lightGlowBoundary">当前只支持有界 SDR 来源。超出范围的 HDR 输入必须明确拒绝，不会裁掉高光或把显示 PNG 当作原图。现有编辑、图层与历史保持不变。</p>
    <p className="lightGlowStatus" role={state.phase === 'failed' || state.phase === 'unknown' ? 'alert' : 'status'} aria-live="polite">{state.message}</p>
    {context && <p className="lightGlowEvidence">完整当前来源 · {context.owner.source.width} × {context.owner.source.height}
      {' · '}修订 {context.owner.document_revision}{' · '}来源 {context.owner.source.sha256.slice(0, 12)}
      {state.stale ? ' · 已失效，不能应用' : ' · 已统一 EXIF 方向'}</p>}
    <div className="lightGlowLayout">
      <div className="lightGlowSourceColumn">
        {context && state.source_verified && !state.stale ? <figure>
          <div className="lightGlowFrame" style={{aspectRatio: `${context.before.width} / ${context.before.height}`}}>
            <img key={`${context.session_id}:${context.before.sha256}`} src={glowImageUrl(context.before)}
              alt="当前完整修图结果，尚未叠加本次发光" draggable={false}
              onLoad={event => controller.sourceLoaded(context.before.sha256, event.currentTarget.naturalWidth, event.currentTarget.naturalHeight, true)}
              onError={() => controller.sourceLoaded(context.before.sha256, 0, 0, false)}/>
          </div>
          <figcaption>本次发光之前的完整来源。显示图不是可回写的源文件。</figcaption>
        </figure> : <div className="lightGlowEmpty">{state.stale ? '旧来源已作废。原配方保留；请等待未决请求结束，再明确获取当前来源。' : '等待已校验的完整来源，没有占位效果图。'}</div>}
        <p className="lightGlowBoundary">官方文档提供模式、程度与控件名称，未披露数值范围或预设参数。这里的数值是本地校准，不冒充官方参数。</p>
        <a href={GLOW_REFERENCE} target="_blank" rel="noreferrer">查看发光功能参考说明</a>
      </div>
      <fieldset className="lightGlowControls" disabled={locked}>
        <legend>发光配方</legend>
        <div className="lightGlowModes" role="group" aria-label="发光效果">
          {GLOW_MODES.map(mode => <button type="button" key={mode} aria-pressed={recipe?.mode === mode}
            disabled={!state.capability.modes.includes(mode)} onClick={() => controller.selectMode(mode)}>{GLOW_MODE_LABELS[mode]}</button>)}
        </div>
        {recipe && <>
          <p className="lightGlowModeDescription">{recipe.mode === 'black_mist' ? '选取亮部进行柔化，优先保留反差。'
            : recipe.mode === 'white_mist' ? '更宽的柔光与雾化，区别于黑柔的亮部处理。' : '对亮部做加法式扩散，不与白柔共用同一处理方式。'}</p>
          <div className="lightGlowPresets" role="group" aria-label="程度">
            {glowPresets(recipe.mode).map(value => <button type="button" key={value} aria-pressed={preset === value}
              onClick={() => controller.selectPreset(value)}>{GLOW_PRESET_LABELS[value]}</button>)}
          </div>
          <p className="lightGlowCaption">{preset ? `程度：${GLOW_PRESET_LABELS[preset]}` : '程度：自定义'} · 预设展开为标量；之后可逐项调整。</p>
          <Scalar label="强度" value={recipe.strength} min={0} max={1} step={.01} change={value => edit({strength: value})}/>
          <Scalar label="半径" value={recipe.radius_px} min={0} max={512} step={1} unit=" 源像素" change={value => edit({radius_px: value})}/>
          <Scalar label="阈值" value={recipe.threshold} min={0} max={1} step={.01} change={value => edit({threshold: value})}/>
          <Scalar label="曝光" value={recipe.exposure_ev} min={-4} max={4} step={.05} unit=" EV" change={value => edit({exposure_ev: value})}/>
          <Scalar label="光散射" value={recipe.scattering} min={0} max={1} step={.01} change={value => edit({scattering: value})}/>
          <p className="lightGlowCaption">光散射为本地色通道扩散近似，不是实测棱镜色散。</p>
          <h4>着色</h4>
          <Scalar label="色相" value={recipe.tint.hue_deg} min={-180} max={180} step={1} unit="°" change={value => tint({hue_deg: value})}/>
          <Scalar label="饱和度" value={recipe.tint.saturation} min={-1} max={1} step={.01} change={value => tint({saturation: value})}/>
          <Scalar label="亮度" value={recipe.tint.lightness} min={-1} max={1} step={.01} change={value => tint({lightness: value})}/>
          {recipe.strength === 0 && <p role="status">强度为 0：必须保持源像素完全不变，不因曝光或着色暗中改变图像。</p>}
          <div className="lightGlowActions"><button type="button" disabled={!state.undo.length} onClick={() => controller.undo()}>撤销参数</button>
            <button type="button" disabled={!state.redo.length} onClick={() => controller.redo()}>重做参数</button></div>
        </>}
      </fieldset>
    </div>
    <div className="lightGlowActions">
      <button type="button" disabled={disabled || !controller.canPreview()} onClick={() => void controller.preview()}>生成完整前后对比</button>
      {context && !['applied', 'cancelled'].includes(state.phase) && <button type="button"
        disabled={disabled || controller.unresolved() || state.phase === 'cancelling' || state.terminal_refresh === 'refreshing'} onClick={() => void controller.cancel()}>取消本次发光</button>}
      {controller.unresolved() && <button type="button" disabled={state.checking || ['applying', 'cancelling'].includes(state.phase)} onClick={() => void controller.check()}>查询原应用/取消请求</button>}
    </div>
    {review && state.phase === 'review' && <section className="lightGlowReview" aria-label="完整前后图和实际作用范围">
      <h4>完整前后对比</h4>
      <div className="lightGlowPair">
        <figure><div className="lightGlowFrame" style={{aspectRatio: `${review.before.width} / ${review.before.height}`}}>
          <img key={`before:${reviewKey}`} src={glowImageUrl(review.before)} alt="发光之前的完整照片" draggable={false}
            onLoad={event => controller.presented('before', reviewKey, event.currentTarget.naturalWidth, event.currentTarget.naturalHeight, true)}
            onError={() => controller.presented('before', reviewKey, 0, 0, false)}/>
        </div><figcaption>之前 · 完整当前修图结果</figcaption></figure>
        <figure><div className="lightGlowFrame" style={{aspectRatio: `${review.after.width} / ${review.after.height}`}}>
          <img key={`after:${reviewKey}`} src={glowImageUrl(review.after)} alt="本次发光之后的完整照片" draggable={false}
            onLoad={event => controller.presented('after', reviewKey, event.currentTarget.naturalWidth, event.currentTarget.naturalHeight, true)}
            onError={() => controller.presented('after', reviewKey, 0, 0, false)}/>
          <img key={`coverage:${reviewKey}`} className="lightGlowCoverage" style={{opacity: showRange ? 1 : 0}}
            src={glowImageUrl(review.coverage)} alt={showRange ? '绿色表示本次算法实际改变像素的范围' : ''} aria-hidden={!showRange} draggable={false}
            onLoad={event => controller.presented('coverage', reviewKey, event.currentTarget.naturalWidth, event.currentTarget.naturalHeight, true)}
            onError={() => controller.presented('coverage', reviewKey, 0, 0, false)}/>
        </div><figcaption>之后 · {GLOW_MODE_LABELS[review.recipe.mode]}{showRange ? ' + 实际变化范围' : ''}</figcaption></figure>
      </div>
      <label className="lightGlowToggle"><input type="checkbox" checked={showRange} disabled={!state.coverage_loaded}
        onChange={event => setShowRange(event.target.checked)}/>显示发光范围</label>
      <p className="lightGlowCaption">绿色透明度来自实际输出与输入的最大预乘 RGB 差值。未变化处透明；这不是 AI 识别的受光面、阈值选区或可编辑蒙版。显示叠层不进入成片。</p>
      {review.no_change && <p role="status">真实输出未改变像素，作用范围应为空。创建新图仍需下方确认。</p>}
      {review.notes.length > 0 && <ul className="lightGlowNotes">{review.notes.map((note, index) => <li key={index}>{note}</li>)}</ul>}
      <label className="lightGlowToggle"><input type="checkbox" checked={state.reviewed} disabled={!canAcknowledge}
        onChange={event => controller.acknowledge(event.target.checked)}/>我已查看完整前后对比，确认创建独立新图，不覆盖原照片。</label>
    </section>}
    <footer className="lightGlowFooter">
      <p>返回方式：仅创建独立新图。更新源图尚未接入，不提供伪装可用的入口。项目保存与图片导出仍需另行操作。</p>
      <button type="button" disabled={disabled || !controller.canApply()} onClick={() => void controller.apply()}>应用为独立新图</button>
      {state.terminal_refresh === 'failed' && <button type="button" onClick={() => void controller.refreshTerminal()}>仅重试编辑器刷新</button>}
    </footer>
  </section>;
}
