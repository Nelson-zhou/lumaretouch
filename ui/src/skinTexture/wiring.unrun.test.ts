// AUTHORED / UNRUN. Source-contract fixtures only; not imported, compiled, executed or UI-accepted.
import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
const source = (path: string) => readFileSync(new URL(path, import.meta.url), 'utf8');
const panel = source('../components/RetouchPanel.tsx'), control = source('./SkinTextureControl.tsx');
const model = source('./model.ts');

test('only the exact two skin-texture handbook leaves are connected', () => {
  for (const [path, key] of [['皮肤质感/纹理度', 'texture'], ['皮肤质感/清晰度', 'clarity']]) {
    assert.ok(source('../spec/refine.json').includes(`"path": "${path}"`));
    assert.ok(panel.includes(`"PC-32465|${path}": "skin_texture.${key}"`));
    assert.ok(panel.includes(`case "skin_texture.${key}":`));
  }
  assert.equal((panel.match(/"PC-32465\|[^"\n]+": "skin_texture\./g) ?? []).length, 2);
  assert.ok(panel.includes('<SkinTextureControl key={leaf.path}'));
  assert.ok(control.includes('data-control-id={SKIN_TEXTURE_CONTROL_IDS[control]}'));
  for (const existing of ['"PC-32465|高低频磨皮-脸部/身体": "skin.strength"', '"PC-32465|质感磨皮": "skin.detail"',
    '"PC-32465|AI肤色统一（脸部）": "skin.broad"', '"PC-32465|水润磨皮-脸部/身体": "skin.radius"',
    '"PC-32465|肤色色温": "skin_colour.temperature"', '"PC-32465|肤色色调": "skin_colour.tint"',
    '"PC-32465|肤色美白": "skin_finish.whitening"', '"PC-32465|皮肤红润": "skin_finish.rosiness"',
    '"PC-32465|皮肤质感/光泽度": "skin_gloss.amount"']) assert.ok(panel.includes(existing));
});

test('existing people owner handles scalar updates and one-request atomic neutral recovery', () => {
  for (const text of ['people.patch([skinTexturePatch(control, value)])', 'people.patch(skinTextureResetPatches())',
    'reading.value !== null', 'targetLabel(view)', 'sourceLabel(reading.source)', 'reading.overridePresent',
    "min={control === 'texture' ? -100 : 0} max={100}", 'onChange={value => commit(value / 100)}',
    'current.current.access.resetDisabled : current.current.access.changeDisabled',
    'mounted.current && current.current.binding === binding && current.current.control === control',
    'mounted.current = false', 'key={`${binding}:${control}`}', 'people.check()', 'if (stillCurrent()) note(String(error))',
    'onClick={() => commit(0)}', 'onClick={resetBoth}', 'if (!stillCurrent() || current.current.access.resetDisabled) return']) {
    assert.ok(control.includes(text));
  }
  assert.ok(model.includes('return SKIN_TEXTURE_KEYS.map(key => skinTexturePatch(key, 0))'));
  assert.equal((control.match(/people\.patch\(/g) ?? []).length, 2);
  for (const forbidden of ['runEnhance', 'runGrade', 'runExposure', 'runHistory', 'setStrength', 'invoke(',
    'createPeopleWorkflow', 'people.submit(', 'people.submitCaptured(', 'detail_gain']) assert.equal(control.includes(forbidden), false);
  assert.ok(model.includes('const source = resolved.operations[SKIN_TEXTURE_OPERATION]?.[path]'));
  assert.ok(source('../people/model.ts').includes("'lnx.skin_texture.v1': '面部纹理度与皮肤清晰度（已有细节）'"));
});

test('the exact two leaves use dedicated readiness and every existing competing-owner fence', () => {
  assert.ok(source('../native.ts').includes('skin_texture_available?: boolean'));
  assert.ok(source('../native.ts').includes('skin_texture_reason?: string | null'));
  const textureCase = panel.slice(panel.indexOf('case "skin_texture.texture":'), panel.indexOf('case "slim_face.v2":'));
  for (const text of ['people={props.people}', 'capability={status?.ready_caps}', 'blocked={dim', 'props.hairBusy',
    'props.whiteBalanceBusy', 'portraitRequestsBusy()', 'status?.edit_queue?.in_flight', 'status?.edit_queue?.pending',
    'status?.edit_queue?.closed', 'faceOk={props.faceOk}', 'faceWhy={props.faceWhy}']) assert.ok(textureCase.includes(text));
  for (const forbidden of ['skin_colour_available', 'skin_finish_available', 'skin_gloss_available']) assert.equal(model.includes(forbidden), false);
});

test('clear source, existing-detail, face-only, unsigned-sharpening and acceptance limits remain visible', () => {
  for (const text of ['当前有效来源图像（原图或已返回合成图）', '向左减少纹理，向右增加纹理',
    '独立于质感磨皮的细节保留', '已有面部皮肤细节进行局部锐化', '不是全图粗尺度对比度', '不替代全图锐化',
    '仅作用于已测得的面部皮肤，不扩展到身体', '不沿用其他皮肤功能的身体范围',
    '官方说明没有明确保证纹理度的身体覆盖', '不是 AI 修复', '不生成或恢复来源中不存在的皮肤细节',
    '不恢复继承', '缺少核心或有效面部分析时仍可归零', '真实面部皮肤语义分割及 478 点人脸分析',
    '核心就绪不等于此脸可用', '非零数值不保证可见变化', '仅支持 RGB SDR，不宣称 HDR 支持',
    '纹理度显示 -100 至 100 对应内部 -1 至 1', '清晰度显示 0 至 100 对应内部 0 至 1',
    '这是本产品量程，不是手册规定', '噪声、边缘与彩色光照的真实照片验收尚未运行', '皮肤功能族仍未完整验收']) {
    assert.ok(control.includes(text));
  }
  for (const forbidden of ['SkinBodyPanel', 'skinBodyAttached', 'skinBodyReport', 'bodyReviewModel', 'skin_texture_body']) {
    assert.equal(control.includes(forbidden), false);
    assert.equal(model.includes(forbidden), false);
  }
  assert.equal(source('../people/model.ts').includes("'skin_texture_body_reference'"), false);
});

test('zero buttons remain independent of readable sliders, available core and face analysis', () => {
  const valueBlock = control.indexOf('{reading.value !== null && <>');
  const valueBlockEnd = control.indexOf('</>}', valueBlock);
  assert.ok(control.indexOf('onClick={() => commit(0)}') > valueBlockEnd);
  assert.ok(control.indexOf('onClick={resetBoth}') > valueBlockEnd);
  const resetFunction = control.slice(control.indexOf('function resetBoth()'), control.indexOf('function checkOriginal()'));
  assert.ok(resetFunction.includes('current.current.access.resetDisabled'));
  assert.equal(resetFunction.includes('changeDisabled'), false);
  assert.equal(resetFunction.includes('core.available'), false);
  assert.equal(resetFunction.includes('faceOk'), false);
  assert.equal(resetFunction.includes('reading.value'), false);
  assert.ok(control.includes('同一人物请求将本范围的纹理度与清晰度同时设为 0'));
});

test('updates reuse generic bounded correlated people transactions, not a new history or retry owner', () => {
  const workflow = source('../people/workflow.ts');
  for (const text of ["action: 'patch', payload: {patches}", 'command.document_epoch === current.binding.document_epoch',
    'command.document_revision === current.binding.document_revision', 'command.state_revision === current.revision',
    'command.association_revision === current.association_revision', 'reply.request_id !== command.request_id',
    'result.action !== command.action', 'result.document_id !== command.document_id', 'result.outcome_unknown',
    'view.uncertain', 'queued = null; waitFor = null;']) assert.ok(workflow.includes(text));
  assert.ok(control.includes('查询原请求结果（不重发修改）'));
});
