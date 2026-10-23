// AUTHORED / UNRUN. Source contracts only, not UI/native/photo acceptance.
import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {redEyeReadiness, RED_EYE_CONTROL_ID} from './model.ts';

const source = (path:string) => readFileSync(new URL(path, import.meta.url), 'utf8');
const panel = source('../components/RetouchPanel.tsx');
const native = source('../native.ts');
const bridge = source('../../src-tauri/src/portrait_api.rs');
const envelope = source('../../src-tauri/src/facial_wrinkle_api.rs');

test('the handbook flash red-eye path has a distinct scalar and real control', () => {
  assert.equal(RED_EYE_CONTROL_ID, 'LNX-REF-PC-32470-C-ee00f0a195');
  assert.ok(source('../spec/refine.json').includes('"path": "祛红眼"'));
  assert.ok(panel.includes('"PC-32470|祛红眼": "enh.red_eye"'));
  assert.ok(panel.includes('"PC-32470|祛红血丝": "enh.veins"'));
  assert.ok(panel.includes('"enh.red_eye": "祛红眼"'));
  assert.ok(panel.includes('case "enh.red_eye":'));
  assert.ok(panel.includes('data-control-id={RED_EYE_CONTROL_ID}'));
  assert.ok(panel.includes('onChange={(v) => commitEnhance({red_eye: v / 100})}'));
  assert.ok(panel.includes('onReset={() => commitEnhance({red_eye: 0})}'));
});

test('ordinary edits use the existing people scope and captured legacy context', () => {
  assert.ok(panel.includes('const capturedPeople = peopleContext(doc?.people)'));
  assert.ok(panel.includes('if (doc?.people) {\n      commitPeopleLeaves(Object.entries(patch)'));
  assert.ok(panel.includes("? 'lnx.facial_wrinkles.v1' : 'lnx.enhance.v1'"));
  assert.ok(panel.includes('parameter_path: `/${key}`, unset: false, value'));
  assert.ok(panel.includes('runEnhance("set", patch, capturedPeople)'));
  assert.ok(bridge.includes('crate::people_api::add_context(&mut cmd, people_context)?'));
});

test('the optional red-eye amount is transported without manufacturing a zero', () => {
  assert.ok(native.includes('red_eye?: number'));
  assert.ok(native.includes('redEye: opts?.red_eye'));
  assert.ok(bridge.includes('red_eye: Option<f64>'));
  assert.ok(bridge.includes('enhance_command_with_red_eye(&action'));
  assert.ok(bridge.includes('red_eye,\n        [teeth_brightness, teeth_yellow_removal], wrinkles)?'));
  assert.ok(envelope.includes('enhance_command_with_red_eye(action, legacy, None, teeth_colour, wrinkles)'));
  assert.ok(envelope.includes('.chain([("red_eye", red_eye)])'));
  assert.ok(envelope.includes('if let Some(amount) = value'));
  assert.ok(envelope.includes('!amount.is_finite() || !(0.0..=1.0).contains(&amount)'));
});

test('unreported or absent native capability disables edits but leaves reset reachable', () => {
  assert.equal(redEyeReadiness(undefined).available, false);
  assert.equal(redEyeReadiness(null).available, false);
  assert.equal(redEyeReadiness({}).available, false);
  assert.deepEqual(redEyeReadiness({red_eye_available:false, red_eye_reason:'ABI mismatch'}),
    {available:false,reason:'ABI mismatch'});
  assert.deepEqual(redEyeReadiness({red_eye_available:true}), {available:true});
  assert.ok(native.includes('red_eye_available?: boolean'));
  assert.ok(native.includes('red_eye_reason?: string | null'));
  const control = panel.slice(panel.indexOf('case "enh.red_eye":'), panel.indexOf('case "enh.veins":'));
  assert.ok(control.includes('disabled={dim || !props.faceOk || !redEyeReady.available}'));
  assert.ok(control.includes('role="status">{reason}</p>'));
  assert.ok(control.includes('disabled={dim || props.people.state.pending || (doc?.people ? !capturedPeople : !doc)}'));
  assert.ok(control.includes('onClick={() => commitEnhance({red_eye: 0})}'));
});

test('scalar-only preset owner remains generic and refuses a derived legacy source', () => {
  const scope = source('../../../engine/src/lumaretouch_engine/enhance_scope.py');
  const replay = source('../../../engine/src/lumaretouch_engine/people_scope.py');
  const registry = JSON.parse(source('../../../docs/p0/registry-extensions.json'));
  const entry = registry.entries.find((entry:{operation_id:string}) => entry.operation_id === 'lnx.enhance.v1');
  assert.equal(entry.neutral.amounts.red_eye, 0);
  assert.ok(entry.source_requirements.includes(RED_EYE_CONTROL_ID));
  assert.ok(scope.includes("A.check_enhance(recipe['amounts'])"));
  assert.ok(scope.includes('if SOURCE.record(state) is not None:'));
  assert.ok(replay.includes("if TEETH.active(amounts) or RED_EYE.active(amounts):kwargs['strict_local']=True"));
});
