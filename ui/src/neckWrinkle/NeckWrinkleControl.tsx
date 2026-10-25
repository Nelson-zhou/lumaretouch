// SPDX-License-Identifier: GPL-3.0-or-later
import {useEffect, useLayoutEffect, useRef, useState, useSyncExternalStore} from 'react';
import {NECK_WRINKLE_CONTROL_ID, NECK_WRINKLE_OPERATION, bodyKey, canonical, emptyNeckConfirmations, emptyNeckMask,
  makeNeckReview, parseAmount, parseHalfWidth, type NeckMask, type NeckReview} from './review';
import {capture, confirmation, family, imageUrl, inspectionAck, neckAmount, neckBinding, receiptMatches, requestFits,
  sameFace, targetReady, validCrop, validPreview, validReference, validWritePayload, verifyImage, type NeckCommand, type NeckCrop,
  type NeckCropRequest, type NeckPreview, type NeckReference, type NeckSnapshot, type NeckWrinklePort} from './model';
import {NeckSourceEditor} from './NeckSourceEditor';
import {NeckReviewedImage} from './NeckReviewedImage';
import {NeckCropFields, cropRect, emptyCropFields} from './NeckCropFields';

const unavailable: NeckSnapshot = {value: null, enabled: false, pending: false, uncertain: false, lastResult: null,
  capability: {available: false, reason: '当前版本尚未连接独立颈纹审核协议。'}};
const noSubscribe = () => () => {};
const emptySnapshot = () => unavailable;
type Expected = {command: NeckCommand; draft: string; reference?: NeckReference; review?: NeckReview;
  amount?: number; preview?: NeckPreview; crop?: NeckCropRequest};

/** The injected port outlives this panel. Collapsing, changing photos or closing
 * a draft never cancels/forgets an uncertain operation in the canonical owner. */
export function NeckWrinkleControl({port, blocked = false}: {port?: NeckWrinklePort | null; blocked?: boolean}) {
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
    const command: NeckCommand = {document_id, document_epoch, document_revision, state_revision: view.revision, association_revision: view.association_revision,
      request_id: crypto.randomUUID(), target: {scope: 'face', target_id: row.face_ref.face_instance_id, face_ref: {...row.face_ref}}, action: 'select', payload: {}};
    sentSelection.current = true;
    void port.submitCaptured(command).catch(cause => {
      if (mounted.current && live.current.port === port) {
        setError(String(cause)); if (!port.getSnapshot().pending && !port.getSnapshot().uncertain) sentSelection.current = false;
      }
    });
  }
  return <section data-control-id={NECK_WRINKLE_CONTROL_ID} aria-label="手动辅助颈部细纹淡化">
    <p>颈部细纹淡化（手动辅助、独立审核）</p>
    <p>仅在本人真实来源颈部皮肤中测量并淡化细暗纹，不拉长或缩窄脖子，不复制脸部祛皱，不做大范围磨皮，也不补全遮挡下皮肤。</p>
    <p className="muted">不是自动 AI 颈部、首饰或皮肤实例分割。头部与姿态观察只用于身份和否决，不推算颈部轮廓或细纹宽度。真人画质、原生交互与运行验收仍未完成。</p>
    <label>实际已保留人脸（FaceRef）<select disabled={busy || !port} value={snapshot.value?.selected_face_id ?? ''}
      onChange={event => selectFace(event.target.value)}><option value="">请明确选择人脸</option>
      {snapshot.value?.faces.map((face, index) => <option key={canonical(face.face_ref)} value={face.face_ref.face_instance_id}>
        人物 {index + 1} · {face.face_ref.face_instance_id} · 分析版本 {face.face_ref.analysis_revision}{!face.enabled ? '（已禁用）' : face.analysis_status !== 'verified' ? '（待真实分析）' : ''}
      </option>)}</select></label>
    {!targetReady(snapshot.value) && <p role="status">请选择此照片的独立人脸编辑范围。当前不允许共享分组、跨照片或复制他人颈部审核。</p>}
    <NeckSession key={neckBinding(snapshot.value)} port={port ?? null} snapshot={snapshot} blocked={blocked}/>
    {snapshot.pending && <p role="status">请求已交给现有人物事务；关闭本面板不会取消或重复提交它。</p>}
    {snapshot.uncertain && <p role="alert">原请求结果未知。只查询原请求，不重新发送，也不把刷新当作撤销。</p>}
    {snapshot.refreshRequired && <p role="status">原结果已知但权威状态尚待刷新，暂不发起下一次修改。</p>}
    {snapshot.message && <p role="status">{snapshot.message}</p>}
    <button type="button" disabled={!port || querying || !snapshot.uncertain} onClick={() => void reconcile(false)}>查询原请求结果，不重发</button>
    <button type="button" disabled={!port || querying || snapshot.pending || snapshot.uncertain} onClick={() => void reconcile(true)}>刷新权威人物状态</button>
    {error && <p role="alert">{error}</p>}
  </section>;
}

function NeckSession({port, snapshot, blocked}: {port: NeckWrinklePort | null; snapshot: NeckSnapshot; blocked: boolean}) {
  const view = snapshot.value, binding = neckBinding(view);
  const [reference, setReference] = useState<NeckReference | null>(null), [open, setOpen] = useState(false);
  const [choice, setChoice] = useState(''), [region, setRegion] = useState<NeckMask>(emptyNeckMask), [protect, setProtect] = useState<NeckMask>(emptyNeckMask);
  const [flags, setFlags] = useState(emptyNeckConfirmations), [amountText, setAmountText] = useState(''), [halfWidthText, setHalfWidthText] = useState('');
  const [sourceFields, setSourceFields] = useState(emptyCropFields), [outputFields, setOutputFields] = useState(emptyCropFields);
  const [sourceCrop, setSourceCrop] = useState<NeckCrop | null>(null), [sourceCropSeen, setSourceCropSeen] = useState(false), [editorLoaded, setEditorLoaded] = useState(false);
  const [preview, setPreview] = useState<NeckPreview | null>(null), [beforeCrop, setBeforeCrop] = useState<NeckCrop | null>(null), [afterCrop, setAfterCrop] = useState<NeckCrop | null>(null);
  const [seen, setSeen] = useState<Record<string, boolean>>({}), [accepted, setAccepted] = useState(false), [inspectionAccepted, setInspectionAccepted] = useState(false);
  const [error, setError] = useState(''), [checking, setChecking] = useState(false), [waiting, setWaiting] = useState(false);
  const expected = useRef<Expected | null>(null), mounted = useRef(false), session = useRef(0), processing = useRef('');
  const draftGeneration = useRef(0), renderedGeneration = draftGeneration.current;
  const amount = parseAmount(amountText), neutralAmount = neckAmount(view);
  const selected = reference?.bodies.find(body => bodyKey(body.body_ref) === choice);
  const busy = blocked || !snapshot.enabled || snapshot.pending || snapshot.uncertain || !!snapshot.refreshRequired || checking || waiting;
  const protocol = snapshot.capability.protocol === 1, ready = protocol && snapshot.capability.available === true;
  const neutralAllowed = !!port && !busy && targetReady(view), reviewAllowed = neutralAllowed && targetReady(view, true) && protocol;
  const draftKey = canonical([binding, session.current, choice, region, protect, amountText, halfWidthText, flags]);
  const live = useRef({draftKey, binding, busy, reference, preview, sourceCrop, beforeCrop, afterCrop, accepted, inspectionAccepted, seen,
    sourceCropSeen, editorLoaded, port, protocol, ready, neutralAllowed, reviewAllowed});
  live.current = {draftKey, binding, busy, reference, preview, sourceCrop, beforeCrop, afterCrop, accepted, inspectionAccepted, seen,
    sourceCropSeen, editorLoaded, port, protocol, ready, neutralAllowed, reviewAllowed};
  useLayoutEffect(() => {mounted.current = true; return () => {mounted.current = false; expected.current = null;};}, []);
  function clearCandidate() {draftGeneration.current++; setPreview(null); setBeforeCrop(null); setAfterCrop(null); setSeen({}); setAccepted(false); setInspectionAccepted(false); setError('');}
  function edit(nextRegion: NeckMask, nextProtect: NeckMask) {setRegion(nextRegion); setProtect(nextProtect); setFlags(emptyNeckConfirmations()); clearCandidate();}
  function close() {
    session.current++; expected.current = null; setChecking(false); setWaiting(false); setOpen(false); setReference(null); setChoice('');
    setRegion(emptyNeckMask()); setProtect(emptyNeckMask()); setFlags(emptyNeckConfirmations()); setAmountText(''); setHalfWidthText('');
    setSourceCrop(null); setSourceCropSeen(false); setEditorLoaded(false); setSourceFields(emptyCropFields()); setOutputFields(emptyCropFields()); clearCandidate();
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
  function send(action: NeckCommand['action'], payload: Record<string, unknown>, details: Partial<Expected> = {}) {
    if (!port || !mounted.current || draftGeneration.current !== renderedGeneration || live.current.port !== port
      || live.current.draftKey !== draftKey || live.current.busy || expected.current) return;
    const neutral = action === 'patch' || action === 'neck_wrinkle_detach';
    if (neutral ? !live.current.neutralAllowed : !live.current.reviewAllowed) return;
    if ((action === 'neck_wrinkle_preview' || action === 'neck_wrinkle_confirm') && !live.current.ready) return;
    if (action === 'neck_wrinkle_preview' && (!live.current.sourceCropSeen || !live.current.editorLoaded)) return;
    if (action === 'neck_wrinkle_confirm') {
      const state = live.current, candidate = state.preview;
      const pair = candidate ? inspectionAck(state.beforeCrop, state.afterCrop, candidate) : null;
      if (!candidate || !pair || !state.accepted || !state.inspectionAccepted
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
        if (!receiptMatches(receipt, request.command, view)) throw Error('颈纹回执与原请求或当前照片不匹配，请查询原请求。');
        if (!receipt.result.success) throw Error(receipt.result.error || '颈纹请求被拒绝，没有接受候选。');
        if (receipt.result.payload_released) throw Error('原审核图已释放；重新读取来源，不重发原修改。');
        const payload = receipt.result.payload;
        switch (request.command.action) {
          case 'neck_wrinkle_reference':
            if (!view || !validReference(payload, view) || !await verifyImage(payload.source_image)) throw Error('实际来源、人脸、身体清单或图像字节校验失败。');
            if (current()) {setReference(payload); setOpen(true); setSourceCrop(null); setSourceCropSeen(false); setEditorLoaded(false);}
            break;
          case 'neck_wrinkle_preview':
            if (!request.reference || !request.review || request.amount === undefined || !validPreview(payload, request.reference, request.review, request.amount)
              || !await verifyImage(payload.before) || !await verifyImage(payload.after) || !await verifyImage(payload.support)) throw Error('候选的来源、修补、人脸、笔迹、强度或三张图像哈希不一致。');
            if (current()) {setPreview(payload); setSeen({}); setAccepted(false); setInspectionAccepted(false); setBeforeCrop(null); setAfterCrop(null);}
            break;
          case 'neck_wrinkle_crop': {
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
          case 'neck_wrinkle_confirm':
          case 'neck_wrinkle_detach':
            if (!validWritePayload(payload, request.command.action,
              request.command.action === 'neck_wrinkle_confirm' ? request.preview?.amount : 0)) throw Error('写入回执不属于此颈纹候选或未确认独立强度，请查询原请求。');
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
  const outputRect = preview ? cropRect(outputFields, preview.before_output_size) : null;
  const inspection = preview ? inspectionAck(beforeCrop, afterCrop, preview) : null;
  const fullKey = preview ? `${binding}:${preview.preview_id}` : '';
  const seenKey = (side: string, hash: string, rect?: number[]) => `${fullKey}:${side}:${hash}:${rect?.join(',') ?? 'full'}`;
  const fullSeen = !!preview && (['before', 'after', 'support'] as const).every(side => seen[seenKey(side, preview[side].sha256)]);
  const cropSeen = !!inspection && !!beforeCrop && !!afterCrop
    && seen[seenKey('before-crop', beforeCrop.image.sha256, beforeCrop.rect)] && seen[seenKey('after-crop', afterCrop.image.sha256, afterCrop.rect)];
  let review: NeckReview | null = null;
  try {if (reference && selected) review = makeNeckReview(selected, reference.source, region, protect, halfWidthText, flags);} catch {/* incomplete draft */}
  const draftMatches = !!preview && !!review && preview.amount === amount && canonical(preview.review) === canonical(review);
  const canConfirm = ready && reviewAllowed && draftMatches && fullSeen && cropSeen && accepted && inspectionAccepted;
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
      const crop: NeckCropRequest = {reference_id: reference.reference_id, plane, rect: sourceRect};
      send('neck_wrinkle_crop', crop, {crop, reference});
      clearCandidate();
    } else if (plane !== 'source' && preview && outputRect) {
      const crop: NeckCropRequest = {preview_id: preview.preview_id, plane, rect: outputRect};
      send('neck_wrinkle_crop', crop, {crop, preview});
    }
  }
  const image = reference ? sourceCrop?.plane === 'source' ? {...sourceCrop.image, url: imageUrl(sourceCrop.image), rect: sourceCrop.rect}
    : {...reference.source_image, url: imageUrl(reference.source_image)} : null;
  const currentSession = session.current;
  const currentCallback = () => mounted.current && live.current.binding === binding && session.current === currentSession;
  return <div>
    <p>此人物当前权威强度：{neutralAmount === null ? '未提供有效独立读数' : `${Number((neutralAmount * 100).toFixed(6))} / 100`}。0 为严格中性，非零须独立来源与像素审核。</p>
    <p role="status">{report ? report.attached ? report.needs_review ? '保留的颈部范围已过期或需重审，不能用于新调整。' : '此人物已附加独立颈部审核范围。' : '此人物尚未附加颈部审核范围。' : '尚未取得颈部范围权威状态。'}{report?.reason ? ` ${report.reason}` : ''}</p>
    {!ready && <p role="status">{snapshot.capability.reason || '独立颈纹核心或审核协议缺失，非零候选不可用；不会调用通用模糊替代。'}</p>}
    <button type="button" disabled={!neutralAllowed} onClick={() => send('patch', {patches: [{operation_id: NECK_WRINKLE_OPERATION,
      parameter_path: '/amount', unset: false, value: 0}]})}>仅将此人物颈纹强度归零</button>
    <button type="button" disabled={!neutralAllowed || report?.attached !== true} onClick={() => send('neck_wrinkle_detach', {})}>归零并移除此人物颈部范围</button>
    <p className="muted">中性操作不要求有效分析、旧范围或数值核心；不会恢复共享继承，也不改动其他效果。已发出但结果未知时仍须先查询。</p>
    <button type="button" disabled={!reviewAllowed || open} onClick={() => send('neck_wrinkle_reference', {})}>打开真实来源，开始独立颈部审核</button>
    {open && reference && <div>
      <button type="button" onClick={close}>关闭本地草稿，不撤回或重发已送请求</button>
      <p>来源 {reference.source.width} × {reference.source.height} · FaceRef {reference.face_ref.face_instance_id} · 分析版本 {reference.face_ref.analysis_revision}。</p>
      <p>来源像素与修补身份已由宿主绑定；返回的合成图使用其实际像素，不会用物理原图冒充。</p>
      <label>实际已确认关联身体（BodyRef）<select value={choice} disabled={busy} onChange={event => {
        setChoice(event.target.value); edit(emptyNeckMask(), emptyNeckMask()); setSourceCrop(null); setSourceCropSeen(false); setEditorLoaded(false); setHalfWidthText('');
      }}><option value="">请明确选择关联身体</option>{reference.bodies.map(body => <option key={bodyKey(body.body_ref)} value={bodyKey(body.body_ref)}>
        {body.body_ref.body_instance_id} · 分析版本 {body.body_ref.analysis_revision}
      </option>)}</select></label>
      {!reference.bodies.length && <p role="status">没有当前人脸明确关联的真实身体观察。请先在人物/身体关联流程确认，不能按最近下巴分配。</p>}
      <NeckCropFields fields={sourceFields} size={[reference.source.width, reference.source.height]} label="来源 100% 观察裁片"
        disabled={busy || !selected} onChange={fields => {setSourceFields(fields); setSourceCrop(null); setSourceCropSeen(false); setEditorLoaded(false);
          setFlags(emptyNeckConfirmations()); clearCandidate();}}/>
      <button type="button" disabled={!reviewAllowed || !selected || !sourceRect} onClick={() => requestCrop('source')}>读取这个来源像素裁片，不缩放</button>
      {sourceCrop && <figure style={{overflow: 'auto', maxHeight: 600}}><NeckReviewedImage image={sourceCrop.image}
        identity={`${binding}:${reference.reference_id}:source:${canonical(sourceCrop.rect)}:${sourceCrop.image.sha256}`} nativePixels
        alt="来源原生像素裁片，用于观察实际颈部细纹半宽" onSeen={() => {if (currentCallback() && live.current.sourceCrop?.image.sha256 === sourceCrop.image.sha256
          && canonical(live.current.sourceCrop?.rect) === canonical(sourceCrop.rect)) setSourceCropSeen(true);}}
        onError={() => {if (currentCallback()) {setSourceCropSeen(false); setFlags(emptyNeckConfirmations()); clearCandidate();}}}/>
        <figcaption>来源像素 1:1，仅此矩形，不代表整张照片 100% 已检查。没有颈部或细纹时请换位置，不能猜测。</figcaption></figure>}
      <NeckSourceEditor key={`${binding}:${choice}`} binding={`${binding}:${choice}`} source={reference.source} image={image}
        region={region} protect={protect} disabled={busy || !selected} onLoaded={value => {if (currentCallback()) {setEditorLoaded(value); if (!value) {setFlags(emptyNeckConfirmations()); clearCandidate();}}}}
        onDraftStart={() => {if (currentCallback()) {setFlags(emptyNeckConfirmations()); clearCandidate();}}}
        onChange={(nextRegion, nextProtect) => {if (currentCallback()) edit(nextRegion, nextProtect);}}/>
      <label>实际观察到的细纹半宽（来源像素，1.4 至 12）<input type="number" min={1.4} max={12} step="any"
        value={halfWidthText} disabled={busy || !sourceCropSeen} onChange={event => {setHalfWidthText(event.target.value); setFlags(emptyNeckConfirmations()); clearCandidate();}}/></label>
      <p>半宽为空不设默认；不是画笔半径，也不是眼宽或脸宽。归一化值：{parseHalfWidth(halfWidthText, reference.source) ?? '尚未明确'}（来源短边比例）。</p>
      <label>候选强度（0 至 100，显式选择）<input type="number" min={0} max={100} step="any" value={amountText} disabled={busy}
        onChange={event => {setAmountText(event.target.value); clearCandidate();}}/></label>
      <p>这是本产品强度刻度，不冒称官方数值。候选为空或 0 不生成效果；归零使用上方独立中性操作。修改非零强度也须重新检查真实候选。</p>
      {([
        ['visible', '我画出的区域是来源中实际可见的皮肤，不含衣物下或被遮挡的推测部分。'],
        ['unoccluded', '我已检查并排除首饰、衣领、头发、胡须、纹身/皮肤标记、手和其他人物；自动观察不能保证识别这些遮挡。'],
        ['ownership_confirmed', '我确认这些颈部及采样上下文属于上面明确选定的 FaceRef 和关联 BodyRef，不借用另一人的皮肤。'],
        ['visible_neck_skin_reviewed', '我已在真实来源 1:1 裁片中观察颈部细纹，并独立确认手绘可见颈部与所填半宽，不沿用其他功能审核。'],
        ['protections_reviewed', protect.objects.length ? '我已独立检查硬保护，包含不应淡化的喉结、肌腱、下颌/锁骨结构阴影及其他非目标线条。' : '当前保护笔迹为空：我已检查并明确确认本次不添加硬保护；这不证明图像没有遮挡或结构阴影。'],
      ] as const).map(([field, label]) => <label key={field} style={{display: 'block'}}><input type="checkbox" checked={flags[field]}
        disabled={busy || !selected || !editorLoaded || !sourceCropSeen} onChange={event => {setFlags(old => ({...old, [field]: event.target.checked})); clearCandidate();}}/>{label}</label>)}
      <button type="button" disabled={!reviewAllowed || !ready || !review || !editorLoaded || !sourceCropSeen || amount === null || amount <= 0}
        onClick={() => {if (review && amount !== null && amount > 0 && editorLoaded && sourceCropSeen) send('neck_wrinkle_preview', {review, amount}, {reference, review, amount});}}>生成私有完整混合前后图与真实准入叠图</button>
      {preview && <div>
        <p>候选尚未发布。以下前后图来自完整混合渲染，包含其余现有效果；显示图是缩略图，不是来源或输出 100%。</p>
        {(['before', 'after', 'support'] as const).map(side => <figure key={`${preview.preview_id}:${side}:${preview[side].sha256}`}>
          <NeckReviewedImage image={preview[side]} identity={seenKey(side, preview[side].sha256)}
            alt={side === 'before' ? '本次候选前完整混合结果' : side === 'after' ? '本次候选后完整混合结果，尚未发布' : '来源坐标的最终颈部准入、硬保护与上下文排除叠图'}
            onSeen={() => seenImage(side, preview[side].sha256, true)} onError={() => seenImage(side, preview[side].sha256, false)}/>
          <figcaption>{side === 'before' ? '完整混合结果：调整前' : side === 'after' ? '完整混合结果：候选后' : '来源叠图：青色最终准入，粉红硬保护，橙色上下文不足排除；不是自动实例分割'}</figcaption>
        </figure>)}
        <NeckCropFields fields={outputFields} size={preview.before_output_size} label="混合输出 100% 检查裁片" disabled={busy}
          onChange={fields => {draftGeneration.current++; setOutputFields(fields); setBeforeCrop(null); setAfterCrop(null); setInspectionAccepted(false); setAccepted(false);}}/>
        <p>这是最终输出坐标。经过裁剪、旋转或形变后，不等同来源坐标；不会用这里的坐标绘制来源蒙版。</p>
        <button type="button" disabled={!reviewAllowed || !outputRect} onClick={() => requestCrop('before')}>读取这个输出矩形的调整前原生像素</button>
        <button type="button" disabled={!reviewAllowed || !outputRect} onClick={() => requestCrop('after')}>读取相同输出矩形的候选后原生像素</button>
        {([['before', beforeCrop], ['after', afterCrop]] as const).map(([side, crop]) => crop && <figure key={`${side}:${canonical(crop.rect)}:${crop.image.sha256}`} style={{overflow: 'auto', maxHeight: 600}}>
          <NeckReviewedImage image={crop.image} identity={seenKey(`${side}-crop`, crop.image.sha256, crop.rect)} nativePixels
            alt={side === 'before' ? '选定输出矩形调整前的 1:1 原生像素' : '相同输出矩形候选后的 1:1 原生像素'}
            onSeen={() => seenImage(`${side}-crop`, crop.image.sha256, true, crop.rect)} onError={() => seenImage(`${side}-crop`, crop.image.sha256, false, crop.rect)}/>
          <figcaption>{side === 'before' ? '前' : '后'}：输出矩形 {crop.rect.join(', ')}，原生像素 1:1，无缩放。</figcaption></figure>)}
        <label style={{display: 'block'}}><input type="checkbox" checked={inspectionAccepted} disabled={busy || !cropSeen || !draftMatches}
          onChange={event => {setInspectionAccepted(event.target.checked); setAccepted(false);}}/>我已逐一比较这对相同输出矩形的 1:1 裁片，检查颈纹、毛孔、结构阴影、边界和保护内容；这只是该矩形，不代表全图 100% 覆盖。</label>
        <label style={{display: 'block'}}><input type="checkbox" checked={accepted} disabled={busy || !fullSeen || !cropSeen || !inspectionAccepted || !draftMatches}
          onChange={event => setAccepted(event.target.checked)}/>我已查看这组三张完整审核图及上述裁片，独立接受此人、此范围、此强度的颈部细纹候选。</label>
        <button type="button" disabled={!canConfirm} onClick={() => {
          if (canConfirm && preview && inspection && live.current.preview === preview && live.current.accepted && live.current.inspectionAccepted)
            send('neck_wrinkle_confirm', confirmation(preview, inspection), {preview});
        }}>确认此候选与独立颈部范围</button>
      </div>}
    </div>}
    {error && <p role="alert">{error}</p>}
  </div>;
}
