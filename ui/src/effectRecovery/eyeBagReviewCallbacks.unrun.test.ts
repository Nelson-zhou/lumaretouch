// AUTHORED / UNRUN: static regression fixtures, no browser execution acceptance.
import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
const panel=readFileSync(new URL('./EffectRecoveryPanel.tsx',import.meta.url),'utf8');
test('late previous review image callbacks cannot mark or poison the current review',()=>{
  assert.ok(panel.includes('currentReview.current.preview===preview&&currentReview.current.image===image'));
  assert.equal((panel.match(/if\(isCurrent\(\)\)setLoaded/g)??[]).length,2);
  assert.equal((panel.match(/if\(isCurrent\(\)\)workflow.failed/g)??[]).length,2);
});
test('queued presentation frame checks exact review identity before acknowledging',()=>{
  assert.ok(panel.includes('if(live&&currentReview.current.preview===preview&&currentReview.current.image===image)void workflow.imagePresented(preview!)'));
  assert.ok(panel.includes('cancelAnimationFrame(first);cancelAnimationFrame(second)'));
});
