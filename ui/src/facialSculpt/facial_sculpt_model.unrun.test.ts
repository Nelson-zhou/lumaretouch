// SPDX-License-Identifier: GPL-3.0-or-later
// AUTHORED / UNRUN. No interaction or screenshot acceptance is implied.
import test from 'node:test';
import assert from 'node:assert/strict';
import {check, neutral, patch, parseChoice, proofValid, CONTROL_IDS} from './model.ts';
import {region} from './review.ts';
test('facial_sculpt exact official leaves and separate scalar intent', () => {
  assert.equal(CONTROL_IDS.highlight, 'LNX-REF-PC-32471-C-8f773e9125');
  assert.equal(CONTROL_IDS.shadow, 'LNX-REF-PC-32471-C-01b2ee2d32');
  assert.deepEqual(patch('shadow', .6), {operation_id: 'lnx.facial_sculpt.v1', parameter_path: '/shadow', unset: false, value: .6});
  assert.equal(parseChoice(''), null); assert.equal(parseChoice(' '), null); assert.equal(parseChoice('0'), 0);
  assert.equal(parseChoice('101'), null); assert.equal(parseChoice('Infinity'), null);
  for (const value of [true, NaN, Infinity, -.1, 1.1, '0.5']) assert.throws(() => check({...neutral(), highlight: value}));
  assert.throws(() => check({...neutral(), radius: 5}));
});
test('facial_sculpt reference cannot borrow source or oversized token', () => {
  const proof = {source: {sha256: 'a'.repeat(64), width: 200, height: 300},
    face_ref: {asset_sha256: 'a'.repeat(64), face_instance_id: 'face-1', analysis_revision: 1},
    landmark_digest: 'b'.repeat(64), preview_sha256: 'c'.repeat(64), reference_request_id: 'request-1'};
  assert.equal(proofValid(proof), true);
  assert.equal(proofValid({...proof, reference_request_id: 'x'.repeat(129)}), false);
  assert.equal(proofValid({...proof, reference_request_id: 'bad\nrequest'}), false);
  assert.equal(proofValid({...proof, face_ref: {...proof.face_ref, asset_sha256: 'd'.repeat(64)}}), false);
  assert.throws(() => region([], true, {visible: true, unoccluded: true, owner: true}));
});
test('facial_sculpt stable canonical binding is not tied to fresh callback wrapper identity', async () => {
  const {readFile} = await import('node:fs/promises');
  const source = await readFile(new URL('./FacialSculptPanel.tsx', import.meta.url), 'utf8');
  assert.match(source, /const binding = bindingKey\(view\)/);
  assert.doesNotMatch(source, /owner\.current\.generation/);
  assert.match(source, /current\.current\.submit\(request\)/);
  assert.match(source, /control\?: Key/);
});
