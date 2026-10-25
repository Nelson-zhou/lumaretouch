// SPDX-License-Identifier: GPL-3.0-or-later
import {useEffect, useLayoutEffect, useRef, useState} from 'react';
import type {PeopleAction, PeopleView} from '../people/model';
import type {PeopleOwner} from '../people/usePeopleWorkflow';
import type {SpillImage} from '../spillRemoval/model';
import type {SkinBodyMask} from '../skinColour/bodyReviewModel';
import {SkinBodySourceEditor} from '../skinColour/SkinBodySourceEditor';
import {ReviewedImage} from './ReviewedImage';
import {SkinReferenceChoicePanel} from '../skinReferenceChoice/SkinReferenceChoicePanel';
import {OPERATION_ID, ack, canonical, catalogImage, emptyMask, object, parseAmount, previewMatchesCatalog,
  requestFits, reviewImage, reviewKey, skinReferenceBodyBinding, skinReferenceBodyContext, sourceEditorImage,
  targetKey, validCatalog, validClear, validConfirmation, validMask, validPreview, validReview,
  type SkinReferenceBodyAction, type SkinReferenceBodyCatalog, type SkinReferenceBodyPreview,
  type SkinReferenceBodyReview, type SkinReferenceBodySide} from './model';

type Expected = {command: PeopleAction; key: string; view: PeopleView; preview?: SkinReferenceBodyPreview;
  review?: SkinReferenceBodyReview; side?: SkinReferenceBodySide};
type Pair<T> = Partial<Record<SkinReferenceBodySide, T>>;
type Consent = {visible: boolean; unoccluded: boolean; ownership: boolean; referenceUnchanged: boolean};
const noConsent = (): Consent => ({visible: false, unoccluded: false, ownership: false, referenceUnchanged: false});

/** Ephemeral draft only. The canonical PeopleOwner remains the only request, mutation and history owner. */
export function SkinReferenceBodyPanel({people, blocked, available, choiceAvailable}: {
  people: PeopleOwner; blocked: boolean; available: boolean; choiceAvailable: boolean;
}) {
  const view = people.value, binding = skinReferenceBodyBinding(view);
  const [catalog, setCatalog] = useState<SkinReferenceBodyCatalog | null>(null);
  const [referenceId, setReferenceId] = useState(''), [selectedTarget, setSelectedTarget] = useState('');
  const [amountText, setAmountText] = useState(''), [mask, setMask] = useState<SkinBodyMask>(emptyMask);
  const [sourceSeen, setSourceSeen] = useState(false), [editorReady, setEditorReady] = useState(false);
  const [consent, setConsent] = useState<Consent>(noConsent);
  const [review, setReview] = useState<SkinReferenceBodyReview | null>(null), [images, setImages] = useState<Pair<SpillImage>>({});
  const [seen, setSeen] = useState<Pair<boolean>>({}), [acknowledged, setAcknowledged] = useState(false);
  const [error, setError] = useState('');
  const expected = useRef<Expected | null>(null), mounted = useRef(false);
  const amount = parseAmount(amountText), key = canonical([binding, referenceId, selectedTarget, amountText, mask]);
  const busy = blocked || !people.enabled || people.state.pending || people.state.uncertain || people.state.skinReferenceBodyRefreshRequired;
  const allowed = available && !!view;
  const live = useRef({key, binding, busy, allowed, review, pending: people.state.pending, uncertain: people.state.uncertain});
  live.current = {key, binding, busy, allowed, review, pending: people.state.pending, uncertain: people.state.uncertain};
  useLayoutEffect(() => {mounted.current = true; return () => {mounted.current = false; expected.current = null;};}, []);
  function invalidateReview() {expected.current = null; setReview(null); setImages({}); setSeen({}); setAcknowledged(false); setError('');}
  function invalidateSelection() {setConsent(noConsent()); invalidateReview();}
  useLayoutEffect(() => {
    setCatalog(null); setReferenceId(''); setSelectedTarget(''); setAmountText(''); setMask(emptyMask());
    setSourceSeen(false); setEditorReady(false); setConsent(noConsent()); invalidateReview();
  }, [binding]);
  useLayoutEffect(() => {
    const hide = () => {if (document.visibilityState !== 'visible') {
      setSourceSeen(false); setConsent(noConsent()); setSeen({}); setAcknowledged(false);
    }};
    document.addEventListener('visibilitychange', hide);
    return () => document.removeEventListener('visibilitychange', hide);
  }, []);
  function send(action: SkinReferenceBodyAction, payload: Record<string, unknown>, details: Partial<Expected> = {}) {
    if (!view || !mounted.current || live.current.key !== key || live.current.busy || !live.current.allowed || expected.current) return;
    const context = skinReferenceBodyContext(view); if (!context) return;
    const command: PeopleAction = {...structuredClone(context), request_id: crypto.randomUUID(), action, payload: structuredClone(payload)};
    if (!requestFits(command)) {setError('笔迹请求超过安全传输上限，请撤回或简化笔迹；不会截断或删点后提交。'); return;}
    expected.current = {command, key, view: structuredClone(view), ...details}; setError('');
    void people.submitCaptured(command).catch(cause => {
      if (!mounted.current || live.current.key !== key || expected.current?.command.request_id !== command.request_id) return;
      setError(String(cause)); setAcknowledged(false);
      // An uncertain write stays with its original owner/request ID. Never resend it here.
      if (!live.current.pending && !live.current.uncertain) expected.current = null;
    });
  }
  useEffect(() => {
    const receipt = people.state.lastSkinReferenceBodyResult, request = expected.current;
    if (!receipt || !request || request.key !== live.current.key || receipt.result.request_id !== request.command.request_id
      || receipt.command.action !== request.command.action) return;
    const stillCurrent = () => mounted.current && live.current.key === request.key && expected.current === request;
    void (async () => {
      try {
        if (receipt.result.payload_released) throw Error('原身体审核内容已释放，请重新读取当前照片；不会重发修改。');
        const payload = receipt.result.payload;
        if (!object(payload)) throw Error('身体参考匹配回执缺少有效内容。');
        switch (request.command.action) {
          case 'skin_reference_body_catalog':
            if (!validCatalog(payload, request.view) || !await catalogImage(payload)) throw Error('身体来源图、参考人物或明确归属清单校验失败。');
            if (stillCurrent()) {setCatalog(payload); setReferenceId(''); setSelectedTarget(''); setAmountText('');
              setMask(emptyMask()); setSourceSeen(false); setEditorReady(false); setConsent(noConsent());}
            break;
          case 'skin_reference_body_preview':
            if (payload.kind !== 'skin_reference_body_preview' || !request.preview || !validReview(payload.review, request.view, request.preview))
              throw Error('身体候选与明确参考、目标归属、笔迹或程度不匹配。');
            if (stillCurrent()) {setReview(payload.review); setImages({}); setSeen({}); setAcknowledged(false);}
            break;
          case 'skin_reference_body_image': {
            if (!request.review || !request.side) throw Error('身体审核图缺少冻结候选绑定。');
            const image = await reviewImage(payload, request.review, request.side);
            if (!image) throw Error('整张身体审核图字节、哈希或尺寸校验失败，不能确认。');
            if (stillCurrent()) setImages(old => ({...old, [request.side!]: image}));
            break;
          }
          case 'skin_reference_body_confirm':
            if (!request.review || !validConfirmation(request.review, receipt.result)) throw Error('身体写入回执未通过校验，请查询原请求，不能重发。');
            if (stillCurrent()) {setCatalog(null); setConsent(noConsent()); invalidateReview();}
            break;
          case 'skin_reference_body_clear':
            if (!validClear(request.command, receipt.result)) throw Error('身体清除回执未通过校验，请查询原请求，不能重发。');
            if (stillCurrent()) {setCatalog(null); setConsent(noConsent()); invalidateReview();}
            break;
        }
      } catch (cause) {if (stillCurrent()) {setError(String(cause)); setAcknowledged(false); setConsent(noConsent());}}
      finally {if (stillCurrent()) expected.current = null;}
    })();
  }, [people.state.lastSkinReferenceBodyResult]);
  useEffect(() => {
    if (!people.state.pending && !people.state.uncertain && people.state.message && expected.current
      && people.state.lastSkinReferenceBodyResult?.result.request_id !== expected.current.command.request_id) {
      expected.current = null; setError(people.state.message); setAcknowledged(false);
    }
  }, [people.state]);
  useEffect(() => {
    if (!review || busy || expected.current || error || !allowed) return;
    const side = !images.before ? 'before' : !images.after ? 'after' : null;
    if (side) send('skin_reference_body_image', {token: review.token, side, sha256: review.visual[side].sha256,
      review_sha256: review.review_sha256}, {review, side});
  }, [review, images, busy, error, allowed, key]);

  const reference = catalog?.faces.find(face => face.face_ref.face_instance_id === referenceId);
  const target = catalog?.targets.find(row => targetKey(row) === selectedTarget);
  const consentReady = sourceSeen && editorReady && validMask(mask) && !!reference?.available && !!target && amount !== null;
  const allConsent = consent.visible && consent.unoccluded && consent.ownership && consent.referenceUnchanged;
  const preview: SkinReferenceBodyPreview | null = catalog && reference && target && amount !== null && validMask(mask)
    ? {version: 1, reference_face_ref: reference.face_ref, target_face_ref: target.face_ref,
      review: {operation_id: OPERATION_ID, body_ref: target.body_ref, points_sha256: target.points_sha256, recipe: mask,
        visible: true, unoccluded: true, ownership_confirmed: true, reference_unchanged: true},
      amount, source_review_sha256: catalog.source_review_sha256, ownership_confirmed: true} : null;
  const selectionReady = !!preview && !!catalog && previewMatchesCatalog(preview, catalog);
  const draftMatches = !!review && !!preview && validReview(review, view, preview);
  const ready = draftMatches && !!images.before && !!images.after && seen.before === true && seen.after === true;
  const identity = review ? reviewKey(review) : '';
  const faceNumber = (id: string) => ((catalog?.faces ?? view?.faces)?.findIndex(face => face.face_ref.face_instance_id === id) ?? -1) + 1;
  const current = catalog?.current ?? view?.skin_reference_body_match, donor = current?.reference_face_ref;
  const result = people.state.lastSkinReferenceBodyResult;
  const completed = result && view && result.command.document_id === view.binding.document_id
    && result.command.document_epoch === view.binding.document_epoch
    && ['skin_reference_body_confirm', 'skin_reference_body_clear'].includes(result.command.action);
  return <section aria-label="同照参考脸匹配独立身体皮肤">
    <h4>同照参考脸 → 独立身体皮肤</h4>
    <p>选择当前照片中的真实参考脸，再独立审核明确归属的一处身体皮肤。可请求实测亮度建议，但仍需你明确选择；不推断身体归属，也不是新的身体 AI 算法。</p>
    <p className="muted">可只处理身体，不必启用脸部匹配。参考脸可为目标本人或同照其他人物；本功能保护所有人脸，不把脸框当作身体区域，也不改脸部匹配设置。</p>
    {!available && <p role="status">当前引擎尚未提供独立身体参考协议，不能借用其他身体功能代替。</p>}
    {!view && <p role="status">请先打开照片、完成人物分析，并明确确认目标人物与身体的关联。</p>}
    <button type="button" disabled={busy || !allowed} onClick={() => {
      setCatalog(null); setSourceSeen(false); setEditorReady(false); setConsent(noConsent()); invalidateReview();
      send('skin_reference_body_catalog', {});
    }}>{catalog ? '重新读取来源与身体归属' : '读取当前来源与身体归属'}</button>
    {catalog && <>
      {!catalog.skin_reference_body_available && <p role="status">当前照片不能匹配身体：{catalog.skin_reference_body_reason}</p>}
      <figure>
        <figcaption>不可变来源整图。编号框只标识实测人脸，不代表身体范围；绿色为参考脸，蓝色为目标身体的主人。</figcaption>
        <div style={{position: 'relative', width: '100%', maxWidth: catalog.source_image.width}}>
          <ReviewedImage image={catalog.source_image} identity={catalog.source_review_sha256} alt="身体参考匹配的完整不可变来源及人物编号"
            onSeen={() => {if (live.current.binding === binding) setSourceSeen(true);}}
            onError={() => {setSourceSeen(false); setConsent(noConsent()); setAcknowledged(false); setError('来源图未能完整解码或显示，请重新读取。');}}/>
          {catalog.faces.map((face, index) => {
            const id = face.face_ref.face_instance_id, isReference = id === referenceId, isOwner = id === target?.face_ref.face_instance_id;
            return <div key={id} aria-hidden="true" style={{position: 'absolute', pointerEvents: 'none', boxSizing: 'border-box',
              left: `${face.box[0] * 100}%`, top: `${face.box[1] * 100}%`, width: `${(face.box[2] - face.box[0]) * 100}%`,
              height: `${(face.box[3] - face.box[1]) * 100}%`, border: `2px ${face.available ? 'solid' : 'dashed'} ${isReference ? '#36c785' : isOwner ? '#4a9eff' : '#a6a6a6'}`}}>
              <span style={{background: '#111c', color: '#fff', fontSize: 12}}>人物 {index + 1}{isReference ? ' · 参考脸' : ''}{isOwner ? ' · 身体主人' : ''}</span>
            </div>;
          })}
        </div>
        <p className="muted">来源 {catalog.source.width} × {catalog.source.height}；显示 {catalog.source_image.width} × {catalog.source_image.height}。缩略图不构成原尺寸质量验收。</p>
      </figure>
      <SkinReferenceChoicePanel people={people} family="body" catalog={catalog} sourceSeen={sourceSeen}
        available={choiceAvailable} blocked={busy || !allowed} lockedReference={donor} onReferenceChosen={ref => {
          if (live.current.binding !== binding || live.current.busy || !sourceSeen || document.visibilityState !== 'visible'
            || donor && canonical(donor) !== canonical(ref)) return;
          setReferenceId(ref.face_instance_id); invalidateSelection();
        }}/>
      <fieldset disabled={busy || !allowed || !catalog.skin_reference_body_available}>
        <legend>分别选择参考脸和已明确归属的身体，不自动预选</legend>
        <label>参考脸<select value={referenceId} onChange={event => {setReferenceId(event.target.value); invalidateSelection();}}>
          <option value="">请选择参考人物</option>{catalog.faces.map((face, index) =>
            <option key={face.face_ref.face_instance_id} value={face.face_ref.face_instance_id}
              disabled={!face.enabled || !face.available || !!donor && donor.face_instance_id !== face.face_ref.face_instance_id}>
              人物 {index + 1}{!face.available ? `（${face.reason}）` : ''}</option>)}</select></label>
        {!!donor && <p>本照片已有匹配共同参考人物 {faceNumber(donor.face_instance_id)}。继续编辑需选择同一参考；换参考前需在对应面板清除仍启用的脸部/身体参考匹配。此处清除身体不会清除脸部匹配。</p>}
        <label>目标身体<select value={selectedTarget} onChange={event => {
          setSelectedTarget(event.target.value); setMask(emptyMask()); setEditorReady(false); invalidateSelection();
        }}><option value="">请选择已确认归属的身体</option>{catalog.targets.map((row, index) =>
          <option key={targetKey(row)} value={targetKey(row)}>人物 {faceNumber(row.face_ref.face_instance_id)} 的已确认身体 {index + 1}</option>)}</select></label>
        {!catalog.targets.length && <p role="status">没有可审核的身体。请在既有人物/身体关联流程中明确确认归属，并取得当前来源的可用身体皮肤分析。</p>}
        {target && <>
          <p>目标：人物 {faceNumber(target.face_ref.face_instance_id)} 的明确关联身体。请只画实际可见、无遮挡的身体皮肤；不要画脸、头发、衣物、背景或其他人的皮肤。</p>
          <SkinBodySourceEditor context={canonical([binding, catalog.source_review_sha256, selectedTarget])}
            image={sourceEditorImage(catalog)} source={catalog.source} value={mask} disabled={busy || !allowed || !!review}
            onLoaded={ready => {setEditorReady(ready); if (!ready) {setConsent(noConsent()); setAcknowledged(false);}}}
            onDraftStart={invalidateSelection} onChange={next => {setMask(next); invalidateSelection();}}/>
        </>}
        <label>身体匹配程度（大于 0，至 100）<input type="number" min={0} max={100} step="any" value={amountText}
          onChange={event => {setAmountText(event.target.value); invalidateSelection();}}/></label>
        <p className="muted">只替换当前所选身体的本功能参数与审核范围；其他已保存身体目标保留。100 是本功能允许的最大程度，不保证肤色完全一致；0 不会隐式清除。</p>
        {([
          ['visible', '我已查看来源，所画范围是实际可见的身体皮肤，不补全看不见的部位'],
          ['unoccluded', '所画身体皮肤无遮挡，已减去衣物、头发、背景和其他人物'],
          ['ownership', `参考为${reference ? `人物 ${faceNumber(referenceId)}` : '尚未选择'}；身体明确属于${target ? `人物 ${faceNumber(target.face_ref.face_instance_id)}` : '尚未选择'}，我已核对人物与身体的实际归属`],
          ['referenceUnchanged', '我同意仅审核本身体参考操作，参考脸和所有人脸均保持受保护，不启用脸部匹配'],
        ] as const).map(([flag, label]) => <label key={flag} style={{display: 'block'}}><input type="checkbox" checked={consent[flag]}
          disabled={!consentReady || !selectionReady || !!error} onChange={event => {
            setConsent(old => ({...old, [flag]: event.target.checked})); setAcknowledged(false);
          }}/>{label}</label>)}
        <button type="button" disabled={!preview || !selectionReady || !consentReady || !allConsent || !!error} onClick={() => {
          if (!preview || !validPreview(preview) || !consentReady || !allConsent || document.visibilityState !== 'visible') return;
          invalidateReview(); send('skin_reference_body_preview', preview, {preview});
        }}>生成整张照片真实前后预览</button>
      </fieldset>
    </>}
    {current && <p>{current.target_face_refs.length ? `已保存身体目标：${current.target_face_refs.map(ref => `人物 ${faceNumber(ref.face_instance_id)}`).join('、')}。` : '当前没有启用的身体参考目标。禁用人物可能仍有待清理的本功能关系。'}</p>}
    <button type="button" disabled={busy || !allowed} onClick={() => {invalidateReview(); send('skin_reference_body_clear', {});}}>清除本照片全部身体参考匹配</button>
    <p className="muted">清除不依赖重新取得身体候选或原图审核。仅清除此身体参考操作，保留脸部参考匹配及其他身体调整。撤销/重做仍使用现有照片历史。</p>
    {review && draftMatches && <div>
      <p>尚未应用：参考人物 {faceNumber(review.reference_face_ref.face_instance_id)} → 人物 {faceNumber(review.target_face_ref.face_instance_id)} 的明确关联身体，程度 {Number((review.amount * 100).toFixed(6))}。其余身体目标保留，所有人脸受保护。</p>
      {(['before', 'after'] as const).map(side => <figure key={`${identity}:${side}`}>
        <figcaption>{side === 'before' ? '修改前：整张照片现有全部效果' : '修改后：整张身体参考候选与现有全部效果合成，尚未写入'}</figcaption>
        {images[side] ? <ReviewedImage image={images[side]!} identity={`${identity}:${side}`}
          alt={side === 'before' ? '完整照片当前实际渲染' : '完整照片身体参考匹配实际候选渲染'}
          onSeen={() => {if (live.current.key === key && live.current.review === review) setSeen(old => old[side] ? old : {...old, [side]: true});}}
          onError={() => {if (live.current.key !== key || live.current.review !== review) return;
            setSeen(old => ({...old, [side]: false})); setAcknowledged(false); setError('完整审核图未能正确解码或显示，请重新预览。');}}/>
          : <p role="status">正在读取{side === 'before' ? '修改前' : '修改后'}图…</p>}
      </figure>)}
      <p className="muted">两张都是真实完整混合渲染，不是孤立皮肤色块或示意图。请比较所选身体、参考脸、所有其他人脸、已保留身体目标、皮肤边界和背景；缩略图不代表原尺寸视觉验收。</p>
      <label><input type="checkbox" checked={acknowledged} disabled={busy || !ready || !allConsent || !!error}
        onChange={event => setAcknowledged(event.target.checked)}/>我已查看这两张真实前后图，接受本次身体范围、参考选择及保留目标</label>
      <button type="button" disabled={busy || !ready || !acknowledged || !allConsent || !!error} onClick={() => {
        if (live.current.key !== key || live.current.review !== review || !ready || !acknowledged || !allConsent || error
          || document.visibilityState !== 'visible') return;
        send('skin_reference_body_confirm', {token: review.token, ack: ack(review)}, {review});
      }}>确认应用身体参考匹配</button>
      <button type="button" disabled={busy} onClick={invalidateReview}>放弃候选，不改照片</button>
    </div>}
    {result && completed && <p role="status">{result.command.action === 'skin_reference_body_clear' ? '引擎已确认清除本照片的身体参考匹配。' : '引擎已确认写入本次身体参考匹配。'}可通过现有照片历史撤销或重做。</p>}
    {people.state.skinReferenceBodyRefreshRequired && <p role="alert">修改已确认，但当前照片状态尚未刷新；暂不能继续调整，不会重发修改。
      <button type="button" disabled={people.state.pending || people.state.uncertain} onClick={() => {
        void people.refreshCurrent().catch(cause => setError(String(cause)));
      }}>刷新照片状态（不重发修改）</button></p>}
    {error && <p role="alert">{error}</p>}
    {people.state.uncertain && <p role="alert">原人物请求结果尚未确认，不能重新提交。若始终无法取得原请求终态，可能需要重启整个应用并打开最后确认保存的工程；仅重开照片不能证明旧请求未写入，未保存调整可能无法保留。
      <button type="button" onClick={() => {void people.check().catch(() => {});}}>查询原请求结果（不重发）</button></p>}
  </section>;
}
