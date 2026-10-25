// SPDX-License-Identifier: GPL-3.0-or-later
import type {PeopleAction, PeopleResult, PeopleView} from '../people/model';
import {sameFace} from '../people/transferProof';
import {ack, canonical, catalogImage, echoMatches, isSkinReferenceAction, object, receiptCurrent, reviewImage,
  sameAck, skinReferenceBinding, skinReferenceContext, validCatalog, validClear, validConfirmation,
  validImageReceipt, validPreview, validReleasedReceipt, validReview,
  type SkinReferenceCatalog, type SkinReferencePreview, type SkinReferenceReview, type SkinReferenceSide} from './model';

type Frozen = {review: SkinReferenceReview; preview: SkinReferencePreview; binding: string; images: Set<SkinReferenceSide>};
type Capture = {command: PeopleAction; view: PeopleView; catalog: SkinReferenceCatalog | null; frozen: Frozen | null};
type WriteFence = {document: string; epoch: string; revision: number; state: number};
const exact = (value: Record<string, unknown>, names: string[]) => Object.keys(value).sort().join('|') === [...names].sort().join('|');
export const isSkinReferenceRead = (command: PeopleAction) => isSkinReferenceAction(command.action)
  && !['skin_reference_match_confirm', 'skin_reference_match_clear'].includes(command.action);

/** Frozen proof admission inside the existing people owner. This has no transport,
 * poller, request queue, graph, publication path, history or retry mechanism. */
export function createSkinReferenceReviewGuard() {
  let catalog: {value: SkinReferenceCatalog; binding: string} | null = null;
  let frozen: Frozen | null = null, captured: Capture | null = null, writeFence: WriteFence | null = null;
  function needsRefresh(view: PeopleView | null): boolean {
    return !!writeFence && !!view && view.binding.document_id === writeFence.document && view.binding.document_epoch === writeFence.epoch
      && (view.binding.document_revision < writeFence.revision || view.revision < writeFence.state);
  }
  function update(view: PeopleView | null) {
    const binding = skinReferenceBinding(view);
    if (catalog?.binding !== binding) catalog = null;
    if (frozen?.binding !== binding) frozen = null;
    if (writeFence && view && view.binding.document_id === writeFence.document && view.binding.document_epoch === writeFence.epoch
      && view.binding.document_revision >= writeFence.revision && view.revision >= writeFence.state) writeFence = null;
  }
  function prepare(command: PeopleAction, view: PeopleView | null) {
    if (!isSkinReferenceAction(command.action)) return;
    if (!view || needsRefresh(view)) throw Error('肤色匹配结果等待当前照片状态刷新，不能重复修改。');
    const context = skinReferenceContext(view), {request_id: _id, action: _action, payload, ...actual} = command;
    if (!context || canonical(context) !== canonical(actual)) throw Error('肤色匹配必须绑定当前整张照片，不能借用人物光标或旧版本。');
    const binding = skinReferenceBinding(view);
    if (command.action === 'skin_reference_match_catalog' || command.action === 'skin_reference_match_clear') {
      if (!exact(payload, [])) throw Error('读取与清除不能携带隐式参考人物或目标。');
    } else if (command.action === 'skin_reference_match_preview') {
      if (!validPreview(payload) || !catalog || catalog.binding !== binding || !catalog.value.skin_reference_match_available
        || payload.source_review_sha256 !== catalog.value.source_review_sha256
        || ![payload.reference_face_ref, ...payload.target_face_refs].every(ref => catalog!.value.faces.some(face =>
          face.enabled && face.available && sameFace(face.face_ref, ref))))
        throw Error('请先读取并明确确认当前来源图、参考人物和全部目标，再生成匹配预览。');
    } else {
      if (!frozen || frozen.binding !== binding || !validReview(frozen.review, view, frozen.preview)
        || payload.token !== frozen.review.token) throw Error('肤色匹配审核已过期，请重新生成完整预览。');
      if (command.action === 'skin_reference_match_image') {
        if (!exact(payload, ['token', 'side', 'sha256', 'review_sha256']) || !['before', 'after'].includes(String(payload.side))
          || payload.review_sha256 !== frozen.review.review_sha256
          || payload.sha256 !== frozen.review.visual[payload.side as SkinReferenceSide].sha256)
          throw Error('审核图必须属于当前冻结候选的精确一侧。');
      } else if (!exact(payload, ['token', 'ack']) || !sameAck(payload.ack, ack(frozen.review))
        || !frozen.images.has('before') || !frozen.images.has('after'))
        throw Error('请完整加载并明确确认当前两张审核图；不能跳过图片直接写入。');
    }
    captured = {command: structuredClone(command), view: structuredClone(view), catalog: catalog ? structuredClone(catalog.value) : null,
      frozen: frozen ? {review: structuredClone(frozen.review), preview: structuredClone(frozen.preview), binding: frozen.binding,
        images: new Set(frozen.images)} : null};
    if (command.action === 'skin_reference_match_catalog') catalog = null;
    if (['skin_reference_match_catalog', 'skin_reference_match_preview', 'skin_reference_match_clear'].includes(command.action)) frozen = null;
  }
  async function validate(command: PeopleAction, result: PeopleResult, current: () => PeopleView | null): Promise<void> {
    if (!isSkinReferenceAction(command.action)) return;
    const capture = captured;
    if (!capture || canonical(capture.command) !== canonical(command) || !echoMatches(command, result)
      || result.protocol !== 1 || typeof result.success !== 'boolean' || result.outcome_unknown !== false
      || result.request_id !== command.request_id || result.action !== command.action || result.document_id !== command.document_id
      || result.batch_id != null || (isSkinReferenceRead(command) || !result.success)
        && (result.doc_state !== undefined || Object.hasOwn(result, 'frame'))
      || !result.success && result.payload !== undefined)
      throw Error('肤色匹配回执缺少原请求的精确身份或包含未授权写入，只能查询原请求。');
    const released = validReleasedReceipt(command, result);
    if (result.payload_released !== undefined && result.payload_released !== false && !released)
      throw Error('只有已确认的只读肤色匹配内容可释放，修改结果必须保留完整证明。');
    if (!result.success) return;
    if (released) {catalog = null; frozen = null; return;}
    const payload = result.payload;
    if (!object(payload)) throw Error('肤色匹配回执缺少有效审核内容。');
    const stillCurrent = () => receiptCurrent(command, result, current())
      && skinReferenceBinding(current()) === skinReferenceBinding(capture.view);
    switch (command.action) {
      case 'skin_reference_match_catalog':
        if (!validCatalog(payload, capture.view) || !await catalogImage(payload)) throw Error('肤色匹配来源图或完整人物清单校验失败。');
        if (stillCurrent()) catalog = {value: structuredClone(payload), binding: skinReferenceBinding(capture.view)};
        break;
      case 'skin_reference_match_preview': {
        const before = capture.catalog;
        if (!exact(payload, ['kind', 'review']) || payload.kind !== command.action || !validPreview(command.payload)
          || !validReview(payload.review, capture.view, command.payload) || !before
          || canonical(payload.review.source) !== canonical(before.source)
          || canonical(payload.review.visual.source_proof) !== canonical(before.source_proof)
          || payload.review.before_bank_sha256 !== before.current.bank_sha256
          || payload.review.before_target_face_refs.length !== before.current.target_face_refs.length
          || !payload.review.before_target_face_refs.every(ref => before.current.target_face_refs.some(prior => sameFace(ref, prior))))
          throw Error('肤色匹配候选与已确认来源、完整旧目标或支持库不一致。');
        if (stillCurrent()) frozen = {review: structuredClone(payload.review), preview: structuredClone(command.payload),
          binding: skinReferenceBinding(capture.view), images: new Set()};
        break;
      }
      case 'skin_reference_match_image': {
        if (!capture.frozen || !validImageReceipt(payload, command)
          || !await reviewImage(payload, capture.frozen.review, command.payload.side as SkinReferenceSide))
          throw Error('肤色匹配审核图字节、尺寸或冻结来源不匹配。');
        if (stillCurrent() && frozen?.review.review_sha256 === capture.frozen.review.review_sha256)
          frozen.images.add(command.payload.side as SkinReferenceSide);
        break;
      }
      case 'skin_reference_match_confirm':
        if (!capture.frozen || !validConfirmation(capture.frozen.review, result))
          throw Error('肤色匹配写入缺少完整候选、支持库或原生结果证明，只能查询原请求。');
        break;
      case 'skin_reference_match_clear':
        if (!validClear(command, result)) throw Error('肤色匹配清除缺少完整中性结果证明，只能查询原请求。');
        break;
    }
    if (!isSkinReferenceRead(command)) {
      const next = result.doc_state!.people!;
      writeFence = {document: next.binding.document_id, epoch: next.binding.document_epoch,
        revision: next.binding.document_revision, state: next.revision};
      catalog = null; frozen = null;
    }
  }
  function complete(command: PeopleAction) {
    if (isSkinReferenceAction(command.action) && captured?.command.request_id === command.request_id) captured = null;
  }
  return {prepare, validate, complete, update, needsRefresh};
}
