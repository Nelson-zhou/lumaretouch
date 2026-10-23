// AUTHORED / UNRUN. Source contracts only, not UI/native/photo acceptance.
import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {scleraPurifyReadiness, SCLERA_PURIFY_CONTROL_ID} from './model.ts';

const source = (path:string) => readFileSync(new URL(path, import.meta.url), 'utf8');
const panel = source('../components/RetouchPanel.tsx');
const control = source('./ScleraPurifyControl.tsx');
const native = source('../native.ts');
const bridge = source('../../src-tauri/src/portrait_api.rs');
const envelope = source('../../src-tauri/src/facial_wrinkle_api.rs');

test('eye-white purification has its own handbook leaf and real scalar control', () => {
  assert.equal(SCLERA_PURIFY_CONTROL_ID, 'LNX-REF-PC-32470-C-26ab900915');
  assert.ok(source('../spec/refine.json').includes('"path": "眼白净化"'));
  assert.ok(panel.includes('"PC-32470|眼白净化": "enh.sclera_purify"'));
  assert.ok(panel.includes('"PC-32470|亮眼/眼白": "enh.sclera"'));
  assert.ok(panel.includes('"PC-32470|祛红血丝": "enh.veins"'));
  assert.ok(panel.includes('"PC-32470|祛红眼": "enh.red_eye"'));
  assert.ok(panel.includes('case "enh.sclera_purify":'));
  assert.ok(panel.includes('<ScleraPurifyControl key={leaf.path} amount={enhAmounts.sclera_purify ?? 0}'));
  assert.ok(control.includes('data-control-id={SCLERA_PURIFY_CONTROL_ID}'));
  assert.ok(control.includes('onChange={(v) => commit({sclera_purify: v / 100})}'));
  assert.ok(control.includes('onReset={() => commit({sclera_purify: 0})}'));
});

test('the live control explains bounded local correction and non-semantic support', () => {
  assert.ok(control.includes('仅减轻眼白局部暗淡瑕疵与偏色'));
  assert.ok(control.includes('不是整体提亮或祛红血丝'));
  assert.ok(control.includes('范围由眼部几何估计，并非语义分割'));
  assert.ok(control.includes('请对比调整前后'));
  assert.ok(control.includes('不能保证识别全部瑕疵'));
});

test('edits and explicit resets retain the canonical people path and captured context', () => {
  assert.ok(panel.includes('const capturedPeople = peopleContext(doc?.people)'));
  assert.ok(panel.includes('if (doc?.people) {\n      commitPeopleLeaves(Object.entries(patch)'));
  assert.ok(panel.includes("? 'lnx.facial_wrinkles.v1' : 'lnx.enhance.v1'"));
  assert.ok(panel.includes('parameter_path: `/${key}`, unset: false, value'));
  assert.ok(panel.includes('runEnhance("set", patch, capturedPeople)'));
  assert.ok(bridge.includes('crate::people_api::add_context(&mut cmd, people_context)?'));
});

test('optional purification crosses the bridge without changing prior wrapper signatures', () => {
  assert.ok(native.includes('sclera_purify?: number'));
  assert.ok(native.includes('scleraPurify: opts?.sclera_purify'));
  assert.ok(bridge.includes('sclera_purify: Option<f64>'));
  assert.ok(bridge.includes('enhance_command_with_red_eye(&action'));
  assert.ok(bridge.includes('red_eye,\n        [teeth_brightness, teeth_yellow_removal], wrinkles)?'));
  assert.ok(bridge.includes('append_sclera_purify(&mut cmd, sclera_purify)?'));
  assert.ok(envelope.includes('enhance_command_with_teeth(action, legacy, [None, None], wrinkles)'));
  assert.ok(envelope.includes('enhance_command_with_red_eye(action, legacy, None, teeth_colour, wrinkles)'));
  const append = envelope.slice(envelope.indexOf('pub fn append_sclera_purify'), envelope.indexOf('#[cfg(test)]'));
  assert.ok(append.includes('let Some(amount) = value else { return Ok(()); }'));
  assert.ok(append.includes('!amount.is_finite() || !(0.0..=1.0).contains(&amount)'));
  assert.ok(append.includes('object.insert("sclera_purify".into(), serde_json::json!(amount))'));
  assert.ok(!append.includes('"sclera"'));
  assert.ok(!append.includes('"veins"'));
});

test('absent capability disables editing but not a fenced explicit-zero reset', () => {
  for (const value of [undefined, null, {}]) assert.equal(scleraPurifyReadiness(value).available, false);
  assert.deepEqual(scleraPurifyReadiness({sclera_purify_available:false, sclera_purify_reason:'ABI mismatch'}),
    {available:false,reason:'ABI mismatch'});
  assert.deepEqual(scleraPurifyReadiness({sclera_purify_available:true}), {available:true});
  assert.ok(native.includes('sclera_purify_available?: boolean'));
  assert.ok(native.includes('sclera_purify_reason?: string | null'));
  assert.ok(panel.includes('doc?.enhance?.sclera_purify_available === undefined ? status?.enhance : doc?.enhance'));
  assert.ok(control.includes('disabled={disabled || !faceOk || !ready.available}'));
  assert.ok(control.includes('role="status">{why}</p>'));
  assert.ok(panel.includes('resetDisabled={dim || props.people.state.pending || (doc?.people ? !capturedPeople : !doc)}'));
  assert.ok(control.includes('{amount > 0 && <button'));
  assert.ok(control.includes('disabled={resetDisabled}'));
  assert.ok(control.includes('onClick={() => commit({sclera_purify: 0})}'));
});

test('scalar preset state stays target-owned and active replay remains strict', () => {
  const scope = source('../../../engine/src/lumaretouch_engine/enhance_scope.py');
  const replay = source('../../../engine/src/lumaretouch_engine/people_scope.py');
  const registry = JSON.parse(source('../../../docs/p0/registry-extensions.json'));
  const entry = registry.entries.find((entry:{operation_id:string}) => entry.operation_id === 'lnx.enhance.v1');
  assert.equal(entry.neutral.amounts.sclera_purify, 0);
  assert.ok(entry.source_requirements.includes(SCLERA_PURIFY_CONTROL_ID));
  assert.ok(entry.reason.includes('Runtime, numerical and photographic acceptance UNRUN'));
  assert.ok(scope.includes("A.check_enhance(recipe['amounts'])"));
  assert.ok(scope.includes('if SOURCE.record(state) is not None:'));
  assert.ok(scope.includes("current['built'], current['box'] = False, box"));
  assert.ok(replay.includes("if SCLERA_PURIFY.active(amounts):kwargs['strict_local']=True"));
  assert.ok(replay.includes("if TEETH.active(amounts) or RED_EYE.active(amounts):kwargs['strict_local']=True"));
});
