// SPDX-License-Identifier: GPL-3.0-or-later
import {useEffect, useLayoutEffect, useRef, useState, useSyncExternalStore} from 'react';
import {HAIR_SMOOTHING_CONTROL_ID, HAIR_SMOOTHING_OPERATION, canonical, emptyHairSmoothingConfirmations, emptyHairSmoothingMask,
  makeHairSmoothingReview, parseAmount, parseTextureScale, type HairSmoothingMask, type HairSmoothingReview} from './review';
import {capture, confirmation, family, imageUrl, inspectionAck, hairSmoothingAmount, hairSmoothingBinding, receiptMatches, requestFits,
  sameFace, targetReady, validCrop, validPreview, validReference, validWritePayload, verifyImage, type HairSmoothingCommand, type HairSmoothingCrop,
  type HairSmoothingCropRequest, type HairSmoothingPreview, type HairSmoothingReference, type HairSmoothingSnapshot, type HairSmoothingPort} from './model';
import {HairSmoothingSourceEditor} from './HairSmoothingSourceEditor';
import {HairSmoothingReviewedImage} from './HairSmoothingReviewedImage';
import {HairSmoothingCropFields, cropRect, emptyCropFields} from './HairSmoothingCropFields';

const unavailable: HairSmoothingSnapshot = {value: null, enabled: false, pending: false, uncertain: false, lastResult: null,
  capability: {available: false, reason: '当前版本尚未连接独立头发柔顺审核协议。'}};
const noSubscribe = () => () => {};
const emptySnapshot = () => unavailable;
type Expected = {command: HairSmoothingCommand; draft: string; reference?: HairSmoothingReference; review?: HairSmoothingReview;
  amount?: number; preview?: HairSmoothingPreview; crop?: HairSmoothingCropRequest};

/** The injected port outlives this panel. Collapsing, changing photos or closing
 * a draft never cancels/forgets an uncertain operation in the canonical owner. */
export function HairSmoothingControl({port, blocked = false}: {port?: HairSmoothingPort | null; blocked?: boolean}) {
  const snapshot = useSyncExternalStore(port?.subscribe ?? noSubscribe, port?.getSnapshot ?? emptySnapshot, port?.getSnapshot ?? emptySnapshot);
  const [error, setError] = useState(''), [querying, setQuerying] = useState(false);
  const live = useRef({port, snapshot, blocked}); live.current = {port, snapshot, blocked};
  const mounted = useRef(false), sentSelection = useRef(false), queryingRef = useRef(false);
  useLayoutEffect(() => {mounted.current = true; return () => {mounted.current = false;};}, []);
  useEffect(() => {if (!snapshot.pending && !snapshot.uncertain) sentSelection.current = false;}, [snapshot]);
  const busy = blocked || !snapshot.enabled || snapshot.pending || snapshot.uncertain || !!snapshot.refreshRequired;
  async function reconcile(refresh: boolean) {
    if (!port || queryingRef.current || live.current.port !== port || refresh && live.current.snapshot.uncertain) return;
    queryingRef.current = true; setQuerying(true); setError('');
    try {if (refresh) await port.refreshCurrent(); else await port.check();}
    catch (cause) {if (mounted.current && live.current.port === port) setError(String(cause));}
    finally {queryingRef.current = false; if (mounted.current && live.current.port === port) setQuerying(false);}
  }
  function selectFace(id: string) {
    const view = snapshot.value, row = view?.faces.find(face => face.face_ref.face_instance_id === id);
    if (!port || !view || !row || busy || sentSelection.current || live.current.snapshot !== snapshot || live.current.port !== port) return;
    const {document_id, document_epoch, document_revision} = view.binding;
    const command: HairSmoothingCommand = {document_id, document_epoch, document_revision, state_revision: view.revision, association_revision: view.association_revision,
      request_id: crypto.randomUUID(), target: {scope: 'face', target_id: row.face_ref.face_instance_id, face_ref: {...row.face_ref}}, action: 'select', payload: {}};
    sentSelection.current = true;
    void port.submitCaptured(command).catch(cause => {
      if (mounted.current && live.current.port === port) {
        setError(String(cause)); if (!port.getSnapshot().pending && !port.getSnapshot().uncertain) sentSelection.current = false;
      }
    });
  }
  return <section data-control-id={HAIR_SMOOTHING_CONTROL_ID} aria-label="手动辅助可见头发定向柔顺">
    <p>可见头发定向柔顺（手动辅助、独立审核）</p>
    <p>只在本人已审核可见头发中，沿来源实际测得的局部方向柔化已分辨纹理的亮度起伏。不拉直几何、不去飞发、不填补遮挡下头发，不使用新 AI 模型或全局模糊。</p>
    <p className="muted">既有头发类别只是编辑权重，不是人物归属或遮挡识别。方向弱、纹理无信号或门限否决时可能保持原样；支持像素数不等于可见改善。真人画质、原生交互与运行验收仍未完成。</p>
    <label>实际已保留人脸（FaceRef）<select disabled={busy || !port} value={snapshot.value?.selected_face_id ?? ''}
      onChange={event => selectFace(event.target.value)}><option value="">请明确选择人脸</option>
      {snapshot.value?.faces.map((face, index) => <option key={canonical(face.face_ref)} value={face.face_ref.face_instance_id}>
        人物 {index + 1} · {face.face_ref.face_instance_id} · 分析版本 {face.face_ref.analysis_revision}{!face.enabled ? '（已禁用）' : face.analysis_status !== 'verified' ? '（待真实分析）' : ''}
      </option>)}</select></label>
    {!targetReady(snapshot.value) && <p role="status">请选择此照片的独立人脸编辑范围。当前不允许共享分组、跨照片或复制他人头发审核。</p>}
    <HairSmoothingSession key={hairSmoothingBinding(snapshot.value)} port={port ?? null} snapshot={snapshot} blocked={blocked}/>
    {snapshot.pending && <p role="status">请求已交给现有人物事务；关闭本面板不会取消或重复提交它。</p>}
    {snapshot.uncertain && <p role="alert">原请求结果未知。只查询原请求，不重新发送，也不把刷新当作撤销。</p>}
    {snapshot.refreshRequired && <p role="status">原结果已知但权威状态尚待刷新，暂不发起下一次修改。</p>}
    {snapshot.message && <p role="status">{snapshot.message}</p>}
    <button type="button" disabled={!port || querying || !snapshot.uncertain} onClick={() => void reconcile(false)}>查询原请求结果，不重发</button>
    <button type="button" disabled={!port || querying || snapshot.pending || snapshot.uncertain} onClick={() => void reconcile(true)}>刷新权威人物状态</button>
    {error && <p role="alert">{error}</p>}
  </section>;
}

function HairSmoothingSession({port, snapshot, blocked}: {port: HairSmoothingPort | null; snapshot: HairSmoothingSnapshot; blocked: boolean}) {
  const view = snapshot.value, binding = hairSmoothingBinding(view);
  const [reference, setReference] = useState<HairSmoothingReference | null>(null), [open, setOpen] = useState(false);
  const [target, setTarget] = useState<HairSmoothingMask>(emptyHairSmoothingMask), [context, setContext] = useState<HairSmoothingMask>(emptyHairSmoothingMask),
    [protect, setProtect] = useState<HairSmoothingMask>(emptyHairSmoothingMask);
  const [flags, setFlags] = useState(emptyHairSmoothingConfirmations), [amountText, setAmountText] = useState(''), [textureScaleText, setTextureScaleText] = useState('');
  const [sourceFields, setSourceFields] = useState(emptyCropFields);
  const [sourceCrop, setSourceCrop] = useState<HairSmoothingCrop | null>(null), [sourceCropSeen, setSourceCropSeen] = useState(false), [editorLoaded, setEditorLoaded] = useState(false);
  const [preview, setPreview] = useState<HairSmoothingPreview | null>(null), [beforeCrop, setBeforeCrop] = useState<HairSmoothingCrop | null>(null), [afterCrop, setAfterCrop] = useState<HairSmoothingCrop | null>(null);
  const [seen, setSeen] = useState<Record<string, boolean>>({}), [accepted, setAccepted] = useState(false), [inspectionAccepted, setInspectionAccepted] = useState(false);
  const [error, setError] = useState(''), [checking, setChecking] = useState(false), [waiting, setWaiting] = useState(false);
  const expected = useRef<Expected | null>(null), mounted = useRef(false), session = useRef(0), processing = useRef('');
  const draftGeneration = useRef(0), renderedGeneration = draftGeneration.current;
  const amount = parseAmount(amountText), neutralAmount = hairSmoothingAmount(view);
  const busy = blocked || !snapshot.enabled || snapshot.pending || snapshot.uncertain || !!snapshot.refreshRequired || checking || waiting;
  const protocol = snapshot.capability.protocol === 1, ready = protocol && snapshot.capability.available === true;
  const neutralAllowed = !!port && !busy && targetReady(view), reviewAllowed = neutralAllowed && targetReady(view, true) && protocol;
  const draftKey = canonical([binding, session.current, target, context, protect, amountText, textureScaleText, flags]);
  const live = useRef({draftKey, binding, busy, reference, preview, sourceCrop, beforeCrop, afterCrop, accepted, inspectionAccepted, seen,
    sourceCropSeen, editorLoaded, port, protocol, ready, neutralAllowed, reviewAllowed});
  live.current = {draftKey, binding, busy, reference, preview, sourceCrop, beforeCrop, afterCrop, accepted, inspectionAccepted, seen,
    sourceCropSeen, editorLoaded, port, protocol, ready, neutralAllowed, reviewAllowed};
  useLayoutEffect(() => {mounted.current = true; return () => {mounted.current = false; expected.current = null;};}, []);
  function clearCandidate() {draftGeneration.current++; setPreview(null); setBeforeCrop(null); setAfterCrop(null); setSeen({}); setAccepted(false); setInspectionAccepted(false); setError('');}
  function edit(nextTarget: HairSmoothingMask, nextContext: HairSmoothingMask, nextProtect: HairSmoothingMask) {
    setTarget(nextTarget); setContext(nextContext); setProtect(nextProtect); setFlags(emptyHairSmoothingConfirmations()); clearCandidate();
  }
  function close() {
    session.current++; expected.current = null; setChecking(false); setWaiting(false); setOpen(false); setReference(null);
    setTarget(emptyHairSmoothingMask()); setContext(emptyHairSmoothingMask()); setProtect(emptyHairSmoothingMask()); setFlags(emptyHairSmoothingConfirmations()); setAmountText(''); setTextureScaleText('');
    setSourceCrop(null); setSourceCropSeen(false); setEditorLoaded(false); setSourceFields(emptyCropFields()); clearCandidate();
  }
  useEffect(() => {
    const hidden = () => {if (document.visibilityState !== 'visible') {setSeen({}); setAccepted(false); setInspectionAccepted(false); setSourceCropSeen(false);}};
    document.addEventListener('visibilitychange', hidden); return () => document.removeEventListener('visibilitychange', hidden);
  }, []);
  // A known failed command can be dismissed; an uncertain command stays fenced in
  // the sole application owner even if this ephemeral draft has been closed.
  useEffect(() => {
    if (!snapshot.pending && !snapshot.uncertain && !snapshot.lastResult && snapshot.message && !checking) {expected.current = null; setWaiting(false);}
  }, [snapshot.pending, snapshot.uncertain, snapshot.lastResult, snapshot.message, checking]);
  function send(action: HairSmoothingCommand['action'], payload: Record<string, unknown>, details: Partial<Expected> = {}) {
    if (!port || !mounted.current || draftGeneration.current !== renderedGeneration || live.current.port !== port
      || live.current.draftKey !== draftKey || live.current.busy || expected.current) return;
    const neutral = action === 'patch' || action === 'hair_smoothing_detach';
    if (neutral ? !live.current.neutralAllowed : !live.current.reviewAllowed) return;
    if ((action === 'hair_smoothing_preview' || action === 'hair_smoothing_confirm') && !live.current.ready) return;
    if (action === 'hair_smoothing_preview' && (!live.current.sourceCropSeen || !live.current.editorLoaded)) return;
    if (action === 'hair_smoothing_confirm') {
      const state = live.current, candidate = state.preview;
      const pair = candidate ? inspectionAck(state.beforeCrop, state.afterCrop, candidate) : null;
      if (!candidate || !pair || !state.sourceCrop || canonical(pair.rect) !== canonical(state.sourceCrop.rect) || !state.accepted || !state.inspectionAccepted
        || canonical(payload) !== canonical(confirmation(candidate, pair))) return;
      const prefix = `${binding}:${candidate.preview_id}`;
      if (!( ['before', 'after', 'support'] as const).every(side => state.seen[`${prefix}:${side}:${candidate[side].sha256}:full`])
        || !state.seen[`${prefix}:before-crop:${pair.before_sha256}:${pair.rect.join(',')}`]
        || !state.seen[`${prefix}:after-crop:${pair.after_sha256}:${pair.rect.join(',')}`]) return;
    }
    const command = capture(view, action, payload); if (!command) return;
    if (!requestFits(command)) {setError('请求超过 192 KiB 安全预算，尚未发送。请清理草稿；不会自动删点。'); return;}
    expected.current = {command, draft: draftKey, ...details}; setWaiting(true); setError('');
    void port.submitCaptured(command).catch(cause => {
      if (!mounted.current || live.current.port !== port || expected.current?.command.request_id !== command.request_id) return;
      setError(String(cause)); setAccepted(false); setInspectionAccepted(false);
      const current = port.getSnapshot(); if (!current.pending && !current.uncertain) {expected.current = null; setWaiting(false);}
    });
  }
  useEffect(() => {
    const receipt = snapshot.lastResult, request = expected.current;
    if (!receipt || !request || receipt.result.request_id !== request.command.request_id || processing.current === request.command.request_id) return;
    const current = () => mounted.current && expected.current === request && live.current.port === port && live.current.draftKey === request.draft;
    if (!current()) return;
    processing.current = request.command.request_id; setChecking(true);
    void (async () => {
      try {
        if (!receiptMatches(receipt, request.command, view)) throw Error('头发柔顺回执与原请求或当前照片不匹配，请查询原请求。');
        if (!receipt.result.success) throw Error(receipt.result.error || '头发柔顺请求被拒绝，没有接受候选。');
        if (receipt.result.payload_released) throw Error('原审核图已释放；重新读取来源，不重发原修改。');
        const payload = receipt.result.payload;
        switch (request.command.action) {
          case 'hair_smoothing_reference':
            if (!view || !validReference(payload, view) || !await verifyImage(payload.source_image)) throw Error('实际来源、本人头发归属证明或图像字节校验失败。');
            if (current()) {setReference(payload); setOpen(true); setSourceCrop(null); setSourceCropSeen(false); setEditorLoaded(false);}
            break;
          case 'hair_smoothing_preview':
            if (!request.reference || !request.review || request.amount === undefined || !validPreview(payload, request.reference, request.review, request.amount)
              || !await verifyImage(payload.before) || !await verifyImage(payload.after) || !await verifyImage(payload.support)) throw Error('候选的来源、修补、人脸、笔迹、强度或三张图像哈希不一致。');
            if (current()) {setPreview(payload); setSeen({}); setAccepted(false); setInspectionAccepted(false); setBeforeCrop(null); setAfterCrop(null);}
            break;
          case 'hair_smoothing_crop': {
            const owner = request.crop?.plane === 'source' ? request.reference : request.preview;
            if (!request.crop || !owner || !validCrop(payload, request.crop, owner) || !await verifyImage(payload.image)) throw Error('原生像素裁片的冻结来源、修补、位置、尺寸或图像哈希不一致。');
            if (current()) {
              if (payload.plane === 'source') {
                const sameLoadedCrop = live.current.sourceCrop?.image.sha256 === payload.image.sha256
                  && canonical(live.current.sourceCrop?.rect) === canonical(payload.rect);
                setSourceCrop(payload);
                if (!sameLoadedCrop) {setSourceCropSeen(false); setEditorLoaded(false);}
              }
              else if (payload.plane === 'before') {setBeforeCrop(payload); setInspectionAccepted(false);}
              else {setAfterCrop(payload); setInspectionAccepted(false);}
            }
            break;
          }
          case 'hair_smoothing_confirm':
          case 'hair_smoothing_detach':
            if (!validWritePayload(payload, request.command.action,
              request.command.action === 'hair_smoothing_confirm' ? request.preview?.amount : 0)) throw Error('写入回执不属于此头发柔顺候选或未确认独立强度，请查询原请求。');
            if (current()) close();
            break;
          case 'patch':
            // The existing people owner validates canonical publication/readback.
            // A bare local success flag never writes amount or support state here.
            if (current()) close();
            break;
        }
      } catch (cause) {if (current()) {setError(String(cause)); setAccepted(false); setInspectionAccepted(false);}}
      finally {
        if (processing.current === request.command.request_id) processing.current = '';
        if (mounted.current && expected.current === request && live.current.port === port) {expected.current = null; setChecking(false); setWaiting(false);}
      }
    })();
  }, [snapshot.lastResult, view, port]);

  const sourceRect = reference ? cropRect(sourceFields, [reference.source.width, reference.source.height]) : null;
  const outputRect = preview && sourceCrop && preview.before_output_size[0] === reference?.source.width
    && preview.before_output_size[1] === reference?.source.height ? sourceCrop.rect : null;
  const inspection = preview ? inspectionAck(beforeCrop, afterCrop, preview) : null;
  const fullKey = preview ? `${binding}:${preview.preview_id}` : '';
  const seenKey = (side: string, hash: string, rect?: number[]) => `${fullKey}:${side}:${hash}:${rect?.join(',') ?? 'full'}`;
  const fullSeen = !!preview && (['before', 'after', 'support'] as const).every(side => seen[seenKey(side, preview[side].sha256)]);
  const cropSeen = !!inspection && !!beforeCrop && !!afterCrop
    && seen[seenKey('before-crop', beforeCrop.image.sha256, beforeCrop.rect)] && seen[seenKey('after-crop', afterCrop.image.sha256, afterCrop.rect)];
  let review: HairSmoothingReview | null = null;
  try {if (reference) review = makeHairSmoothingReview(reference.source, target, context, protect, textureScaleText, flags);} catch {/* incomplete draft */}
  const draftMatches = !!preview && !!review && preview.amount === amount && canonical(preview.review) === canonical(review);
  const canConfirm = ready && reviewAllowed && draftMatches && fullSeen && cropSeen && accepted && inspectionAccepted
    && !!sourceCrop && !!inspection && canonical(sourceCrop.rect) === canonical(inspection.rect);
  const face = view?.faces.find(item => item.face_ref.face_instance_id === view.selected_face_id);
  const report = snapshot.report && family(snapshot.report) && sameFace(snapshot.report.face_ref, face?.face_ref)
    && snapshot.report.source.sha256 === view?.binding.asset_sha256 ? snapshot.report : null;
  function seenImage(side: string, imageHash: string, okay: boolean, rect?: number[]) {
    if (!mounted.current || live.current.preview?.preview_id !== preview?.preview_id || live.current.binding !== binding) return;
    const crop = side === 'before-crop' ? live.current.beforeCrop : side === 'after-crop' ? live.current.afterCrop : null;
    if (rect && (!crop || crop.image.sha256 !== imageHash || canonical(crop.rect) !== canonical(rect))) return;
    setSeen(old => ({...old, [seenKey(side, imageHash, rect)]: okay}));
    if (!okay) {setAccepted(false); setInspectionAccepted(false); setError('审核图解码或尺寸检查失败，不能确认。');}
  }
  function requestCrop(plane: 'source' | 'before' | 'after') {
    if (plane === 'source' && reference && sourceRect) {
      const crop: HairSmoothingCropRequest = {reference_id: reference.reference_id, plane, rect: sourceRect};
      send('hair_smoothing_crop', crop, {crop, reference});
      clearCandidate();
    } else if (plane !== 'source' && preview && outputRect) {
      const crop: HairSmoothingCropRequest = {preview_id: preview.preview_id, plane, rect: outputRect};
      send('hair_smoothing_crop', crop, {crop, preview});
    }
  }
  const image = reference ? sourceCrop?.plane === 'source' ? {...sourceCrop.image, url: imageUrl(sourceCrop.image), rect: sourceCrop.rect}
    : {...reference.source_image, url: imageUrl(reference.source_image)} : null;
  const currentSession = session.current;
  const currentCallback = () => mounted.current && live.current.binding === binding && session.current === currentSession;
  return <div>
    <p>此人物当前权威强度：{neutralAmount === null ? '未提供有效独立读数' : `${Number((neutralAmount * 100).toFixed(6))} / 100`}。0 为严格中性，非零须独立来源与像素审核。</p>
    <p role="status">{report ? report.attached ? report.needs_review ? '保留的头发范围已过期或需重审，不能用于新调整。' : '此人物已附加独立头发审核范围。' : '此人物尚未附加头发审核范围。' : '尚未取得头发范围权威状态。'}{report?.reason ? ` ${report.reason}` : ''}</p>
    {!ready && <p role="status">{snapshot.capability.reason || '独立头发柔顺核心或审核协议缺失，非零候选不可用；不会调用通用模糊替代。'}</p>}
    <button type="button" disabled={!neutralAllowed} onClick={() => send('patch', {patches: [{operation_id: HAIR_SMOOTHING_OPERATION,
      parameter_path: '/amount', unset: false, value: 0}]})}>仅将此人物头发柔顺强度归零</button>
    <button type="button" disabled={!neutralAllowed || report?.attached !== true} onClick={() => send('hair_smoothing_detach', {})}>归零并移除此人物头发范围</button>
    <p className="muted">中性操作不要求有效分析、旧范围或数值核心；不会恢复共享继承，也不改动其他效果。已发出但结果未知时仍须先查询。</p>
    <button type="button" disabled={!reviewAllowed || open} onClick={() => send('hair_smoothing_reference', {})}>打开真实来源，开始独立头发审核</button>
    {open && reference && <div>
      <button type="button" onClick={close}>关闭本地草稿，不撤回或重发已送请求</button>
      <p>来源 {reference.source.width} × {reference.source.height} · FaceRef {reference.face_ref.face_instance_id} · 分析版本 {reference.face_ref.analysis_revision}。</p>
      <p>来源像素与修补身份由宿主绑定。本阶段仅接受有验证的原始来源；派生合成、坐标映射未证明的裁剪、旋转、翻转或形变均拒绝。</p>
      <p>已保留头发资产 {reference.hair_colour_asset_sha256.slice(0, 12)}… · 归属审核 {reference.ownership_review_key.slice(0, 12)}… · 全部保留人物证明 {reference.retained_faces_sha256.slice(0, 12)}…。颜色或蓬松度审核不等于本次柔顺授权。</p>
      <HairSmoothingCropFields fields={sourceFields} size={[reference.source.width, reference.source.height]} label="来源 100% 观察裁片"
        disabled={busy} onChange={fields => {setSourceFields(fields); setSourceCrop(null); setSourceCropSeen(false); setEditorLoaded(false);
          setFlags(emptyHairSmoothingConfirmations()); clearCandidate();}}/>
      <button type="button" disabled={!reviewAllowed || !sourceRect} onClick={() => requestCrop('source')}>读取这个来源像素裁片，不缩放</button>
      {sourceCrop && <figure style={{overflow: 'auto', maxHeight: 600}}><HairSmoothingReviewedImage image={sourceCrop.image}
        identity={`${binding}:${reference.reference_id}:source:${canonical(sourceCrop.rect)}:${sourceCrop.image.sha256}`} nativePixels
        alt="来源原生像素裁片，用于观察可见头发实际纹理尺度" onSeen={() => {if (currentCallback() && live.current.sourceCrop?.image.sha256 === sourceCrop.image.sha256
          && canonical(live.current.sourceCrop?.rect) === canonical(sourceCrop.rect)) setSourceCropSeen(true);}}
        onError={() => {if (currentCallback()) {setSourceCropSeen(false); setFlags(emptyHairSmoothingConfirmations()); clearCandidate();}}}/>
        <figcaption>来源像素 1:1，仅此矩形，不代表整张照片 100% 已检查。没有已分辨头发纹理时请换位置，不应猜测尺度或方向。</figcaption></figure>}
      <HairSmoothingSourceEditor key={binding} binding={binding} source={reference.source} image={image}
        target={target} context={context} protect={protect} disabled={busy} onLoaded={value => {if (currentCallback()) {setEditorLoaded(value); if (!value) {setFlags(emptyHairSmoothingConfirmations()); clearCandidate();}}}}
        onDraftStart={() => {if (currentCallback()) {setFlags(emptyHairSmoothingConfirmations()); clearCandidate();}}}
        onChange={(nextTarget, nextContext, nextProtect) => {if (currentCallback()) edit(nextTarget, nextContext, nextProtect);}}/>
      <label>实际观察到的纹理尺度（来源像素，1 至 8）<input type="number" min={1} max={8} step="any"
        value={textureScaleText} disabled={busy || !sourceCropSeen} onChange={event => {setTextureScaleText(event.target.value); setFlags(emptyHairSmoothingConfirmations()); clearCandidate();}}/></label>
      <p>不设默认尺度；不是画笔半径或脸宽。请先看实际来源 1:1 裁片。归一化值：{parseTextureScale(textureScaleText, reference.source) ?? '尚未明确'}（来源短边比例）。</p>
      <label>候选强度（0 至 100，显式选择）<input type="number" min={0} max={100} step="any" value={amountText} disabled={busy}
        onChange={event => {setAmountText(event.target.value); clearCandidate();}}/></label>
      <p>这是本产品强度刻度，不冒称官方数值。候选为空或 0 不生成效果；归零使用上方独立中性操作。修改非零强度也须重新检查真实候选。</p>
      {([
        ['visible_hair_reviewed', '我已在真实来源 1:1 裁片观察已分辨的可见头发纹理，独立标记目标、同人上下文及实际尺度，不补画遮挡下头发。'],
        ['ownership_confirmed', '我确认目标及每个采样上下文都属于当前精确 FaceRef；不借用其他人，包括已禁用人物的头发；不把类别权重当作人物边界。'],
        ['protections_reviewed', protect.objects.length ? '我已独立硬保护皮肤、头皮、耳朵、饰物、其他人、归属不清的接触边界及不应柔化的结构；自动门限不能保证识别遮挡或物理高光。' : '当前硬保护笔迹为空：我已逐一检查并明确决定本次无需新增保护；这不证明没有皮肤、耳朵、饰物、其他人、边界歧义或物理高光。'],
      ] as const).map(([field, label]) => <label key={field} style={{display: 'block'}}><input type="checkbox" checked={flags[field]}
        disabled={busy || !editorLoaded || !sourceCropSeen} onChange={event => {setFlags(old => ({...old, [field]: event.target.checked})); clearCandidate();}}/>{label}</label>)}
      <button type="button" disabled={!reviewAllowed || !ready || !review || !editorLoaded || !sourceCropSeen || amount === null || amount <= 0}
        onClick={() => {if (review && amount !== null && amount > 0 && editorLoaded && sourceCropSeen) send('hair_smoothing_preview', {review, amount}, {reference, review, amount});}}>生成私有完整混合前后图与真实准入叠图</button>
      {preview && <div>
        <p>候选尚未发布。以下前后图来自完整混合渲染，包含其余现有效果；显示图是缩略图，不是来源或输出 100%。</p>
        <dl aria-label="冻结来源测量诊断，不代表最终视觉变化">
          <dt>完整上下文准入像素</dt><dd>{preview.diagnostics.supported_pixels}</dd>
          <dt>上下文不全排除像素</dt><dd>{preview.diagnostics.context_rejected_pixels}</dd>
          <dt>具有可靠局部方向的像素</dt><dd>{preview.diagnostics.directional_pixels}</dd>
          <dt>冻结来源中提出非零亮度修正的像素</dt><dd>{preview.diagnostics.changed_pixels}</dd>
          <dt>实际源纹理尺度</dt><dd>{preview.diagnostics.texture_scale_px} 像素</dd>
        </dl>
        <p>这些计数是源图测量与提案，不是最终混合输出中发生变化的像素数，不承诺视觉改善。当前像素、共同亮度余量与后续效果还会影响实际输出；真人画质仍未验收。</p>
        {preview.diagnostics.directional_pixels === 0 && <p role="status">未测得可靠的局部头发方向；不猜测方向、不使用通用模糊补偿。</p>}
        {preview.diagnostics.changed_pixels === 0 && <p role="status">本次没有存储非零柔顺提案。信号不足或门限抑制是中性结果，不冒充已改善纹理。{preview.diagnostics.no_signal_reason ? ` 原因：${preview.diagnostics.no_signal_reason}` : ''}</p>}
        {(['before', 'after', 'support'] as const).map(side => <figure key={`${preview.preview_id}:${side}:${preview[side].sha256}`}>
          <HairSmoothingReviewedImage image={preview[side]} identity={seenKey(side, preview[side].sha256)}
            alt={side === 'before' ? '本次候选前完整混合结果' : side === 'after' ? '本次候选后完整混合结果，尚未发布' : '来源坐标的实际目标准入、硬保护与完整采样上下文排除叠图'}
            onSeen={() => seenImage(side, preview[side].sha256, true)} onError={() => seenImage(side, preview[side].sha256, false)}/>
          <figcaption>{side === 'before' ? '完整混合结果：调整前' : side === 'after' ? '完整混合结果：候选后' : '来源叠图：青色最终准入，粉红硬保护，橙色上下文不足排除；不是自动实例分割'}</figcaption>
        </figure>)}
        <p>输出原生检查固定为已检查的来源矩形 {outputRect?.join(', ') ?? '无有效对应矩形'}。本阶段宿主先拒绝不兼容几何，并验证完整输出与来源坐标一致；相同尺寸本身不是映射证明。更换矩形须重新读取来源并生成候选。</p>
        <button type="button" disabled={!reviewAllowed || !outputRect} onClick={() => requestCrop('before')}>读取这个输出矩形的调整前原生像素</button>
        <button type="button" disabled={!reviewAllowed || !outputRect} onClick={() => requestCrop('after')}>读取相同输出矩形的候选后原生像素</button>
        {([['before', beforeCrop], ['after', afterCrop]] as const).map(([side, crop]) => crop && <figure key={`${side}:${canonical(crop.rect)}:${crop.image.sha256}`} style={{overflow: 'auto', maxHeight: 600}}>
          <HairSmoothingReviewedImage image={crop.image} identity={seenKey(`${side}-crop`, crop.image.sha256, crop.rect)} nativePixels
            alt={side === 'before' ? '选定输出矩形调整前的 1:1 原生像素' : '相同输出矩形候选后的 1:1 原生像素'}
            onSeen={() => seenImage(`${side}-crop`, crop.image.sha256, true, crop.rect)} onError={() => seenImage(`${side}-crop`, crop.image.sha256, false, crop.rect)}/>
          <figcaption>{side === 'before' ? '前' : '后'}：输出矩形 {crop.rect.join(', ')}，原生像素 1:1，无缩放。</figcaption></figure>)}
        {beforeCrop && afterCrop && canonical(beforeCrop.rect) === canonical(afterCrop.rect)
          && beforeCrop.image.sha256 === afterCrop.image.sha256 && <p role="status">这对原生裁片的编码像素相同，本区域没有编码可见的变化。方向或信号不足可能返回中性；准入叠图不代表已经改善纹理，也不推断全图均无变化。</p>}
        <label style={{display: 'block'}}><input type="checkbox" checked={inspectionAccepted} disabled={busy || !cropSeen || !draftMatches}
          onChange={event => {setInspectionAccepted(event.target.checked); setAccepted(false);}}/>我已逐一比较这对相同输出矩形的 1:1 裁片，检查发丝纹理、亮度起伏、强过渡、边界和硬保护内容；这只是该矩形，不代表全图 100% 覆盖。</label>
        <label style={{display: 'block'}}><input type="checkbox" checked={accepted} disabled={busy || !fullSeen || !cropSeen || !inspectionAccepted || !draftMatches}
          onChange={event => setAccepted(event.target.checked)}/>我已查看这组三张完整审核图及上述裁片，独立接受此人、此范围、此强度的可见头发定向柔顺候选。</label>
        <button type="button" disabled={!canConfirm} onClick={() => {
          if (canConfirm && preview && inspection && live.current.preview === preview && live.current.accepted && live.current.inspectionAccepted)
            send('hair_smoothing_confirm', confirmation(preview, inspection), {preview});
        }}>确认此候选与独立头发范围</button>
      </div>}
    </div>}
    {error && <p role="alert">{error}</p>}
  </div>;
}
