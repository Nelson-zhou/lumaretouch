import type {PickGroupEyeCapability, PickRun, PickSuggestion} from '../native';

// Presentation only. No detector-count comparison or hint predicate lives in UI.
export function ruleCapability(value: PickGroupEyeCapability | undefined) {
  return !!value && value.version === 1 && value.default === null
    && Number.isInteger(value.min) && Number.isInteger(value.max)
    && value.min >= 1 && value.max >= value.min && value.max < value.detection_limit;
}
export function eyeStatus(p: PickSuggestion | null | undefined): string {
  if (!p) return '尚无有效缓存；眼睛状态未知，不代表睁眼或通过。';
  if (p.group_eye_rule_state === 'omit' && p.reasons.some(r => r.kind === 'eyes_omitted_by_rule'))
    return '按用户规则省略闭眼提示；不是睁眼或分析通过。';
  if (p.reasons.some(r => r.kind === 'eyes_unknown')) return '眼睑测量未知；不是睁眼或通过。';
  if (p.labels.includes('eyes_closed')) return '疑似闭眼，仅供人工复核。';
  return '本次没有闭眼提示；不证明睁眼、分析成功或质量合格。';
}

export function pickFailure(run: PickRun | null): string | null {
  return (run?.action === 'group_rule' || run?.action === 'analyze') && run.event === 'pick_failed'
    ? run.error || run.reason || '挑图请求未完成；请刷新后重试。' : null;
}
