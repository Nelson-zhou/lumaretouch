// SPDX-License-Identifier: GPL-3.0-or-later
import {useEffect, useRef, useState} from 'react';
import {peopleContext, type PeopleAction} from '../people/model';
import type {PeopleOwner} from '../people/usePeopleWorkflow';
import {matchesSource, previewImage} from '../legShape/sourcePreview';
import {skinColourBindingKey, skinColourTargetReady} from './model';
import {SkinBodySourceEditor} from './SkinBodySourceEditor';
import {bodyRefKey, bodyReview, bodyReviewKey, emptyBodyMask, previewMatches, referenceMatches, renderedSkinImage,
  skinBodyAttached, skinBodyTarget, skinBodyRequestFits, type SkinBodyAction, type SkinBodyMask, type SkinBodyPayload,
  type SkinBodyPreview, type SkinBodyReference, type SkinBodyReview} from './bodyReviewModel';
const emptyFlags = () => ({visible: false, unoccluded: false, ownership_confirmed: false});
type Expected = {id: string; context: string; action: SkinBodyAction; review?: SkinBodyReview};

/** Local review drafts only; submission, uncertainty and publication stay with people. */
export function SkinBodyPanel({people, blocked, coreAvailable}: {people: PeopleOwner; blocked: boolean; coreAvailable: boolean}) {
  const view = people.value, context = skinColourBindingKey(view);
  const latest = useRef(context); latest.current = context;
  const expected = useRef<Expected | null>(null);
  const [open, setOpen] = useState(false), [reference, setReference] = useState<SkinBodyReference | null>(null);
  const [choice, setChoice] = useState(''), [mask, setMask] = useState<SkinBodyMask>(emptyBodyMask);
  const [flags, setFlags] = useState(emptyFlags), [preview, setPreview] = useState<SkinBodyPreview | null>(null);
  const [sourceLoaded, setSourceLoaded] = useState(false), [loaded, setLoaded] = useState<Record<string, boolean>>({});
  const [reviewed, setReviewed] = useState(false), [error, setError] = useState('');
  const busy = blocked || !people.enabled || people.state.pending || people.state.uncertain;
  const allowed = skinBodyTarget(view), attached = skinBodyAttached(view);
  const canDetach = !!view && skinColourTargetReady(view) && view.editing_target?.scope === 'face'
    && view.editing_target.target_id === view.selected_face_id;
  const live = useRef({context, busy, allowed, canDetach, coreAvailable}); live.current = {context, busy, allowed, canDetach, coreAvailable};
  function close() {expected.current = null; setOpen(false); setReference(null); setPreview(null); setMask(emptyBodyMask()); setChoice(''); setFlags(emptyFlags()); setReviewed(false); setLoaded({}); setSourceLoaded(false);}
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
      if (request.action === 'skin_body_reference' && payload.kind === 'reference') {
        const image = previewImage(payload.source_preview);
        if (!referenceMatches(payload, view) || !matchesSource(image, {...payload.source, orientation: 'exif_normalized_once'})) throw Error('参考图与当前人物、实际来源或身体观察不匹配。');
        setReference(payload); setOpen(true); setChoice(''); setMask(emptyBodyMask()); setFlags(emptyFlags()); setPreview(null); setReviewed(false); setLoaded({}); setSourceLoaded(false);
      } else if (request.action === 'skin_body_preview' && payload.kind === 'preview' && reference && request.review) {
        const overlay = previewImage(payload.overlay);
        if (!previewMatches(payload, reference, request.review) || !matchesSource(overlay, {...reference.source, orientation: 'exif_normalized_once'})) throw Error('候选回执与提交的笔迹、人物或来源不匹配，请重新审核。');
        setPreview(payload); setReviewed(false); setLoaded({});
      } else if ((request.action === 'skin_body_confirm' && payload.kind === 'confirmed')
        || (request.action === 'skin_body_detach' && payload.kind === 'detached')) close();
      else throw Error('审核回执类型与当前请求不匹配。');
      setError('');
    } catch (reason) {setPreview(null); setReviewed(false); setError(String(reason));}
  }, [people.state.lastBodyResult, view, reference]);

  function send(action: SkinBodyAction, payload: Record<string, unknown>, review?: SkinBodyReview) {
    if (expected.current || live.current.context !== context || live.current.busy || (action === 'skin_body_detach' ? !live.current.canDetach : !live.current.allowed)) return;
    if ((action === 'skin_body_preview' || action === 'skin_body_confirm') && !live.current.coreAvailable) return;
    const captured = peopleContext(view); if (!captured) return;
    const command: PeopleAction = {...structuredClone(captured), request_id: crypto.randomUUID(), action, payload: structuredClone(payload)};
    if (!skinBodyRequestFits(command)) {
      setError('笔迹请求超过 192 KiB 安全预算，尚未发送。请撤回或清理草稿；不会自动删减几何点。'); return;
    }
    expected.current = {id: command.request_id, context, action, review: review ? structuredClone(review) : undefined};
    setError('');
    void people.submitCaptured(command).catch(reason => {
      if (latest.current === context && expected.current?.id === command.request_id) setError(String(reason));
    });
  }
  function edit(next: SkinBodyMask) {setMask(next); setFlags(emptyFlags()); setPreview(null); setReviewed(false); setLoaded({});}
  function invalidateReview() {setFlags(emptyFlags()); setPreview(null); setReviewed(false); setLoaded({});}
  const selected = reference?.bodies.find(body => bodyRefKey(body.body_ref) === choice);
  const sourceImage = reference ? previewImage(reference.source_preview) : null;
  const overlay = preview ? previewImage(preview.overlay) : null;
  const images = preview ? [
    {key: 'before', url: renderedSkinImage(preview.before), width: preview.before.width, height: preview.before.height, caption: '添加此身体范围前：真实渲染结果'},
    {key: 'after', url: renderedSkinImage(preview.after), width: preview.after.width, height: preview.after.height, caption: '添加此身体范围后：真实候选结果，尚未提交'},
    {key: 'overlay', url: overlay?.url ?? null, width: overlay?.displayWidth ?? 0, height: overlay?.displayHeight ?? 0, caption: '来源坐标中的实际皮肤范围叠图，不是裁剪后效果图'},
  ] : [];
  const comparisonLoaded = images.length === 3 && images.every(image => !!image.url && loaded[`${preview!.preview_id}:${image.key}`]);
  const draftMatches = !!preview && !!selected && bodyReviewKey(preview.review) === bodyReviewKey({body_ref: selected.body_ref,
    points_sha256: selected.points_sha256, recipe: mask, visible: true, unoccluded: true, ownership_confirmed: true});
  return <section aria-label="可见身体皮肤范围审核">
    <p>身体扩展只使用当前人物已确认关联的真实身体观察，并经手绘复核。不会复制其他人物的范围，也不会推测衣物下或被遮挡的皮肤。</p>
    <p role="status">{attached === true ? view?.skin_body?.needs_review === false ? '当前人物已附加有效身体皮肤范围；色温与色调同时作用于其脸部及审核范围。' : '当前人物保留了身体范围，但有效性尚未确认或需要重新审核，不能视为可用。' : attached === false ? '当前人物尚未附加身体范围，仍仅调整面部皮肤。' : '尚未取得当前人物的身体范围状态。'}</p>
    {attached !== null && view?.skin_body?.reason && <p role="status">{view.skin_body.reason}</p>}
    {!allowed && <p className="muted">请在人物栏选择当前已分析人物的独立编辑范围；人物、分组或全部默认不能直接拥有此来源选区。</p>}
    <button type="button" className="specBtn" disabled={busy || !allowed} onClick={() => {if (expected.current) return; close(); send('skin_body_reference', {});}}>打开当前来源图审核身体皮肤</button>
    <button type="button" className="specBtn" disabled={busy || !canDetach || attached !== true} onClick={() => send('skin_body_detach', {})}>移除此人物身体范围，保留面部调色</button>
    {open && reference && <div>
      <button type="button" onClick={close}>{people.state.pending ? '关闭审核，已发请求仍待确认' : '关闭审核，不提交草稿'}</button>
      <label>已确认关联的身体<select value={choice} disabled={busy} onChange={event => {setChoice(event.target.value); edit(emptyBodyMask()); setSourceLoaded(false);}}>
        <option value="">请明确选择身体</option>{reference.bodies.map((body, index) => <option key={bodyRefKey(body.body_ref)} value={bodyRefKey(body.body_ref)}>已关联身体 {index + 1}</option>)}
      </select></label>
      {!reference.bodies.length && <p role="status">没有与此脸可靠关联的真实身体观察。请先在全身塑形中完成身体分析与人物关联；不会按脸框或肤色猜测。</p>}
      {selected && <SkinBodySourceEditor key={`${context}:${choice}`} context={`${context}:${choice}`} source={reference.source} image={sourceImage}
        value={mask} disabled={busy} onChange={edit} onLoaded={setSourceLoaded} onDraftStart={invalidateReview}/>}
      {(['visible', 'unoccluded', 'ownership_confirmed'] as const).map(flag => <label key={flag} style={{display: 'block'}}>
        <input type="checkbox" disabled={busy || !selected || !sourceLoaded || !mask.objects.length} checked={flags[flag]}
          onChange={event => {setFlags(old => ({...old, [flag]: event.target.checked})); setPreview(null); setReviewed(false); setLoaded({});}}/>
        {flag === 'visible' ? '我确认笔迹所选均为来源图中真实可见的身体皮肤' : flag === 'unoccluded' ? '我确认已排除衣物、头发、物体及遮挡区域' : '我确认所选范围只属于当前脸与已关联身体，没有其他人物'}
      </label>)}
      <button type="button" className="specBtn" disabled={busy || !coreAvailable || !selected || !sourceLoaded || !Object.values(flags).every(Boolean)} onClick={() => {
        if (!selected) return; try {const review = bodyReview(selected, mask, flags); setPreview(null); setReviewed(false); setLoaded({}); send('skin_body_preview', {review}, review);} catch (reason) {setError(String(reason));}
      }}>生成真实前后对比与范围审核图</button>
      {!coreAvailable && <p role="status">肤色调整核心不可用，不能生成或确认真实候选；仍可移除当前人物已附加的身体范围。</p>}
      <p className="muted">请先在色温或色调设置非零值，再打开审核；两项均为零时不会制造虚假的变化。更改调色、照片、人物或分析会使本次审核失效。</p>
      {preview && <div>
        {images.map(image => <figure key={`${preview.preview_id}:${image.key}`} style={{margin: '8px 0'}}>
          {image.url && <img src={image.url} alt={image.caption} style={{width: '100%', height: 'auto'}} onLoad={event => {
            const valid = event.currentTarget.naturalWidth === image.width && event.currentTarget.naturalHeight === image.height;
            setLoaded(old => ({...old, [`${preview.preview_id}:${image.key}`]: valid})); if (!valid) {setReviewed(false); setError('审核图实际尺寸与回执不符。');}
          }} onError={() => {setLoaded(old => ({...old, [`${preview.preview_id}:${image.key}`]: false})); setReviewed(false); setError('审核图加载失败，不能确认。');}}/>}
          <figcaption>{image.caption}</figcaption>
        </figure>)}
        <p>请对比肤色、皮肤边缘与邻近人物；手工确认不等于分割或照片质量验收。图像为缩略对比，不能证明所有细节正确。</p>
        <label><input type="checkbox" checked={reviewed} disabled={busy || !comparisonLoaded || !draftMatches} onChange={event => setReviewed(event.target.checked)}/>我已看过这组三张审核图，确认可见皮肤范围与当前人物一致，并接受此候选效果</label>
        <button type="button" className="specBtn" disabled={busy || !coreAvailable || !allowed || !reviewed || !comparisonLoaded || !draftMatches}
          onClick={() => {if (preview && comparisonLoaded && draftMatches && reviewed) send('skin_body_confirm', {preview_id: preview.preview_id, reviewed: true});}}>确认附加此身体皮肤范围</button>
      </div>}
    </div>}
    {error && <p role="alert">{error}</p>}
    <p className="muted">这是手动审核的身体皮肤扩展，不是自动全身肤色识别、AI 美白或肤色统一；皮肤功能族仍未完整验收。</p>
  </section>;
}
