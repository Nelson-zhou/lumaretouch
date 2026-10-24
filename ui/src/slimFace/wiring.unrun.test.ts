// AUTHORED / UNRUN. Source-contract fixtures only; no import, execution, compilation or UI acceptance.
import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
const source = (path: string) => readFileSync(new URL(path, import.meta.url), 'utf8');
const panel = source('../components/RetouchPanel.tsx'), control = source('./SlimFaceControl.tsx'), model = source('./model.ts');

test('the exact slim leaf defaults to v2, without rerouting independent contour or chin controls', () => {
  assert.ok(source('../spec/refine.json').includes('"path": "脸型/瘦脸"'));
  assert.ok(panel.includes('"PC-32466|脸型/瘦脸": "slim_face.v2"'));
  assert.equal(panel.includes('"PC-32466|脸型/瘦脸": "deform.slim_face"'), false);
  assert.ok(panel.includes('case "slim_face.v2":'));
  assert.ok(panel.includes("import {SlimFaceControl} from '../slimFace/SlimFaceControl'"));
  assert.ok(panel.includes('<SlimFaceControl key={leaf.path}'));
  assert.ok(control.includes('data-control-id={SLIM_FACE_CONTROL_ID}'));
  for (const text of ['"PC-32466|脸型/太阳穴": "face_contour.temple"',
    '"PC-32466|脸型/颧骨": "face_contour.cheekbone"', '"PC-32466|脸型/下颌": "face_contour.jaw"',
    '"PC-32466|脸型/收下巴": "deform.small_chin"']) assert.ok(panel.includes(text));
  assert.ok(source('../people/model.ts').includes("'lnx.slim_face.v2': '新版瘦脸（真实可见轮廓，左右独立）'"));
});

test('existing contour readiness and all existing competing-owner fences reach the new control', () => {
  const branch = panel.slice(panel.indexOf('case "slim_face.v2":'), panel.indexOf('case "deform.big_eye":'));
  for (const text of ['people={props.people}', 'capability={status?.ready_caps}', 'blocked={dim', 'props.hairBusy',
    'props.whiteBalanceBusy', 'portraitRequestsBusy()', 'status?.edit_queue?.in_flight', 'status?.edit_queue?.pending',
    'status?.edit_queue?.closed', 'faceOk={props.faceOk}', 'faceWhy={props.faceWhy}']) assert.ok(branch.includes(text));
  for (const text of ['faceContourReadiness(capability)', 'faceContourTargetReady(view)', 'fences.pending',
    'fences.uncertain', 'fences.externalBusy', 'selected.analysis_status === \'verified\'']) assert.ok(model.includes(text));
  for (const borrowed of ['slim_face_available', 'skin_texture_available', 'brow_shape_protocol', 'nose_shape_protocol'])
    assert.equal(model.includes(borrowed), false);
});

test('one generic people owner is the only mutation, queue, receipt and history authority', () => {
  assert.equal((control.match(/people\.patch\(/g) ?? []).length, 1);
  for (const text of ['people.patch(patches)', 'dispatch(slimFaceAdjustPatches(side, value, linked))',
    'dispatch([slimFaceLinkPatch(linked)])', 'dispatch(slimFaceResetPatches())', 'dispatch([legacySlimFacePatch(value)])',
    'dispatch(replaceLegacySlimFacePatches(left, right, linked))', 'reading.linked.overridePresent', 'access.writeLinked',
    'targetLabel(view)', 'sourceLabel(source)', 'item.value !== null', 'min={-100} max={100}',
    'onChange={value => commit(side, value / 100)}']) assert.ok(control.includes(text));
  for (const forbidden of ['runDeform', 'runHistory', 'invoke(', 'createPeopleWorkflow', 'people.submit(',
    'people.submitCaptured(', 'latestIntent', 'neutralSlimFace()']) assert.equal(control.includes(forbidden), false);
  const workflow = source('../people/workflow.ts');
  for (const text of ["action: 'patch', payload: {patches}", 'command.document_epoch === current.binding.document_epoch',
    'command.document_revision === current.binding.document_revision', 'command.state_revision === current.revision',
    'command.association_revision === current.association_revision', 'reply.request_id !== command.request_id',
    'result.action !== command.action', 'result.document_id !== command.document_id', 'result.outcome_unknown',
    'view.uncertain', 'queued = null; waitFor = null;']) assert.ok(workflow.includes(text));
});

test('late handlers, duplicate submission and uncertain outcomes cannot migrate or resend a mutation', () => {
  for (const text of ['mounted.current && current.current.binding === binding', 'mounted.current = false',
    'key={`${binding}:${side}`}', 'key={`${binding}:legacy`}', 'key={`${binding}:${access.writeLinked}`}',
    'if (!stillCurrent() || submitted.current) return', 'submitted.current = true',
    'if (!people.state.pending && !people.state.uncertain) submitted.current = false',
    '}, [binding, people.state])',
    'people.check()', 'if (stillCurrent()) note(String(error))', '查询原请求结果（不重发修改）']) assert.ok(control.includes(text));
  for (const name of ['commit', 'setLinked', 'resetNew', 'commitLegacy', 'replaceLegacy']) {
    const start = control.indexOf(`function ${name}(`), end = control.indexOf('\n  function ', start + 1);
    assert.ok(control.slice(start, end).includes('if (!stillCurrent() ||'));
  }
  assert.ok(control.includes('current.current.access.resetDisabled : current.current.access.changeDisabled'));
  assert.ok(control.includes('current.current.access.resetDisabled : current.current.access.legacyChangeDisabled'));
  assert.ok(control.includes('if (!stillCurrent() || current.current.access.replacementDisabled) return'));
  assert.ok(model.includes('faceContourBindingKey(view), faceContourTargetReady(view)'));
  assert.ok(model.includes('view.resolved?.operations[LEGACY_SLIM_FACE_OPERATION]'));
  assert.ok(model.includes('view.editing_overrides[LEGACY_SLIM_FACE_OPERATION]'));
});

test('replacement draft starts blank, is source-keyed, and only its explicit button may apply chosen values', () => {
  const draft = control.slice(control.indexOf('function ReplacementChoice('), control.indexOf('/** The existing generic people owner'));
  assert.ok(draft.includes("useState(''), [right, setRight] = useState('')"));
  assert.ok(draft.includes('parseSlimFaceChoice(left)'));
  assert.ok(draft.includes('linked ? chosenLeft : parseSlimFaceChoice(right)'));
  assert.ok(draft.includes('chosenLeft === null || chosenRight === null'));
  assert.ok(draft.includes('onReplace(chosenLeft, chosenRight)'));
  for (const forbidden of ['reading.legacy', 'reading.left', 'useEffect(', 'useLayoutEffect(', 'onBlur=', 'onSubmit=', 'people.patch'])
    assert.equal(draft.includes(forbidden), false);
  const effects = control.slice(control.indexOf('useLayoutEffect(() =>'), control.indexOf('const stillCurrent'));
  for (const forbidden of ['dispatch(', 'people.patch(', 'replaceLegacySlimFacePatches(', 'legacySlimFacePatch('])
    assert.equal(effects.includes(forbidden), false);
  assert.ok(control.includes('一次替换：归零旧版并应用我选择的新数值'));
  assert.ok(control.includes('若其他范围仍令同一人脸的新旧效果或独立轮廓同时生效，引擎会拒绝整个请求'));
});

test('neutral recovery has standalone buttons independent of slider, link, anatomy and core availability', () => {
  const reset = control.slice(control.indexOf('function resetNew()'), control.indexOf('function commitLegacy('));
  assert.ok(reset.includes('current.current.access.resetDisabled'));
  assert.ok(reset.includes('dispatch(slimFaceResetPatches())'));
  for (const forbidden of ['changeDisabled', 'writeLinked', 'core.available', 'faceOk', 'reading.']) assert.equal(reset.includes(forbidden), false);
  assert.ok(control.includes('disabled={access.resetDisabled} onClick={resetNew}'));
  assert.ok(control.includes('disabled={access.resetDisabled} onClick={() => commitLegacy(0)}'));
  assert.ok(model.includes("return SLIM_FACE_SIDES.map(side => slimFaceAmountPatch(side, 0))"));
});

test('unmanaged saved legacy documents retain a clearly labelled compatibility slider and old command', () => {
  const branch = panel.slice(panel.indexOf('case "slim_face.v2":'), panel.indexOf('case "deform.big_eye":'));
  for (const text of ['if (!doc?.people)', '新版左右独立瘦脸暂不可用', '不会自动升级或换算',
    '旧版右侧控制点列表含非面部椭圆点和嘴唇点', '历史错误拓扑',
    'Number.isFinite(amounts.slim_face)', 'value={amounts.slim_face * 100}', 'min={-100} max={100}',
    'onChange={value => commitDeform({slim_face: value / 100})}', 'onReset={() => commitDeform({slim_face: 0})}',
    '引擎尚未提供有效的旧版瘦脸读数，不以 0 代替']) assert.ok(branch.includes(text));
  const legacyDispatch = panel.slice(panel.indexOf('const commitDeform ='), panel.indexOf('const commitEnhance ='));
  assert.ok(legacyDispatch.includes("scalarLeaves('lnx.deform.v1', patch)"));
  assert.ok(legacyDispatch.includes('runDeform("set", patch, undefined, capturedPeople)'));
  assert.equal(legacyDispatch.includes('lnx.slim_face.v2'), false);
});

test('historical preset recipe numbers and reachable historical adjustment are preserved, not reinterpreted', () => {
  for (const text of ['经典: { slim_face: 0.22, big_eye: 0.04, small_chin: 0.14, smile: 0 }',
    '幼态: { slim_face: 0.12, big_eye: 0.10, small_chin: 0.10, smile: 0.05 }',
    '英气: { slim_face: 0.30, big_eye: 0.02, small_chin: 0.18, smile: 0 }',
    'commitDeform(SHAPE_PRESETS[preset] ?? {})', '历史预设 · 旧版瘦脸',
    '保留旧版数值及错误拓扑，不是新版瘦脸']) assert.ok(panel.includes(text));
  for (const text of ['保留并调整旧版瘦脸（历史错误拓扑，兼容保留）',
    '旧版右侧控制点列表含非面部椭圆点和嘴唇点', '仅用于已保存作品的外观兼容',
    '不代表与新版同等正确', '新的强度标尺', '不保证与旧版同值同效果', '不会自动换算',
    '进入此面板不会修改或升级旧效果', 'onChange={value => commitLegacy(value / 100)}']) assert.ok(control.includes(text));
});

test('subject-side semantics, source limits, negative local extension and unrun acceptance remain disclosed', () => {
  for (const text of ['当前有效来源图像（原图或已返回合成图）', '正值向内收窄，负值向外扩展',
    '人物自身解剖侧', '不是观看者或画面左右', '人物自身左侧', '人物自身右侧',
    '仅支持正脸与轻度偏转', '不补造被遮挡或画面外的部位',
    '共享范围内每个目标仍须通过自己的真实分析与可见轮廓检查', '切换联动只改变联动标记',
    '不复制、平均或重置已有的左右值', '下一次数值修改才同时写入两侧',
    '共享范围必须明确选择写入模式', '不改变联动继承',
    '归零不需要核心、有效读数或可用分析', '归零不是恢复继承',
    '不是 AI 重建、3D 塑颜或骨骼矫正', '轮廓外的邻近背景过渡带可能移动',
    '不能保证背景完全不动', '显示 -100 至 100 对应内部 -1 至 1', '不是手册规定',
    '负值向外扩展也是本产品扩展，不宣称官方同等行为',
    '核心就绪不证明每个人脸和每一侧都可用', '验收尚未运行', '功能族仍未完整验收']) assert.ok(control.includes(text));
  assert.ok(control.includes('view?.refusals?.map'));
  assert.ok(control.includes('{refusal.reason}'));
  for (const inventedFact of ['support_px', 'side_available', 'side_applied', 'contour_facts']) assert.equal(control.includes(inventedFact), false);
});
