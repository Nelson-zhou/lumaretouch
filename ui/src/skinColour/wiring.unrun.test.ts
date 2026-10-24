// AUTHORED / UNRUN. Static wiring contracts only; no UI or photographic acceptance claim.
import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';

const source = (path: string) => readFileSync(new URL(path, import.meta.url), 'utf8');
const panel = source('../components/RetouchPanel.tsx');
const control = source('./SkinColourControl.tsx');
const model = source('./model.ts');

test('only the two independent skin-colour handbook paths are newly wired', () => {
  for (const [path, key] of [['肤色色温', 'temperature'], ['肤色色调', 'tint']]) {
    assert.ok(source('../spec/refine.json').includes(`"path": "${path}"`));
    assert.ok(panel.includes(`"PC-32465|${path}": "skin_colour.${key}"`));
    assert.ok(panel.includes(`case "skin_colour.${key}":`));
  }
  assert.equal((panel.match(/"PC-32465\|[^"\n]+": "skin_colour\./g) ?? []).length, 2);
  for (const existing of ['"PC-32465|AI肤色统一（脸部）": "skin.broad"',
    '"PC-32465|高低频磨皮-脸部/身体": "skin.strength"', '"skin.broad": "肤色匀净"',
    '"PC-32455|白平衡/色温": "exp.temp"', '"PC-32455|白平衡/色调": "exp.tint"']) assert.ok(panel.includes(existing));
  assert.ok(control.includes('data-control-id={SKIN_COLOUR_CONTROL_IDS[control]}'));
});

test('canonical people owner is the sole mutation path including single-transaction neutral recovery', () => {
  assert.ok(control.includes('people.patch([skinColourPatch(control, value)])'));
  assert.ok(control.includes('people.patch(SKIN_COLOUR_KEYS.map(key => skinColourPatch(key, 0)))'));
  assert.ok(model.includes('parameter_path: `/${key}`, unset: false, value'));
  for (const forbidden of ['runEnhance', 'runGrade', 'runExposure', 'runHistory', 'invoke(', 'createPeopleWorkflow']) {
    assert.equal(control.includes(forbidden), false);
  }
  assert.ok(source('../people/model.ts').includes("'lnx.skin_colour.v1': '面部肤色色温与色调'"));
  assert.ok(source('../presets/presetModel.ts').includes("'lnx.skin_colour.v1':'面部肤色色温/色调'"));
});

test('resolved current-face numbers and target labels are explicit; unsupported readback is not invented', () => {
  assert.ok(model.includes('const source = resolved.operations[SKIN_COLOUR_OPERATION]?.[path]'));
  assert.ok(control.includes('reading.value !== null'));
  assert.ok(control.includes('targetLabel(view)'));
  assert.ok(control.includes('sourceLabel(reading.source)'));
  assert.ok(control.includes('不代表所有人物或共享默认值'));
  assert.ok(control.includes("['冷', '暖'] : ['绿', '洋红']"));
  assert.ok(control.includes('min={-100} max={100}'));
  assert.ok(control.includes('onChange={value => commit(value / 100)}'));
});

test('native support is distinct from actual semantic skin and 478-point source validation', () => {
  assert.ok(panel.includes('capability={status?.ready_caps}'));
  assert.ok(source('../native.ts').includes('skin_colour_available?: boolean'));
  assert.ok(source('../native.ts').includes('skin_colour_reason?: string | null'));
  for (const text of ['仅调整已测得的面部皮肤', '不覆盖全身皮肤', '手动调色，不是 AI 美白或肤色统一',
    '皮肤功能族仍为部分实现', '当前有效来源图像', '真实面部皮肤语义分割及 478 点人脸分析', '仅核心就绪不等于此脸可用',
    '不用全图肤色键替代', '遮挡与分割边缘可能不准确', '不是手册规定']) assert.ok(control.includes(text));
});

test('reset remains visible without the core, while pending ownership, input binding and edit queue remain fenced', () => {
  assert.ok(control.includes('disabled={access.resetDisabled}'));
  assert.ok(control.includes('onClick={() => commit(0)}'));
  assert.ok(control.includes('!access.core.available && <><button'));
  assert.ok(control.includes('current.current.binding !== binding'));
  assert.ok(control.includes('current.current.access.resetDisabled : current.current.access.changeDisabled'));
  assert.ok(control.includes('key={`${binding}:${control}`}'));
  assert.ok(control.includes('pending: people.state.pending, uncertain: people.state.uncertain'));
  assert.ok(control.includes('people.check()'));
  for (const fence of ['props.hairBusy', 'props.whiteBalanceBusy', 'portraitRequestsBusy()',
    'status?.edit_queue?.in_flight', 'status?.edit_queue?.pending', 'status?.edit_queue?.closed']) assert.ok(panel.includes(fence));
});
