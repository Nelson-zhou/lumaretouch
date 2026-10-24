// SPDX-License-Identifier: GPL-3.0-or-later
import {bindingKey, type ParameterPatch, type PeopleAction, type PeopleMailbox, type PeopleView} from './model';
import {faceStyleAck, faceStyleEchoMatches, faceStyleReceiptCurrent, object, sameFaceStyleAck,
  validFaceStyleConfirmation, validFaceStyleRecipe, validFaceStyleReview,
  type FaceStyleAliasCommit, type FaceStyleReceipt, type FaceStyleReviewV2} from '../faceStyle/model';
import {skinBodyActionFamily, skinBodyFamilyMatches, skinBodyReceiptCurrent, type SkinBodyResult} from '../skinColour/bodyReviewModel';

type View = {pending: boolean; pendingAction: PeopleAction['action'] | null; uncertain: boolean; message: string;
  lastBodyResult: SkinBodyResult | null; lastFaceStyleResult: FaceStyleReceipt | null; lastAliasCommit: FaceStyleAliasCommit | null};
type Ports = {
  send: (command: PeopleAction) => Promise<unknown>;
  read: (requestId: string) => Promise<PeopleMailbox>;
  refresh: () => Promise<void>;
};
/** One in-flight receipt and latest scalar intentions, never a second people graph.
 * Body results retain their exact action and family-tagged payload; sharing this
 * mailbox never promotes colour review authority into skin-finish authority. */
export function createPeopleWorkflow(ports: Ports) {
  let current: PeopleView | null = null, enabled = false;
  let pending: PeopleAction | null = null, checking: Promise<void> | null = null;
  let aliasReview: FaceStyleReviewV2 | null = null, pendingAliasReview: FaceStyleReviewV2 | null = null;
  let pendingPreviewView: PeopleView | null = null;
  let queued: {key: string; patches: Map<string, ParameterPatch>} | null = null;
  let waitFor: {key: string; revision: number; documentRevision: number} | null = null;
  let view: View = {pending: false, pendingAction: null, uncertain: false, message: '', lastBodyResult: null, lastFaceStyleResult: null, lastAliasCommit: null};
  const listeners = new Set<() => void>();
  const publish = (patch: Partial<View>) => {view = {...view, ...patch}; listeners.forEach(listener => listener());};
  const targetKey = (value: PeopleView) => `${bindingKey(value.binding)}:${value.association_revision}:${JSON.stringify(value.editing_target)}`;
  const pause = (ms: number) => new Promise<void>(resolve => setTimeout(resolve, ms));
  const bounded = <T,>(promise: Promise<T>, ms: number): Promise<T> => new Promise((resolve, reject) => {
    const timer = setTimeout(() => reject(Error('等待人物修改结果超时，请查询原请求；未重发修改。')), Math.max(1, ms));
    promise.then(value => {clearTimeout(timer); resolve(value);}, error => {clearTimeout(timer); reject(error);});
  });
  const matches = (command: PeopleAction) => !!current
    && command.document_id === current.binding.document_id
    && command.document_epoch === current.binding.document_epoch
    && command.document_revision === current.binding.document_revision
    && command.state_revision === current.revision
    && command.association_revision === current.association_revision;
  const owns = (command: PeopleAction) => !!current && command.document_id === current.binding.document_id
    && command.document_epoch === current.binding.document_epoch;
  async function poll() {
    const command = pending;
    if (!command) return;
    const deadline = Date.now() + 120000;
    try {
      while (pending === command) {
        const reply = await bounded(ports.read(command.request_id), deadline - Date.now());
        if (reply.request_id !== command.request_id) throw Error('人物修改回执身份不匹配；请查询原请求。');
        if (reply.phase === 'done') {
          const result = reply.result;
          if (!result || result.request_id !== command.request_id || result.action !== command.action
            || result.document_id !== command.document_id || result.outcome_unknown) {
            throw Error(result?.error ?? '人物修改结果未确认；未自动重发。');
          }
          const faceStyle = command.action.startsWith('face_style_');
          if (faceStyle && !faceStyleEchoMatches(command, result)) throw Error('脸型请求回执绑定不匹配，请查询原请求，未重发。');
          let aliasCommit: FaceStyleAliasCommit | null = null;
          if (result.success && command.action === 'face_style_preview') {
            aliasReview = null;
            if (object(result.payload) && object(result.payload.review) && result.payload.review.version === 2) {
              if (result.payload.kind !== 'face_style_preview' || !validFaceStyleRecipe(command.payload)
                || !validFaceStyleReview(result.payload.review, pendingPreviewView, command.payload) || result.payload.review.version !== 2)
                throw Error('共享来源完整审核与原请求不符，请查询原请求。');
              // Navigation during a read does not turn a harmless old-document reply into an
              // uncertain mutation. Validate the captured view, but retain only a still-current draft.
              if (faceStyleReceiptCurrent(command, result, current)
                && validFaceStyleReview(result.payload.review, current, command.payload)) aliasReview = structuredClone(result.payload.review);
            }
          }
          if (pendingAliasReview && (result.protocol !== 1 || typeof result.success !== 'boolean'
            || typeof result.outcome_unknown !== 'boolean' || !result.success && result.batch_id != null))
            throw Error('共享来源失败回执不能同时声明已发布的批次，只能查询原请求。');
          if (result.success && command.action === 'face_style_confirm') {
            if (pendingAliasReview) {
              if (!validFaceStyleConfirmation(pendingAliasReview, result))
                throw Error('共享来源确认缺少完整逐成员版本证明或真实批次身份，只能查询原请求。');
              aliasCommit = {batchId: result.batch_id!, documentEpoch: command.document_epoch, requestId: command.request_id,
                review: structuredClone(pendingAliasReview), command: structuredClone(command), result: structuredClone(result)};
            } else if (object(result.payload) && Object.hasOwn(result.payload, 'alias_members'))
              throw Error('未请求的共享来源确认回执，只能查询原请求。');
          }
          const faceStyleRead = faceStyle && command.action !== 'face_style_confirm';
          if (result.success && faceStyleRead) {
            // Read-only face-style receipts must not manufacture or publish a document mutation.
            // A stale response is harmless and discarded below, never applied to the current face.
            waitFor = null;
          } else if (result.success) {
            const next = result.doc_state?.people;
            if (!next || next.binding.document_id !== command.document_id
              || next.binding.document_epoch !== command.document_epoch
              || (command.target.scope === 'all_people' && next.binding.asset_sha256 !== command.target.target_id)
              || next.binding.document_revision < command.document_revision
              || next.revision < command.state_revision || next.association_revision < command.association_revision) {
              throw Error('人物修改缺少匹配的新文档状态；请查询原请求。');
            }
            waitFor = owns(command) && current && JSON.stringify(current.editing_target) === JSON.stringify(command.target)
              ? {key: targetKey(next), revision: next.revision, documentRevision: next.binding.document_revision} : null;
          } else {queued = null; waitFor = null;}
          // Receipt proves the operation; only the next engine status replaces UI facts.
          let refreshError = '';
          try {await bounded(ports.refresh(), 10000);} catch {refreshError = '修改结果已确认，但照片状态刷新失败。请刷新查看，勿重复提交。';}
          pending = null;
          pendingAliasReview = null;
          pendingPreviewView = null;
          if (aliasCommit) aliasReview = null;
          const bodyFamily = skinBodyActionFamily(command.action);
          const bodyPayloadInvalid = !!bodyFamily && !result.payload_released && !skinBodyFamilyMatches(result.payload, bodyFamily);
          publish({pending: !!queued, pendingAction: queued ? 'patch' : null, uncertain: false,
            lastFaceStyleResult: faceStyleReceiptCurrent(command, result, current) ? {command, result} : null,
            ...(aliasCommit ? {lastAliasCommit: aliasCommit} : {}),
            lastBodyResult: skinBodyReceiptCurrent(command, result, current)
              ? {command, result} : null,
            message: !result.success ? (result.error ?? '人物修改被拒绝，未重试。')
              : bodyPayloadInvalid ? '请求结果已收到，但身体皮肤审核回执的功能身份不匹配。请重新读取来源参考；已发送的修改不会重发。'
              : refreshError || (owns(command) ? '' : '原照片请求已确认，未将编辑范围或参数套用到当前照片。')});
          if (!result.success) throw new ConfirmedFailure(result.error ?? '人物修改被拒绝。');
          return;
        }
        if (reply.phase !== 'pending') throw Error(reply.error ?? '原请求结果无法查询；未自动重发。');
        if (Date.now() >= deadline) throw Error('人物修改仍待确认，请查询原请求。');
        await pause(100);
      }
    } catch (error) {
      if (!(error instanceof ConfirmedFailure)) publish({pending: true, uncertain: true, message: String(error)});
      throw error;
    }
  }
  function check(): Promise<void> {
    if (!checking) checking = poll().finally(() => {checking = null; flush();});
    return checking;
  }
  async function submit(command: PeopleAction): Promise<void> {
    if (pending || queued) throw Error('上一项人物修改尚未确认，请先查询结果。');
    if (!enabled || !matches(command)) throw Error('照片或人物状态已变化，请等待刷新后再修改。');
    let captured: FaceStyleReviewV2 | null = null;
    if (command.action === 'face_style_confirm' && object(command.payload.ack) && Object.hasOwn(command.payload.ack, 'members')) {
      if (!aliasReview || !validFaceStyleReview(aliasReview, current, aliasReview.recipe)
        || command.payload.token !== aliasReview.token || !sameFaceStyleAck(command.payload.ack, faceStyleAck(aliasReview)))
        throw Error('完整共享来源审核已失效；请重新逐张预览，不会提交部分成员。');
      captured = structuredClone(aliasReview);
    }
    pendingAliasReview = captured;
    pendingPreviewView = command.action === 'face_style_preview' ? structuredClone(current) : null;
    if (command.action === 'face_style_preview') aliasReview = null;
    pending = command;
    publish({pending: true, pendingAction: command.action, uncertain: false, lastBodyResult: null, lastFaceStyleResult: null, message: '正在提交人物修改，等待引擎确认。'});
    try {await bounded(ports.send(command), 10000);}
    catch (error) {publish({uncertain: true, message: `${String(error)}。正在查询原请求，不重发修改。`});}
    await check();
  }
  function flush() {
    if (pending || checking || !queued || !current?.editing_target || !enabled || view.uncertain) return;
    const key = targetKey(current);
    if (queued.key !== key) {
      queued = null; waitFor = null;
      publish({pending: false, pendingAction: null, message: '照片或编辑范围已变化，未提交的拖动意图已取消。'});
      return;
    }
    if (waitFor && (waitFor.key !== key || current.revision < waitFor.revision
      || current.binding.document_revision < waitFor.documentRevision)) return;
    const patches = [...queued.patches.values()]; queued = null; waitFor = null;
    const {document_id, document_epoch, document_revision} = current.binding;
    void submit({document_id, document_epoch, document_revision, state_revision: current.revision,
      association_revision: current.association_revision, request_id: crypto.randomUUID(),
      action: 'patch', payload: {patches}, target: current.editing_target}).catch(() => {});
  }
  return {
    update(value: PeopleView | null, canEdit: boolean) {
      const changed = !!current && (!value || targetKey(current) !== targetKey(value));
      current = value; enabled = canEdit;
      if (view.lastFaceStyleResult && !faceStyleReceiptCurrent(view.lastFaceStyleResult.command, view.lastFaceStyleResult.result, value)) publish({lastFaceStyleResult: null});
      if (view.lastBodyResult && !skinBodyReceiptCurrent(view.lastBodyResult.command, view.lastBodyResult.result, value)) publish({lastBodyResult: null});
      if (changed) {
        queued = null; waitFor = null;
        if (view.lastBodyResult) publish({lastBodyResult: null});
        if (view.lastFaceStyleResult) publish({lastFaceStyleResult: null});
        if (!pending) publish({pending: false, pendingAction: null, message: '', uncertain: false});
      }
      flush();
    },
    subscribe(listener: () => void) {listeners.add(listener); return () => {listeners.delete(listener);};},
    snapshot: () => view,
    submit,
    patch(patches: ParameterPatch[]) {
      if (!current?.editing_target || !enabled || view.uncertain) throw Error('请先选择可编辑的人物范围并确认上一请求。');
      if (pending && (pending.action !== 'patch' || !owns(pending)
        || JSON.stringify(pending.target) !== JSON.stringify(current.editing_target))) throw Error('人物范围修改仍在确认，请稍候调整。');
      const key = targetKey(current);
      if (!queued || queued.key !== key) queued = {key, patches: new Map()};
      for (const patch of patches) queued.patches.set(`${patch.operation_id}:${patch.parameter_path}`, patch);
      publish({pending: true, pendingAction: 'patch'});
      flush();
    },
    check,
  };
}
class ConfirmedFailure extends Error {}
