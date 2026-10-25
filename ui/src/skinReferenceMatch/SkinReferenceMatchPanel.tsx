// SPDX-License-Identifier: GPL-3.0-or-later
import {useEffect, useLayoutEffect, useRef, useState} from 'react';
import type {PeopleAction, PeopleView} from '../people/model';
import type {PeopleOwner} from '../people/usePeopleWorkflow';
import type {SpillImage} from '../spillRemoval/model';
import {ReviewedImage} from './ReviewedImage';
import {ack, canonical, catalogImage, object, parseAmount, reviewImage, reviewKey, skinReferenceBinding,
  skinReferenceContext, validCatalog, validClear, validConfirmation, validPreview, validReview,
  type SkinReferenceAction, type SkinReferenceCatalog, type SkinReferencePreview, type SkinReferenceReview,
  type SkinReferenceSide} from './model';

type Expected = {command: PeopleAction; key: string; view: PeopleView; preview?: SkinReferencePreview;
  review?: SkinReferenceReview; side?: SkinReferenceSide};
type Pair<T> = Partial<Record<SkinReferenceSide, T>>;

/** Draft UI only. PeopleOwner owns admission, pending IDs, polling, mutation and history. */
export function SkinReferenceMatchPanel({people, blocked, available}: {
  people: PeopleOwner; blocked: boolean; available: boolean;
}) {
  const view = people.value, binding = skinReferenceBinding(view);
  const [catalog, setCatalog] = useState<SkinReferenceCatalog | null>(null);
  const [referenceId, setReferenceId] = useState(''), [targetIds, setTargetIds] = useState<string[]>([]);
  const [amountText, setAmountText] = useState('');
  const [sourceSeen, setSourceSeen] = useState(false), [ownership, setOwnership] = useState(false);
  const [review, setReview] = useState<SkinReferenceReview | null>(null), [images, setImages] = useState<Pair<SpillImage>>({});
  const [seen, setSeen] = useState<Pair<boolean>>({}), [acknowledged, setAcknowledged] = useState(false);
  const [error, setError] = useState('');
  const expected = useRef<Expected | null>(null), mounted = useRef(false);
  const amount = parseAmount(amountText), key = canonical([binding, referenceId, targetIds, amountText]);
  const busy = blocked || !people.enabled || people.state.pending || people.state.uncertain || people.state.skinReferenceRefreshRequired;
  const allowed = available && !!view;
  const live = useRef({key, binding, busy, allowed, review, pending: people.state.pending, uncertain: people.state.uncertain});
  live.current = {key, binding, busy, allowed, review, pending: people.state.pending, uncertain: people.state.uncertain};
  useLayoutEffect(() => {mounted.current = true; return () => {mounted.current = false; expected.current = null;};}, []);
  function invalidateReview() {expected.current = null; setReview(null); setImages({}); setSeen({}); setAcknowledged(false); setError('');}
  function invalidateSelection() {setOwnership(false); invalidateReview();}
  useLayoutEffect(() => {
    setCatalog(null); setReferenceId(''); setTargetIds([]); setAmountText(''); setSourceSeen(false); setOwnership(false); invalidateReview();
  }, [binding]);
  useLayoutEffect(() => {
    const hide = () => {if (document.visibilityState !== 'visible') {
      setSourceSeen(false); setOwnership(false); setSeen({}); setAcknowledged(false);
    }};
    document.addEventListener('visibilitychange', hide);
    return () => document.removeEventListener('visibilitychange', hide);
  }, []);
  function send(action: SkinReferenceAction, payload: Record<string, unknown>, details: Partial<Expected> = {}) {
    if (!view || !mounted.current || live.current.key !== key || live.current.busy || !live.current.allowed || expected.current) return;
    const context = skinReferenceContext(view); if (!context) return;
    const command: PeopleAction = {...structuredClone(context), request_id: crypto.randomUUID(), action, payload: structuredClone(payload)};
    expected.current = {command, key, view: structuredClone(view), ...details}; setError('');
    void people.submitCaptured(command).catch(cause => {
      if (!mounted.current || live.current.key !== key || expected.current?.command.request_id !== command.request_id) return;
      setError(String(cause)); setAcknowledged(false);
      // Uncertain work remains query-only in the owner. No new request is sent here.
      if (!live.current.pending && !live.current.uncertain) expected.current = null;
    });
  }
  useEffect(() => {
    const receipt = people.state.lastSkinReferenceResult, request = expected.current;
    if (!receipt || !request || request.key !== live.current.key || receipt.result.request_id !== request.command.request_id
      || receipt.command.action !== request.command.action) return;
    const stillCurrent = () => mounted.current && live.current.key === request.key && expected.current === request;
    void (async () => {
      try {
        if (receipt.result.payload_released) throw Error('原审核内容已释放，请重新读取当前照片；不会重发修改。');
        const payload = receipt.result.payload;
        if (!object(payload)) throw Error('肤色匹配回执缺少有效内容。');
        if (stillCurrent()) setError('');
        switch (request.command.action) {
          case 'skin_reference_match_catalog': {
            if (!validCatalog(payload, request.view) || !await catalogImage(payload)) throw Error('来源、人物列表或原图字节校验失败。');
            if (stillCurrent()) {setCatalog(payload); setReferenceId(''); setTargetIds([]); setAmountText('');
              setSourceSeen(false); setOwnership(false);}
            break;
          }
          case 'skin_reference_match_preview': {
            if (payload.kind !== 'skin_reference_match_preview' || !request.preview || !validReview(payload.review, request.view, request.preview))
              throw Error('候选与已确认的来源、参考脸、目标列表或程度不匹配。');
            if (stillCurrent()) {setReview(payload.review); setImages({}); setSeen({}); setAcknowledged(false);}
            break;
          }
          case 'skin_reference_match_image': {
            if (!request.review || !request.side) throw Error('审核图缺少冻结候选绑定。');
            const image = await reviewImage(payload, request.review, request.side);
            if (!image) throw Error('整张审核图字节、哈希或尺寸校验失败，不能确认。');
            if (stillCurrent()) setImages(old => ({...old, [request.side!]: image}));
            break;
          }
          case 'skin_reference_match_confirm':
            if (!request.review || !validConfirmation(request.review, receipt.result)) throw Error('写入回执未通过校验，请查询原请求，不能重发。');
            if (stillCurrent()) {setCatalog(null); setOwnership(false); invalidateReview();} break;
          case 'skin_reference_match_clear':
            if (!validClear(request.command, receipt.result)) throw Error('清除回执未通过校验，请查询原请求，不能重发。');
            if (stillCurrent()) {setCatalog(null); setOwnership(false); invalidateReview();} break;
        }
      } catch (cause) {if (stillCurrent()) {setError(String(cause)); setAcknowledged(false); setOwnership(false);}}
      finally {if (stillCurrent()) expected.current = null;}
    })();
  }, [people.state.lastSkinReferenceResult]);
  useEffect(() => {
    if (!people.state.pending && !people.state.uncertain && people.state.message && expected.current
      && people.state.lastSkinReferenceResult?.result.request_id !== expected.current.command.request_id) {
      expected.current = null; setError(people.state.message); setAcknowledged(false);
    }
  }, [people.state]);
  useEffect(() => {
    if (!review || busy || expected.current || error || !allowed) return;
    const side = !images.before ? 'before' : !images.after ? 'after' : null;
    if (side) send('skin_reference_match_image', {token: review.token, side, sha256: review.visual[side].sha256,
      review_sha256: review.review_sha256}, {review, side});
  }, [review, images, busy, error, allowed, key]);

  const reference = catalog?.faces.find(face => face.face_ref.face_instance_id === referenceId);
  const targets = catalog?.faces.filter(face => targetIds.includes(face.face_ref.face_instance_id)) ?? [];
  const selectionReady = !!catalog && !!reference?.available && reference.enabled && targets.length > 0
    && targets.length === targetIds.length && targets.every(face => face.available && face.enabled && face.face_ref.face_instance_id !== referenceId)
    && amount !== null;
  const preview: SkinReferencePreview | null = selectionReady && catalog && reference && amount !== null
    ? {version: 1, reference_face_ref: reference.face_ref, target_face_refs: targets.map(face => face.face_ref), amount,
      source_review_sha256: catalog.source_review_sha256, ownership_confirmed: true} : null;
  const draftMatches = !!review && !!preview && validReview(review, view, preview);
  const ready = draftMatches && !!images.before && !!images.after && seen.before === true && seen.after === true;
  const identity = review ? reviewKey(review) : '';
  const faceNumber = (id: string) => (catalog?.faces.findIndex(face => face.face_ref.face_instance_id === id) ?? -1) + 1;
  const labels = (ids: string[]) => ids.map(id => `人物 ${faceNumber(id)}`).join('、');
  const current = catalog?.current;
  const removed = review?.before_target_face_refs.filter(ref => !review.target_face_refs.some(next => next.face_instance_id === ref.face_instance_id)) ?? [];
  const result = people.state.lastSkinReferenceResult;
  const completed = result && view && result.command.document_id === view.binding.document_id
    && result.command.document_epoch === view.binding.document_epoch
    && ['skin_reference_match_confirm', 'skin_reference_match_clear'].includes(result.command.action);
  return <section aria-label="多人肤色与亮度参考匹配">
    <h4>多人肤色与亮度参考匹配</h4>
    <p>仅匹配当前照片中明确勾选人脸的皮肤颜色与亮度，使用你选择的另一张脸作为参考。不会自动选择最亮的人，不处理身体，也不是身体 AI 匹配。</p>
    <p className="muted">这是部分匹配功能：基于已测得的脸部区域与当前原图或有效派生来源，不识别人名或身份。参考脸不会被本功能修改；眼睛、嘴唇、头发和背景不属于目标皮肤。请以真实前后图判断局部边缘、肤色和原有效果叠加后的结果。</p>
    {!available && <p role="status">当前引擎尚未提供此功能，不能使用其他肤色滑块代替。</p>}
    {!view && <p role="status">请先打开照片并完成人物分析。</p>}
    <button type="button" disabled={busy || !allowed} onClick={() => {
      setCatalog(null); setSourceSeen(false); setOwnership(false); invalidateReview();
      send('skin_reference_match_catalog', {});
    }}>{catalog ? '重新读取来源与人物' : '读取当前照片来源与人物'}</button>
    {catalog && <>
      {!catalog.skin_reference_match_available && <p role="status">当前照片不能匹配：{catalog.skin_reference_match_reason}</p>}
      <figure>
        <figcaption>不可变来源整图与实测人脸框。绿色为明确参考，蓝色为目标，灰色为未选择或不可用。编号与下方选择一一对应。</figcaption>
        <div style={{position: 'relative', width: '100%', maxWidth: catalog.source_image.width}}>
          <ReviewedImage image={catalog.source_image} identity={catalog.source_review_sha256} alt="当前照片不可变来源，带实测人脸编号"
            onSeen={() => {if (live.current.binding === binding) setSourceSeen(true);}}
            onError={() => {setSourceSeen(false); setOwnership(false); setAcknowledged(false); setError('来源图未能完整解码或显示，请重新读取。');}}/>
          {catalog.faces.map((face, index) => {
            const id = face.face_ref.face_instance_id, donor = id === referenceId, target = targetIds.includes(id);
            return <div key={id} aria-hidden="true" style={{position: 'absolute', pointerEvents: 'none', boxSizing: 'border-box',
              left: `${face.box[0] * 100}%`, top: `${face.box[1] * 100}%`, width: `${(face.box[2] - face.box[0]) * 100}%`,
              height: `${(face.box[3] - face.box[1]) * 100}%`, border: `2px ${face.available ? 'solid' : 'dashed'} ${donor ? '#36c785' : target ? '#4a9eff' : '#a6a6a6'}`}}>
              <span style={{background: '#111c', color: '#fff', fontSize: 12}}>人物 {index + 1}{donor ? ' · 参考' : target ? ' · 目标' : ''}</span>
            </div>;
          })}
        </div>
        <p className="muted">来源 {catalog.source.width} × {catalog.source.height}；显示图 {catalog.source_image.width} × {catalog.source_image.height}。此图用于确认人物归属，不是编辑后预览，也不是原尺寸质量验收。</p>
      </figure>
      <fieldset disabled={busy || !allowed || !catalog.skin_reference_match_available}>
        <legend>明确选择参考与目标，不自动预选</legend>
        <label>参考人物<select value={referenceId} onChange={event => {
          const next = event.target.value; setReferenceId(next); setTargetIds(old => old.filter(id => id !== next)); invalidateSelection();
        }}><option value="">请选择参考人物</option>{catalog.faces.map((face, index) =>
          <option key={face.face_ref.face_instance_id} value={face.face_ref.face_instance_id} disabled={!face.enabled || !face.available}>
            人物 {index + 1}{!face.available ? `（${face.reason}）` : ''}</option>)}</select></label>
        <div role="group" aria-label="明确选择目标人物">{catalog.faces.map((face, index) => {
          const id = face.face_ref.face_instance_id;
          return <label key={id} style={{display: 'block'}}><input type="checkbox" checked={targetIds.includes(id)}
            disabled={!face.enabled || !face.available || id === referenceId} onChange={event => {
              const checked = event.target.checked;
              setTargetIds(old => checked ? [...old.filter(item => item !== id), id] : old.filter(item => item !== id)); invalidateSelection();
            }}/>人物 {index + 1}{id === referenceId ? '（参考，不会作为目标）' : ''}
            {!face.available && <span> · 不可用：{face.reason}</span>}
            {face.amount > 0 && <span> · 已保存匹配程度 {Number((face.amount * 100).toFixed(6))}</span>}</label>;
        })}</div>
        <label>匹配程度（大于 0，至 100）<input type="number" min={0} max={100} step="any" value={amountText}
          onChange={event => {setAmountText(event.target.value); invalidateSelection();}}/></label>
        <p className="muted">100 表示本功能允许的最大匹配，不保证肤色完全相同；0 不是清除。新候选会替换本照片原有参考匹配及目标名单，不会叠加。</p>
        <label><input type="checkbox" checked={ownership} disabled={!sourceSeen || !selectionReady || !!error}
          onChange={event => {setOwnership(event.target.checked); setAcknowledged(false);}}/>
          我已查看真实来源图，确认参考为{reference ? `人物 ${faceNumber(referenceId)}` : '尚未选择'}，目标为{targetIds.length ? labels(targetIds) : '尚未选择'}，人物框归属正确</label>
        <button type="button" disabled={!preview || !ownership || !sourceSeen || !!error} onClick={() => {
          if (!preview || !validPreview(preview) || !ownership || !sourceSeen || document.visibilityState !== 'visible') return;
          invalidateReview(); send('skin_reference_match_preview', preview, {preview});
        }}>生成整张照片前后预览</button>
      </fieldset>
      {current && <div>
        {current.target_face_refs.length > 0
          ? <p>当前已保存参考：{current.reference_face_ref ? `人物 ${faceNumber(current.reference_face_ref.face_instance_id)}` : '无'}；目标：{labels(current.target_face_refs.map(ref => ref.face_instance_id))}。</p>
          : <p className="muted">当前没有启用的匹配目标。已禁用的人物可能仍保留本功能的旧参数或支持关系。</p>}
        <button type="button" disabled={busy || !allowed} onClick={() => {invalidateReview(); send('skin_reference_match_clear', {});}}>清除本照片全部参考匹配</button>
        <p className="muted">清除只移除此功能，不清除其他肤色、亮度或人物调整。通过现有照片历史撤销或重做。</p>
      </div>}
    </>}
    {review && draftMatches && <div>
      <p>尚未应用：参考人物 {faceNumber(review.reference_face_ref.face_instance_id)} → {labels(review.target_face_refs.map(ref => ref.face_instance_id))}，程度 {Number((review.amount * 100).toFixed(6))}。</p>
      {!!removed.length && <p role="status">确认后，以下旧目标将移除此功能的匹配：{labels(removed.map(ref => ref.face_instance_id))}。请同时检查这些人脸。</p>}
      {(['before', 'after'] as const).map(side => <figure key={`${identity}:${side}`}>
        <figcaption>{side === 'before' ? '修改前：整张当前真实渲染' : '修改后：整张候选真实渲染，尚未写入'}</figcaption>
        {images[side] ? <ReviewedImage image={images[side]!} identity={`${identity}:${side}`}
          alt={side === 'before' ? '完整照片现有全部效果' : '完整照片参考匹配与现有全部效果合成候选'}
          onSeen={() => {if (live.current.key === key && live.current.review === review) setSeen(old => old[side] ? old : {...old, [side]: true});}}
          onError={() => {if (live.current.key !== key || live.current.review !== review) return;
            setSeen(old => ({...old, [side]: false})); setAcknowledged(false); setError('完整审核图未能正确解码或显示，请重新预览。');}}/>
          : <p role="status">正在读取{side === 'before' ? '修改前' : '修改后'}图…</p>}
      </figure>)}
      <p className="muted">两张均为包含当前其他调整的完整渲染缩略图，不是孤立色块、人物替身或虚构示意。请检查目标、参考、未选人物、皮肤边缘和背景。画面或参数变化后需重新审核。</p>
      <label><input type="checkbox" checked={acknowledged} disabled={busy || !ready || !!error}
        onChange={event => setAcknowledged(event.target.checked)}/>我已查看这两张实际前后图，接受明确目标名单与替换范围</label>
      <button type="button" disabled={busy || !ready || !acknowledged || !!error} onClick={() => {
        if (live.current.key !== key || live.current.review !== review || !ready || !acknowledged || error
          || document.visibilityState !== 'visible') return;
        send('skin_reference_match_confirm', {token: review.token, ack: ack(review)}, {review});
      }}>确认应用本照片匹配</button>
      <button type="button" disabled={busy} onClick={invalidateReview}>放弃候选，不改照片</button>
    </div>}
    {result && completed && <p role="status">{result.command.action === 'skin_reference_match_clear' ? '引擎已确认清除本照片的参考匹配。' : '引擎已确认写入本照片的参考匹配。'}可通过现有照片历史撤销或重做。</p>}
    {people.state.skinReferenceRefreshRequired && <p role="alert">修改已确认，但当前照片状态尚未刷新，暂不能继续调整。不会重新应用原修改。
      <button type="button" disabled={people.state.pending || people.state.uncertain} onClick={() => {
        void people.refreshCurrent().catch(cause => setError(String(cause)));
      }}>刷新当前照片状态（不重发修改）</button></p>}
    {error && <p role="alert">{error}</p>}
    {people.state.uncertain && <p role="alert">原人物请求结果尚未确认，不能重新提交。若始终无法取得原请求终态，可能需要重启整个应用并打开最后确认保存的工程；仅重开照片不能证明旧请求未写入，未保存调整可能无法保留。
      <button type="button" onClick={() => {void people.check().catch(() => {});}}>查询原请求结果（不重发）</button></p>}
  </section>;
}
