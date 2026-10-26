// SPDX-License-Identifier: GPL-3.0-or-later
import {useLayoutEffect, useMemo} from 'react';
import {peopleContext, type PeopleAction, type PeopleResult, type PeopleView} from '../people/model';
import type {PeopleOwner} from '../people/usePeopleWorkflow';
import {HAIR_SMOOTHING_OPERATION, canonical, finite, keys, object, validReview,
  type HairSmoothingReview} from './review';
import {confirmation, inspectionAck, isHairSmoothingAction, hairSmoothingBinding, receiptMatches, requestFits, sameFace, targetReady,
  validCrop, validPreview, validReference, validRect, validWriteResult, verifyImage,
  type HairSmoothingCommand, type HairSmoothingCrop, type HairSmoothingCropRequest, type HairSmoothingPreview,
  type HairSmoothingReceipt, type HairSmoothingReference, type HairSmoothingReport, type HairSmoothingResult, type HairSmoothingSnapshot, type HairSmoothingPort} from './model';

export type HairSmoothingPortInput = {people: PeopleOwner; capability: HairSmoothingSnapshot['capability']; blocked?: boolean};
type PeopleWithHairSmoothing = PeopleView & {hair_smoothing?: HairSmoothingReport | null};
type StateWithHairSmoothing = PeopleOwner['state'] & {lastHairSmoothingResult?: HairSmoothingReceipt | null; hairSmoothingRefreshRequired?: boolean};
type AnyPeopleCommand = PeopleAction | HairSmoothingCommand;
type AnyPeopleResult = PeopleResult | HairSmoothingResult;

export function isHairSmoothingCommand(command: AnyPeopleCommand): boolean {
  return isHairSmoothingAction(command.action) || command.action === 'patch' && Array.isArray(command.payload.patches)
    && command.payload.patches.some(patch => object(patch) && patch.operation_id === HAIR_SMOOTHING_OPERATION);
}
export const isHairSmoothingRead = (command: AnyPeopleCommand): boolean => ['hair_smoothing_reference', 'hair_smoothing_preview', 'hair_smoothing_crop'].includes(command.action);
const neutralPatch = (command: AnyPeopleCommand): boolean => command.action === 'patch'
  && canonical(command.payload) === canonical({patches: [{operation_id: HAIR_SMOOTHING_OPERATION, parameter_path: '/amount', unset: false, value: 0}]});

function exactContext(command: AnyPeopleCommand, view: PeopleView): boolean {
  const context = peopleContext(view), {request_id: _id, action: _action, payload: _payload, ...actual} = command;
  return !!context && canonical(actual) === canonical(context);
}

/** Stable external-store projection, not a second workflow. All pending/result
 * state comes from the existing application-lifetime PeopleOwner. */
export function createHairSmoothingPortAdapter(initial: HairSmoothingPortInput) {
  let input = initial;
  const project = (value: HairSmoothingPortInput): HairSmoothingSnapshot => {
    const state = value.people.state as StateWithHairSmoothing;
    return {value: value.people.value, enabled: value.people.enabled && !value.blocked,
      pending: state.pending, uncertain: state.uncertain, message: state.message,
      refreshRequired: state.hairSmoothingRefreshRequired === true,
      lastResult: state.lastHairSmoothingResult ?? null,
      report: (value.people.value as PeopleWithHairSmoothing | null)?.hair_smoothing ?? null,
      capability: {protocol: value.capability.protocol, available: value.capability.available === true, reason: value.capability.reason}};
  };
  let snapshot = project(initial);
  const listeners = new Set<() => void>();
  const port: HairSmoothingPort = {
    getSnapshot: () => snapshot,
    subscribe: listener => {listeners.add(listener); return () => {listeners.delete(listener);};},
    submitCaptured: async command => {
      const current = input, state = current.people.state as StateWithHairSmoothing, view = current.people.value;
      if (!view || !current.people.enabled || current.blocked || state.pending || state.uncertain || state.hairSmoothingRefreshRequired)
        throw Error('现有人物事务未就绪或结果仍未知；请查询原请求，不要另建请求。');
      if (!requestFits(command)) throw Error('头发柔顺请求超过有界传输预算，未发送。');
      if (command.action === 'select') {
        const row = view.faces.find(face => sameFace(face.face_ref, command.target.face_ref));
        const {request_id: _id, action: _action, payload: _payload, target: _target, ...actual} = command;
        const {document_id, document_epoch, document_revision} = view.binding;
        const expected = {document_id, document_epoch, document_revision, state_revision: view.revision,
          association_revision: view.association_revision};
        if (!keys(command.payload, []) || canonical(actual) !== canonical(expected) || !row
          || command.target.scope !== 'face' || command.target.target_id !== row.face_ref.face_instance_id
          || row.face_ref.asset_sha256 !== view.binding.asset_sha256) throw Error('只能选择当前照片真实保留的精确 FaceRef。');
      } else {
        if (!isHairSmoothingCommand(command) || !targetReady(view) || !exactContext(command, view))
          throw Error('头发柔顺请求不属于当前独立人脸与原文档版本。');
        if (command.action === 'patch' && !neutralPatch(command)) throw Error('非零头发柔顺不能通过普通参数补丁绕过独立审核。');
        if (!['patch', 'hair_smoothing_detach'].includes(command.action) && current.capability.protocol !== 1)
          throw Error('当前引擎没有独立头发柔顺审核协议；仍可用人物参数事务归零。');
        if (!['patch', 'hair_smoothing_detach'].includes(command.action) && !targetReady(view, true))
          throw Error('新头发柔顺审核需要实际启用并完成分析的当前人脸。');
        if (['hair_smoothing_preview', 'hair_smoothing_confirm'].includes(command.action) && current.capability.available !== true)
          throw Error(current.capability.reason || '独立头发柔顺核心不可用；不会使用通用模糊替代。');
      }
      // The parent registers HairSmoothingAction in PeopleAction/native allowlists. This
      // type bridge NEVER bypasses the actual existing workflow's admission.
      await current.people.submitCaptured(structuredClone(command) as PeopleAction);
    },
    check: () => input.people.check(),
    refreshCurrent: () => {
      if (input.people.state.uncertain) return Promise.reject(Error('原请求结果未知，刷新不能代替查询原请求。'));
      return input.people.refreshCurrent();
    },
  };
  return {port, update(next: HairSmoothingPortInput) {
    input = next; const value = project(next);
    if (value.value === snapshot.value && value.enabled === snapshot.enabled && value.pending === snapshot.pending
      && value.uncertain === snapshot.uncertain && value.refreshRequired === snapshot.refreshRequired && value.message === snapshot.message
      && value.lastResult === snapshot.lastResult && value.report === snapshot.report
      && value.capability.protocol === snapshot.capability.protocol && value.capability.available === snapshot.capability.available
      && value.capability.reason === snapshot.capability.reason) return;
    snapshot = value; listeners.forEach(listener => listener());
  }};
}

/** Call alongside usePeopleWorkflow at APP lifetime, never inside a conditional
 * panel. Owner callbacks may change each render; port identity never does. */
export function useHairSmoothingPort(input: HairSmoothingPortInput): HairSmoothingPort {
  const adapter = useMemo(() => createHairSmoothingPortAdapter(input), []);
  useLayoutEffect(() => {adapter.update(input);}, [adapter, input.people, input.capability.protocol,
    input.capability.available, input.capability.reason, input.blocked]);
  return adapter.port;
}

type ReferenceCache = {reference: HairSmoothingReference; binding: string; sourceCrop: HairSmoothingCrop | null};
type Frozen = {preview: HairSmoothingPreview; binding: string; sourceCrop: HairSmoothingCrop; before: HairSmoothingCrop | null; after: HairSmoothingCrop | null};
type Capture = {command: HairSmoothingCommand; before: PeopleView; reference: ReferenceCache | null; frozen: Frozen | null};
type WriteFence = {document: string; epoch: string; documentRevision: number; stateRevision: number};

function echoMatches(command: AnyPeopleCommand, result: AnyPeopleResult): boolean {
  // The exact neutral patch also carries this operation's echo. A generic patch success
  // cannot bypass this operation's captured identity or post-state validation.
  if (!isHairSmoothingCommand(command)) return false;
  const {request_id: _id, ...request} = command;
  const echo = (result as unknown as Record<string, unknown>).hair_smoothing_request;
  return object(echo) && keys(echo, ['action', 'document_id', 'document_epoch', 'document_revision',
    'state_revision', 'association_revision', 'target', 'payload']) && canonical(echo) === canonical(request);
}

export function hairSmoothingReleasedReceipt(command: AnyPeopleCommand, result: AnyPeopleResult): boolean {
  return isHairSmoothingRead(command) && result.success === true && result.outcome_unknown === false && result.payload_released === true
    && result.payload === undefined && result.doc_state === undefined && !Object.hasOwn(result, 'frame')
    && (result as unknown as Record<string, unknown>).frame_emitted !== true && result.batch_id == null
    && result.protocol === 1 && result.request_id === command.request_id && result.action === command.action
    && result.document_id === command.document_id && echoMatches(command, result);
}

export function hairSmoothingReceiptCurrent(command: AnyPeopleCommand, result: AnyPeopleResult, view: PeopleView | null): boolean {
  if (!isHairSmoothingCommand(command) || !echoMatches(command, result)) return false;
  return receiptMatches({command: command as HairSmoothingCommand, result: result as HairSmoothingResult}, command as HairSmoothingCommand, view);
}

function checkedReview(value: unknown, reference: HairSmoothingReference): HairSmoothingReview | null {
  return validReview(value, reference.source) ? structuredClone(value) : null;
}

/** Read-proof cache and post-state guard only. Instantiate once INSIDE the
 * canonical createPeopleWorkflow, beside its other review guards. This object
 * never sends, polls, replays, publishes a graph, owns pending state or history.
 * Keep captured evidence on update/unknown so a closed panel cannot lose it. */
export function createHairSmoothingReviewGuard() {
  let reference: ReferenceCache | null = null, frozen: Frozen | null = null, captured: Capture | null = null;
  let writeFence: WriteFence | null = null;
  function needsRefresh(view: PeopleView | null): boolean {
    return !!writeFence && !!view && view.binding.document_id === writeFence.document && view.binding.document_epoch === writeFence.epoch
      && (view.binding.document_revision < writeFence.documentRevision || view.revision < writeFence.stateRevision);
  }
  function update(view: PeopleView | null) {
    const binding = hairSmoothingBinding(view);
    if (reference?.binding !== binding) reference = null;
    if (frozen?.binding !== binding) frozen = null;
    if (writeFence && view && view.binding.document_id === writeFence.document && view.binding.document_epoch === writeFence.epoch
      && view.binding.document_revision >= writeFence.documentRevision && view.revision >= writeFence.stateRevision) writeFence = null;
    // captured deliberately survives navigation, close and state refresh. Only
    // complete() after validated terminal receipt releases that request proof.
  }
  function prepare(command: AnyPeopleCommand, view: PeopleView | null) {
    if (!isHairSmoothingCommand(command)) return;
    if (!view || needsRefresh(view) || !targetReady(view) || !exactContext(command, view) || !requestFits(command))
      throw Error('头发柔顺请求需要当前独立人脸的精确文档版本；已知写入后必须先刷新，未知写入只能查询。');
    const binding = hairSmoothingBinding(view), payload = command.payload;
    if (command.action === 'patch') {
      if (!neutralPatch(command)) throw Error('普通人物补丁只可独立归零头发柔顺，非零、共享或混合补丁不能绕过本功能审核。');
    } else if (command.action === 'hair_smoothing_reference' || command.action === 'hair_smoothing_detach') {
      if (!keys(payload, [])) throw Error('头发柔顺读取或移除不接受隐藏来源、范围或额外参数。');
      if (command.action === 'hair_smoothing_reference' && !targetReady(view, true)) throw Error('头发柔顺来源读取需要当前真实已分析人脸。');
    } else if (command.action === 'hair_smoothing_preview') {
      if (!keys(payload, ['review', 'amount']) || !finite(payload.amount, Number.MIN_VALUE, 1) || !targetReady(view, true)
        || !reference || reference.binding !== binding || !reference.sourceCrop || !checkedReview(payload.review, reference.reference))
        throw Error('请先读取真实来源及原生像素裁片，再独立确认此人头发笔迹、保护和观察尺度。');
    } else if (command.action === 'hair_smoothing_crop') {
      if (payload.plane === 'source') {
        if (!keys(payload, ['reference_id', 'plane', 'rect']) || !reference || reference.binding !== binding
          || payload.reference_id !== reference.reference.reference_id || !validRect(payload.rect,
            [reference.reference.source.width, reference.reference.source.height])) throw Error('来源裁片必须属于当前参考的精确整数来源矩形。');
      } else if (!keys(payload, ['preview_id', 'plane', 'rect']) || !['before', 'after'].includes(String(payload.plane))
        || !frozen || frozen.binding !== binding || payload.preview_id !== frozen.preview.preview_id
        || !validRect(payload.rect, frozen.preview.before_output_size) || canonical(payload.rect) !== canonical(frozen.sourceCrop.rect)) throw Error('输出裁片必须对应已检查的同一来源矩形；本阶段只允许宿主证明无几何变化的候选。');
    } else if (command.action === 'hair_smoothing_confirm') {
      const inspected = frozen ? inspectionAck(frozen.before, frozen.after, frozen.preview) : null;
      if (frozen && inspected && canonical(inspected.rect) !== canonical(frozen.sourceCrop.rect))
        throw Error('确认裁片不对应本候选已查看的原生来源矩形。');
      if (!frozen || frozen.binding !== binding || !inspected || canonical(payload) !== canonical(confirmation(frozen.preview, inspected)))
        throw Error('头发柔顺确认需要本候选的三张完整图哈希和实际返回的匹配原生输出裁片，不能使用另一操作或旧候选。');
    } else throw Error('未知头发柔顺动作，未发送。');
    captured = {command: structuredClone(command) as HairSmoothingCommand, before: structuredClone(view),
      reference: reference ? structuredClone(reference) : null, frozen: frozen ? structuredClone(frozen) : null};
    if (command.action === 'hair_smoothing_reference') {reference = null; frozen = null;}
    if (command.action === 'hair_smoothing_preview') frozen = null;
    if (command.action === 'hair_smoothing_crop' && payload.plane === 'source') {
      if (reference) reference.sourceCrop = null;
      frozen = null;
    } else if (command.action === 'hair_smoothing_crop' && frozen) {
      const old = frozen.before?.rect ?? frozen.after?.rect;
      if (old && canonical(old) !== canonical(payload.rect)) {frozen.before = null; frozen.after = null;}
      if (payload.plane === 'before') frozen.before = null; else frozen.after = null;
    }
  }
  async function validate(command: AnyPeopleCommand, result: AnyPeopleResult, current: () => PeopleView | null): Promise<void> {
    if (!isHairSmoothingCommand(command)) return;
    const capture = captured;
    if (!capture || canonical(capture.command) !== canonical(command) || !echoMatches(command, result)
      || result.protocol !== 1 || typeof result.success !== 'boolean' || result.outcome_unknown !== false
      || result.request_id !== command.request_id || result.action !== command.action || result.document_id !== command.document_id
      || result.batch_id != null || (isHairSmoothingRead(command) || !result.success)
        && (result.doc_state !== undefined || Object.hasOwn(result, 'frame')
          || (result as unknown as Record<string, unknown>).frame_emitted === true) || !result.success && result.payload !== undefined)
      throw Error('头发柔顺回执缺少原请求精确身份或夹带未授权写入；保留原请求查询，不重发。');
    const released = hairSmoothingReleasedReceipt(command, result);
    if (result.payload_released !== undefined && result.payload_released !== false && !released)
      throw Error('只有已确认结束的头发柔顺只读图像可释放；写入回执必须保留完整证明。');
    if (!result.success) return;
    if (released) {reference = null; frozen = null; return;}
    const payload = result.payload, binding = hairSmoothingBinding(capture.before);
    const stillCurrent = () => captured === capture && hairSmoothingReceiptCurrent(command, result, current()) && hairSmoothingBinding(current()) === binding;
    switch (command.action) {
      case 'hair_smoothing_reference':
        if (!validReference(payload, capture.before) || !await verifyImage(payload.source_image)) throw Error('头发柔顺来源、人脸、头发归属证明或完整来源图哈希不匹配。');
        if (stillCurrent()) reference = {reference: structuredClone(payload), binding, sourceCrop: null};
        break;
      case 'hair_smoothing_preview': {
        const review = capture.reference ? checkedReview(command.payload.review, capture.reference.reference) : null;
        if (!capture.reference || !capture.reference.sourceCrop || !review || !finite(command.payload.amount, Number.MIN_VALUE, 1)
          || !validPreview(payload, capture.reference.reference, review, command.payload.amount)
          || !await verifyImage(payload.before) || !await verifyImage(payload.after) || !await verifyImage(payload.support))
          throw Error('头发柔顺私有候选没有精确来源、修补、独立审核或三张已校验完整混合图。');
        if (stillCurrent()) frozen = {preview: structuredClone(payload), binding,
          sourceCrop: structuredClone(capture.reference.sourceCrop), before: null, after: null};
        break;
      }
      case 'hair_smoothing_crop': {
        const request = command.payload as HairSmoothingCropRequest;
        const owner = request.plane === 'source' ? capture.reference?.reference : capture.frozen?.preview;
        if (!owner || !validCrop(payload, request, owner) || !await verifyImage(payload.image))
          throw Error('头发柔顺原生像素裁片与冻结来源、修补、候选、坐标或哈希不一致。');
        if (stillCurrent()) {
          if (request.plane === 'source' && reference && reference.reference.reference_id === payload.reference_id) reference.sourceCrop = structuredClone(payload);
          else if (payload.plane !== 'source' && frozen && frozen.preview.preview_id === payload.preview_id) {
            const old = frozen.before?.rect ?? frozen.after?.rect;
            if (old && canonical(old) !== canonical(payload.rect)) {frozen.before = null; frozen.after = null;}
            if (payload.plane === 'before') frozen.before = structuredClone(payload);
            else if (payload.plane === 'after') frozen.after = structuredClone(payload);
          }
        }
        break;
      }
      case 'hair_smoothing_confirm':
      case 'hair_smoothing_detach':
      case 'patch': {
        const inspected = capture.frozen ? inspectionAck(capture.frozen.before, capture.frozen.after, capture.frozen.preview) : null;
        if (!validWriteResult(command as HairSmoothingCommand, result as HairSmoothingResult, capture.before, capture.frozen?.preview, inspected ?? undefined))
          throw Error('头发柔顺写入缺少精确候选与权威独立强度/范围后态，或改动了其他效果；保留原请求查询。');
        const next = result.doc_state!.people!;
        writeFence = {document: next.binding.document_id, epoch: next.binding.document_epoch,
          documentRevision: next.binding.document_revision, stateRevision: next.revision};
        reference = null; frozen = null;
        break;
      }
    }
  }
  function complete(command: AnyPeopleCommand) {
    if (isHairSmoothingCommand(command) && captured?.command.request_id === command.request_id) captured = null;
  }
  // Called only by the canonical workflow after native replacement authority.
  function retire() { reference = null; frozen = null; captured = null; writeFence = null; }
  return {prepare, validate, complete, update, needsRefresh, retire};
}
