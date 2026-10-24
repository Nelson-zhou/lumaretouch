// SPDX-License-Identifier: GPL-3.0-or-later
import {useLayoutEffect, useRef, useState} from 'react';
import type {PeopleOwner} from '../people/usePeopleWorkflow';
import type {PeopleAction} from '../people/model';
import type {SpillImage} from '../spillRemoval/model';
import {bindingKey, canonical, command, referenceCurrent} from './model';
import {FaceDecorationSupportEditor} from './FaceDecorationSupportEditor';
import {DecorationTransferReview} from './TransferReview';
import {supportAliasAck, supportAliasImage, supportAliasKey, supportAliasReceiptCurrent, validSupportAliasReview, verifySupportAliasReview,
  type SupportAliasDraft, type SupportAliasReview} from './supportAliasModel';
/** Painted source geometry stays a draft until every complete member image is decoded and explicitly acknowledged. */
export function FaceDecorationSupportAliasEditor({people, disabled}: {people: PeopleOwner; disabled: boolean}) {
  const view = people.value, report = view?.face_decoration, binding = bindingKey(view);
  const [reference, setReference] = useState<PeopleAction | null>(null), [review, setReview] = useState<SupportAliasReview | null>(null);
  const [ready, setReady] = useState<Record<string, boolean>>({}), [error, setError] = useState('');
  const mounted = useRef(false), generation = useRef(0), busy = useRef(false), draft = useRef<SupportAliasDraft | null>(null);
  const pendingImage = useRef<{id: string; resolve: (value: SpillImage) => void; reject: (error: Error) => void;
    timer: ReturnType<typeof setTimeout>; review: SupportAliasReview; document: string; side: 'before' | 'after'; live: () => boolean} | null>(null);
  const latest = useRef({view, binding, reference, review, disabled, released: people.state.faceDecorationReleasedRequestId});
  latest.current = {view, binding, reference, review, disabled, released: people.state.faceDecorationReleasedRequestId};
  function rejectImage(reason: string) {
    const pending = pendingImage.current;
    if (pending) {clearTimeout(pending.timer); pendingImage.current = null; pending.reject(Error(reason));}
  }
  function clearDraft() {generation.current++; draft.current = null; setReference(null); setReview(null); setReady({}); setError(''); rejectImage('范围审核已关闭或更换；原请求仍由队列跟踪。');}
  useLayoutEffect(() => {mounted.current = true; return () => {mounted.current = false; generation.current++; draft.current = null; rejectImage('审核界面已关闭；原请求仍由队列跟踪。');};}, []);
  useLayoutEffect(clearDraft, [binding]);
  useLayoutEffect(() => {
    if (reference && people.state.faceDecorationReleasedRequestId === reference.request_id) clearDraft();
  }, [people.state.faceDecorationReleasedRequestId, reference]);
  useLayoutEffect(() => {
    const receipt = people.state.lastDecorationSupportAliasResult;
    if (!receipt || !supportAliasReceiptCurrent(receipt.command, receipt.result, latest.current.view)) return;
    const {command: request, result} = receipt;
    if (request.action === 'face_decoration_support_alias_preview') {
      const payload = result.payload as {kind?: unknown; review?: unknown} | undefined, staged = draft.current;
      if (!staged || !latest.current.reference || payload?.kind !== 'face_decoration_support_alias_preview'
        || canonical(request.payload) !== canonical(staged) || !validSupportAliasReview(payload.review, latest.current.view, staged)) return;
      const candidate = payload.review, sequence = ++generation.current;
      void verifySupportAliasReview(candidate).then(valid => {
        if (!mounted.current || sequence !== generation.current || draft.current !== staged) return;
        if (!valid) {setError('全部成员的范围与图像摘要不一致，不能提交。'); return;}
        setReview(candidate); setReady({});
      }).catch(cause => {if (mounted.current && sequence === generation.current) setError(String(cause));});
    }
    if (request.action === 'face_decoration_support_alias_image') {
      const pending = pendingImage.current;
      if (!pending || pending.id !== request.request_id) return;
      clearTimeout(pending.timer); pendingImage.current = null;
      void supportAliasImage(result.payload, pending.review, pending.document, pending.side).then(image => {
        if (!mounted.current || !pending.live() || latest.current.review !== pending.review) pending.reject(Error('范围图像审核已失效。'));
        else pending.resolve(image);
      }, cause => pending.reject(Error(String(cause))));
    }
  }, [people.state.lastDecorationSupportAliasResult]);
  const canEdit = !disabled && !people.state.pending && !people.state.uncertain && !!view && !report?.support_alias_reason
    && view.editing_target?.scope === 'face' && view.editing_target.target_id === view.selected_face_id;
  const currentReference = !!reference && people.state.faceDecorationReleasedRequestId !== reference.request_id && referenceCurrent(reference, view);
  const selected = view?.faces.find(face => face.face_ref.face_instance_id === view.selected_face_id);
  async function openReference() {
    if (!canEdit || !view || busy.current) return;
    busy.current = true; clearDraft();
    const request = command(view, 'face_decoration_reference', crypto.randomUUID(), {}), sequence = generation.current;
    setReference(request);
    try {await people.submitCaptured(request);}
    catch (cause) {if (mounted.current && sequence === generation.current) setError(String(cause));}
    finally {busy.current = false;}
  }
  function readImage(member: SupportAliasReview['members'][number], side: 'before' | 'after', live: () => boolean): Promise<SpillImage> {
    const current = latest.current;
    if (!review || !view || current.review !== review || current.binding !== binding || pendingImage.current || current.disabled)
      return Promise.reject(Error('上一图像请求尚未确认或审核已失效，请查询原请求。'));
    const request = command(view, 'face_decoration_support_alias_image', crypto.randomUUID(), {
      token: review.token, document_id: member.visual.document_id, side, sha256: member.visual[side].sha256, review_sha256: review.review_sha256,
    });
    return new Promise((resolve, reject) => {
      const timer = setTimeout(() => {
        if (pendingImage.current?.id === request.request_id) {pendingImage.current = null; reject(Error('图像读取等待超时；请先查询原请求，不能重发未知请求。'));}
      }, 130000);
      pendingImage.current = {id: request.request_id, resolve, reject, timer, review, document: member.visual.document_id, side, live};
      void people.submitCaptured(request).catch(cause => {
        if (pendingImage.current?.id === request.request_id) {clearTimeout(timer); pendingImage.current = null; reject(Error(String(cause)));}
      });
    });
  }
  const allReady = !!review && review.members.every(member => ready[supportAliasKey(review, member.visual)] === true);
  async function confirm() {
    const staged = draft.current;
    if (!canEdit || !allReady || !review || !view || busy.current || !staged || !validSupportAliasReview(review, view, staged)) return;
    busy.current = true; setError('');
    try {
      if (!await verifySupportAliasReview(review) || latest.current.disabled || latest.current.review !== review || latest.current.binding !== binding || draft.current !== staged)
        throw Error('范围审核已变化，请重新绘制并预览全部成员。');
      await people.submitCaptured(command(view, 'face_decoration_support_alias_confirm', crypto.randomUUID(), {token: review.token, ack: supportAliasAck(review)}));
    } catch (cause) {if (mounted.current) setError(String(cause));}
    finally {busy.current = false;}
  }
  return <section aria-label="共享来源脸部装饰可见皮肤事务">
    <h4>共享来源：独立绘制可见皮肤范围</h4>
    <p>在真实未修饰来源的完整坐标画布绘制，只暂存当前人物的范围。不改图案、程度、其他人物的范围或效果恢复笔迹。初次中性范围允许没有旧支持；已有活动装饰的旧支持失效时仍拒绝，不能用新绘制绕过。</p>
    <button type="button" disabled={!canEdit} onClick={() => void openReference()}>{reference || review ? '放弃候选并重新读取原图' : '读取原图并起草共享来源范围'}</button>
    {report?.support_alias_reason && <p role="status">{report.support_alias_reason}</p>}
    {reference && !currentReference && <p role="status">等待与本次请求、来源和人物匹配的真实原图参考，尚未开放绘制。</p>}
    {currentReference && reference && report && selected && !review && <FaceDecorationSupportEditor key={`${reference.request_id}:${binding}`}
      report={report} faceBox={selected.box} disabled={!canEdit} staged onReview={async region => {
        const current = latest.current;
        if (!mounted.current || !canEdit || current.disabled || busy.current || current.reference !== reference || current.released === reference.request_id
          || current.binding !== binding || !referenceCurrent(reference, current.view)) throw Error('来源、人物或参考已变化，请重新读取原图。');
        const proof = current.view!.face_decoration!.reference_proof!;
        if (canonical(proof) !== canonical(report.reference_proof)) throw Error('本次原图证明已变化，请重新绘制。');
        const staged: SupportAliasDraft = {region: structuredClone(region), reference_proof: structuredClone(proof)};
        draft.current = staged; generation.current++; setReview(null); setReady({}); setError(''); busy.current = true;
        try {await people.submitCaptured(command(current.view!, 'face_decoration_support_alias_preview', crypto.randomUUID(), staged));}
        finally {busy.current = false;}
      }}/>}
    {review && <><p>共 {review.members.length} 张完整照片。源成员与全部共享来源成员都要实际读取前后图，并逐张勾选确认；不存在只提交当前照片的回退路径。中性配方可能前后相同，不代表已产生装饰。</p>
      {review.members.map((member, index) => <section key={member.visual.document_id}>
        <strong>{index === 0 ? '当前照片' : '共享来源成员'}：{member.path}</strong>
        <DecorationTransferReview value={member.visual} coverage={member.coverage} token={review.token} reviewKey={supportAliasKey(review, member.visual)}
          disabled={!canEdit} readImage={(side, live) => readImage(member, side, live)} onReady={(key, value) => setReady(old => old[key] === value ? old : {...old, [key]: value})}/>
      </section>)}
      <button type="button" disabled={!canEdit || !allReady} onClick={() => void confirm()}>确认全部照片并原子应用此人物范围</button>
    </>}
    {reference && <button type="button" onClick={clearDraft}>关闭范围候选（不取消已发送请求）</button>}
    {error && <p role="alert">{error}</p>}
  </section>;
}
