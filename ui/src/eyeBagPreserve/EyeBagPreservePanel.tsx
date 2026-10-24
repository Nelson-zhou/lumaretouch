// SPDX-License-Identifier: GPL-3.0-or-later
import {useEffect, useLayoutEffect, useRef, useState} from 'react';
import {peopleContext, type PeopleAction} from '../people/model';
import type {PeopleOwner} from '../people/usePeopleWorkflow';
import type {SpillImage} from '../spillRemoval/model';
import {previewImage} from '../legShape/sourcePreview';
import {sourceCropImage, type SourceCrop} from './sourceCrops';
import {RidgeSourceEditor} from './RidgeSourceEditor';
import {canonical, emptyMask, reviewEyes, type EyeSide, type RidgeMask} from './support';
import {OPERATION_ID, ack, eyeBagBinding, imageMetadata, neutral, object, reviewImage, targetReady,
  validCandidate, validConfirmation, validReference, validReview, type EyeBagAction, type EyeBagCandidate,
  type EyeBagRecipe, type EyeBagReference, type EyeBagReview, type EyeBagSide} from './model';

type Expected = {id: string; binding: string; draft: string; action: EyeBagAction; candidate?: EyeBagCandidate; review?: EyeBagReview; side?: EyeBagSide; cropSide?: EyeSide; reference?: EyeBagReference; preserveDraft?: boolean};
const noMasks = (): Record<EyeSide, RidgeMask> => ({left: emptyMask(), right: emptyMask()});
const noFlags = (): Record<EyeSide, boolean> => ({left: false, right: false});
/** Drafts and image load state only; original people queue owns requests/history/uncertainty. */
export function EyeBagPreservePanel({people, blocked, faceOk, coreAvailable}: {
  people: PeopleOwner; blocked: boolean; faceOk: boolean; coreAvailable: boolean;
}) {
  const view = people.value, binding = eyeBagBinding(view), report = view?.eye_bag_preserve;
  const saved = useRef(people.eyeBagDraft(binding));
  const [draftSaving, setDraftSaving] = useState(true);
  const [draftBinding, setDraftBinding] = useState(binding), [reviewPaused, setReviewPaused] = useState(!!saved.current);
  const [reference, setReference] = useState<EyeBagReference | null>(null), [recipe, setRecipe] = useState<EyeBagRecipe>(() => saved.current?.recipe ?? neutral());
  const [masks, setMasks] = useState(() => saved.current?.masks ?? noMasks()), [flags, setFlags] = useState(noFlags), [side, setSide] = useState<EyeSide>('left');
  const [replaceLegacy, setReplaceLegacy] = useState(saved.current?.replaceLegacy ?? false), [sourceLoaded, setSourceLoaded] = useState(noFlags);
  const [review, setReview] = useState<EyeBagReview | null>(null), [images, setImages] = useState<Partial<Record<EyeBagSide, SpillImage>>>({});
  const [loaded, setLoaded] = useState<Partial<Record<EyeBagSide, boolean>>>({}), [accepted, setAccepted] = useState(false), [error, setError] = useState('');
  const [sourceCrops, setSourceCrops] = useState<Partial<Record<EyeSide, SourceCrop>>>({});
  const [confirmed, setConfirmed] = useState(''), [referenceSession, setReferenceSession] = useState(0);
  const expected = useRef<Expected | null>(null), mounted = useRef(false);
  const draft = canonical([recipe, masks, flags, replaceLegacy]);
  const busy = blocked || !people.enabled || people.state.pending || people.state.uncertain;
  const allowed = faceOk && targetReady(view);
  const live = useRef({binding, draft, busy, allowed, review, view, reviewPaused}); live.current = {binding, draft, busy, allowed, review, view, reviewPaused};
  useLayoutEffect(() => {mounted.current = true; return () => {mounted.current = false; expected.current = null;};}, []);
  function confirmationOwner(request: Expected): boolean {
    const owner = request.review?.owner, v = live.current.view;
    return request.action === 'eye_bag_confirm' && !!owner && !!v
      && v.binding.document_id === owner.document.document_id && v.binding.document_epoch === owner.document.epoch
      && v.binding.asset_sha256 === owner.source_proof.asset_sha256 && v.editing_target?.scope === 'face'
      && canonical(v.editing_target.face_ref) === canonical(request.review?.face_ref)
      && v.association_revision === owner.association_revision
      && [owner.document.revision, owner.document.revision + 1].includes(v.binding.document_revision);
  }
  function invalidate() {setReview(null); setImages({}); setLoaded({}); setAccepted(false); setError('');}
  useLayoutEffect(() => {
    if (!expected.current || !confirmationOwner(expected.current)) expected.current = null;
    const kept = people.eyeBagDraft(binding);
    setDraftSaving(true); setDraftBinding(binding); setReviewPaused(!!kept);
    setReference(null); setMasks(kept?.masks ?? noMasks()); setFlags(noFlags()); setRecipe(kept?.recipe ?? report?.recipe ?? neutral());
    setReplaceLegacy(kept?.replaceLegacy ?? false); setSourceLoaded(noFlags()); setSourceCrops({}); invalidate();
  }, [binding]);
  useEffect(() => {
    if (draftSaving && draftBinding === binding) people.saveEyeBagDraft(binding, {recipe, masks, replaceLegacy});
  }, [binding, draftBinding, draftSaving, recipe, masks, replaceLegacy]);
  function close() {setDraftSaving(false); people.saveEyeBagDraft(binding, null); setRecipe(report?.recipe ?? neutral()); setReplaceLegacy(false); setReviewPaused(true); expected.current = null; setReference(null); setSourceLoaded(noFlags()); setSourceCrops({}); setMasks(noMasks()); setFlags(noFlags()); invalidate();}
  function send(action: EyeBagAction, payload: Record<string, unknown>, details: Partial<Expected> = {}) {
    if (!mounted.current || live.current.binding !== binding || live.current.draft !== draft || live.current.busy || !live.current.allowed || expected.current) return;
    const context = peopleContext(view); if (!context) return;
    const command: PeopleAction = {...structuredClone(context), request_id: crypto.randomUUID(), action, payload: structuredClone(payload)};
    expected.current = {id: command.request_id, binding, draft, action, ...details}; setError(''); setConfirmed('');
    void people.submitCaptured(command).catch(cause => {
      if (mounted.current && live.current.binding === binding && expected.current?.id === command.request_id) {
        setError(String(cause)); if (!live.current.busy) expected.current = null;
      }
    });
  }
  useEffect(() => {
    const receipt = people.state.lastEyeBagResult, request = expected.current;
    if (!receipt || !request || (!confirmationOwner(request) && (request.binding !== live.current.binding || request.draft !== live.current.draft))
      || receipt.result.request_id !== request.id || receipt.command.action !== request.action) return;
    const current = () => mounted.current && expected.current === request && (confirmationOwner(request)
      || live.current.binding === request.binding && live.current.draft === request.draft);
    void (async () => {
      try {
        if (receipt.result.payload_released) throw Error('审核图已释放，请重新生成候选；原修改不会重发。');
        const payload = receipt.result.payload;
        if (!object(payload)) throw Error('卧蚕保护回执缺少有效内容。');
        if (request.action === 'eye_bag_reference') {
          if (!validReference(payload, view)) throw Error('来源图、人物或分析版本不匹配，不能复制旧笔迹。');
          if (current()) {
            setDraftSaving(true); setReferenceSession(n => n + 1); setReference(payload); setReviewPaused(false);
            if (!request.preserveDraft) {setRecipe(payload.recipe); setReplaceLegacy(false);}
            if (!request.preserveDraft) setMasks({left: payload.eyes.left?.recipe ?? emptyMask(), right: payload.eyes.right?.recipe ?? emptyMask()});
            setFlags(noFlags()); setSourceLoaded(noFlags()); setSourceCrops({}); invalidate();
          }
        } else if (request.action === 'eye_bag_source_image') {
          if (!request.reference || !request.cropSide) throw Error('原生裁片缺少来源绑定。');
          const crop = await sourceCropImage(payload, request.reference.source_crops, request.cropSide);
          if (!crop) throw Error('原生裁片摘要、尺寸或冻结来源不匹配。');
          if (current()) setSourceCrops(old => ({...old, [request.cropSide!]: crop}));
        } else if (request.action === 'eye_bag_preview') {
          if (payload.kind !== 'eye_bag_preview' || !request.candidate || !validReview(payload.review, view, request.candidate))
            throw Error('候选不属于当前来源、人物或草稿，请重新生成。');
          if (current()) {setReview(payload.review); setImages({}); setLoaded({}); setAccepted(false);}
        } else if (request.action === 'eye_bag_image') {
          if (!request.review || !request.side) throw Error('审核图片缺少绑定。');
          const image = await reviewImage(payload, request.review, request.side);
          if (!image) throw Error('审核图字节摘要或尺寸不匹配，不能确认。');
          if (current()) setImages(old => ({...old, [request.side!]: image}));
        } else {
          if (!request.review || !validConfirmation(request.review, receipt.result)) throw Error('确认结果不匹配，只能查询原请求。');
          if (current()) {close(); setConfirmed('引擎已确认写入当前脸的新版祛眼袋与源图保护范围。可通过现有照片历史撤销或重做。');}
        }
      } catch (cause) {if (current()) {setError(String(cause)); setAccepted(false);}}
      finally {if (expected.current === request) expected.current = null;}
    })();
  }, [people.state.lastEyeBagResult, view]);
  useEffect(() => {
    if (!people.state.pending && !people.state.uncertain && people.state.message && !people.state.lastEyeBagResult) {
      expected.current = null; setError(people.state.message);
    }
  }, [people.state]);
  useEffect(() => {
    if (reviewPaused || !review || busy || expected.current || error || !allowed) return;
    const side = (['support', 'before', 'after'] as const).find(k => !images[k]);
    if (side) send('eye_bag_image', {token: review.token, side, sha256: imageMetadata(review, side).sha256}, {review, side});
  }, [reviewPaused, review, images, busy, error, binding, draft]);
  useEffect(() => {
    if (reviewPaused || !reference || busy || expected.current || error || !allowed || sourceCrops[side]) return;
    send('eye_bag_source_image', {token: reference.source_crops.token, side, sha256: reference.source_crops.eyes[side].image.sha256}, {cropSide: side, reference});
  }, [reviewPaused, reference, side, sourceCrops, busy, error, binding, draft]);
  useEffect(() => {
    if (people.state.eyeBagCancel === 'none') return;
    expected.current = null; setReviewPaused(true); invalidate();
    setFlags(noFlags()); setSourceLoaded(noFlags()); setSourceCrops({});
  }, [people.state.eyeBagCancel]);
  const canCancel = people.state.pending && !!people.state.pendingAction
    && ['eye_bag_reference', 'eye_bag_preview', 'eye_bag_image', 'eye_bag_source_image'].includes(people.state.pendingAction);
  async function cancelRead() {
    expected.current = null; setReviewPaused(true); invalidate(); setFlags(noFlags());
    try {await people.cancelEyeBagRead();} catch (cause) {setError(String(cause));}
  }
  const paintedCropsReady = (['left', 'right'] as const).every(eye => !masks[eye].objects.length || sourceLoaded[eye]);
  let candidate: EyeBagCandidate | null = null;
  try {const value = {recipe, eyes: reviewEyes(masks, flags), replace_legacy: replaceLegacy}; if (validCandidate(value)) candidate = value;} catch { /* no submitted review yet */ }
  const matches = !!review && !!candidate && validReview(review, view, candidate);
  const ready = matches && (['support', 'before', 'after'] as const).every(k => !!images[k] && loaded[k] === true);
  const legacy = reference?.legacy_amount ?? report?.legacy_amount;
  const legacyReady = legacy === 0 || (typeof legacy === 'number' && legacy > 0 && replaceLegacy);
  const sourceImage = previewImage(reference?.source_preview ?? null);
  function imageLoaded(side: EyeBagSide, element: HTMLImageElement) {
    if (!mounted.current || live.current.binding !== binding || live.current.review !== review || !review) return;
    const meta = imageMetadata(review, side), good = element.naturalWidth === meta.width && element.naturalHeight === meta.height;
    setLoaded(old => ({...old, [side]: good})); if (!good) {setAccepted(false); setError('图片实际解码尺寸与凭据不符。');}
  }
  function stage() {
    if (!candidate || !reference || !paintedCropsReady || !legacyReady || !coreAvailable) return;
    invalidate(); send('eye_bag_preview', candidate, {candidate});
  }
  const reset = async () => {
    if (busy || !allowed || !view?.editing_target) return;
    invalidate(); setError(''); setConfirmed('');
    try {await people.submit('patch', {patches: [{operation_id: OPERATION_ID, parameter_path: '/amount', unset: false, value: 0}]}, view.editing_target);}
    catch (cause) {setError(String(cause));}
  };
  return <section aria-label="新版祛眼袋与保留卧蚕" data-eye-bag-preserve-version={2}>
    <h4>新版祛眼袋 · 保留卧蚕</h4>
    <p>手动逐眼审核卧蚕，不会自动识别卧蚕边界。默认保留为 100%，祛眼袋默认 0；只处理已审核的眼侧，未审核侧不改变。</p>
    <p>保留 100% 只让本操作在满覆盖位置不改变像素，羽化位置按覆盖比例保护。保留 0 关闭这层保护，不承诺完全移除卧蚕。其他修补、形变、调色仍可能改变这些位置。</p>
    {!allowed && <p role="status">请先选择已真实分析且无参数冲突的人物，切换到「此脸独立」范围。共享来源多照片或休眠同源成员目前会明确拒绝，不暗改其他照片。</p>}
    {!coreAvailable && <p role="status">新版祛眼袋审核核心未就绪；仍可归零新版程度，不会用旧版或眼神光蒙版替代。</p>}
    {report?.support_error && <p role="status">原保护范围需要重新审核：{report.support_error}</p>}
    {report?.suspended && <p role="status">当前效果暂停：{report.suspended}</p>}
    {report && <p>当前已审核眼侧：{report.reviewed_eyes.length ? report.reviewed_eyes.map(s => s === 'left' ? '人物左眼' : '人物右眼').join('、') : '无'}。引擎报告本操作变化 {report.changed_pixels} 像素，不代表整张画面最终变化。</p>}
    <button type="button" disabled={busy || !allowed} onClick={() => send('eye_bag_reference', {}, {preserveDraft: reviewPaused && draftSaving})}>读取此脸当前来源并审核{reviewPaused && draftSaving ? '（保留草稿，重新确认）' : ''}</button>
    {canCancel && <button type="button" disabled={people.state.eyeBagCancel === 'requested'} onClick={() => void cancelRead()}>请求停止只读审核，保留草稿</button>}
    {canCancel && people.state.uncertain && <button type="button" onClick={() => void people.recoverEyeBagRead().catch(cause => setError(String(cause)))}>核对原只读请求并恢复等待</button>}
    {people.state.pendingAction === 'eye_bag_confirm' && <p role="status">确认修改已发送，只能查询原请求，不能视为已取消或再次提交。</p>}
    {reviewPaused && draftSaving && <p role="status">草稿已保留；请重新读取当前来源并逐眼确认，旧图像和审核凭据不再授权应用。</p>}
    <button type="button" disabled={busy || !allowed} onClick={() => void reset()}>归零新版祛眼袋（保留保护设置）</button>
    {reference && <fieldset disabled={busy}>
      <legend>当前源图上的逐眼保护草稿</legend>
      <label>祛眼袋程度<input type="range" min={0} max={100} step={1} value={recipe.amount * 100} onChange={e => {setRecipe({...recipe, amount: Number(e.target.value) / 100}); invalidate();}}/>{Math.round(recipe.amount * 100)}%</label>
      <label>保留卧蚕<input type="range" min={0} max={100} step={1} value={recipe.preserve * 100} onChange={e => {setRecipe({...recipe, preserve: Number(e.target.value) / 100}); invalidate();}}/>{Math.round(recipe.preserve * 100)}%</label>
      {typeof legacy === 'number' && legacy > 0 && <label><input type="checkbox" checked={replaceLegacy} onChange={e => {setReplaceLegacy(e.target.checked); invalidate();}}/>
        此脸旧版祛眼袋为 {Math.round(legacy * 100)}%。我明确同意确认候选时把旧版眼袋程度置 0，再使用新版；不清除其他旧版增强参数。</label>}
      <label>审核人物眼侧<select value={side} onChange={e => setSide(e.target.value as EyeSide)}><option value="left">人物左眼</option><option value="right">人物右眼</option></select></label>
      {sourceImage && <details><summary>完整来源定位图（仅定位，不在缩略图绘制）</summary><img src={sourceImage.url} alt="完整来源定位缩略图" style={{maxWidth: '100%'}}/></details>}
      <p>眼部裁片使用{reference.source_crops.input_stage === 'committed_repair' ? '已提交修补后的来源' : '当前不可变来源'}像素，位于人物形变与调色之前；每个眼侧分别加载、校验并审核。</p>
      <button type="button" disabled={busy} onClick={() => {
        if (expected.current) return;
        setSourceCrops(old => {const next = {...old}; delete next[side]; return next;});
        setSourceLoaded(old => ({...old, [side]: false})); setFlags(old => ({...old, [side]: false})); invalidate();
      }}>重新读取当前眼原生裁片（保留草稿，重新确认）</button>
      <RidgeSourceEditor key={`${binding}:${referenceSession}:${side}:${sourceCrops[side]?.image.sha256 ?? 'pending'}`} context={`${binding}:${referenceSession}`} crop={sourceCrops[side] ?? null} source={reference.source} side={side} masks={masks} disabled={busy || reviewPaused}
        onLoaded={ready => {if (!mounted.current || live.current.binding !== binding || live.current.reviewPaused) return; setSourceLoaded(old => ({...old, [side]: ready})); if (!ready) {setAccepted(false);}}} onDraftStart={invalidate}
        onChange={(eye, mask) => {setMasks(old => ({...old, [eye]: mask})); setFlags(old => ({...old, [eye]: false})); invalidate();}}/>
      <label><input type="checkbox" checked={flags[side]} disabled={!sourceLoaded[side] || !masks[side].objects.length}
        onChange={e => {setFlags(old => ({...old, [side]: e.target.checked})); invalidate();}}/>
        我确认当前眼的标注是清晰可见、无遮挡且属于选中人物的卧蚕，不是邻人、眼袋、眼球或无法判断的区域</label>
      <p>当前草稿：左眼 {masks.left.objects.length} 笔{flags.left ? '，已确认' : '，未确认'}；右眼 {masks.right.objects.length} 笔{flags.right ? '，已确认' : '，未确认'}。空白眼侧不处理，不自动套用另一眼。</p>
      {recipe.amount === 0 && <p>0 程度不生成效果预览；使用上方「归零新版祛眼袋」安全重置。</p>}
      <button type="button" disabled={!allowed || !coreAvailable || !paintedCropsReady || !candidate || !legacyReady} onClick={stage}>生成实际保护范围与整张前后图</button>
      <button type="button" onClick={close}>关闭审核，放弃未应用草稿</button>
    </fieldset>}
    {review && matches && <section aria-label="真实保护与完整照片前后审核">
      <p>来源 {review.support_source.source_width} × {review.support_source.source_height}；本次实际解码保护网格 {review.support_source.decoded_width} × {review.support_source.decoded_height}，下方仅显示缩略图。</p>
      <p>候选尚未应用。请检查保护范围、此脸、邻近人物和背景；所有图片是当前冻结来源的真实渲染缩略图，不是原尺寸质量验收。</p>
      {(['support', 'before', 'after'] as const).map(side => <figure key={`${review.token}:${side}`}>
        <figcaption>{side === 'support' ? '引擎实际覆盖：青色满覆盖 1，琥珀色部分覆盖，无色 0；底图是未修补的来源分析参考，不是上方已修补眼部裁片' : side === 'before' ? '修改前：当前完整混合人像实际渲染' : '修改后：本次候选完整混合人像实际渲染（未应用）'}</figcaption>
        {images[side] ? <img src={`data:image/png;base64,${images[side]!.base64}`} alt={side === 'support' ? '未修补来源参考上的真实保护几何与羽化边缘' : side === 'before' ? '完整照片修改前' : '完整照片候选修改后'} style={{maxWidth: '100%', height: 'auto'}}
          onLoad={e => imageLoaded(side, e.currentTarget)} onError={() => {if (live.current.review !== review) return; setLoaded(old => ({...old, [side]: false})); setAccepted(false); setError('审核图片未完整显示，请重新生成预览。');}}/>
          : <p role="status">正在读取审核图…</p>}
      </figure>)}
      <label><input type="checkbox" disabled={busy || !ready} checked={accepted} onChange={e => setAccepted(e.target.checked)}/>
        我已查看真实保护范围和完整修改前后图，接受此脸当前候选{replaceLegacy ? '及明确替换旧版眼袋程度' : ''}</label>
      <button type="button" disabled={busy || !ready || !accepted || !!error || !allowed} onClick={() => {
        if (!ready || !accepted || error || live.current.review !== review || live.current.draft !== draft) return;
        send('eye_bag_confirm', {token: review.token, ack: ack(review)}, {review});
      }}>确认并应用此脸候选</button>
      <button type="button" disabled={busy} onClick={invalidate}>放弃候选，不改当前照片</button>
    </section>}
    {confirmed && <p role="status">{confirmed}</p>}
    {(error || people.state.message) && <p role="alert">{error || people.state.message}</p>}
    {people.state.uncertain && <button type="button" onClick={() => void people.check().catch(() => {})}>查询原请求，不重复提交</button>}
  </section>;
}
