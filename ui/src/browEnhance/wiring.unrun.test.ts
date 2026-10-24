// AUTHORED / UNRUN. Source-contract fixtures only, not mounted interaction, type checking or runtime acceptance.
import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
const source = (path: string) => readFileSync(new URL(path, import.meta.url), 'utf8');
const panel = source('../components/RetouchPanel.tsx'), control = source('./BrowEnhanceControl.tsx');
const model = source('./model.ts');
const branch = panel.slice(panel.indexOf('case "brow_enhance.v1":'), panel.indexOf('case "chin_length.amount":'));

test('one exact handbook leaf renders complete bilateral controls; brow geometry and material routes remain', () => {
  assert.ok(source('../spec/refine.json').includes('"path": "眉毛增强"'));
  assert.ok(panel.includes('"PC-32471|眉毛增强": "brow_enhance.v1"'));
  assert.equal((panel.match(/"PC-32471\|[^"\n]+": "brow_enhance\./g) ?? []).length, 1);
  assert.ok(branch.includes('<BrowEnhanceControl key={leaf.path}'));
  assert.ok(control.includes('data-control-id={BROW_ENHANCE_CONTROL_ID}'));
  assert.ok(model.includes("BROW_ENHANCE_OPERATION = 'lnx.brow_enhance.v1'"));
  assert.ok(model.includes("BROW_ENHANCE_CONTROL_ID = 'LNX-REF-PC-32471-C-18765fa8ea'"));
  for (const original of ['"PC-32466|眉毛": "brow.family"', '"PC-32466|眉毛/粗细": "brow.thickness"',
    '"PC-32466|眉毛/眉距": "brow.spacing"', '"PC-32466|眉毛/倾斜": "brow.tilt"',
    '"PC-32466|眉毛/形状": "brow.arch"', '"PC-32466|眉毛/位置": "brow.position"',
    '"PC-32466|眉毛/眉头长短": "brow.inner_length"', '"PC-32466|眉毛/眉尾长短": "brow.outer_length"',
    '"PC-32471|局部妆容/眉毛": "browMakeup.family"', '"PC-32471|局部妆容/眉毛/RGB": "browMakeup.rgb"',
    '"PC-32471|局部妆容/眉毛/HEX": "browMakeup.hex"', '"PC-32471|唇妆增强": "lip.family"',
    '<BrowShapeControls key={leaf.path}', 'props.browMakeupPanel']) assert.ok(panel.includes(original));
});

test('unmanaged documents refuse explicitly, without material, geometry, exposure or direct-native fallback', () => {
  for (const text of ['if (!doc?.people) return <section', '眉毛增强暂不可用',
    '不会改用眉妆素材、眉形变形或通用曝光替代']) assert.ok(branch.includes(text));
  for (const forbidden of ['runDeform', 'runHistory', 'invoke(', 'runExposure', 'runBrowShape', 'runEnhance', 'setStrength']) {
    assert.equal(branch.includes(forbidden), false); assert.equal(control.includes(forbidden), false);
  }
  for (const operation of ["'lnx.brow_makeup.v1'", "'lnx.brow_shape.v1'", "'lnx.exposure.v1'", "'lnx.enhance.v1'"])
    assert.equal(model.includes(operation), false);
});

test('dedicated capability and editor fences feed only the existing people command owner', () => {
  assert.ok(source('../native.ts').includes('brow_enhance_available?: boolean'));
  assert.ok(source('../native.ts').includes('brow_enhance_reason?: string | null'));
  assert.ok(source('../people/model.ts').includes("'lnx.brow_enhance.v1': '眉毛增强（已有眉毛对比，左右独立）'"));
  for (const text of ['people={props.people}', 'capability={status?.ready_caps}', 'blocked={dim',
    'props.hairBusy', 'props.whiteBalanceBusy', 'portraitRequestsBusy()', 'status?.edit_queue?.in_flight',
    'status?.edit_queue?.pending', 'status?.edit_queue?.closed', 'faceOk={props.faceOk}', 'faceWhy={props.faceWhy}'])
    assert.ok(branch.includes(text));
  for (const text of ['people.patch(patches)', 'people.state.pending', 'people.state.uncertain',
    'people.state.message', 'note(String(error))']) assert.ok(control.includes(text));
  for (const forbidden of ["from '../native'", 'setInterval(', 'createPeopleWorkflow(', 'crypto.randomUUID(',
    'setTimeout(', 'neutralBrowEnhance()', 'defaultValue=', 'onBlur=']) assert.equal(control.includes(forbidden), false);
});

test('effective provenance remains separate from blank or explicit shared-scope intent', () => {
  for (const text of ['所选人脸实际联动', '当前范围的联动显式值', 'item.source', 'item.overridePresent',
    '不把所选人脸的继承参数复制给其他人物', 'value === null', 'useState(\'\')',
    '留空不会被当成 0', '只有点击应用才写入当前范围']) assert.ok(control.includes(text));
  for (const text of ['item.overridePresent ? item.override', "target?.scope === 'face' ? item.value : null",
    'view.groups', 'view.persons', 'view.links', "link.state === 'confirmed'",
    'link.confirmation_revision <= view.association_revision', 'selectedTargetMatches(view)']) assert.ok(model.includes(text));
  for (const forbidden of ['item.value ?? 0', 'item.override ?? item.value', 'setText(String(', 'Math.round'])
    assert.equal(model.includes(forbidden) || control.includes(forbidden), false);
});

test('relinking requires deliberate equal numbers and one-sided recovery explicitly unlocks and zeros', () => {
  for (const text of ['recipe.linked && recipe.left !== recipe.right',
    "parameter_path: '/linked', unset: false, value: true}, ...sides]",
    "parameter_path: '/linked', unset: false, value: false}",
    'return [browEnhanceUnlockPatch(), browEnhanceAmountPatch(side, 0)]',
    'BROW_ENHANCE_SIDES.map(side => browEnhanceAmountPatch(side, 0))']) assert.ok(model.includes(text));
  for (const text of ['access.editLeft !== null && access.editLeft === access.editRight',
    'onChoose={linkWithChoice}', '解除联动，独立调整左右', '重新联动必须明确选择一个新数值',
    '同一请求写入联动和相同的左右值', '不会自动复制、平均、归零或迁移已有参数',
    '必须由你明确解除联动并把该侧归零，不能自动跳过',
    'dispatch(browEnhanceZeroSidePatches(side))', 'onClick={() => zeroSide(side)}',
    '另一侧保持原值', '在共享范围内会作用于该范围', '另一侧的非零效果仍须通过引擎检查']) assert.ok(control.includes(text));
  assert.equal(control.includes('setLinked(true)'), false);
});

test('late callbacks, owner replacements, membership changes and repeated clicks cannot retarget writes', () => {
  for (const text of ['mounted.current && current.current.binding === binding', 'mounted.current = false',
    'current.current.patch === people.patch', 'current.current.check === people.check',
    'owner.current.generation + 1', 'browEnhanceBindingKey(view), owner.current.generation',
    'if (!stillCurrent() || submitted.current) return', 'submitted.current = true', '}, [binding, people.state])',
    'key={`${binding}:linked`}', 'key={`${binding}:linked-choice`}', 'key={`${binding}:${side}:choice`}',
    'key={`${binding}:relink-choice`}', 'current.current.access.resetDisabled : current.current.access.changeDisabled',
    'people.check()', 'if (stillCurrent()) note(String(error))', '查询原请求结果（不重发修改）']) assert.ok(control.includes(text));
  assert.ok(model.includes('view.faces, view.groups, view.persons, view.links'));
  const workflow = source('../people/workflow.ts');
  for (const text of ["action: 'patch', payload: {patches}", 'command.document_epoch === current.binding.document_epoch',
    'command.document_revision === current.binding.document_revision', 'command.state_revision === current.revision',
    'command.association_revision === current.association_revision', 'reply.request_id !== command.request_id',
    'result.action !== command.action', 'result.document_id !== command.document_id', 'result.outcome_unknown',
    'view.uncertain', 'queued = null; waitFor = null;']) assert.ok(workflow.includes(text));
});

test('neutral actions have separate owner-fenced buttons and no anatomy, native or value-read dependency', () => {
  const reset = control.slice(control.indexOf('function resetBoth()'), control.indexOf('function checkOriginal()'));
  assert.ok(reset.includes('if (!stillCurrent() || current.current.access.resetDisabled) return'));
  assert.ok(reset.includes('dispatch(browEnhanceResetPatches())'));
  for (const forbidden of ['changeDisabled', 'core.available', 'faceOk', 'reading.', 'writeLinked']) assert.equal(reset.includes(forbidden), false);
  const zeroSide = control.slice(control.indexOf('function zeroSide('), control.indexOf('function resetBoth()'));
  assert.ok(zeroSide.includes('current.current.access.resetDisabled'));
  assert.ok(zeroSide.includes('dispatch(browEnhanceZeroSidePatches(side))'));
  assert.ok(control.includes('disabled={access.resetDisabled} onClick={resetBoth}'));
  assert.ok(control.includes('缺少核心、有效读数或面部分析时仍可归零'));
  assert.ok(control.includes('归零写入中性覆盖，不恢复继承'));
  assert.ok(control.includes('不改变联动标记、眉妆、眉形或其他效果'));
});

test('source-owned contrast, support, refusal and acceptance language avoids false promises', () => {
  for (const text of ['原片已有深色眉毛相对邻近额头皮肤的对比', '负值减弱已有眉毛，正值加强',
    '人物自身左右侧', '不是观看者或画面左右', '不是添加眉妆素材、生成毛发、改变眉形',
    '完整去除眉毛或卸妆', '不是通用曝光调整', '当前有效来源图像（原图或已返回合成图）',
    '可靠的邻近额头参考', '每个目标自己的几何支撑和光度证据由引擎检查', '界面不提供测量值',
    '不把核心就绪当成眉毛可见、支撑可靠或照片质量的证明', '每个目标都必须独立通过来源、几何和光度检查',
    '不保证两侧视觉结果相同', '以下保留引擎原始原因', 'view?.refusals?.map', '{refusal.reason}',
    '遮挡、裁切、侧脸、浅色或稀疏眉毛、额头纹理与强光阴影', '不会补造缺失毛发',
    '已有眉妆素材、眉形几何和其他效果保持各自含义', '当前来源及叠加兼容性由引擎决定',
    '显示 -100 至 100 对应内部 -1 至 1', '不是手册规定', '不是官方标定',
    '均未运行（UNRUN）', '妆容调整功能族仍未完整验收']) assert.ok(control.includes(text));
  for (const invented of ['brow_enhance_applied', 'brow_enhance_facts', 'support_px', 'forehead_luminance',
    'composition_available', 'skipCompatibility', 'brow_shape_protocol', 'brow_makeup_available']) {
    assert.equal(model.includes(invented), false); assert.equal(control.includes(invented), false);
  }
});
