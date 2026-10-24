// AUTHORED / UNRUN. Source-boundary fixtures, not UI execution evidence.
import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
const source = (name: string) => readFileSync(new URL(name, import.meta.url), 'utf8');
test('persistent selector exposes a remedy for unknown target-local active effects and all member policies', () => {
  const s = source('../people/ConfirmedPeopleTransfer.tsx');
  for (const pattern of [/eyeCohortRequired/, /eyeBagIntentRequiresReview/, /eyeCohortChoice/, /eyeBagCohortPolicy\(\[listing.source.document.document_id, \.\.\.selected\]/,
    /associationOperation, eyeCohortRequested/, /reviewEpoch: eyePolicies.revision/, /!persistent && eyeSelected/]) assert.match(s, pattern);
  assert.match(s, /仍有新版启用效果/); assert.match(s, /源成员/);
});
test('actual images both decode and display before any member checkbox can authorize', () => {
  const s = source('./EyeBagCohortReview.tsx');
  for (const text of ['verifyEyeBagCohortCoverage', "read('before'), after = await read('after')", 'loaded.before && loaded.after',
    'element.naturalWidth', 'element.naturalHeight', 'mounted.current', 'liveAttempt.current', 'setAcknowledged(false)', "['before', 'after'] as const"])
    assert.ok(s.includes(text));
});
test('separate read-only native route and ACK never change App or reuse ordinary eye submission', () => {
  const s = source('../native.ts'); assert.match(s, /'portrait_cohort_visual','eye_bag_cohort_visual'/);
  assert.match(s, /eyeBagCohortAck:opts.eyeBagCohortAck/); assert.match(s, /\{\.\.\.value,action:'eye_bag_cohort_visual'\}/);
  assert.match(s, /observeEyeBagCohortHistory\(status.session\?\.sync, observation\)/);
  const review = source('../batch/BatchReview.tsx'); assert.match(review, /eyeCohortTargets.length===plan!\.targets.length\+1/);
  assert.match(review, /eyeCohortSelected\?eyeBagCohortAck\(eyeCohortTargets\)/);
});
