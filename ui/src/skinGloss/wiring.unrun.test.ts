// AUTHORED / UNRUN. Static source contracts only, not compiled or exercised UI acceptance.
import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
const source = (path: string) => readFileSync(new URL(path, import.meta.url), 'utf8');
const panel = source('../components/RetouchPanel.tsx'), control = source('./SkinGlossControl.tsx');
const model = source('./model.ts');

test('only the exact gloss leaf connects, leaving distinct colour and finish leaves unchanged', () => {
  assert.ok(source('../spec/refine.json').includes('"path": "皮肤质感/光泽度"'));
  assert.ok(panel.includes('"PC-32465|皮肤质感/光泽度": "skin_gloss.amount"'));
  assert.equal((panel.match(/"PC-32465\|[^"\n]+": "skin_gloss\./g) ?? []).length, 1);
  assert.ok(panel.includes('case "skin_gloss.amount":'));
  assert.ok(panel.includes('<SkinGlossControl key={leaf.path}'));
  assert.ok(control.includes('data-control-id={SKIN_GLOSS_CONTROL_ID}'));
  for (const existing of ['"PC-32465|肤色色温": "skin_colour.temperature"', '"PC-32465|肤色色调": "skin_colour.tint"',
    '"PC-32465|肤色美白": "skin_finish.whitening"', '"PC-32465|皮肤红润": "skin_finish.rosiness"',
    '"PC-32465|AI肤色统一（脸部）": "skin_evenness.amount"', '"PC-32465|高低频磨皮-脸部/身体": "skin.strength"']) {
    assert.ok(panel.includes(existing));
  }
  for (const compatibility of ['data-legacy-skin-compat="true"', 'value={params.broad_gain ?? 0} min={0} max={2}',
    'onChange={value => commitSkin({ broad: value })}', 'onReset={() => commitSkin({ broad: 0 })}',
    '大尺度增益 0 只是旧默认值，不代表中性或关闭']) assert.ok(panel.includes(compatibility));
});

test('the existing people owner is the only mutation and uncertain-receipt route', () => {
  for (const text of ['people.patch([skinGlossPatch(value)])', 'reading.value !== null', 'targetLabel(view)',
    'sourceLabel(reading.source)', 'reading.overridePresent', 'min={-100} max={100}', 'onChange={value => commit(value / 100)}',
    'current.current.binding !== binding', 'current.current.access.resetDisabled : current.current.access.changeDisabled',
    '!mounted.current', 'mounted.current = false', 'key={binding}', 'people.check()', 'onClick={() => commit(0)}']) {
    assert.ok(control.includes(text));
  }
  for (const forbidden of ['runEnhance', 'runGrade', 'runExposure', 'runHistory', 'invoke(', 'createPeopleWorkflow',
    'people.submit(', 'people.submitCaptured(', 'SkinBodyPanel', 'skinBodyAttached', 'skinBodyReport', 'bodyReviewModel']) {
    assert.equal(control.includes(forbidden), false);
  }
  assert.ok(model.includes("const source = resolved.operations[SKIN_GLOSS_OPERATION]?.['/amount']"));
  assert.ok(source('../people/model.ts').includes("'lnx.skin_gloss.v1': '面部已有高光光泽度（抑制与增强）'"));
});

test('gloss readiness and every existing competing-owner fence gate the actual gloss leaf', () => {
  assert.ok(source('../native.ts').includes('skin_gloss_available?: boolean'));
  assert.ok(source('../native.ts').includes('skin_gloss_reason?: string | null'));
  const glossCase = panel.slice(panel.indexOf('case "skin_gloss.amount":'), panel.indexOf('case "slim_face.v2":'));
  for (const text of ['people={props.people}', 'capability={status?.ready_caps}', 'blocked={dim', 'props.hairBusy',
    'props.whiteBalanceBusy', 'portraitRequestsBusy()', 'status?.edit_queue?.in_flight', 'status?.edit_queue?.pending',
    'status?.edit_queue?.closed', 'faceOk={props.faceOk}', 'faceWhy={props.faceWhy}']) assert.ok(glossCase.includes(text));
  assert.equal(model.includes('skin_colour_available'), false); assert.equal(model.includes('skin_finish_available'), false);
});

test('face-only existing-highlight semantics, no-observable-highlight no-op and SDR limits stay explicit', () => {
  for (const text of ['当前有效来源图像（原图或已返回合成图）', '真实面部皮肤范围', '抑制或增强已有高光', '不会绘制新高光', '不是全图曝光',
    '肤色色温色调、美白红润或磨皮的替代', '仅作用于面部皮肤，不扩展到身体', '不沿用其他皮肤功能的身体范围',
    '缺少可观察到的原有高光时，调整可能没有可见效果', '非零数值不保证像素发生变化',
    '不恢复继承', '缺少核心或有效面部分析时仍可归零', '真实面部皮肤语义分割及 478 点人脸分析',
    '核心就绪不等于此脸可用', '不是精确镜面反射分割', '不保证完美去油或恢复过曝细节',
    '仅支持 RGB SDR，不宣称 HDR 支持', '不是手册规定', '真实照片效果验收尚未运行', '皮肤功能族仍未完整验收']) {
    assert.ok(control.includes(text));
  }
});

test('amount patches reuse generic correlated people transactions, not new admission or history commands', () => {
  const workflow = source('../people/workflow.ts');
  for (const text of ["action: 'patch', payload: {patches}", 'command.document_epoch === current.binding.document_epoch',
    'command.document_revision === current.binding.document_revision', 'command.state_revision === current.revision',
    'command.association_revision === current.association_revision', 'reply.request_id !== command.request_id',
    'result.action !== command.action', 'result.document_id !== command.document_id', 'result.outcome_unknown',
    'view.uncertain', 'queued = null; waitFor = null;']) assert.ok(workflow.includes(text));
  assert.equal(control.includes('skin_gloss_body'), false);
  assert.equal(source('../people/model.ts').includes("'skin_gloss_body_reference'"), false);
});
