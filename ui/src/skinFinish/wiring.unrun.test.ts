// AUTHORED / UNRUN. Source contracts only, not compiled or exercised UI acceptance.
import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
const source = (path: string) => readFileSync(new URL(path, import.meta.url), 'utf8');
const panel = source('../components/RetouchPanel.tsx'), control = source('./SkinFinishControl.tsx');
const bodyPanel = source('../skinColour/SkinBodyPanel.tsx'), bodyModel = source('../skinColour/bodyReviewModel.ts');

test('only exact whitening and rosiness handbook paths connect to separate finish controls', () => {
  for (const [path, key] of [['肤色美白', 'whitening'], ['皮肤红润', 'rosiness']]) {
    assert.ok(source('../spec/refine.json').includes(`"path": "${path}"`));
    assert.ok(panel.includes(`"PC-32465|${path}": "skin_finish.${key}"`));
    assert.ok(panel.includes(`case "skin_finish.${key}":`));
  }
  assert.equal((panel.match(/"PC-32465\|[^"\n]+": "skin_finish\./g) ?? []).length, 2);
  for (const existing of ['"PC-32465|肤色色温": "skin_colour.temperature"', '"PC-32465|肤色色调": "skin_colour.tint"',
    '"PC-32465|AI肤色统一（脸部）": "skin.broad"', '"PC-32465|高低频磨皮-脸部/身体": "skin.strength"']) assert.ok(panel.includes(existing));
  assert.ok(control.includes('data-control-id={SKIN_FINISH_CONTROL_IDS[control]}'));
});

test('existing people owner is the only mutation and recovery route, with unsigned authoritative readback', () => {
  for (const text of ['people.patch([skinFinishPatch(control, value)])', 'people.patch(SKIN_FINISH_KEYS.map(key => skinFinishPatch(key, 0)))',
    'reading.value !== null', 'targetLabel(view)', 'sourceLabel(reading.source)', 'min={0} max={100}',
    'onChange={value => commit(value / 100)}', 'current.current.binding !== binding',
    'current.current.access.resetDisabled : current.current.access.changeDisabled', 'people.check()', 'key={`${binding}:${control}`}']) assert.ok(control.includes(text));
  for (const forbidden of ['runEnhance', 'runGrade', 'runExposure', 'runHistory', 'invoke(', 'createPeopleWorkflow']) assert.equal(control.includes(forbidden), false);
  assert.ok(source('./model.ts').includes('const source = resolved.operations[SKIN_FINISH_OPERATION]?.[path]'));
  assert.ok(source('../people/model.ts').includes("'lnx.skin_finish.v1': '肤色美白与皮肤红润（手动强度）'"));
});

test('capability, edit queue and other portrait owners gate changes without claiming measurement readiness', () => {
  assert.ok(source('../native.ts').includes('skin_finish_available?: boolean'));
  assert.ok(source('../native.ts').includes('skin_finish_reason?: string | null'));
  for (const fence of ['props.hairBusy', 'props.whiteBalanceBusy', 'portraitRequestsBusy()',
    'status?.edit_queue?.in_flight', 'status?.edit_queue?.pending', 'status?.edit_queue?.closed']) assert.ok(panel.includes(fence));
  for (const text of ['不是全图曝光或单独色温替代', '不是局部腮红绘制', '不推断疾病、血液循环或健康程度',
    '不覆盖全身皮肤', '不是自动全身选择', '手动强度调整与手动辅助身体扩展', '核心就绪不等于此脸可用',
    '真实面部皮肤语义分割及 478 点人脸分析', '不是手册规定', '皮肤功能族仍未完整验收']) assert.ok(control.includes(text));
});

test('finish review stays independent and needs loaded real images plus explicit separate consent', () => {
  assert.ok(control.includes('control === \'whitening\' && <SkinBodyPanel family="skin_finish"'));
  assert.ok(control.includes("skinBodyAttached(view, 'skin_finish')"));
  assert.ok(bodyPanel.includes("family = 'skin_colour'"));
  assert.ok(bodyPanel.includes('`${family}:${skinColourBindingKey(view)}`'));
  for (const text of ['skinBodyFamilyMatches(payload, family)', 'referenceMatches(payload, view, family)',
    'previewMatches(payload, reference, request.review, family)', 'people.submitCaptured(command)',
    'setMask(emptyBodyMask())', 'setFlags(emptyFlags())', 'comparisonLoaded', 'draftMatches',
    'naturalWidth === image.width', 'naturalHeight === image.height', '独立接受{operationLabel}',
    'preview_id: preview.preview_id, reviewed: true', 'receipt.result.payload_released',
    'busy || !canDetach || attached !== true', '已有色温色调的身体范围不会复制、扩大或自动授权本功能']) assert.ok(bodyPanel.includes(text));
  assert.ok(bodyModel.includes("identity.family === family && identity.operation_id === SKIN_BODY_FAMILIES[family].operation"));
  assert.ok(bodyModel.includes('identity.family === undefined && identity.operation_id === undefined'));
  assert.equal(bodyPanel.includes('runHistory'), false);
});

test('finish admission uses existing bounded people transport and correlated receipt lifecycle', () => {
  const bridge = source('../../src-tauri/src/people_api.rs'), workflow = source('../people/workflow.ts');
  for (const action of ['skin_finish_body_reference', 'skin_finish_body_preview', 'skin_finish_body_confirm', 'skin_finish_body_detach']) {
    assert.ok(bridge.includes(`"${action}"`)); assert.ok(source('../people/model.ts').includes(`'${action}'`)); assert.ok(bodyModel.includes(`'${action}'`));
  }
  assert.ok(bridge.includes('request.to_string().len() > 256 * 1024'));
  assert.ok(bodyModel.includes('byteLength <= 192 * 1024'));
  assert.ok(workflow.includes('lastBodyResult: skinBodyReceiptCurrent(command, result, current)'));
  assert.ok(workflow.includes('!skinBodyReceiptCurrent(view.lastBodyResult.command, view.lastBodyResult.result, value)'));
  assert.ok(workflow.includes('bodyPayloadInvalid'));
  assert.ok(workflow.includes('审核回执的功能身份不匹配'));
  assert.ok(bodyModel.includes('result.action !== command.action'));
  assert.ok(bodyModel.includes('result.request_id !== command.request_id'));
});
