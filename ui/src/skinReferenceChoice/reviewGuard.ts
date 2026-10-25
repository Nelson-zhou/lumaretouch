// SPDX-License-Identifier: GPL-3.0-or-later
// AUTHORED / UNRUN. Proof capture only; no transport, poller, queue or mutation.
import type {PeopleAction, PeopleResult, PeopleView} from '../people/model';
import {catalogImage as faceCatalogImage, echoMatches as faceEcho,
  skinReferenceBinding} from '../skinReferenceMatch/model';
import {catalogImage as bodyCatalogImage, echoMatches as bodyEcho,
  skinReferenceBodyBinding} from '../skinReferenceBody/model';
import {ACTION, canonical, choiceBinding, commandMatches, parseReport, receiptCurrent, validChoiceCatalog,
  validReceiptEnvelope, type ChoiceCatalog, type ChoiceCommand, type ChoiceContext, type ChoiceFamily} from './model';

type CatalogCapture = {kind: 'catalog'; family: ChoiceFamily; command: PeopleAction; view: PeopleView; generation: number};
type ChoiceCapture = {kind: 'choice'; command: ChoiceCommand; context: ChoiceContext; binding: string; generation: number};
const viewBinding = (view: PeopleView | null) => canonical([skinReferenceBinding(view), skinReferenceBodyBinding(view)]);
const familyOf = (action: string): ChoiceFamily | null => action === 'skin_reference_match_catalog' ? 'face'
  : action === 'skin_reference_body_catalog' ? 'body' : null;
export const isSkinReferenceChoiceRead = (command: Pick<PeopleAction, 'action'>): boolean => command.action === ACTION;

/** Install beside the existing guards in the sole PeopleOwner. Catalog image
 * verification is proof admission; actual decoded/visible presentation remains
 * in the original panel and gates the child component's explicit click handlers. */
export function createSkinReferenceChoiceGuard() {
  const catalogs = new Map<ChoiceFamily, ChoiceContext>();
  let captured: CatalogCapture | ChoiceCapture | null = null;
  let generation = 0;
  function update(view: PeopleView | null) {
    for (const [family, context] of catalogs) if (viewBinding(view) !== viewBinding(context.view)) catalogs.delete(family);
    // Retain captured original identity for uncertain-result queries. Never turn
    // a changed document into permission to submit a replacement request.
  }
  function prepare(command: PeopleAction, view: PeopleView | null) {
    const family = familyOf(command.action);
    if (!family && command.action !== ACTION) return;
    if (!view) throw Error('请先打开当前照片并读取真实来源图。');
    update(view);
    if (captured) throw Error('参考测量原请求尚未结束，只能通过现有人物请求查询结果。');
    if (family) {
      catalogs.delete(family);
      captured = {kind: 'catalog', family, command: structuredClone(command), view: structuredClone(view), generation: ++generation};
      return;
    }
    const requestedFamily = command.payload.family;
    const context = requestedFamily === 'face' || requestedFamily === 'body' ? catalogs.get(requestedFamily) : undefined;
    if (!context || !commandMatches(command, {...context, view}))
      throw Error('请先读取当前匹配面板的完整来源与人物清单，旧目录或另一面板的回执不能用于参考测量。');
    captured = {kind: 'choice', command: structuredClone(command), context: structuredClone(context),
      binding: choiceBinding(context), generation: ++generation};
  }
  async function validate(command: PeopleAction, result: PeopleResult, current: () => PeopleView | null): Promise<void> {
    const family = familyOf(command.action);
    if (!family && command.action !== ACTION) return;
    const capture = captured;
    if (!capture || canonical(capture.command) !== canonical(command)) throw Error('参考测量回执不属于已捕获的原请求。');
    if (capture.kind === 'catalog') {
      // Existing family guard still owns its complete envelope and operation checks.
      const echo = family === 'face' ? faceEcho : bodyEcho;
      if (result.protocol !== 1 || result.request_id !== command.request_id || result.action !== command.action
        || result.document_id !== command.document_id || typeof result.success !== 'boolean' || result.outcome_unknown !== false
        || !echo(command, result) || result.doc_state !== undefined || Object.hasOwn(result, 'frame'))
        throw Error('参考测量不能接受来源目录中的写入或外来回执。');
      if (!result.success || result.payload_released === true) return;
      if (!validChoiceCatalog(result.payload, capture.family, capture.view)) throw Error('参考测量来源目录缺少完整的当前人物与来源身份。');
      const catalog = result.payload;
      const image = capture.family === 'face' ? await faceCatalogImage(catalog as Parameters<typeof faceCatalogImage>[0])
        : await bodyCatalogImage(catalog as Parameters<typeof bodyCatalogImage>[0]);
      if (!image) throw Error('参考测量来源 PNG 字节或尺寸验证失败。');
      if (captured !== capture || capture.generation !== generation || viewBinding(current()) !== viewBinding(capture.view)) return;
      catalogs.set(capture.family, {family: capture.family, view: structuredClone(capture.view), catalog: structuredClone(catalog)});
      return;
    }
    if (!validReceiptEnvelope(capture.command, result)) throw Error('参考测量回执缺少精确原请求，或包含写入、帧、未知状态。');
    if (!result.success) return;
    if (result.payload_released === true) {catalogs.delete(capture.context.family); return;}
    if (!parseReport(result.payload, capture.command, capture.context))
      throw Error('参考测量与原目录、完整候选、实际亮度排序或来源证明不一致。');
    const retained = catalogs.get(capture.context.family), view = current();
    if (captured !== capture || capture.generation !== generation || !retained || !view
      || choiceBinding(retained) !== capture.binding || viewBinding(view) !== viewBinding(capture.context.view)
      || !receiptCurrent(command, result, view)) return;
    // No reference/target/consent value is written here. The owner may expose this
    // validated read receipt only after its own current-request admission.
  }
  function complete(command: PeopleAction) {
    if (captured?.command.request_id === command.request_id && captured.command.action === command.action) captured = null;
  }
  return {prepare, validate, complete, update};
}
