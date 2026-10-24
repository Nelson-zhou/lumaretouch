// SPDX-License-Identifier: GPL-3.0-or-later
import {echoMatches as sculptEchoMatches,referenceReceiptValid as sculptReferenceReceiptValid,reviewReceiptValid as sculptReviewReceiptValid,releasedReferenceReceiptValid as sculptReleasedReferenceValid} from '../facialSculpt/model';
import {supportAliasWorkspace,type SupportAliasWorkspaceReplacement} from '../faceDecoration/supportAliasHistoryRegistry';
import {createDecorationSupportQueue} from './decorationSupportQueue';
import {isSupportAliasAction,supportAliasReceiptCurrent,type SupportAliasReceipt} from '../faceDecoration/supportAliasModel';
import {echoMatches as decorationEchoMatches, referenceReceiptValid as decorationReferenceReceiptValid, reviewReceiptValid as decorationReviewReceiptValid, releasedReferenceReceiptValid as decorationReleasedReferenceValid} from '../faceDecoration/model';
import {isDecorationAliasAction,validAliasReview,validAliasConfirmation,aliasAck,aliasEchoMatches,aliasReceiptCurrent,verifyDecorationAliasReview,aliasHistoryDigest,type DecorationAliasReview,type DecorationAliasReceipt} from '../faceDecoration/aliasModel';
import {canonical as decorationCanonical} from '../faceDecoration/model';
import {registerDecorationMultiHistory} from '../faceDecoration/multiHistory';
import {bindingKey, type ParameterPatch, type PeopleAction, type PeopleMailbox, type PeopleView} from './model';
import {faceStyleAck, faceStyleEchoMatches, faceStyleReceiptCurrent, object, sameFaceStyleAck,
  validFaceStyleConfirmation, validFaceStyleRecipe, validFaceStyleReview,
  type FaceStyleAliasCommit, type FaceStyleReceipt, type FaceStyleReviewV2} from '../faceStyle/model';
import {skinBodyActionFamily, skinBodyFamilyMatches, skinBodyReceiptCurrent, type SkinBodyResult} from '../skinColour/bodyReviewModel';

import {ack as eyeBagAck, echoMatches as eyeBagEchoMatches, isEyeBagAction, receiptCurrent as eyeBagReceiptCurrent, validCandidate as validEyeBagCandidate, validConfirmation as validEyeBagConfirmation, validReview as validEyeBagReview, type EyeBagReview, type EyeBagReceipt, type EyeBagAliasCommit} from '../eyeBagPreserve/model';
import {validDraft, type EyeBagDraft} from '../eyeBagPreserve/draft';
import {eyeBagBinding} from '../eyeBagPreserve/model';
import {canonical as eyeBagCanonical} from '../eyeBagPreserve/support';

type DecorationAliasCommit = {batchId:string;documentEpoch:string;review:DecorationAliasReview;reviewSha256:string};
type View = {lastDecorationSupportAliasResult:SupportAliasReceipt|null;lastDecorationAliasResult:DecorationAliasReceipt|null;lastDecorationAliasCommit:DecorationAliasCommit|null;facialSculptReleasedRequestId: string | null;faceDecorationReleasedRequestId: string | null; eyeBagCancel: 'none' | 'requested' | 'stopped' | 'completed' | 'released'; pending: boolean; pendingAction: PeopleAction['action'] | null; uncertain: boolean; message: string;
  lastEyeBagResult: EyeBagReceipt | null; lastEyeBagAliasCommit: EyeBagAliasCommit | null; lastBodyResult: SkinBodyResult | null; lastFaceStyleResult: FaceStyleReceipt | null; lastAliasCommit: FaceStyleAliasCommit | null};
type Ports = {
  send: (command: PeopleAction) => Promise<unknown>;
  read: (requestId: string) => Promise<PeopleMailbox>;
  refresh: () => Promise<void>;
  cancelEyeBagRead?: (requestId: string) => Promise<unknown>;
  recoverEyeBagRead?: (requestId: string) => Promise<unknown>;
};
/** One in-flight receipt and latest scalar intentions, never a second people graph.
 * Body results retain their exact action and family-tagged payload; sharing this
 * mailbox never promotes colour review authority into skin-finish authority. */
export function createPeopleWorkflow(ports: Ports) {
  const decorationSupport=createDecorationSupportQueue();
  let current: PeopleView | null = null, enabled = false;
  let pending: PeopleAction | null = null, checking: Promise<void> | null = null;
  let checkingCommand: PeopleAction | null = null;
  let aliasReview: FaceStyleReviewV2 | null = null, pendingAliasReview: FaceStyleReviewV2 | null = null;
  let eyeBagReview: EyeBagReview | null = null, pendingEyeBagReview: EyeBagReview | null = null;
  let decorationAliasReview:DecorationAliasReview|null=null,pendingDecorationAliasReview:DecorationAliasReview|null=null;
  let pendingPreviewView: PeopleView | null = null;
  let eyeDraft: {binding: string; value: EyeBagDraft} | null = null;
  let cancelIntent: PeopleAction | null = null;
  const eyeRead = (command: PeopleAction) => isEyeBagAction(command.action) && command.action !== 'eye_bag_confirm';
  let queued: {key: string; patches: Map<string, ParameterPatch>} | null = null;
  let waitFor: {key: string; revision: number; documentRevision: number} | null = null;
  let view: View = {lastDecorationSupportAliasResult:null,lastDecorationAliasResult:null,lastDecorationAliasCommit:null,facialSculptReleasedRequestId: null,faceDecorationReleasedRequestId: null, eyeBagCancel: 'none', pending: false, pendingAction: null, uncertain: false, message: '', lastEyeBagResult: null, lastEyeBagAliasCommit: null, lastBodyResult: null, lastFaceStyleResult: null, lastAliasCommit: null};
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
        if (pending !== command) return;
        if (reply.request_id !== command.request_id) throw Error('人物修改回执身份不匹配；请查询原请求。');
        if (reply.phase === 'done') {
          const result = reply.result;
          if (!result || result.request_id !== command.request_id || result.action !== command.action
            || result.document_id !== command.document_id || result.outcome_unknown) {
            throw Error(result?.error ?? '人物修改结果未确认；未自动重发。');
          }
          await decorationSupport.validate(command,result,()=>current);
          const decorationAlias=isDecorationAliasAction(command.action);
          if(decorationAlias&&(!aliasEchoMatches(command,result)||result.protocol!==1||typeof result.success!=='boolean'
            ||typeof result.outcome_unknown!=='boolean'||!result.success&&result.batch_id!=null))
            throw Error('共享来源装饰回执缺少原请求的精确身份，请查询原请求，未重发。');
          if(decorationAlias&&command.action!=='face_decoration_alias_confirm'&&(result.batch_id!=null||command.action==='face_decoration_alias_image'&&result.doc_state!==undefined))
            throw Error('共享来源装饰只读审核不能发布文档或批次。');
          if(result.success&&command.action==='face_decoration_alias_preview'){
            decorationAliasReview=null;
            if(!object(result.payload)||result.payload.kind!=='face_decoration_alias_preview'
              ||!validAliasReview(result.payload.review,pendingPreviewView,command.payload.recipe)
              ||!result.doc_state?.people||decorationCanonical(result.doc_state.people.face_decoration?.alias_review)!==decorationCanonical(result.payload.review)
              ||decorationCanonical(result.doc_state.people.binding)!==decorationCanonical(pendingPreviewView?.binding)
              ||decorationCanonical(result.doc_state.people.editing_target)!==decorationCanonical(pendingPreviewView?.editing_target)
              ||result.doc_state.people.binding.document_revision!==command.document_revision
              ||result.doc_state.people.revision!==pendingPreviewView?.revision
              ||result.doc_state.people.association_revision!==pendingPreviewView?.association_revision
              ||!await verifyDecorationAliasReview(result.payload.review))
              throw Error('共享来源装饰完整审核与实际来源、配方或可见范围不符，请查询原请求。');
            if(aliasReceiptCurrent(command,result,current)&&validAliasReview(result.payload.review,current,command.payload.recipe))
              decorationAliasReview=structuredClone(result.payload.review);
          }
          let decorationAliasCommit:DecorationAliasCommit|null=null;
          if(result.success&&command.action==='face_decoration_alias_confirm'){
            if(!pendingDecorationAliasReview||!validAliasConfirmation(pendingDecorationAliasReview,result))
              throw Error('共享来源装饰确认缺少完整成员、候选图和批次证明，请查询原请求。');
            const historyDigest=await aliasHistoryDigest(pendingDecorationAliasReview);
            if(!object(result.payload)||result.payload.history_review_sha256!==historyDigest
              ||!registerDecorationMultiHistory(command.document_epoch,result.batch_id!,'face_decoration_alias_review',
                {version:1,review_sha256:historyDigest,member_count:pendingDecorationAliasReview.members.length}))
              throw Error('共享来源装饰历史身份不匹配，请查询原请求，不要重复应用。');
            decorationAliasCommit={batchId:result.batch_id!,documentEpoch:command.document_epoch,
              review:structuredClone(pendingDecorationAliasReview),reviewSha256:historyDigest};
          }
          let sculptReleased=false;
          if(command.action==='facial_sculpt_reference'||command.action==='facial_sculpt_review'){
            if(!sculptEchoMatches(command,result)||result.batch_id!=null)
              throw Error('面部立体回执与原请求不匹配，请查询原请求，不要重发。');
            const released=sculptReleased=sculptReleasedReferenceValid(command,result);
            if(result.payload_released!==undefined&&result.payload_released!==false&&!released)
              throw Error('面部立体只有已确认的只读参考可以释放图像。');
            if(command.action==='facial_sculpt_reference'&&result.success&&!released&&!sculptReferenceReceiptValid(command,result))
              throw Error('面部立体参考缺少当前来源与人物证明。');
            if(command.action==='facial_sculpt_review'&&result.success&&!sculptReviewReceiptValid(command,result))
              throw Error('面部立体审核缺少已提交的源图范围证明。');
          }
          const decoration = command.action === 'face_decoration_reference' || command.action === 'face_decoration_review';
          if (decoration && (!decorationEchoMatches(command, result) || result.batch_id != null))
            throw Error('脸部装饰回执与原请求不匹配，请查询原请求，不要重发。');
          const decorationReleased = decorationReleasedReferenceValid(command, result);
          if (decoration && result.payload_released !== undefined && result.payload_released !== false && !decorationReleased)
            throw Error('只有已确认结束的脸部装饰只读参考可释放图像；原请求仍需查询。');
          if (command.action === 'face_decoration_reference' && result.success && !decorationReleased && !decorationReferenceReceiptValid(command, result))
            throw Error('脸部装饰参考图缺少匹配的来源、人物或图像证明，请查询原请求。');
          if (command.action === 'face_decoration_review' && result.success && !decorationReviewReceiptValid(command, result))
            throw Error('脸部装饰审核缺少匹配的来源证明或已提交范围，请查询原请求。');
          const faceStyle = command.action.startsWith('face_style_');
          const eyeBag = isEyeBagAction(command.action);
          if (eyeBag && !eyeBagEchoMatches(command, result)) throw Error('卧蚕保护回执与原请求不匹配，请查询原请求，未重发。');
          if (Object.hasOwn(result, 'eye_bag_cancelled') && result.eye_bag_cancelled !== true)
            throw Error('取消标记无效，只能查询原请求。');
          const cancelled = result.eye_bag_cancelled === true;
          if (cancelled && (!eyeRead(command) || result.success || result.outcome_unknown || result.doc_state !== undefined || result.payload !== undefined))
            throw Error('取消回执不能代表已应用或结果未知的修改，只能查询原请求。');
          let discardedRead = eyeRead(command) && (cancelIntent === command || cancelled);
          if (discardedRead) eyeBagReview = null;
          if (!discardedRead && result.success && command.action === 'eye_bag_preview') {
            eyeBagReview = null;
            if (!validEyeBagCandidate(command.payload) || !object(result.payload) || result.payload.kind !== 'eye_bag_preview'
              || !validEyeBagReview(result.payload.review, pendingPreviewView, command.payload))
              throw Error('卧蚕保护预览缺少匹配的来源、完整图像或配方凭据，请查询原请求。');
            if (eyeBagReceiptCurrent(command, result, current) && validEyeBagReview(result.payload.review, current, command.payload))
              eyeBagReview = structuredClone(result.payload.review);
          }
          let eyeBagAliasCommit: EyeBagAliasCommit | null = null;
          if (pendingEyeBagReview?.version === 2 && (result.protocol !== 1 || typeof result.success !== 'boolean'
            || typeof result.outcome_unknown !== 'boolean' || !result.success && result.batch_id != null))
            throw Error('共享来源祛眼袋失败回执不能声明已发布批次，只能查询原请求。');
          if (result.success && command.action === 'eye_bag_confirm'
            && (!pendingEyeBagReview || !validEyeBagConfirmation(pendingEyeBagReview, result)))
            throw Error('卧蚕保护确认缺少完整匹配证明，请查询原请求，不要重发。');
          if (result.success && command.action === 'eye_bag_confirm' && pendingEyeBagReview?.version === 2)
            eyeBagAliasCommit = {batchId: result.batch_id!, documentEpoch: command.document_epoch, requestId: command.request_id,
              review: structuredClone(pendingEyeBagReview), command: structuredClone(command), result: structuredClone(result)};
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
          const faceStyleRead = isSupportAliasAction(command.action)&&command.action!=='face_decoration_support_alias_confirm' || decorationAlias && command.action !== 'face_decoration_alias_confirm' || faceStyle && command.action !== 'face_style_confirm' || eyeBag && command.action !== 'eye_bag_confirm';
          if (result.success && (faceStyleRead || decorationReleased || sculptReleased)) {
            // Read-only face-style receipts must not manufacture or publish a document mutation.
            // A stale response is harmless and discarded below, never applied to the current face.
            if (eyeBag && (result.doc_state !== undefined || result.batch_id != null)) throw Error('卧蚕只读审核不能发布修改后的文档状态或批次。');
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
          try {await bounded(ports.refresh(), 10000);} catch {refreshError = decorationReleased || sculptReleased ? '原只读参考请求已结束，但照片状态刷新失败。请刷新后重新读取原图。' : '修改结果已确认，但照片状态刷新失败。请刷新查看，勿重复提交。';}
          if (pending !== command) return;
          discardedRead = discardedRead || eyeRead(command) && cancelIntent === command;
          if (discardedRead) eyeBagReview = null;
          decorationSupport.complete(command);
          pending = null;
          pendingAliasReview = null;
          pendingEyeBagReview = null;
          pendingDecorationAliasReview=null;
          if(decorationAliasCommit)decorationAliasReview=null;
          if (command.action === 'eye_bag_confirm') eyeBagReview = null;
          pendingPreviewView = null;
          cancelIntent = null;
          if (aliasCommit) aliasReview = null;
          const bodyFamily = skinBodyActionFamily(command.action);
          const bodyPayloadInvalid = !!bodyFamily && !result.payload_released && !skinBodyFamilyMatches(result.payload, bodyFamily);
          publish({lastDecorationSupportAliasResult:supportAliasReceiptCurrent(command,result,current)?{command,result}:null,
            lastDecorationAliasResult:aliasReceiptCurrent(command,result,current)?{command,result}:null,
            ...(decorationAliasCommit?{lastDecorationAliasCommit:decorationAliasCommit}:{}),facialSculptReleasedRequestId: sculptReleased ? command.request_id : null,faceDecorationReleasedRequestId: decorationReleased ? command.request_id : null, eyeBagCancel: discardedRead ? (cancelled ? 'stopped' : 'completed') : 'none', pending: !!queued, pendingAction: queued ? 'patch' : null, uncertain: false,
            lastEyeBagResult: !discardedRead && eyeBagReceiptCurrent(command, result, current) ? {command, result} : null,
            lastFaceStyleResult: faceStyleReceiptCurrent(command, result, current) ? {command, result} : null,
            ...(aliasCommit ? {lastAliasCommit: aliasCommit} : {}),
            ...(eyeBagAliasCommit ? {lastEyeBagAliasCommit: eyeBagAliasCommit} : {}),
            lastBodyResult: skinBodyReceiptCurrent(command, result, current)
              ? {command, result} : null,
            message: sculptReleased ? refreshError || (owns(command) ? '原只读面部立体参考已释放，请重新读取当前人物原图；未提交修改。' : '原照片只读参考已结束，过期图像未套用到当前照片。') : decorationReleased ? refreshError || (owns(command) ? '原只读参考图缓存已释放，请重新读取当前人物原图；未提交装饰修改。' : '原照片的只读参考请求已结束，过期图像已释放；未套用到当前照片。') : discardedRead ? (cancelled ? '引擎已确认只读审核停止；草稿保留，未应用任何候选。' : '原只读请求已结束；迟到结果已丢弃，不表示解码曾被中断。草稿保留。') : !result.success ? (result.error ?? '人物修改被拒绝，未重试。')
              : bodyPayloadInvalid ? '请求结果已收到，但身体皮肤审核回执的功能身份不匹配。请重新读取来源参考；已发送的修改不会重发。'
              : refreshError || (owns(command) ? (command.action === 'eye_bag_confirm' ? eyeBagAliasCommit ? '引擎已确认全部共享来源成员；通过受保护批次历史撤销或重做。' : '引擎已确认应用卧蚕保护候选；通过现有照片历史撤销或重做。' : '') : '原照片请求已确认，未将编辑范围或参数套用到当前照片。')});
          if (!result.success && !discardedRead) throw new ConfirmedFailure(result.error ?? '人物修改被拒绝。');
          return;
        }
        if (reply.phase !== 'pending') throw Error(reply.error ?? '原请求结果无法查询；未自动重发。');
        if (Date.now() >= deadline) throw Error('人物修改仍待确认，请查询原请求。');
        await pause(100);
      }
    } catch (error) {
      if (pending === command && !(error instanceof ConfirmedFailure)) publish({pending: true, uncertain: true, message: String(error)});
      throw error;
    }
  }
  function check(): Promise<void> {
    if (!pending) return Promise.resolve();
    if (!checking || checkingCommand !== pending) {
      checkingCommand = pending;
      const job = poll().finally(() => {
        if (checking === job) {checking = null; checkingCommand = null; flush();}
      });
      checking = job;
    }
    return checking;
  }
  async function submit(command: PeopleAction): Promise<void> {
    if (pending || queued) throw Error('上一项人物修改尚未确认，请先查询结果。');
    if (!enabled || !matches(command)) throw Error('照片或人物状态已变化，请等待刷新后再修改。');
    decorationSupport.prepare(command,current);
    pendingDecorationAliasReview=null;
    if(command.action==='face_decoration_alias_confirm'){
      if(!decorationAliasReview||!validAliasReview(decorationAliasReview,current,decorationAliasReview.recipe)
        ||command.payload.token!==decorationAliasReview.token||decorationCanonical(command.payload.ack)!==decorationCanonical(aliasAck(decorationAliasReview)))
        throw Error('共享来源装饰审核已失效，请重新查看每张照片，未提交修改。');
      pendingDecorationAliasReview=structuredClone(decorationAliasReview);
    }
    if(command.action==='face_decoration_alias_preview')decorationAliasReview=null;
    let captured: FaceStyleReviewV2 | null = null;
    if (command.action === 'face_style_confirm' && object(command.payload.ack) && Object.hasOwn(command.payload.ack, 'members')) {
      if (!aliasReview || !validFaceStyleReview(aliasReview, current, aliasReview.recipe)
        || command.payload.token !== aliasReview.token || !sameFaceStyleAck(command.payload.ack, faceStyleAck(aliasReview)))
        throw Error('完整共享来源审核已失效；请重新逐张预览，不会提交部分成员。');
      captured = structuredClone(aliasReview);
    }
    pendingEyeBagReview = null;
    if (command.action === 'eye_bag_confirm') {
      if (!eyeBagReview || command.payload.token !== eyeBagReview.token || eyeBagCanonical(command.payload.ack) !== eyeBagCanonical(eyeBagAck(eyeBagReview))
        || !current || eyeBagReview.owner.document.revision !== current.binding.document_revision
        || eyeBagReview.owner.state_revision !== current.revision || eyeBagReview.owner.association_revision !== current.association_revision
        || eyeBagReview.owner.document.document_id !== current.binding.document_id || eyeBagReview.owner.document.epoch !== current.binding.document_epoch
        || eyeBagCanonical(eyeBagReview.face_ref) !== eyeBagCanonical(command.target.face_ref))
        throw Error('卧蚕保护完整审核已失效，请重新预览，未提交修改。');
      pendingEyeBagReview = structuredClone(eyeBagReview);
    }
    if (command.action === 'eye_bag_preview') eyeBagReview = null;
    pendingAliasReview = captured;
    pendingPreviewView = (command.action === 'face_decoration_alias_preview' || command.action === 'face_style_preview' || command.action === 'eye_bag_preview') ? structuredClone(current) : null;
    if (command.action === 'face_style_preview') aliasReview = null;
    pending = command;
    decorationSupport.sent(command);
    cancelIntent = null;
    publish({lastDecorationSupportAliasResult:null,lastDecorationAliasResult:null,facialSculptReleasedRequestId: null,faceDecorationReleasedRequestId: null, eyeBagCancel: 'none', pending: true, pendingAction: command.action, uncertain: false, lastEyeBagResult: null, lastBodyResult: null, lastFaceStyleResult: null, message: '正在提交人物修改，等待引擎确认。'});
    try {await bounded(ports.send(command), 10000);}
    catch (error) {if (pending === command) publish({uncertain: true, message: `${String(error)}。正在查询原请求，不重发修改。`});}
    if (pending === command) await check();
  }
  async function cancelEyeBagRead(): Promise<void> {
    const command = pending;
    if (!command || !eyeRead(command) || !ports.cancelEyeBagRead)
      throw Error('只有当前只读卧蚕审核可取消；已发送确认必须查询原请求。');
    if (cancelIntent === command) return;
    cancelIntent = command; eyeBagReview = null;
    publish({eyeBagCancel: 'requested', lastEyeBagResult: null,
      message: '已请求停止只读审核，尚未确认停止；正在等待解码或求解安全返回。草稿保留。'});
    try {
      const reply = await bounded(ports.cancelEyeBagRead(command.request_id), 10000);
      if (!object(reply) || Object.keys(reply).sort().join('|') !== 'cancel_requested|eye_bag_request|request_id|stopped'
        || reply.request_id !== command.request_id || typeof reply.cancel_requested !== 'boolean' || reply.stopped !== false
        || !eyeBagEchoMatches(command, reply as unknown as import('./model').PeopleResult))
        throw Error('取消请求回执不匹配');
    }
    catch (error) {
      if (pending === command) publish({message: `取消请求结果未确认：${String(error)}。继续查询原请求，不重发修改。`});
    }
    // Never release pending merely because cancellation was requested or its send failed.
    // The original correlated receipt remains the only terminal authority.
    if (pending === command) await check();
  }
  async function recoverEyeBagRead(): Promise<void> {
    const command = pending;
    if (!command || !eyeRead(command) || !ports.recoverEyeBagRead)
      throw Error('只有已保留身份的只读审核可恢复；确认修改必须查询原请求。');
    const reply = await bounded(ports.recoverEyeBagRead(command.request_id), 10000);
    if (!object(reply) || Object.keys(reply).sort().join('|') !== 'eye_bag_request|read_only|reason|released|request_id|stopped'
      || reply.request_id !== command.request_id || reply.read_only !== true || reply.released !== true
      || !['terminal_read', 'engine_ended'].includes(String(reply.reason)) || typeof reply.stopped !== 'boolean'
      || !eyeBagEchoMatches(command, reply as unknown as import('./model').PeopleResult))
      throw Error('原只读请求的恢复证明不匹配，保留原请求等待查询。');
    if (pending !== command) return;
    // Native proof is restricted to a known read; it never proves a write failed.
    pending = null; queued = null; waitFor = null; cancelIntent = null;
    pendingPreviewView = null; eyeBagReview = null;
    publish({pending: false, pendingAction: null, uncertain: false, eyeBagCancel: 'released', lastEyeBagResult: null,
      message: reply.reason === 'terminal_read' ? '原只读请求已有终态，迟到图像已释放；请重新读取来源，草稿保留。'
        : reply.stopped ? '原引擎已结束，已释放其只读审核等待；请重新读取来源，草稿保留。'
        : '原引擎身份已失效，已释放旧只读审核等待；不代表旧工作曾被中断，请重新读取来源。'});
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
      decorationSupport.update(value);
      if(view.lastDecorationSupportAliasResult&&!supportAliasReceiptCurrent(view.lastDecorationSupportAliasResult.command,view.lastDecorationSupportAliasResult.result,value))publish({lastDecorationSupportAliasResult:null});
      if (eyeDraft && eyeDraft.binding !== eyeBagBinding(value)) eyeDraft = null;
      if (view.lastEyeBagResult && !eyeBagReceiptCurrent(view.lastEyeBagResult.command, view.lastEyeBagResult.result, value)) publish({lastEyeBagResult: null});
      if (view.lastFaceStyleResult && !faceStyleReceiptCurrent(view.lastFaceStyleResult.command, view.lastFaceStyleResult.result, value)) publish({lastFaceStyleResult: null});
      if(view.lastDecorationAliasResult&&!aliasReceiptCurrent(view.lastDecorationAliasResult.command,view.lastDecorationAliasResult.result,value))publish({lastDecorationAliasResult:null});
      if (view.lastBodyResult && !skinBodyReceiptCurrent(view.lastBodyResult.command, view.lastBodyResult.result, value)) publish({lastBodyResult: null});
      if (changed) {
        decorationAliasReview=null;
        if(view.lastDecorationAliasResult)publish({lastDecorationAliasResult:null});
        eyeBagReview = null;
        if (view.lastEyeBagResult) publish({lastEyeBagResult: null});
        queued = null; waitFor = null;
        if (view.lastBodyResult) publish({lastBodyResult: null});
        if (view.lastFaceStyleResult) publish({lastFaceStyleResult: null});
        if (!pending) publish({pending: false, pendingAction: null, message: '', uncertain: false});
      }
      flush();
    },
    retireDecorationSupportWorkspace(replacement:SupportAliasWorkspaceReplacement){
      const request=pending;
      if(!request||!isSupportAliasAction(request.action)||request.document_epoch!==replacement.previous
        ||replacement.previous===replacement.current||supportAliasWorkspace()!==replacement.current
        ||request.action==='face_decoration_support_alias_confirm'&&!replacement.retiredWrites.some(row=>row.requestId===request.request_id&&row.epoch===request.document_epoch))return;
      pending=null;queued=null;waitFor=null;decorationSupport.retire();
      publish({lastDecorationSupportAliasResult:null,pending:false,pendingAction:null,uncertain:false,
        message:'已核实重新打开后的工作区，旧共享可见范围请求已隔离；这不表示旧请求未写入，请以重新打开的来源和受保护历史为准。'});
    },
    subscribe(listener: () => void) {listeners.add(listener); return () => {listeners.delete(listener);};},
    snapshot: () => view,
    cancelEyeBagRead,
    recoverEyeBagRead,
    eyeBagDraft(binding: string): EyeBagDraft | null {
      return current && eyeDraft?.binding === binding && binding === eyeBagBinding(current) ? structuredClone(eyeDraft.value) : null;
    },
    saveEyeBagDraft(binding: string, value: EyeBagDraft | null) {
      if (!current || binding !== eyeBagBinding(current)) return;
      if (value === null) {eyeDraft = null; return;}
      if (!validDraft(value)) throw Error('卧蚕草稿超出来源笔迹边界');
      eyeDraft = {binding, value: structuredClone(value)};
    },
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
