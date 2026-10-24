// AUTHORED / UNRUN. Source-contract fixtures only; not imported, compiled, executed or UI accepted.
import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
const source = (path: string) => readFileSync(new URL(path, import.meta.url), 'utf8');
const panel = source('../components/RetouchPanel.tsx'), control = source('./LipTextureControl.tsx');
const model = source('./model.ts');

test('exact one lip-texture catalogue leaf routes to the dedicated control', () => {
  assert.ok(source('../spec/refine.json').includes('"path": "面部祛瑕疵/唇纹修整"'));
  assert.ok(panel.includes('"PC-32464|面部祛瑕疵/唇纹修整": "lip_texture.amount"'));
  assert.equal((panel.match(/"PC-32464\|[^"\n]+": "lip_texture\./g) ?? []).length, 1);
  assert.ok(panel.includes('case "lip_texture.amount":'));
  assert.ok(panel.includes('<LipTextureControl key={leaf.path}'));
  assert.ok(control.includes('data-control-id={LIP_TEXTURE_CONTROL_ID}'));
  assert.ok(model.includes("'LNX-REF-PC-32464-C-b6315c40ca'"));
  assert.ok(source('../people/model.ts').includes("'lnx.lip_texture.v1': '唇纹修整（仅淡化已测得的窄暗纹）'"));
});

test('lip makeup, lipstick, mouth-surround wrinkles, skin texture and legacy paths keep their meaning', () => {
  for (const existing of ['"PC-32471|唇妆增强": "lip.family"', '"PC-32471|唇妆增强/饱和度": "lip.saturation"',
    '"PC-32471|唇妆增强/明度": "lip.brightness"', '"PC-32471|唇妆增强/立体度": "lip.dimensionality"',
    '"PC-32471|局部妆容/口红": "lipstick.family"',
    '"PC-32464|面部祛纹/祛嘴周纹": "wrinkle.mouth_surround"',
    '"PC-32465|皮肤质感/纹理度": "skin_texture.texture"', '"PC-32465|皮肤质感/清晰度": "skin_texture.clarity"']) {
    assert.ok(panel.includes(existing));
  }
  for (const forbidden of ['runLipMakeup', 'runEnhance', 'runGrade', 'runExposure', 'runHistory', 'setStrength',
    'invoke(', 'createPeopleWorkflow', 'people.submit(', 'people.submitCaptured(', 'lnx.lip_makeup.v1',
    'lnx.facial_wrinkles.v1', 'lnx.skin_texture.v1', 'LipstickSupportEditor', 'canvas', 'preview_src']) {
    assert.equal(control.includes(forbidden), false); assert.equal(model.includes(forbidden), false);
  }
});

test('the dedicated capability and all existing competing-owner fences are passed through', () => {
  assert.ok(source('../native.ts').includes('lip_texture_available?: boolean'));
  assert.ok(source('../native.ts').includes('lip_texture_reason?: string | null'));
  const route = panel.slice(panel.indexOf('case "lip_texture.amount":'), panel.indexOf('case "histogram.control":'));
  for (const text of ['people={props.people}', 'capability={status?.ready_caps}', 'blocked={dim', 'props.hairBusy',
    'props.whiteBalanceBusy', 'portraitRequestsBusy()', 'status?.edit_queue?.in_flight', 'status?.edit_queue?.pending',
    'status?.edit_queue?.closed', 'faceOk={props.faceOk}', 'faceWhy={props.faceWhy}', 'Slider={Slider}']) assert.ok(route.includes(text));
  for (const forbidden of ['lip_makeup_protocol', 'skin_texture_available', 'lipstick_protocol', 'skin_semantics_available']) {
    assert.equal(model.includes(forbidden), false);
  }
});

test('face provenance is separate from explicit shared intent and unknowns never become a zero slider', () => {
  for (const text of ['targetLabel(view)', 'sourceLabel(source)', 'display(reading.value)', 'reading.overridePresent',
    'access.editValue !== null', 'value={access.editValue * 100}', 'min={0} max={100}',
    'onChange={value => commit(value / 100)}', "useState('')", 'parseLipTextureChoice(text)',
    'key={`${binding}:amount`}', 'key={`${binding}:choice`}', '留空不等于 0', '不把某一张脸的继承值复制给其他人物']) assert.ok(control.includes(text));
  assert.ok(model.includes('const source = resolved.operations[LIP_TEXTURE_OPERATION]?.[path]'));
  assert.ok(model.includes("view?.editing_target?.scope === 'face' ? reading.value : null"));
  assert.ok(model.includes("link.state === 'confirmed'"));
  assert.ok(model.includes('link.confirmation_revision <= view.association_revision'));
  assert.ok(model.includes('view.groups, view.persons, view.links'));
  assert.equal(control.includes('reading.value ?? 0'), false);
  const choice = control.slice(control.indexOf('function AmountChoice'), control.indexOf('export function LipTextureControl'));
  assert.equal(choice.includes('onBlur='), false); assert.equal(choice.includes('useEffect'), false);
});

test('single canonical owner and current-owner mounted guards prevent late or duplicate writes', () => {
  for (const text of ['people.patch(patches)', 'dispatch([lipTexturePatch(value)])', 'dispatch(lipTextureResetPatches())',
    'owner.current.patch !== people.patch || owner.current.check !== people.check', 'owner.current.generation + 1',
    'mounted.current && current.current.binding === binding', 'current.current.patch === people.patch',
    'current.current.check === people.check', 'mounted.current = false', 'if (!stillCurrent() || submitted.current) return',
    'submitted.current = true', 'if (!people.state.pending && !people.state.uncertain) submitted.current = false',
    'current.current.access.resetDisabled : current.current.access.changeDisabled', 'people.check()',
    'if (stillCurrent()) note(String(error))', '查询原请求结果（不重发修改）']) assert.ok(control.includes(text));
  assert.equal((control.match(/people\.patch\(/g) ?? []).length, 1);
  const workflow = source('../people/workflow.ts');
  for (const text of ["action: 'patch', payload: {patches}", 'command.document_epoch === current.binding.document_epoch',
    'command.document_revision === current.binding.document_revision', 'command.state_revision === current.revision',
    'command.association_revision === current.association_revision', 'reply.request_id !== command.request_id',
    'result.action !== command.action', 'result.document_id !== command.document_id', 'result.outcome_unknown',
    'view.uncertain', 'queued = null; waitFor = null;']) assert.ok(workflow.includes(text));
});

test('standalone neutral recovery never needs a slider, core, membership preview or measured anatomy', () => {
  const reset = control.slice(control.indexOf('function reset()'), control.indexOf('function checkOriginal()'));
  assert.ok(reset.includes('current.current.access.resetDisabled'));
  for (const forbidden of ['changeDisabled', 'reading.value', 'core.available', 'faceOk', 'selectionMatches']) {
    assert.equal(reset.includes(forbidden), false);
  }
  assert.ok(control.includes('disabled={access.resetDisabled} onClick={reset}'));
  assert.ok(model.includes('return [lipTexturePatch(0)]'));
  assert.ok(model.includes("parameter_path: '/amount', unset: false, value"));
  assert.ok(control.includes('不恢复继承，不清除其他范围或其他效果'));
  assert.ok(control.includes('缺少核心、有效读数或面部分析时仍可归零'));
});

test('visible bounds describe measured narrow-furrow attenuation, not broader handbook parity', () => {
  for (const text of ['当前有效来源图像（原图或已返回合成图）', '已测得的唇部窄暗纹',
    '官方说明涵盖明显唇纹、干皮死皮和小裂口', '不支持干皮修复或完整裂口重建', '不代表官方完整效果',
    '不是唇妆饱和度、明度、立体度或口红素材', '不是大范围模糊或 AI 祛瑕疵',
    '不提供手动涂抹审核', '不宣称新增唇部分割', '每个目标必须独立通过当前来源、唇部支撑与暗纹证据检查',
    '核心就绪不等于此脸可处理', '非零强度不保证可见变化', '仅支持 RGB SDR，不宣称 HDR 支持',
    '显示 0 至 100 对应内部 0 至 1', '不是官方标定', '验收均未运行（UNRUN）', '祛除瑕疵功能族仍未完整验收']) {
    assert.ok(control.includes(text));
  }
});
