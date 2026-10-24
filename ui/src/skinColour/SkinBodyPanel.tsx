// SPDX-License-Identifier: GPL-3.0-or-later
import {useEffect, useLayoutEffect, useRef, useState} from 'react';
import {peopleContext, type PeopleAction} from '../people/model';
import type {PeopleOwner} from '../people/usePeopleWorkflow';
import {matchesSource, previewImage} from '../legShape/sourcePreview';
import {skinColourBindingKey, skinColourTargetReady} from './model';
import {SkinBodySourceEditor} from './SkinBodySourceEditor';
import {OwnFaceReferenceDisclosure} from '../bodyFaceMatch/OwnFaceReferenceDisclosure';
import {validOwnFaceReference} from '../bodyFaceMatch/reference';
import {bodyRefKey, bodyReview, bodyReviewKey, emptyBodyMask, parseBodyReviewAmount, previewMatches, referenceMatches, renderedSkinImage,
  SKIN_BODY_FAMILIES, skinBodyAttached, skinBodyFamilyMatches, skinBodyReport, skinBodyTarget, skinBodyRequestFits,
  type SkinBodyFamily, type SkinBodyAction, type SkinBodyMask, type SkinBodyPayload,
  type SkinBodyPreview, type SkinBodyReference, type SkinBodyReview} from './bodyReviewModel';
const emptyFlags = () => ({visible: false, unoccluded: false, ownership_confirmed: false});
type Expected = {id: string; context: string; action: SkinBodyAction; review?: SkinBodyReview; amount?: number};

/** Local review drafts only; submission, uncertainty and publication stay with people. */
export function SkinBodyPanel({people, blocked, coreAvailable, family = 'skin_colour', reviewBinding,
  reviewCanSubmit = true, detachNeutral = false}: {
  people: PeopleOwner; blocked: boolean; coreAvailable: boolean; family?: SkinBodyFamily;
  reviewBinding?: string; reviewCanSubmit?: boolean; detachNeutral?: boolean;
}) {
  const actions = SKIN_BODY_FAMILIES[family].actions, finish = family === 'skin_finish', evenness = family === 'body_skin_evenness';
  const faceMatch = family === 'body_face_match', stagedBody = evenness || faceMatch;
  const operationLabel = faceMatch ? '身体向本人脸部色度匹配' : evenness ? '身体色度均匀' : finish ? '美白与红润' : '色温与色调';
  const view = people.value, context = reviewBinding === undefined
    ? `${family}:${skinColourBindingKey(view)}` : `${family}:${reviewBinding}`;
  const latest = useRef(context); latest.current = context;
  const expected = useRef<Expected | null>(null);
  const [open, setOpen] = useState(false), [reference, setReference] = useState<SkinBodyReference | null>(null);
  const [choice, setChoice] = useState(''), [mask, setMask] = useState<SkinBodyMask>(emptyBodyMask);
  const [flags, setFlags] = useState(emptyFlags), [preview, setPreview] = useState<SkinBodyPreview | null>(null);
  const [sourceLoaded, setSourceLoaded] = useState(false), [loaded, setLoaded] = useState<Record<string, boolean>>({});
  const [referenceLoaded, setReferenceLoaded] = useState(false), [referenceAccepted, setReferenceAccepted] = useState(false);
  const reviewSession = useRef(0), imageSession = reviewSession.current;
  const [reviewed, setReviewed] = useState(false), [error, setError] = useState('');
  const [amountText, setAmountText] = useState(''), amount = parseBodyReviewAmount(amountText);
  const mounted = useRef(false);
  useLayoutEffect(() => {mounted.current = true; return () => {mounted.current = false;};}, []);
  const busy = blocked || !people.enabled || people.state.pending || people.state.uncertain;
  const allowed = skinBodyTarget(view), attached = skinBodyAttached(view, family), report = skinBodyReport(view, family);
  const canDetach = !!view && skinColourTargetReady(view) && view.editing_target?.scope === 'face'
    && view.editing_target.target_id === view.selected_face_id && (!stagedBody || detachNeutral);
  const live = useRef({context, busy, allowed, canDetach, coreAvailable, reviewCanSubmit}); live.current = {context, busy, allowed, canDetach, coreAvailable, reviewCanSubmit};
  function close() {reviewSession.current++; expected.current = null; setOpen(false); setReference(null); setPreview(null); setMask(emptyBodyMask()); setChoice(''); setFlags(emptyFlags()); setReviewed(false); setLoaded({}); setSourceLoaded(false); setReferenceLoaded(false); setReferenceAccepted(false); setAmountText('');}
  useEffect(() => {close(); setError('');}, [context]);
  useEffect(() => {
    if (!people.state.pending && !people.state.uncertain && !people.state.lastBodyResult && people.state.message) expected.current = null;
  }, [people.state.pending, people.state.uncertain, people.state.lastBodyResult, people.state.message]);

  useEffect(() => {
    const receipt = people.state.lastBodyResult, request = expected.current;
    if (!receipt || !request || receipt.result.request_id !== request.id || receipt.command.action !== request.action
      || request.context !== latest.current || !view) return;
    expected.current = null;
    try {
      if (receipt.result.payload_released) throw Error('这次审核图已释放；请重新打开来源参考并生成新的审核图，原请求不会重发。');
      const payload = receipt.result.payload as SkinBodyPayload | undefined;
      if (!payload) throw Error('审核回执缺少图像数据，请重新读取来源参考。');
      if (!skinBodyFamilyMatches(payload, family)) throw Error(stagedBody ? `审核回执不属于${operationLabel}；其他身体或脸部功能的审核不能授权本功能。` : '审核回执不属于当前调整功能；色温色调与美白红润的审核不能互相授权。');
      if (request.action === actions.reference && payload.kind === 'reference') {
        const image = previewImage(payload.source_preview);
        if (!referenceMatches(payload, view, family) || !matchesSource(image, {...payload.source, orientation: 'exif_normalized_once'})) throw Error('参考图与当前人物、实际来源或身体观察不匹配。');
        reviewSession.current++; setReference(payload); setOpen(true); setChoice(''); setMask(emptyBodyMask()); setFlags(emptyFlags()); setPreview(null); setReviewed(false); setLoaded({}); setSourceLoaded(false); setReferenceLoaded(false); setReferenceAccepted(false); setAmountText('');
      } else if (request.action === actions.preview && payload.kind === 'preview' && reference && request.review) {
        const overlay = previewImage(payload.overlay);
        const matching = stagedBody ? previewMatches(payload, reference, request.review, family, request.amount)
          : previewMatches(payload, reference, request.review, family);
        if (!matching || !matchesSource(overlay, {...reference.source, orientation: 'exif_normalized_once'})) throw Error(stagedBody ? '候选回执与提交的笔迹、人物、强度或来源不匹配，请重新审核。' : '候选回执与提交的笔迹、人物或来源不匹配，请重新审核。');
        setPreview(payload); setReviewed(false); setLoaded({});
      } else if ((request.action === actions.confirm && payload.kind === 'confirmed' && payload.attached === true)
        || (request.action === actions.detach && payload.kind === 'detached' && payload.attached === false)) close();
      else throw Error('审核回执类型与当前请求不匹配。');
      setError('');
    } catch (reason) {setPreview(null); setReviewed(false); setError(String(reason));}
  }, [people.state.lastBodyResult, view, reference, family, actions]);

  function send(action: SkinBodyAction, payload: Record<string, unknown>, review?: SkinBodyReview, candidateAmount?: number) {
    if (stagedBody && (!mounted.current || liveDraft.current !== draftSnapshot)) return;
    if (expected.current || live.current.context !== context || live.current.busy || (action === actions.detach ? !live.current.canDetach : !live.current.allowed)) return;
    if ((action === actions.preview || action === actions.confirm) && (!live.current.coreAvailable || (stagedBody && !live.current.reviewCanSubmit))) return;
    if (stagedBody && (action === actions.preview || action === actions.confirm)
      && (!reference || !view || !referenceMatches(reference, view, family))) return;
    if (faceMatch && (action === actions.preview || action === actions.confirm) && !referenceReady) return;
    const captured = peopleContext(view); if (!captured) return;
    const command: PeopleAction = {...structuredClone(captured), request_id: crypto.randomUUID(), action, payload: structuredClone(payload)};
    if (!skinBodyRequestFits(command)) {
      setError('笔迹请求超过 192 KiB 安全预算，尚未发送。请撤回或清理草稿；不会自动删减几何点。'); return;
    }
    expected.current = {id: command.request_id, context, action, review: review ? structuredClone(review) : undefined, amount: candidateAmount};
    setError('');
    void people.submitCaptured(command).catch(reason => {
      if ((!stagedBody || mounted.current) && latest.current === context && expected.current?.id === command.request_id) setError(String(reason));
    });
  }
  function edit(next: SkinBodyMask) {setMask(next); setFlags(emptyFlags()); setPreview(null); setReviewed(false); setLoaded({});}
  function invalidateReview() {setFlags(emptyFlags()); setPreview(null); setReviewed(false); setLoaded({});}
  const selected = reference?.bodies.find(body => bodyRefKey(body.body_ref) === choice);
  const sourceImage = reference ? previewImage(reference.source_preview) : null;
  const referenceImage = reference ? previewImage(reference.reference_overlay ?? null) : null;
  const referenceReady = !faceMatch || (referenceLoaded && referenceAccepted);
  const reportReady = report?.needs_review === false && (!faceMatch || validOwnFaceReference(report.own_face_reference, report.face_ref));
  const overlay = preview ? previewImage(preview.overlay) : null;
  const images = preview ? [
    {key: 'before', url: renderedSkinImage(preview.before), width: preview.before.width, height: preview.before.height, caption: stagedBody ? '本次审核前：真实渲染结果' : '添加此身体范围前：真实渲染结果'},
    {key: 'after', url: renderedSkinImage(preview.after), width: preview.after.width, height: preview.after.height, caption: stagedBody ? '独立身体范围与所选强度：真实候选结果，尚未提交' : '添加此身体范围后：真实候选结果，尚未提交'},
    {key: 'overlay', url: overlay?.url ?? null, width: overlay?.displayWidth ?? 0, height: overlay?.displayHeight ?? 0, caption: faceMatch ? '未修饰有效来源坐标中的实际身体范围（青色）；本人脸部的实际采样阶段另见参考图，不是裁剪后效果图' : '来源坐标中的实际皮肤范围叠图，不是裁剪后效果图'},
  ] : [];
  const comparisonLoaded = images.length === 3 && images.every(image => !!image.url && loaded[`${preview!.preview_id}:${image.key}`]);
  const draftMatches = !!preview && !!selected && (!stagedBody || (amount !== null && preview.amount === amount)) && bodyReviewKey(preview.review) === bodyReviewKey({body_ref: selected.body_ref,
    points_sha256: selected.points_sha256, recipe: mask, visible: true, unoccluded: true, ownership_confirmed: true});
  const draftSnapshot = bodyReviewKey([choice, mask, flags, amount, sourceLoaded, referenceLoaded, referenceAccepted, imageSession, preview?.preview_id, comparisonLoaded, draftMatches, reviewed]);
  const liveDraft = useRef(draftSnapshot); liveDraft.current = draftSnapshot;
  const canvasKey = `${context}:${choice}`, liveCanvasKey = useRef(canvasKey); liveCanvasKey.current = canvasKey;
  const currentPreview = useRef(preview?.preview_id); currentPreview.current = preview?.preview_id;
  const imageCurrent = () => mounted.current && latest.current === context && reviewSession.current === imageSession;
  return <section aria-label={`${operationLabel}的可见身体皮肤范围审核`} data-body-family={family}>
    <p>{stagedBody ? `${operationLabel}只使用当前人物已确认关联的真实身体观察，并经本功能独立手绘复核。` : '身体扩展只使用当前人物已确认关联的真实身体观察，并经手绘复核。'}不会复制其他人物的范围，也不会推测衣物下或被遮挡的皮肤。</p>
    {finish && <p>此处仅授权美白与红润。已有色温色调的身体范围不会复制、扩大或自动授权本功能，请重新画出并独立确认。</p>}
    {stagedBody && <p>此处只授权{operationLabel}，不复制色温、美白红润或脸部蒙版，也不沿用其他身体功能的审核。先明确选择一个候选强度，再画出并检查本人的身体皮肤；确认会一起提交此人物独立强度与本功能范围，不写入分组、关联人物或全部默认。</p>}
    <p role="status">{attached === true ? reportReady ? stagedBody ? `当前人物已有${operationLabel}的有效独立审核范围；只作用于该身体范围，不调整脸部。` : `当前人物已附加本功能的有效身体皮肤范围；${operationLabel}同时作用于其脸部及审核范围。` : '当前人物保留了本功能的身体范围，但审核或参考身份尚未确认或需要重新审核，不能视为可用。' : attached === false ? stagedBody ? `当前人物尚未附加${operationLabel}范围；非零调整不可用，不能回退到脸部或其他功能范围。` : '当前人物尚未为本功能附加身体范围，仍仅调整面部皮肤。' : '尚未取得当前人物在本功能中的身体范围状态。'}</p>
    {attached !== null && report?.reason && <p role="status">{report.reason}</p>}
    {!allowed && <p className="muted">请在人物栏选择当前已分析人物的独立编辑范围；人物、分组或全部默认不能直接拥有此来源选区。</p>}
    <button type="button" className="specBtn" disabled={busy || !allowed} onClick={() => {if (expected.current) return; close(); send(actions.reference, {});}}>打开当前来源图审核{operationLabel}的身体皮肤</button>
    <button type="button" className="specBtn" disabled={busy || !canDetach || attached !== true} onClick={() => send(actions.detach, {})}>{stagedBody ? `仅移除此人物的${operationLabel}审核范围（须先归零）` : `移除此人物的${operationLabel}身体范围，保留面部调整`}</button>
    {stagedBody && attached === true && !detachNeutral && <p role="status">移除前请先将此人物独立身体强度归零，并等待权威读数确认。不会偷偷清除或恢复共享范围强度。</p>}
    {open && reference && <div>
      <button type="button" onClick={close}>{people.state.pending ? '关闭审核，已发请求仍待确认' : '关闭审核，不提交草稿'}</button>
      {faceMatch && <OwnFaceReferenceDisclosure key={`${context}:${imageSession}`} image={referenceImage} support={reference.reference_support}
        stage={reference.reference_source_stage} busy={busy} loaded={referenceLoaded} accepted={referenceAccepted}
        onLoaded={ready => {if (!imageCurrent()) return; setReferenceLoaded(ready); if (!ready) {setReferenceAccepted(false); setPreview(null); setReviewed(false); setLoaded({});}}}
        onAccepted={accepted => {if (!imageCurrent()) return; setReferenceAccepted(accepted); setPreview(null); setReviewed(false); setLoaded({});}}/>}
      {stagedBody && <label>本次候选身体强度（大于 0，至 100）<input type="number" min={0} max={100} step="any" value={amountText}
        disabled={busy} aria-label={`${operationLabel}审核候选强度`} onChange={event => {setAmountText(event.target.value); setPreview(null); setReviewed(false); setLoaded({});}}/>
        <span> 留空或 0 不生成候选；这里只保存本地草稿，确认审核前不写入效果。</span></label>}
      <label>已确认关联的身体<select value={choice} disabled={busy} onChange={event => {setChoice(event.target.value); edit(emptyBodyMask()); setSourceLoaded(false);}}>
        <option value="">请明确选择身体</option>{reference.bodies.map((body, index) => <option key={bodyRefKey(body.body_ref)} value={bodyRefKey(body.body_ref)}>已关联身体 {index + 1}</option>)}
      </select></label>
      {!reference.bodies.length && <p role="status">没有与此脸可靠关联的真实身体观察。请先在全身塑形中完成身体分析与人物关联；不会按脸框或肤色猜测。</p>}
      {selected && <SkinBodySourceEditor key={`${context}:${choice}`} context={`${context}:${choice}`} source={reference.source} image={sourceImage}
        value={mask} disabled={busy} onChange={edit} onLoaded={ready => {if (!stagedBody || (imageCurrent() && liveCanvasKey.current === canvasKey)) setSourceLoaded(ready);}} onDraftStart={invalidateReview}/>}
      {(['visible', 'unoccluded', 'ownership_confirmed'] as const).map(flag => <label key={flag} style={{display: 'block'}}>
        <input type="checkbox" disabled={busy || !selected || !sourceLoaded || !mask.objects.length} checked={flags[flag]}
          onChange={event => {setFlags(old => ({...old, [flag]: event.target.checked})); setPreview(null); setReviewed(false); setLoaded({});}}/>
        {operationLabel}：{flag === 'visible' ? '我确认笔迹所选均为来源图中真实可见的身体皮肤' : flag === 'unoccluded' ? '我确认已排除衣物、头发、物体及遮挡区域' : '我确认所选范围只属于当前脸与已关联身体，没有其他人物'}
      </label>)}
      <button type="button" className="specBtn" disabled={busy || !coreAvailable || !selected || !sourceLoaded || !referenceReady || !Object.values(flags).every(Boolean) || (stagedBody && (!reviewCanSubmit || amount === null))} onClick={() => {
        if (!selected || (stagedBody && amount === null)) return; try {const review = bodyReview(selected, mask, flags); setPreview(null); setReviewed(false); setLoaded({}); send(actions.preview, stagedBody ? {review, amount} : {review}, review, stagedBody ? amount! : undefined);} catch (reason) {setError(String(reason));}
      }}>生成真实前后对比与范围审核图</button>
      {!coreAvailable && <p role="status">{operationLabel}核心不可用，不能生成或确认真实候选；{stagedBody ? '仍可先归零，权威读数确认中性后移除本功能身体范围。' : '仍可移除当前人物已附加的本功能身体范围。'}</p>}
      <p className="muted">{stagedBody ? '候选强度只用于这次真实对比；确认后才与此身体范围一起成为当前人物的独立覆盖。已有共享强度也不会自动借入候选。' : `请先在${finish ? '美白或红润' : '色温或色调'}设置非零值，再打开审核；两项均为零时不会制造虚假的变化。`}更改调整参数、照片、人物或分析会使本次审核失效。</p>
      {preview && <div>
        {images.map(image => <figure key={`${preview.preview_id}:${image.key}`} style={{margin: '8px 0'}}>
          {image.url && <img src={image.url} alt={image.caption} style={{width: '100%', height: 'auto'}} onLoad={event => {
            if (stagedBody && (!imageCurrent() || currentPreview.current !== preview.preview_id)) return;
            const valid = event.currentTarget.naturalWidth === image.width && event.currentTarget.naturalHeight === image.height;
            setLoaded(old => ({...old, [`${preview.preview_id}:${image.key}`]: valid})); if (!valid) {setReviewed(false); setError('审核图实际尺寸与回执不符。');}
          }} onError={() => {if (stagedBody && (!imageCurrent() || currentPreview.current !== preview.preview_id)) return; setLoaded(old => ({...old, [`${preview.preview_id}:${image.key}`]: false})); setReviewed(false); setError('审核图加载失败，不能确认。');}}/>}
          <figcaption>{image.caption}</figcaption>
        </figure>)}
        <p>请对比肤色、皮肤边缘与邻近人物；手工确认不等于分割或照片质量验收。图像为缩略对比，不能证明所有细节正确。</p>
        <label><input type="checkbox" checked={reviewed} disabled={busy || !referenceReady || !comparisonLoaded || !draftMatches} onChange={event => setReviewed(event.target.checked)}/>我已看过这组三张审核图，确认可见皮肤范围与当前人物一致，并独立接受{operationLabel}的此候选效果</label>
        <button type="button" className="specBtn" disabled={busy || !coreAvailable || !allowed || !referenceReady || !reviewed || !comparisonLoaded || !draftMatches || (stagedBody && !reviewCanSubmit)}
          onClick={() => {if (preview && comparisonLoaded && draftMatches && reviewed) send(actions.confirm, {preview_id: preview.preview_id, reviewed: true});}}>{stagedBody ? `确认此身体范围，并将此人物独立强度设为 ${preview.amount === undefined ? '未提供有效强度' : Number((preview.amount * 100).toFixed(6))}` : `确认附加${operationLabel}的此身体皮肤范围`}</button>
      </div>}
    </div>}
    {error && <p role="alert">{error}</p>}
    <p className="muted">{faceMatch ? '这是手动辅助、身体向本人来源脸部的色度匹配，不是学习型 AI、自动全身皮肤实例识别、亮度匹配或后续修饰脸部的效果复制。' : evenness ? '这是手动辅助、本人身体自参考的局部色度均匀，不是自动全身皮肤实例识别、学习型 AI 或脸身肤色匹配。' : finish ? '这是美白与红润的手动审核身体扩展，不是自动全身皮肤识别、肤色统一、腮红绘制或健康评估。' : '这是手动审核的身体皮肤扩展，不是自动全身肤色识别、AI 美白或肤色统一；'}皮肤功能族仍未完整验收。</p>
  </section>;
}
