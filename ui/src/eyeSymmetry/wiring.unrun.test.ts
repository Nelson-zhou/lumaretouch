// AUTHORED / UNRUN. Source-contract fixtures only. Imports, execution, compilation and mounted UI acceptance were NOT performed.
import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
const source = (path: string) => readFileSync(new URL(path, import.meta.url), 'utf8');
const panel = source('../components/RetouchPanel.tsx'), control = source('./EyeSymmetryControl.tsx'), model = source('./model.ts');
const branch = panel.slice(panel.indexOf('if (kind === "eye_symmetry.family")'), panel.indexOf('if (kind === "eye.family")'));

test('all four exact PC-32470 paths route to one real section containing scalar and reference controls', () => {
  for (const [path, kind] of [['眼睛对称', 'family'], ['眼睛对称/水平对称', 'horizontal'],
    ['眼睛对称/大小对称', 'size'], ['眼睛对称/参考眼选择', 'reference']]) {
    assert.ok(source('../spec/refine.json').includes(`"path": "${path}"`));
    assert.ok(panel.includes(`"PC-32470|${path}": "eye_symmetry.${kind}"`));
  }
  assert.equal((panel.match(/"PC-32470\|[^"\n]+": "eye_symmetry\./g) ?? []).length, 4);
  assert.ok(branch.includes('<EyeSymmetryControl key={leaf.path}'));
  assert.ok(branch.includes('if (kind.startsWith("eye_symmetry.")) return null'));
  for (const text of ['data-control-id={EYE_SYMMETRY_CONTROL_IDS.family}', 'data-control-id={EYE_SYMMETRY_CONTROL_IDS[control]}',
    'data-control-id={EYE_SYMMETRY_CONTROL_IDS.reference}', "(['horizontal', 'size'] as const).map", '<Slider', '<ReferenceChoice',
    '<select aria-label="当前范围大小对称的参考眼"', 'onChoose={commitReference}']) assert.ok(control.includes(text));
});

test('existing eye light, eye shape, brightness, teeth and adjacent portrait routes are preserved', () => {
  for (const text of ['"PC-32470|眼神光": "eye_light.family"', '"PC-32470|眼神光/水平位置": "eye_light.horizontal"',
    '"PC-32470|亮眼/眼白": "enh.sclera"', '"PC-32470|眼白净化": "enh.sclera_purify"',
    '"PC-32470|祛红眼": "enh.red_eye"', '"PC-32470|亮眼/眼睛高光": "enh.catchlight"',
    '"PC-32469|牙齿美白/明度": "enh.teeth_brightness"', '"PC-32466|脸型/人中": "philtrum.amount"',
    '"PC-32466|眼睛": "eye.family"', '"PC-32466|嘴巴": "mouth.family"',
    '<EyeLightPanel', '<EyeShapeControls', '<PhiltrumControl', '<ChinLengthControl', '<LegacySmallChinControl',
    '经典: { slim_face: 0.22, big_eye: 0.04, small_chin: 0.14, smile: 0 }']) assert.ok(panel.includes(text));
});

test('unmanaged documents refuse, with no alternate eye-shape or direct-native mutation fallback', () => {
  for (const text of ['if (!doc?.people) return <section', '眼睛对称暂不可用',
    '不会改用眼形大小、眼球调整、旧版大眼或像素镜像替代']) assert.ok(branch.includes(text));
  for (const forbidden of ['runDeform', 'runHistory', 'invoke(', 'runEyeShape', 'setStrength', 'amounts.big_eye',
    '<EyeShapeControls', '<EyeLightPanel']) assert.equal(branch.includes(forbidden), false);
  for (const forbidden of ['runDeform', 'runEyeShape', 'runHistory', 'invoke(', '../eyeShape/', '../eyeLight/', '../deform/']) {
    assert.equal(control.includes(forbidden), false); assert.equal(model.includes(forbidden), false);
  }
});

test('strict native enum DTO and dedicated capability are wired without broadening other leaf types', () => {
  const native = source('../native.ts');
  assert.ok(native.includes("export type EyeSymmetryReference = 'auto' | 'left' | 'right'"));
  assert.ok(native.includes('export type EyeSymmetryRecipe = {version: 1; horizontal: number; size: number; reference: EyeSymmetryReference}'));
  assert.ok(model.includes("import type {EyeSymmetryRecipe, EyeSymmetryReference} from '../native'"));
  assert.ok(native.includes('eye_symmetry_available?: boolean')); assert.ok(native.includes('eye_symmetry_reason?: string | null'));
  assert.ok(source('../people/model.ts').includes("'lnx.eye_symmetry.v1': '眼睛对称（独立水平与大小，参考眼仅用于大小）'"));
  assert.ok(source('../people/model.ts').includes('export type ParameterValue = number | boolean | string'));
  assert.ok(native.includes('modules: Record<string, Record<string, unknown>>'));
  assert.ok(model.includes("Object.keys(recipe).sort().join(',') !== 'horizontal,reference,size,version'"));
});

test('canonical people owner and competing-editor fences are used for original and returned composites alike', () => {
  for (const text of ['people={props.people}', 'capability={status?.ready_caps}', 'blocked={dim',
    'props.hairBusy', 'props.whiteBalanceBusy', 'portraitRequestsBusy()', 'status?.edit_queue?.in_flight',
    'status?.edit_queue?.pending', 'status?.edit_queue?.closed', 'faceOk={props.faceOk}', 'faceWhy={props.faceWhy}']) assert.ok(branch.includes(text));
  for (const text of ['enabled: people.enabled', 'pending: people.state.pending', 'uncertain: people.state.uncertain',
    'externalBusy: blocked', 'people.patch(patches)', 'eyeSymmetrySizePatches(value, reference)',
    "eyeSymmetryPatch('reference', value)", 'dispatch(eyeSymmetryResetPatches())']) assert.ok(control.includes(text));
  assert.equal((control.match(/people\.patch\(/g) ?? []).length, 1);
  for (const forbidden of ['createPeopleWorkflow', 'people.submit(', 'people.submitCaptured(', 'latestIntent', 'runPeopleRequest']) assert.equal(control.includes(forbidden), false);
});

test('shared scalar and string choices remain blank, while actual effective/provenance and explicit intent stay separate', () => {
  for (const text of ["target?.scope === 'face' ? reading.value : null", 'reading.overridePresent ? reading.override',
    'resolved.operations[EYE_SYMMETRY_OPERATION]?.[`/${key}`]', 'view.editing_overrides[EYE_SYMMETRY_OPERATION]']) assert.ok(model.includes(text));
  for (const text of ['display(reading.value)', 'display(reading.override)', 'provenance(view, reading.source)',
    'display(access.reference.reading.value)', 'display(access.reference.reading.override)',
    "useState('')", "useState<string>(value ?? '')", 'choice === null', 'parseEyeSymmetryChoice(text)',
    'item.editValue !== null', 'value={item.editValue * 100}', 'min={0} max={100}',
    '不把所选人脸的继承参数复制给其他人物', '保留各目标的参考眼']) assert.ok(control.includes(text));
  for (const forbidden of ['reading.value ?? 0', 'editValue ?? 0', "editValue ?? 'auto'", 'neutralEyeSymmetry()', 'onBlur=']) assert.equal(control.includes(forbidden), false);
  const reference = control.slice(control.indexOf('function ReferenceChoice'), control.indexOf('/** One canonical owner'));
  assert.ok(reference.includes('onChange={event => setDraft(event.target.value)}'));
  assert.ok(reference.includes('onChoose(draft)')); assert.equal(reference.includes('Number('), false);
});

test('binding and owner changes reject old drafts/callbacks, repeated dispatch and stale reply errors', () => {
  for (const text of ['owner.current.patch !== people.patch || owner.current.check !== people.check',
    'owner.current.generation + 1', 'eyeSymmetryBindingKey(view), owner.current.generation',
    'mounted.current && current.current.binding === binding', 'mounted.current = false',
    'current.current.patch === people.patch && current.current.check === people.check',
    'if (!stillCurrent() || submitted.current) return', 'submitted.current = true', '}, [binding, people.state])',
    'key={`${binding}:${control}`}', 'key={`${binding}:${control}:choice`}', 'key={`${binding}:reference`}',
    'if (!stillCurrent() || checking.current) return', 'if (stillCurrent()) note(String(error))']) assert.ok(control.includes(text));
  for (const text of ['view.groups, view.persons, view.links, view.faces', 'view.binding, view.revision, view.association_revision',
    'view.resolved?.operations[EYE_SYMMETRY_OPERATION]', 'view.refusals']) assert.ok(model.includes(text));
});

test('uncertain outcomes query only the original receipt and preserve raw engine refusals', () => {
  for (const text of ['people.check()', '查询原请求结果（不重发修改）', 'people.state.message',
    'view?.refusals?.map', '{refusal.reason}', '以下保留引擎原始原因']) assert.ok(control.includes(text));
  const workflow = source('../people/workflow.ts');
  for (const text of ["action: 'patch', payload: {patches}", 'command.document_epoch === current.binding.document_epoch',
    'command.document_revision === current.binding.document_revision', 'command.state_revision === current.revision',
    'command.association_revision === current.association_revision', 'reply.request_id !== command.request_id',
    'result.action !== command.action', 'result.document_id !== command.document_id', 'result.outcome_unknown',
    'view.uncertain', 'queued = null; waitFor = null;']) assert.ok(workflow.includes(text));
});

test('neutral reset is atomic without anatomy or native gates; reference-only auto is not incorrectly treated as reset', () => {
  const reset = control.slice(control.indexOf('function resetAll()'), control.indexOf('function checkOriginal()'));
  assert.ok(reset.includes('if (!stillCurrent() || current.current.access.horizontal.resetDisabled) return'));
  assert.ok(reset.includes('dispatch(eyeSymmetryResetPatches())'));
  for (const forbidden of ['changeDisabled', 'core.available', 'faceOk', 'reading.', 'editValue']) assert.equal(reset.includes(forbidden), false);
  const reference = control.slice(control.indexOf('function commitReference'), control.indexOf('function resetAll'));
  assert.ok(reference.includes('current.current.access.reference.changeDisabled'));
  assert.equal(reference.includes('resetDisabled'), false);
  assert.ok(model.includes("return [eyeSymmetryPatch('horizontal', 0), ...eyeSymmetrySizePatches(0, 'auto')]"));
  assert.ok(control.includes('choice === 0 ? resetDisabled : changeDisabled'));
  for (const text of ['缺少核心、有效读数或双眼分析时仍可重置', '归零写入中性覆盖，不恢复继承',
    '仅将参考眼改为自动不等于归零', '两项强度均为 0 时，无论参考眼为何都无几何效果']) assert.ok(control.includes(text));
  for (const forbidden of ["'lnx.eye_shape.v1'", "'lnx.deform.v1'", "'lnx.eye_light.v1'", 'unset: true']) assert.equal(model.includes(forbidden), false);
});

test('UI states honest geometry, reference, source, conservative refusal and no-op limits without invented measurements', () => {
  for (const text of ['参考眼只用于大小对称', '当前来源独立测得的头部坐标轴', '保持双眼中心的中点',
    '不是强制对齐画面水平线', '不是以某只参考眼固定另一眼', '头部倾斜时画面横坐标也可能改变',
    '实测开口面积', '局部等比缩放', '不是只拉宽', '不按宽度猜测', '左右指人物自身，不是画面左右',
    '不会把一眼的像素复制、镜像到另一眼', '原图或已返回合成图', '真实双眼证据',
    '不能从眼睛连线反推水平基准', '会保守拒绝', '不生成睁眼', '不补造缺失部位',
    '已经对称时真正的无变化是有效结果', '不人为添加位移', '核心就绪不代表此脸或当前组合可用',
    '不推测测量结果', '不绕过手动液化等兼容性检查', '本产品强度量程，不是官方标定',
    '均未运行（UNRUN）', '眼睛增强功能族仍未完整验收']) assert.ok(control.includes(text));
  for (const invented of ['eye_symmetry_facts', 'measured_eye_area', 'horizontal_applied', 'composition_available', 'skipCompatibility']) {
    assert.equal(control.includes(invented), false); assert.equal(model.includes(invented), false);
  }
});
