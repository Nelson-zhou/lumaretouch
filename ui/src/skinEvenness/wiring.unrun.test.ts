// AUTHORED / UNRUN. Source-contract fixtures only; not imported, compiled, executed or UI accepted.
import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
const source = (path: string) => readFileSync(new URL(path, import.meta.url), 'utf8');
const panel = source('../components/RetouchPanel.tsx'), control = source('./SkinEvennessControl.tsx');
const model = source('./model.ts');
const route = panel.slice(panel.indexOf('case "skin_evenness.amount":'), panel.indexOf('case "skin_colour.temperature":'));
const legacy = route.slice(route.indexOf('<details data-legacy-skin-compat="true">'));

test('only the exact face-evenness leaf routes to the dedicated partial implementation', () => {
  assert.ok(source('../spec/refine.json').includes('"path": "AI肤色统一（脸部）"'));
  assert.ok(panel.includes('"PC-32465|AI肤色统一（脸部）": "skin_evenness.amount"'));
  assert.equal((panel.match(/"PC-32465\|[^"\n]+": "skin_evenness\./g) ?? []).length, 1);
  assert.equal(panel.includes('"PC-32465|AI肤色统一（脸部）": "skin.broad"'), false);
  assert.equal(panel.includes('"PC-32465|AI肤色统一（身体）": "skin_evenness.amount"'), false);
  assert.equal(panel.includes('"PC-32465|多人肤色统一": "skin_evenness.amount"'), false);
  assert.ok(route.includes('<SkinEvennessControl'));
  assert.ok(control.includes('data-control-id={SKIN_EVENNESS_CONTROL_ID}'));
  assert.ok(control.includes('aria-label={SKIN_EVENNESS_LABEL}'));
  assert.ok(model.includes("'LNX-REF-PC-32465-C-60b7c0e3d1'"));
  assert.ok(model.includes("'脸部色度均匀（原片自参考）'"));
  assert.ok(source('../people/model.ts').includes("'lnx.skin_evenness.v1': '脸部色度均匀（原片自参考）'"));
});

test('legacy frequency gain remains accessible, photograph-scoped and semantically unchanged', () => {
  for (const text of ['data-legacy-skin-compat="true"', '旧版磨皮兼容控制（照片级参数，非脸部色度均匀）',
    '旧版照片级磨皮强度（皮肤掩膜）', 'value={Math.round((doc?.strength ?? 0) * 100)} min={0} max={100}',
    'onChange={value => commitSkin({ strength: value / 100 })}', 'onReset={() => commitSkin({ strength: 0 })}',
    '旧版大尺度频率增益（0 至 2，非肤色统一）', 'value={params.broad_gain ?? 0} min={0} max={2}',
    'onChange={value => commitSkin({ broad: value })}', 'onReset={() => commitSkin({ broad: 0 })}',
    '不随人物编辑范围切换', '整张照片的皮肤掩膜', '不进行参数迁移、换算或自动清除',
    '旧版强度 0 关闭旧磨皮', '大尺度增益 0 只是旧默认值，不代表中性或关闭',
    '恢复旧版强度默认值（0，关闭旧磨皮）', '恢复旧版大尺度增益默认值（0，非中性）',
    '不受上方新功能归零按钮影响', '不支持的衍生来源路径仍会拒绝']) assert.ok(legacy.includes(text));
  assert.ok(route.includes('const legacyDisabled = !doc || dim || !!skinWhy || props.people.state.pending || props.people.state.uncertain'));
  assert.ok(legacy.includes('disabled={legacyDisabled}')); assert.ok(legacy.includes('title={skinWhy ||'));
  const commit = panel.slice(panel.indexOf('const commitSkin ='), panel.indexOf('const commitPeopleLeaves ='));
  assert.ok(commit.includes('if (!doc || dim || props.people.state.pending || props.people.state.uncertain) return'));
  assert.ok(commit.includes('if (skinWhy)'));
  assert.ok(commit.includes('setStrength(patch.strength, skinEditOptions(patch))'));
  assert.ok(source('../skinScope.ts').includes('channel: "skin" as const'));
  assert.ok(source('../skinScope.ts').includes('...(patch.broad === undefined ? {} : {broadGain: patch.broad})'));
  assert.ok(source('../native.ts').includes('broadGain: opts?.broadGain'));
  assert.equal(legacy.includes('people.patch('), false);
  assert.equal(legacy.includes('skinEvennessPatch('), false);
  assert.equal(legacy.includes('useEffect'), false);
});

test('adjacent skin and lip controls retain their independent meaning and routes', () => {
  for (const existing of ['"PC-32465|高低频磨皮-脸部/身体": "skin.strength"',
    '"PC-32465|质感磨皮": "skin.detail"', '"PC-32465|水润磨皮-脸部/身体": "skin.radius"',
    '"PC-32465|肤色色温": "skin_colour.temperature"', '"PC-32465|肤色色调": "skin_colour.tint"',
    '"PC-32465|肤色美白": "skin_finish.whitening"', '"PC-32465|皮肤红润": "skin_finish.rosiness"',
    '"PC-32465|皮肤质感/光泽度": "skin_gloss.amount"',
    '"PC-32465|皮肤质感/纹理度": "skin_texture.texture"', '"PC-32465|皮肤质感/清晰度": "skin_texture.clarity"',
    '"PC-32464|面部祛瑕疵/唇纹修整": "lip_texture.amount"']) assert.ok(panel.includes(existing));
  for (const forbidden of ['runLipMakeup', 'runEnhance', 'runGrade', 'runExposure', 'runHistory', 'setStrength',
    'invoke(', 'createPeopleWorkflow', 'people.submit(', 'people.submitCaptured(', 'broad_gain', 'detail_gain',
    'lnx.skin_colour.v1', 'lnx.skin_finish.v1', 'lnx.skin_gloss.v1', 'lnx.skin_texture.v1',
    'canvas', 'preview_src']) {
    assert.equal(control.includes(forbidden), false); assert.equal(model.includes(forbidden), false);
  }
});

test('dedicated readiness and all competing-owner fences are wired without semantic-capability aliases', () => {
  assert.ok(source('../native.ts').includes('skin_evenness_available?: boolean'));
  assert.ok(source('../native.ts').includes('skin_evenness_reason?: string | null'));
  for (const text of ['people={props.people}', 'capability={status?.ready_caps}', 'blocked={dim', 'props.hairBusy',
    'props.whiteBalanceBusy', 'portraitRequestsBusy()', 'status?.edit_queue?.in_flight', 'status?.edit_queue?.pending',
    'status?.edit_queue?.closed', 'faceOk={props.faceOk}', 'faceWhy={props.faceWhy}', 'Slider={Slider}']) assert.ok(route.includes(text));
  for (const forbidden of ['skin_colour_available', 'skin_finish_available', 'skin_gloss_available',
    'skin_texture_available', 'skin_semantics_available', 'lip_texture_available']) assert.equal(model.includes(forbidden), false);
});

test('valid selected-face provenance is distinct from explicit shared target intent and unknown readback', () => {
  for (const text of ['targetLabel(view)', 'sourceLabel(source)', 'display(reading.value)', 'reading.overridePresent',
    'access.editValue !== null', 'value={access.editValue * 100}', 'min={0} max={100}',
    'onChange={value => commit(value / 100)}', "useState('')", 'parseSkinEvennessChoice(text)',
    'key={`${binding}:amount`}', 'key={`${binding}:choice`}', '留空不等于 0',
    '不把某一张脸的继承值复制给其他人物']) assert.ok(control.includes(text));
  for (const text of ['const source = resolved.operations[SKIN_EVENNESS_OPERATION]?.[path]',
    'sourceMatches(view, selected.face_ref, source)', 'source.contributing_targets.every(belongs)',
    "view?.editing_target?.scope === 'face' ? reading.value : null", "link.state === 'confirmed'",
    'link.confirmation_revision <= view.association_revision', 'view.groups, view.persons, view.links']) assert.ok(model.includes(text));
  assert.equal(control.includes('reading.value ?? 0'), false);
  const choice = control.slice(control.indexOf('function AmountChoice'), control.indexOf('export function SkinEvennessControl'));
  assert.equal(choice.includes('onBlur='), false); assert.equal(choice.includes('useEffect'), false);
});

test('canonical owner, owner generation, mounted guard and submission latch fence late or repeated writes', () => {
  for (const text of ['people.patch(patches)', 'dispatch([skinEvennessPatch(value)])', 'dispatch(skinEvennessResetPatches())',
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

test('standalone neutral recovery needs neither slider, selected preview, core nor anatomy', () => {
  const reset = control.slice(control.indexOf('function reset()'), control.indexOf('function checkOriginal()'));
  assert.ok(reset.includes('current.current.access.resetDisabled'));
  for (const forbidden of ['changeDisabled', 'reading.value', 'core.available', 'faceOk', 'selectionMatches']) {
    assert.equal(reset.includes(forbidden), false);
  }
  assert.ok(control.includes('disabled={access.resetDisabled} onClick={reset}'));
  assert.ok(model.includes('return [skinEvennessPatch(0)]'));
  assert.ok(model.includes("parameter_path: '/amount', unset: false, value"));
  assert.ok(control.includes('不恢复继承，不清除其他范围或其他效果'));
  assert.ok(control.includes('缺少核心、有效读数或面部分析时仍可归零'));
});

test('visible limits describe measured same-face chroma and partial status, not official AI parity', () => {
  for (const text of ['当前有效来源图像（原图或已返回合成图）', '测得的低频色度为自身参考',
    '官方条目“AI肤色统一（脸部）”', '当前仅部分实现', '不是学习型瑕疵模型',
    '不代表官方完整效果或专有算法等效', '仅在本项处理阶段保留输入的线性亮度',
    '不承诺其他效果叠加后的最终亮度不变', '不是提亮、美白、大范围模糊或全图染色',
    '不识别妆容，不分离物理光照与皮肤材质', '不会自动判断这些差异是否应当去除',
    '每张脸必须独立通过当前来源、面部皮肤支撑与色度证据检查',
    '参考只来自该脸', '不是多人肤色匹配，也不支持身体肤色统一',
    '核心就绪不等于此脸可处理', '非零强度不保证可见变化', '仅支持 RGB SDR，不宣称 HDR 支持',
    '显示 0 至 100 对应内部 0 至 1', '不是官方标定', '验收均未运行（UNRUN）',
    '皮肤功能族仍未完整验收']) assert.ok(control.includes(text));
});
