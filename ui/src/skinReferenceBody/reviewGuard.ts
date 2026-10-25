// SPDX-License-Identifier: GPL-3.0-or-later
import type {PeopleAction, PeopleResult, PeopleView} from '../people/model';
import {sameFace} from '../people/transferProof';
import {ack, canonical, catalogImage, echoMatches, exact, isSkinReferenceBodyAction, object, previewMatchesCatalog,
  receiptCurrent, requestFits, reviewImage, sameAck, sameCurrent, skinReferenceBodyBinding, skinReferenceBodyContext,
  validCatalog, validClear, validConfirmation, validImageReceipt, validPreview, validReleasedReceipt, validReview,
  type SkinReferenceBodyCatalog, type SkinReferenceBodyPreview, type SkinReferenceBodyReview, type SkinReferenceBodySide} from './model';

type Frozen = {review: SkinReferenceBodyReview; preview: SkinReferenceBodyPreview; binding: string; images: Set<SkinReferenceBodySide>};
type Capture = {command: PeopleAction; view: PeopleView; catalog: SkinReferenceBodyCatalog | null; frozen: Frozen | null};
type WriteFence = {document: string; epoch: string; revision: number; state: number};
export const isSkinReferenceBodyRead = (command: PeopleAction) => isSkinReferenceBodyAction(command.action)
  && !['skin_reference_body_confirm', 'skin_reference_body_clear'].includes(command.action);

/** Operation-owned proof admission inside the existing people owner. No transport,
 * poller, request queue, graph, mutation publication or history mechanism lives here. */
export function createSkinReferenceBodyReviewGuard() {
  let catalog: {value: SkinReferenceBodyCatalog; binding: string} | null = null;
  let frozen: Frozen | null = null, captured: Capture | null = null, writeFence: WriteFence | null = null;
  function needsRefresh(view: PeopleView | null): boolean {
    return !!writeFence && !!view && view.binding.document_id === writeFence.document && view.binding.document_epoch === writeFence.epoch
      && (view.binding.document_revision < writeFence.revision || view.revision < writeFence.state);
  }
  function update(view: PeopleView | null) {
    const binding = skinReferenceBodyBinding(view);
    if (catalog?.binding !== binding) catalog = null;
    if (frozen?.binding !== binding) frozen = null;
    if (writeFence && view && view.binding.document_id === writeFence.document && view.binding.document_epoch === writeFence.epoch
      && view.binding.document_revision >= writeFence.revision && view.revision >= writeFence.state) writeFence = null;
  }
  function prepare(command: PeopleAction, view: PeopleView | null) {
    if (!isSkinReferenceBodyAction(command.action)) return;
    if (!view || needsRefresh(view)) throw Error('身体参考匹配结果等待当前照片状态刷新，不能重复修改。');
    const context = skinReferenceBodyContext(view), {request_id: _id, action: _action, payload, ...actual} = command;
    if (!context || canonical(context) !== canonical(actual) || !requestFits(command))
      throw Error('身体参考请求必须有界并绑定当前整张照片，不能借用人物光标或旧版本。');
    const binding = skinReferenceBodyBinding(view);
    if (command.action === 'skin_reference_body_catalog' || command.action === 'skin_reference_body_clear') {
      if (!exact(payload, [])) throw Error('读取与清除身体参考不能携带隐式参考或目标。');
    } else if (command.action === 'skin_reference_body_preview') {
      if (!validPreview(payload) || !catalog || catalog.binding !== binding || !previewMatchesCatalog(payload, catalog.value))
        throw Error('请先读取本操作来源图，并独立确认参考脸、目标身体归属及可见无遮挡的手画皮肤范围。');
    } else {
      if (!frozen || frozen.binding !== binding || !validReview(frozen.review, view, frozen.preview)
        || payload.token !== frozen.review.token) throw Error('身体参考审核已过期，请重新生成完整预览。');
      if (command.action === 'skin_reference_body_image') {
        if (!exact(payload, ['token', 'side', 'sha256', 'review_sha256']) || !['before', 'after'].includes(String(payload.side))
          || payload.review_sha256 !== frozen.review.review_sha256
          || payload.sha256 !== frozen.review.visual[payload.side as SkinReferenceBodySide].sha256)
          throw Error('身体审核图必须属于当前冻结候选的精确一侧。');
      } else if (!exact(payload, ['token', 'ack']) || !sameAck(payload.ack, ack(frozen.review))
        || !frozen.images.has('before') || !frozen.images.has('after'))
        throw Error('请完整加载并明确确认本身体候选的两张真实审核图，不能借用脸部或其他身体审核。');
    }
    captured = {command: structuredClone(command), view: structuredClone(view), catalog: catalog ? structuredClone(catalog.value) : null,
      frozen: frozen ? {review: structuredClone(frozen.review), preview: structuredClone(frozen.preview), binding: frozen.binding,
        images: new Set(frozen.images)} : null};
    if (command.action === 'skin_reference_body_catalog') catalog = null;
    if (['skin_reference_body_catalog', 'skin_reference_body_preview', 'skin_reference_body_clear'].includes(command.action)) frozen = null;
  }
  async function validate(command: PeopleAction, result: PeopleResult, current: () => PeopleView | null): Promise<void> {
    if (!isSkinReferenceBodyAction(command.action)) return;
    const capture = captured;
    if (!capture || canonical(capture.command) !== canonical(command) || !echoMatches(command, result)
      || result.protocol !== 1 || typeof result.success !== 'boolean' || result.outcome_unknown !== false
      || result.request_id !== command.request_id || result.action !== command.action || result.document_id !== command.document_id
      || result.batch_id != null || (isSkinReferenceBodyRead(command) || !result.success)
        && (result.doc_state !== undefined || Object.hasOwn(result, 'frame'))
      || !result.success && result.payload !== undefined)
      throw Error('身体参考回执缺少原请求的精确身份或包含未授权写入，只能查询原请求。');
    const released = validReleasedReceipt(command, result);
    if (result.payload_released !== undefined && result.payload_released !== false && !released)
      throw Error('只有已确认的只读身体审核内容可释放，修改结果必须保留完整证明。');
    if (!result.success) return;
    if (released) {catalog = null; frozen = null; return;}
    const payload = result.payload;
    if (!object(payload)) throw Error('身体参考回执缺少有效审核内容。');
    const stillCurrent = () => receiptCurrent(command, result, current())
      && skinReferenceBodyBinding(current()) === skinReferenceBodyBinding(capture.view);
    switch (command.action) {
      case 'skin_reference_body_catalog':
        if (!validCatalog(payload, capture.view) || !await catalogImage(payload)) throw Error('身体来源图、完整人物与明确身体归属清单校验失败。');
        if (stillCurrent()) catalog = {value: structuredClone(payload), binding: skinReferenceBodyBinding(capture.view)};
        break;
      case 'skin_reference_body_preview': {
        const before = capture.catalog;
        if (!exact(payload, ['kind', 'review']) || payload.kind !== command.action || !validPreview(command.payload)
          || !validReview(payload.review, capture.view, command.payload) || !before
          || !previewMatchesCatalog(command.payload, before)
          || canonical(payload.review.source) !== canonical(before.source)
          || canonical(payload.review.visual.source_proof) !== canonical(before.source_proof)
          || !sameCurrent(payload.review.before_current, before.current))
          throw Error('身体候选与来源、独立同意、完整旧目标或支持库不一致。');
        if (stillCurrent()) frozen = {review: structuredClone(payload.review), preview: structuredClone(command.payload),
          binding: skinReferenceBodyBinding(capture.view), images: new Set()};
        break;
      }
      case 'skin_reference_body_image':
        if (!capture.frozen || !validImageReceipt(payload, command)
          || !await reviewImage(payload, capture.frozen.review, command.payload.side as SkinReferenceBodySide))
          throw Error('身体审核图字节、尺寸或冻结来源不匹配。');
        if (stillCurrent() && frozen?.review.review_sha256 === capture.frozen.review.review_sha256)
          frozen.images.add(command.payload.side as SkinReferenceBodySide);
        break;
      case 'skin_reference_body_confirm':
        if (!capture.frozen || !validConfirmation(capture.frozen.review, result))
          throw Error('身体参考写入缺少完整候选、保留目标、支持库或原生结果证明，只能查询原请求。');
        break;
      case 'skin_reference_body_clear':
        if (!validClear(command, result) || capture.catalog && !capture.catalog.current.target_face_refs.every(ref =>
          (payload.cleared_face_refs as import('../people/model').FaceRef[]).some(cleared => sameFace(ref, cleared))))
          throw Error('身体参考清除缺少完整中性结果证明，只能查询原请求。');
        break;
    }
    if (!isSkinReferenceBodyRead(command)) {
      const next = result.doc_state!.people!;
      writeFence = {document: next.binding.document_id, epoch: next.binding.document_epoch,
        revision: next.binding.document_revision, state: next.revision};
      catalog = null; frozen = null;
    }
  }
  function complete(command: PeopleAction) {
    if (isSkinReferenceBodyAction(command.action) && captured?.command.request_id === command.request_id) captured = null;
  }
  return {prepare, validate, complete, update, needsRefresh};
}
