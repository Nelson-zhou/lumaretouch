// SPDX-License-Identifier: GPL-3.0-or-later
// AUTHORED / UNRUN. Measured suggestions, never automatic reference/consent writes.
import {useEffect, useLayoutEffect, useRef, useState} from 'react';
import {peopleAssetContext, type FaceRef} from '../people/model';
import type {PeopleOwner} from '../people/usePeopleWorkflow';
import {sameFace} from '../people/transferProof';
import {ACTION, canonical, choiceBinding, commandMatches, measuredReference, parseReport, receiptCurrent,
  validContext, validReceiptEnvelope, type ChoiceCatalog, type ChoiceCommand, type ChoiceContext,
  type ChoiceFamily, type ChoiceReport, type MeasuredCandidate} from './model';

type Capture = {command: ChoiceCommand; context: ChoiceContext; binding: string};
type Display = Capture & {report: ChoiceReport};
const blockerLabel = (reason: string): string => ({
  'fewer-than-two-enabled-retained-faces': '启用的保留人脸不足两张，不能比较多人最亮参考。',
  'enabled-face-measurement-unavailable': '至少一张启用人脸缺少可靠测量，不能省略它后宣布最亮参考。',
  'detector-limit-reached': '检测数量已达上限，可能还有遗漏人物。',
  'brightest-measurements-too-close': '最高亮度相近，不能用人物编号打破并列；请明确手动选择。',
}[reason] ?? reason);
const candidateReason = (reason: string | undefined): string => ({
  'actual-face-analysis-unavailable': '缺少实际人脸分析', 'actual-face-analysis-invalid': '当前人脸分析不完整或不一致',
  'source-measurement-refused': '原始来源测量未通过可靠性要求',
}[reason ?? ''] ?? '不参与亮度排序');

/** Embedded below the EXISTING family source image. It owns only display drafts:
 * all commands, pending IDs, uncertainty and mailbox queries stay in PeopleOwner.
 * onReferenceChosen must reset that panel's source ownership and before/after ACK.
 * It may set a reference input only, never preview, render, apply or confirm. */
export function SkinReferenceChoicePanel({people, family, catalog, sourceSeen, available, blocked,
  lockedReference = null, onReferenceChosen}: {people: PeopleOwner; family: ChoiceFamily; catalog: ChoiceCatalog;
  sourceSeen: boolean; available: boolean; blocked: boolean; lockedReference?: FaceRef | null;
  onReferenceChosen: (reference: FaceRef) => void}) {
  const context: ChoiceContext | null = people.value ? {family, view: people.value, catalog} : null;
  const binding = choiceBinding(context), mounted = useRef(false), expected = useRef<Capture | null>(null);
  const [display, setDisplay] = useState<Display | null>(null), [manualId, setManualId] = useState(''), [error, setError] = useState('');
  const busy = blocked || !people.enabled || people.state.pending || people.state.uncertain
    || people.state.skinReferenceRefreshRequired || people.state.skinReferenceBodyRefreshRequired;
  const integrated = available && typeof people.submitCaptured === 'function'
    && Object.hasOwn(people.state, 'lastSkinReferenceChoiceResult');
  const solverAvailable = catalog.kind === 'skin_reference_match_catalog' ? catalog.skin_reference_match_available : catalog.skin_reference_body_available;
  const solverReason = catalog.kind === 'skin_reference_match_catalog' ? catalog.skin_reference_match_reason : catalog.skin_reference_body_reason;
  const live = useRef({binding, busy, integrated, solverAvailable, sourceSeen, context, lockedReference,
    pending: people.state.pending, uncertain: people.state.uncertain});
  live.current = {binding, busy, integrated, solverAvailable, sourceSeen, context, lockedReference,
    pending: people.state.pending, uncertain: people.state.uncertain};
  useLayoutEffect(() => {mounted.current = true; return () => {mounted.current = false; expected.current = null;};}, []);
  useLayoutEffect(() => {expected.current = null; setDisplay(null); setManualId(''); setError('');}, [binding, integrated]);
  useLayoutEffect(() => {
    const hide = () => {if (document.visibilityState !== 'visible') setManualId('');};
    document.addEventListener('visibilitychange', hide);
    return () => document.removeEventListener('visibilitychange', hide);
  }, []);
  function ready(): boolean {
    return mounted.current && live.current.binding === binding && !live.current.busy && live.current.integrated
      && live.current.solverAvailable && live.current.sourceSeen && validContext(live.current.context) && document.visibilityState === 'visible';
  }
  function request(manual?: FaceRef) {
    if (!ready() || !context || expected.current) return;
    const envelope = peopleAssetContext(context.view); if (!envelope) return;
    const command: ChoiceCommand = {...structuredClone(envelope), action: ACTION, request_id: crypto.randomUUID(),
      payload: {family, source_review_sha256: catalog.source_review_sha256, ...(manual ? {manual_reference: structuredClone(manual)} : {})}};
    if (!commandMatches(command, context)) return;
    expected.current = {command, context: structuredClone(context), binding}; setDisplay(null); setError('');
    void people.submitCaptured(command).catch(cause => {
      if (!mounted.current || live.current.binding !== binding || expected.current?.command.request_id !== command.request_id) return;
      setError(String(cause));
      // No retry or pending reset: the sole owner retains the original request.
      if (!live.current.pending && !live.current.uncertain) expected.current = null;
    });
  }
  useEffect(() => {
    const receipt = people.state.lastSkinReferenceChoiceResult, capture = expected.current;
    if (!receipt || !capture || receipt.result.request_id !== capture.command.request_id) return;
    if (!mounted.current || live.current.binding !== capture.binding) return;
    try {
      if (canonical(receipt.command) !== canonical(capture.command) || !validReceiptEnvelope(capture.command, receipt.result)
        || !receiptCurrent(receipt.command, receipt.result, live.current.context?.view ?? null))
        throw Error('参考建议回执已过期或不属于这个面板的原请求。');
      if (receipt.result.payload_released) throw Error('原测量内容已释放，请重新读取来源后再测量。');
      const report = parseReport(receipt.result.payload, capture.command, capture.context);
      if (!report || !live.current.context || choiceBinding(live.current.context) !== capture.binding)
        throw Error('参考建议的人物清单、原始来源或排序证明校验失败。');
      setDisplay({...capture, report}); setError('');
      // Deliberately no setManualId(report.reference...), callback, ACK or preview.
    } catch (cause) {setDisplay(null); setError(String(cause));}
    finally {if (expected.current === capture) expected.current = null;}
  }, [people.state.lastSkinReferenceChoiceResult]);
  useEffect(() => {
    if (!people.state.pending && !people.state.uncertain && people.state.message && expected.current
      && people.state.lastSkinReferenceChoiceResult?.result.request_id !== expected.current.command.request_id) {
      expected.current = null; setDisplay(null); setError(people.state.message);
    }
  }, [people.state]);
  function selectable(ref: FaceRef): boolean {
    return !!display && display.binding === binding && measuredReference(display.report, ref)
      && catalog.faces.some(row => row.enabled && row.available && sameFace(row.face_ref, ref))
      && (!lockedReference || sameFace(lockedReference, ref));
  }
  function choose(ref: FaceRef) {
    if (!ready() || expected.current || !display || !context || !selectable(ref)
      || !parseReport(display.report, display.command, context)) return;
    onReferenceChosen(structuredClone(ref));
  }
  const currentDisplay = display?.binding === binding ? display : null;
  const proposal = currentDisplay?.report.proposal;
  const suggestion = proposal?.automatic_reference_face_ref ?? null;
  const number = (ref: FaceRef) => catalog.faces.findIndex(row => sameFace(row.face_ref, ref)) + 1;
  const chosen = proposal?.candidates.find(row => row.status === 'measured' && row.face_ref.face_instance_id === manualId);
  const measured = proposal?.candidates.filter((row): row is MeasuredCandidate => row.status === 'measured') ?? [];
  const enabled = integrated && solverAvailable && !busy && sourceSeen && !!context;
  return <section aria-label="实测最亮参考建议">
    <h5>实测最亮参考建议</h5>
    <p>以完整原始来源中每张已保留人脸的实际皮肤亮度进行确定性排序，不是学习型 AI 选人，也不是肤色、身份或美观评分。这里只提供建议，不改照片，不代替人物归属或前后图确认。</p>
    {!integrated && <p role="status">当前引擎或现有人物请求入口尚未接入参考测量。请继续明确手动选择参考，不能用其他滑块或虚构结果代替。</p>}
    {integrated && !solverAvailable && <p role="status">当前照片的实测匹配能力不可用：{solverReason ?? '缺少对应原生测量能力'}。不会生成虚假的参考建议；原面板的读取、手动选择和清除流程保持独立。</p>}
    {!sourceSeen && <p role="status">请先完整加载并查看上方当前来源图与人物编号，再请求参考测量。</p>}
    <button type="button" disabled={!enabled || !!expected.current} onClick={() => request()}>
      {currentDisplay ? '重新测量全部保留人脸' : '测量全部保留人脸的亮度'}</button>
    {proposal && <>
      <p role="status">这里只比较当前保留的人脸，不能证明照片中没有漏检人物。请核对上方原始来源与人物框；所有参考选择都需要你明确操作。</p>
      {proposal.automatic_blockers.map(reason => <p role="status" key={reason}>{blockerLabel(reason)}</p>)}
      {suggestion ? <p>已保留、可靠可测人脸中的最亮建议：人物 {number(suggestion)}。测量本身不会选择或应用参考。
        <button type="button" disabled={!enabled || !selectable(suggestion)} onClick={() => choose(suggestion)}>明确选择人物 {number(suggestion)} 作为参考</button></p>
        : <p role="status">当前不能给出唯一最亮建议。可从可靠可测人脸中明确手动选择，不会忽略缺失测量或用编号打破并列。</p>}
      {lockedReference && <p role="status">已有身体匹配使用人物 {number(lockedReference)} 作为共同参考。当前不能换成另一张脸；如需更换，请先使用原面板的清除流程。</p>}
      {proposal.selection_mode === 'manual-override-proposal' && proposal.reference_face_ref && <p>
        已重新测量你明确指定的人物 {number(proposal.reference_face_ref)}，这不代表它最亮，也不会自动选入或应用。</p>}
      <ol aria-label="每张保留人脸的原始亮度测量">{proposal.candidates.map(row => <li key={row.face_ref.face_instance_id}>
        人物 {number(row.face_ref)}：{row.status === 'measured'
          ? <>自然对数亮度 {row.measurement.log_luminance.toFixed(5)}；线性亮度 {row.measurement.linear_luminance.toFixed(5)}。
            <details><summary>测量事实（不是可信度评分）</summary>
              <p>有效样本 {row.measurement.effective_samples.toFixed(1)}；保留样本 {row.measurement.robust_sample_count}；
                初始亮度离散度 {row.measurement.initial_log_luminance_mad.toFixed(5)}。</p>
              <p>亮度来自完整源尺寸 {catalog.source.width} × {catalog.source.height}，不是上方缩略图。
                语义观测尺寸 {row.face_skin_observation.producer_width} × {row.face_skin_observation.producer_height}，重采样不等于新全分辨率推理。</p>
            </details></>
          : <>{row.status === 'disabled' ? '已禁用，保留保护范围，不参与排序。' : '不可测。'}{candidateReason(row.reason)}</>}
      </li>)}</ol>
      <p className="muted">亮度只反映原图光照和工作色彩变换，不是固有肤色。最高两项相差不超过约 2% 时需手动选择；这是待验证的工程并列范围，不是感知阈值或概率。</p>
      <label>手动覆盖建议<select value={manualId} disabled={!enabled} onChange={event => setManualId(event.target.value)}>
        <option value="">请明确选择参考人物</option>{measured.map(row => <option key={row.face_ref.face_instance_id}
          value={row.face_ref.face_instance_id} disabled={!selectable(row.face_ref)}>人物 {number(row.face_ref)}</option>)}
      </select></label>
      <button type="button" disabled={!enabled || !chosen || !selectable(chosen.face_ref)} onClick={() => {if (chosen) choose(chosen.face_ref);}}>使用这个手动参考</button>
      <button type="button" disabled={!enabled || !chosen || !selectable(chosen.face_ref) || !!expected.current}
        onClick={() => {if (chosen) request(chosen.face_ref);}}>重新测量并核对这个参考</button>
      <p className="muted">选择只更新本面板的参考输入，并清除旧的归属确认和前后图审核。参考脸仍须排除；身体归属、手绘范围与身体确认不由这个建议授权。</p>
    </>}
    {people.state.pending && expected.current && <p role="status">正在测量实际完整来源；不会启动第二个请求。</p>}
    {people.state.uncertain && <p role="alert">原人物请求的结果尚未确定，请通过现有面板查询原请求；这里不会重发或自动选人。</p>}
    {error && <p role="alert">{error}</p>}
  </section>;
}
