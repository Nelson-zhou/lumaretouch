// AUTHORED / UNRUN. Source wiring fixtures, not native/UI or photo acceptance.
import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {teethColourReadiness, TEETH_CONTROL_IDS} from './model.ts';

const source = (path:string) => readFileSync(new URL(path, import.meta.url), 'utf8');
const panel = source('../components/RetouchPanel.tsx');
const native = source('../native.ts');
const bridge = source('../../src-tauri/src/portrait_api.rs');
const envelope = source('../../src-tauri/src/facial_wrinkle_api.rs');

test('the actual handbook child paths each have their own real slider leaf', () => {
  const spec = source('../spec/refine.json');
  for (const [path,key,label] of [
    ['牙齿美白/明度','teeth_brightness','牙齿明度'],
    ['牙齿美白/祛黄','teeth_yellow_removal','牙齿祛黄'],
  ]) {
    assert.ok(spec.includes(`"path": "${path}"`));
    assert.ok(panel.includes(`"PC-32469|${path}": "enh.${key}"`));
    assert.ok(panel.includes(`"enh.${key}": "${label}"`));
    assert.ok(panel.includes(`case "enh.${key}":`));
  }
  assert.ok(panel.includes('"PC-32469|牙齿美白": "enh.teeth"'));
  assert.ok(panel.includes('onChange={(v) => commitEnhance({ [key]: v / 100 })}'));
  assert.ok(panel.includes('onReset={() => commitEnhance({ [key]: 0 })}'));
  assert.ok(panel.includes("? 'lnx.facial_wrinkles.v1' : 'lnx.enhance.v1'"));
});

test('optional typed values reach the real Tauri command and engine envelope', () => {
  for (const [camel,snake] of [['teethBrightness','teeth_brightness'],['teethYellowRemoval','teeth_yellow_removal']]) {
    assert.ok(native.includes(`${snake}?: number`));
    assert.ok(native.includes(`${camel}: opts?.${snake}`));
    assert.ok(bridge.includes(`${snake}: Option<f64>`));
    assert.ok(envelope.includes(`"${snake}"`));
  }
  assert.ok(bridge.includes('[teeth_brightness, teeth_yellow_removal], wrinkles)?'));
  assert.ok(envelope.includes('if let Some(amount) = value'));
  assert.ok(envelope.includes('!amount.is_finite() || !(0.0..=1.0).contains(&amount)'));
});

test('missing actual native capability never enables the independent sliders', () => {
  assert.equal(teethColourReadiness(undefined).available, false);
  assert.equal(teethColourReadiness({}).available, false);
  assert.deepEqual(teethColourReadiness({teeth_colour_available:false, teeth_colour_reason:'ABI mismatch'}),
    {available:false,reason:'ABI mismatch'});
  assert.deepEqual(teethColourReadiness({teeth_colour_available:true}), {available:true});
  assert.equal(TEETH_CONTROL_IDS.teeth_brightness, 'LNX-REF-PC-32469-C-6eb0bef21b');
  assert.equal(TEETH_CONTROL_IDS.teeth_yellow_removal, 'LNX-REF-PC-32469-C-5462a41c9a');
  assert.ok(panel.includes('disabled={dim || !props.faceOk || !teethReady.available}'));
  assert.ok(panel.includes('role="status">{reason}</p>'));
  assert.ok(panel.includes('onClick={() => commitEnhance({teeth_brightness: 0, teeth_yellow_removal: 0})}'));
  assert.ok(panel.includes('disabled={dim || props.people.state.pending || (doc?.people ? !capturedPeople : !doc)}'));
});
