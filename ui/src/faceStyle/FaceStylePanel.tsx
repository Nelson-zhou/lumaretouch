// SPDX-License-Identifier: GPL-3.0-or-later
import {useEffect, useLayoutEffect, useRef, useState} from 'react';
import {peopleContext, type PeopleAction} from '../people/model';
import type {PeopleOwner} from '../people/usePeopleWorkflow';
import type {SpillImage} from '../spillRemoval/model';
import {FACE_STYLES, FACE_STYLE_LABELS, faceStyleAck, faceStyleBinding, faceStyleImage, faceStyleLegacyWarning,
  faceStyleTargetReady, isFaceStyle, object, parseFaceStyleAmount, sameFaceStyleAck, validFaceStyleReview,
  type FaceStyle, type FaceStyleAction, type FaceStyleRecipe, type FaceStyleReview, type FaceStyleSide} from './model';

type Expected = {id: string; key: string; action: FaceStyleAction; recipe?: FaceStyleRecipe; side?: FaceStyleSide; review?: FaceStyleReview};
/** Review drafts only. The established people queue owns all requests, receipts and uncertainty. */
export function FaceStylePanel({people, blocked, faceOk}: {people: PeopleOwner; blocked: boolean; faceOk: boolean}) {
  const view = people.value, binding = faceStyleBinding(view);
  const [style, setStyle] = useState<FaceStyle | ''>(''), [amountText, setAmountText] = useState('');
  const amount = parseFaceStyleAmount(amountText), key = JSON.stringify([binding, style, amountText]);
  const [catalogue, setCatalogue] = useState(false), [review, setReview] = useState<FaceStyleReview | null>(null);
  const [images, setImages] = useState<Partial<Record<FaceStyleSide, SpillImage>>>({});
  const [loaded, setLoaded] = useState<Partial<Record<FaceStyleSide, boolean>>>({});
  const [acknowledged, setAcknowledged] = useState(false), [error, setError] = useState('');
  const expected = useRef<Expected | null>(null), mounted = useRef(false);
  const busy = blocked || !people.enabled || people.state.pending || people.state.uncertain;
  const allowed = faceOk && faceStyleTargetReady(view);
  const reason = allowed ? null : '请先选择当前已验证人脸的「此脸独立」范围，并解决参数冲突。';
  const legacyWarning = faceStyleLegacyWarning(view);
  const live = useRef({key, busy, allowed, review}); live.current = {key, busy, allowed, review};
  useLayoutEffect(() => {mounted.current = true; return () => {mounted.current = false; expected.current = null;};}, []);
  function invalidate() {expected.current = null; setReview(null); setImages({}); setLoaded({}); setAcknowledged(false); setError('');}
  useLayoutEffect(() => {expected.current = null; setCatalogue(false); setStyle(''); setAmountText(''); invalidate();}, [binding]);
  function send(action: FaceStyleAction, payload: Record<string, unknown>, details: Partial<Expected> = {}) {
    if (!mounted.current || live.current.key !== key || live.current.busy || !live.current.allowed || expected.current) return;
    const context = peopleContext(view); if (!context) return;
    const command: PeopleAction = {...structuredClone(context), request_id: crypto.randomUUID(), action, payload: structuredClone(payload)};
    expected.current = {id: command.request_id, key, action, ...details}; setError('');
    void people.submitCaptured(command).catch(cause => {
      if (mounted.current && live.current.key === key && expected.current?.id === command.request_id) {
        // Keep unknown requests query-only. A confirmed rejection permits an explicit fresh attempt.
        if (!people.state.uncertain) setError(String(cause));
      }
    });
  }
  useEffect(() => {
    const receipt = people.state.lastFaceStyleResult, request = expected.current;
    if (!receipt || !request || request.key !== live.current.key || receipt.result.request_id !== request.id
      || receipt.command.action !== request.action) return;
    const stillCurrent = () => mounted.current && live.current.key === request.key && expected.current === request;
    void (async () => {
      try {
        if (receipt.result.payload_released) throw Error('审核图已释放，请重新生成预览；不会重发原修改。');
        const payload = receipt.result.payload;
        if (!object(payload)) throw Error('新版脸型回执缺少有效内容。');
        if (request.action === 'face_style_catalog') {
          if (!validCatalogue(payload)) throw Error('新版脸型目录不匹配，不能用旧版预设替代。');
          if (stillCurrent()) setCatalogue(true);
        } else if (request.action === 'face_style_preview') {
          if (payload.kind !== 'face_style_preview' || !request.recipe || !validFaceStyleReview(payload.review, view, request.recipe))
            throw Error('候选与当前来源、人物或配方不匹配，请重新生成。');
          if (stillCurrent()) {setReview(payload.review); setImages({}); setLoaded({}); setAcknowledged(false);}
        } else if (request.action === 'face_style_image') {
          if (!request.review || !request.side) throw Error('审核图请求缺少绑定。');
          const image = await faceStyleImage(payload, request.review, request.side);
          if (!image) throw Error('审核图字节、尺寸或来源校验失败，不能确认效果。');
          if (stillCurrent()) setImages(old => ({...old, [request.side!]: image}));
        } else {
          if (payload.kind !== 'face_style_confirm' || !request.review || payload.token !== request.review.token
            || payload.review_sha256 !== request.review.review_sha256 || payload.patches_sha256 !== request.review.patches_sha256
            || !sameFaceStyleAck(payload.ack, faceStyleAck(request.review))) throw Error('确认回执不匹配，请查询原请求，不要重发。');
          if (stillCurrent()) invalidate();
        }
      } catch (cause) {if (stillCurrent()) {setError(String(cause)); setAcknowledged(false);}}
      finally {if (stillCurrent()) expected.current = null;}
    })();
  }, [people.state.lastFaceStyleResult, view]);
  useEffect(() => {
    if (!people.state.pending && !people.state.uncertain && people.state.message && !people.state.lastFaceStyleResult) {
      expected.current = null; setError(people.state.message);
    }
  }, [people.state]);
  // Read each PNG through the same exact-envelope mailbox. Metadata alone never unlocks confirmation.
  useEffect(() => {
    if (!review || busy || expected.current || error || !allowed) return;
    const side = !images.before ? 'before' : !images.after ? 'after' : null;
    if (side) send('face_style_image', {token: review.token, side, sha256: review.visual[side].sha256}, {review, side});
  }, [review, images, busy, error, key]);
  const draftMatches = !!review && !!style && amount !== null && validFaceStyleReview(review, view, {version: 1, style, amount});
  const ready = draftMatches && !!images.before && !!images.after && loaded.before === true && loaded.after === true;
  function imageLoaded(side: FaceStyleSide, element: HTMLImageElement) {
    if (!mounted.current || live.current.key !== key || live.current.review !== review || !review) return;
    const good = element.naturalWidth === review.visual[side].width && element.naturalHeight === review.visual[side].height;
    setLoaded(old => ({...old, [side]: good})); if (!good) {setAcknowledged(false); setError('审核图实际解码尺寸不匹配。');}
  }
  return <section aria-label="新版七种脸型配方" data-face-style-version="1" data-control-id="PC-32466-C-3b31aac970">
    <h4>新版脸型配方</h4>
    <p>经典、幼态、英气、少年，以及圆脸、长脸、方脸适用的七种本地配方。名称是风格提示，不会检测或决定性别、年龄，也不自动判断你应选择哪一种。</p>
    <p className="muted">只针对当前明确选中的一张脸。读取原图或受支持的当前派生来源，先看真实渲染前后图，再确认写入现有形变参数；不是新 AI 算法，也不保证照片质量或官方同等效果。</p>
    {!catalogue && <button type="button" disabled={busy || !allowed} onClick={() => send('face_style_catalog', {})}>读取新版七种配方</button>}
    <fieldset disabled={busy || !allowed || !catalogue}>
      <legend>明确选择候选，不自动应用</legend>
      <label>脸型<select value={style} onChange={event => {const next = event.target.value; setStyle(isFaceStyle(next) ? next : ''); invalidate();}}>
        <option value="">请选择新版配方</option>{FACE_STYLES.map(value => <option key={value} value={value}>{FACE_STYLE_LABELS[value]}</option>)}
      </select></label>
      <label data-control-id="PC-32466-C-6c86bf2c55">程度（0–100）<input type="number" min={0} max={100} step="any" value={amountText}
        onChange={event => {setAmountText(event.target.value); invalidate();}}/></label>
      <p className="muted">显示 0–100 对应配方程度 0–1。0 会将此配方管理的 30 个参数设为中性，不是取消预览，也不会清除旧版参数。</p>
      <button type="button" disabled={!!reason || !style || amount === null}
        onClick={() => {if (!style || amount === null || reason) return; invalidate(); const recipe: FaceStyleRecipe = {version: 1, style, amount}; send('face_style_preview', recipe, {recipe});}}>生成此脸前后预览</button>
    </fieldset>
    {reason && <p role="status">{reason}</p>}
    {legacyWarning && <p role="status">{legacyWarning}</p>}
    {review && draftMatches && <div>
      <p>本次候选：{FACE_STYLE_LABELS[review.recipe.style]}，程度 {Number((review.recipe.amount * 100).toFixed(6))}。尚未应用。</p>
      {(['before', 'after'] as const).map(side => <figure key={`${review.token}:${side}`}>
        <figcaption>{side === 'before' ? '修改前：当前真实渲染' : '修改后：本次候选真实渲染（尚未应用）'}</figcaption>
        {images[side] ? <img alt={side === 'before' ? '当前整张照片修改前' : '当前整张照片候选修改后'}
          src={`data:image/png;base64,${images[side]!.base64}`} style={{maxWidth: '100%', height: 'auto'}}
          onLoad={event => imageLoaded(side, event.currentTarget)} onError={() => {
            if (live.current.key !== key || live.current.review !== review) return;
            setLoaded(old => ({...old, [side]: false})); setAcknowledged(false); setError('前后图未能完整显示，请重新预览。');
          }}/> : <p role="status">正在读取{side === 'before' ? '修改前' : '修改后'}图像…</p>}
      </figure>)}
      <p className="muted">这是整张实际渲染的缩略审核图，不是原尺寸质量验收。请检查此脸、邻近人物和背景；局部变形可能牵动邻近背景。</p>
      <label><input type="checkbox" checked={acknowledged} disabled={busy || !ready} onChange={event => setAcknowledged(event.target.checked)}/>
        我已查看两张实际前后图，接受仅对当前这张脸写入此候选参数</label>
      <button type="button" disabled={busy || !ready || !acknowledged || !!error || !!reason}
        onClick={() => {if (live.current.key !== key || live.current.review !== review || !ready || !acknowledged || error || reason) return;
          send('face_style_confirm', {token: review.token, ack: faceStyleAck(review)}, {review});}}>确认此脸配方</button>
      <button type="button" disabled={busy} onClick={invalidate}>放弃候选，不改参数</button>
    </div>}
    {error && <p role="alert">{error}</p>}
    {people.state.uncertain && <button type="button" onClick={() => {void people.check().catch(() => {});}}>查询原请求结果（不重发）</button>}
    <p className="muted">每次确认会替换此脸上配方管理的 30 个参数（分属 10 个现有操作），不累加；未管理的参数保留。请在预览中检查已有自定义调整被替换后的结果。</p>
    <p className="muted">确认保存的是实际参数，不是一个持续激活的风格标签。之后手动改动参数不会被称为仍完整使用此配方。历史三种预设保留原值和原行为，请仅在下方明确打开旧版入口；不会自动转换或清除冲突。</p>
  </section>;
}

function validCatalogue(payload: Record<string, unknown>): boolean {
  const value = payload.catalogue;
  if (!object(value)) return false;
  const styles = value.styles;
  return payload.kind === 'face_style_catalog' && object(value) && value.version === 1 && value.binding_version === 1
    && typeof value.family_control_id === 'string' && typeof value.amount_control_id === 'string'
    && Array.isArray(value.owned_operation_ids) && value.owned_operation_ids.length > 0
    && value.owned_operation_ids.every(id => typeof id === 'string')
    && Array.isArray(styles) && styles.length === 7 && value.amount_min === 0 && value.amount_max === 1
    && FACE_STYLES.every(style => styles.some((row: unknown) => object(row) && row.id === style && row.label === FACE_STYLE_LABELS[style] && row.version === 1 && row.binding_version === 1));
}
