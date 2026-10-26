// SPDX-License-Identifier: GPL-3.0-or-later
// AUTHORED / UNRUN. Draft loading is pure UI state, never crop/apply transport.
import assert from 'node:assert/strict';
import test from 'node:test';
import {readFileSync} from 'node:fs';
import {PortraitCropController} from '../controller.ts';
const draft = {aspect_ratio: '.75', headroom_fraction: '.1', head_fraction: '.6', horizontal_position: '.5'};
test('loading requires readiness and changes draft only, with no engine request', () => {
  let calls = 0;
  const c = new PortraitCropController({send: async () => {calls++; throw Error('must not dispatch');}, status: async () => null});
  assert.throws(() => c.loadRulePreset(draft)); c.setContext('photo-A'); c.setEnabled(true);
  c.loadRulePreset(draft);
  assert.equal(calls, 0); assert.equal(c.snapshot().rules.aspect_ratio, '0.75');
  assert.equal(c.snapshot().current, null); assert.deepEqual(c.snapshot().anchors, {});
  assert.equal(c.snapshot().preview, null); assert.equal(c.snapshot().reviewConfirmed, false);
  assert.deepEqual(c.snapshot().confirmations, {crown: false, chin: false, face_center: false});
  c.setContext('photo-B'); assert.deepEqual(c.snapshot().anchors, {}); assert.equal(c.snapshot().preview, null);
});
test('UI has explicit delete/update confirmations and separate draft-only load', () => {
  const panel = readFileSync(new URL('./RulePresetPanel.tsx', import.meta.url), 'utf8');
  assert.match(panel, /确认永久删除本机规则/); assert.match(panel, /取消，不修改目录/);
  assert.match(panel, /确认更新此规则/); assert.match(panel, /载入为草稿，不应用/);
  assert.doesNotMatch(panel, /controller\.apply|localStorage|window\.confirm/);
  const native = readFileSync(new URL('../../../src-tauri/src/portrait_crop_rules_api.rs', import.meta.url), 'utf8');
  assert.doesNotMatch(native, /send_command|engine::|AppState/);
});
