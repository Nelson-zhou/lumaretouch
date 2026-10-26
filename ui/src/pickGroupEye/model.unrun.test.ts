// AUTHORED / UNRUN; no UI/runtime acceptance is claimed.
import assert from 'node:assert/strict';
import test from 'node:test';
import type {PickSuggestion} from '../native';
import {eyeStatus, pickFailure, ruleCapability} from './model';

test('capability is versioned and unknown never reads as pass (UNRUN)', () => {
  assert.equal(ruleCapability(undefined), false);
  assert.equal(ruleCapability({version:1, default:null, min:1, max:31, detection_limit:32}), true);
  assert.equal(ruleCapability({version:2, default:null, min:1, max:31, detection_limit:32}), false);
  assert.match(eyeStatus(null), /未知/);
});
test('omitted by user rule is not eyes-open or successful analysis (UNRUN)', () => {
  const p = {labels:[], reasons:[{kind:'eyes_omitted_by_rule'}], group_eye_rule_state:'omit'} as unknown as PickSuggestion;
  assert.match(eyeStatus(p), /按用户规则省略/);
  assert.match(eyeStatus(p), /不是睁眼或分析通过/);
  assert.match(eyeStatus({...p, reasons:[], group_eye_rule_state:'unknown'}), /不证明/);
  assert.match(eyeStatus({...p, reasons:[{kind:'eyes_unknown'}] as PickSuggestion['reasons']}), /未知/);
  assert.match(eyeStatus({...p, labels:['eyes_closed'], reasons:[], group_eye_rule_state:'unavailable'}), /疑似闭眼/);
});

test('measurement refusal remains visible after request acknowledgement (UNRUN)', () => {
  assert.equal(pickFailure({event:'pick_failed', action:'analyze', error:'请选择该来源的首个文档', host_sequence:2}), '请选择该来源的首个文档');
  assert.equal(pickFailure({event:'pick_failed', action:'group_rule', error:'缓存失效'}), '缓存失效');
  assert.equal(pickFailure({event:'pick_done', action:'analyze'}), null);
});
