// AUTHORED / UNRUN source contract assertions. No React render, runner, typecheck or build was executed.
import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
const source = (path: string) => readFileSync(new URL(path, import.meta.url), 'utf8');
test('selector preserves selected effects and requires exact explicit per-target policies', () => {
  const s = source('../people/ConfirmedPeopleTransfer.tsx');
  assert.match(s, /eyeBagBatchPolicy\(selected, eyePolicyChoices\)/);
  assert.match(s, /\[id\]: raw === '' \? undefined : raw === 'true'/);
  assert.match(s, /revision: old.revision \+ 1/);
  assert.match(s, /!eyeRouteReady \|\| selectedConflict \? undefined/);
  assert.doesNotMatch(s, /operations\.filter\(\(\[operation\]\) => operation !== EYE_BAGS\)/);
  assert.match(s, /flow\.commit\(spill,shadow,torso,waist,head,collarbone,faceStyle,portrait,eyeBag\)/);
});
test('neutral stop is explicit, requires selected numeric zero, and sends no eye envelope or ACK', () => {
  const s = source('../people/ConfirmedPeopleTransfer.tsx');
  assert.match(s, /selection\[EYE_BAGS\]\.includes\('\/amount'\)/);
  assert.match(s, /leaf\.path === '\/amount' && leaf\.value === 0 && !leaf\.conflict/);
  assert.match(s, /eyeSelected && !eyeNeutralReset \? eyeBagBatchPolicy/);
  assert.match(s, /eyeNeutralReset \? !persistent && eyeNeutralEligible/);
  assert.match(s, /mode: 'neutral_reset'/);
  assert.match(s, /不发送卧蚕保护、旧版替换策略或祛眼袋图像确认/);
});
test('full real images require digest, natural decoded dimensions and explicit per-target acknowledgment', () => {
  const s = source('./EyeBagBatchReview.tsx');
  for (const fragment of ['verifyEyeBagBatchCoverage(value, coverage)', "read('before'), after = await read('after')",
    'element.naturalWidth === value[side].width', 'element.naturalHeight === value[side].height',
    'disabled={disabled || !ready}', 'setAcknowledged(false)', 'liveAttempt.current === attempt',
    'key={JSON.stringify([props.reviewKey, props.coverage, props.policy])}', '全部所选参数', '最长边最多 1024']) assert.ok(s.includes(fragment), fragment);
});
test('image reads bypass mutation notification; native commit preserves ordered eye acknowledgment', () => {
  const s = source('../native.ts');
  assert.match(s, /\['batch','preset'\]\.includes\(command\).*action==='eye_bag_visual'/);
  assert.match(s, /eyeBagReviewAck:opts\.eyeBagReviewAck/);
  assert.match(s, /\{\.\.\.value,action:'eye_bag_visual'\}/);
});
test('workflow context revision fences reads only while original writes stay query-only', () => {
  const s = source('../batch/batchWorkflow.ts');
  for (const fragment of ['contextRevision++', 'request.contextRevision!==contextRevision', 'pending?.eyeBagWrite',
    'queryOnly:request.faceStyleWrite||request.portraitWrite||request.eyeBagWrite',
    'sameEyeBagBatchAck(result.eye_bag_review_ack,request.eyeBagAck)', 'eyeBagAckSnapshot',
    "['applied','skipped','noop']"]) assert.ok(s.includes(fragment), fragment);
});
