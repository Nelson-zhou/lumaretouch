// Authored regression fixtures only. NOT RUN under the source-only authorization.
import {test} from 'node:test';
import assert from 'node:assert/strict';
import {boundedText, currentImageFacts} from './model.ts';

function snapshot(load = 'load-a', project = 'project-a') {
  const doc = {document_id: load};
  const projectState = {open: true, project_id: project, path: project};
  return {engine_alive: true, project: projectState,
    image: {load_id: load, doc: '/same/path.jpg', session_index: 0, doc_state: doc,
      device: 'cpu', notes: ['源图没有 ICC：按 sRGB 输入假设处理'], bytes_filter: 123, bytes_lut: 0},
    doc_report: {doc_state: doc}, session: {current: '/same/path.jpg', index: 0, doc_state: doc, project: projectState}};
}

test('explicit decode notes and reported resources survive; CPU is not proof of fallback', () => {
  const facts = currentImageFacts(snapshot())!;
  assert.equal(facts.device, 'cpu');
  assert.equal(facts.fallbackReported, false);
  assert.equal(facts.fallback, null);
  assert.deepEqual(facts.notes, ['源图没有 ICC：按 sRGB 输入假设处理']);
  assert.deepEqual(facts.resources, [{label: '滤波缓存', bytes: 123}, {label: '色彩查找表', bytes: 0}]);
});

test('absence never invents CPU, ICC assumption, resource bytes or fallback', () => {
  const value = snapshot();
  const image = {load_id: value.image.load_id, doc: value.image.doc, session_index: 0, doc_state: value.image.doc_state};
  const facts = currentImageFacts({...value, image})!;
  assert.equal(facts.device, null);
  assert.equal(facts.fallbackReported, false);
  assert.deepEqual(facts.notes, []);
  assert.deepEqual(facts.resources, []);
});

test('structured same-image fallback is distinct from explicit null and unrelated logs', () => {
  const value = snapshot();
  assert.equal(currentImageFacts({...value, logs: ['事件 engine_warn: old cpu fallback']})!.fallback, null);
  const reported = currentImageFacts({...value, image: {...value.image, device_fallback: '要求 cuda，但不可用，已退到 cpu'}})!;
  assert.equal(reported.fallbackReported, true);
  assert.equal(reported.fallback, '要求 cuda，但不可用，已退到 cpu');
  assert.equal(currentImageFacts({...value, image: {...value.image, device_fallback: null}})!.fallbackReported, true);
});

test('different load on same path, stale report, stale session and dead engine are rejected', () => {
  const value = snapshot();
  for (const changed of [
    {...value, engine_alive: false}, {...value, engine_alive: undefined},
    {...value, doc_report: {doc_state: {document_id: 'new-load'}}},
    {...value, image: {...value.image, load_id: 'new-load'}},
    {...value, session: {...value.session, index: 1}},
    {...value, session: {...value.session, doc_state: {document_id: 'new-load'}}},
    {...value, image: null},
  ]) assert.equal(currentImageFacts(changed), null);
});

test('successful create retains current load only with authoritative session-project bridge', () => {
  const a = snapshot(), b = snapshot('load-a', 'project-b');
  assert.ok(currentImageFacts(a));
  assert.equal(currentImageFacts({...a, project: b.project}), null);
  assert.ok(currentImageFacts(b));
  // A failed prevalidation operation retains A's facts; no intent-based reset.
  assert.ok(currentImageFacts({...a, last_error: 'project create rejected'}));
  assert.equal(currentImageFacts({...a, session: {...a.session, project: undefined}}), null);
});

test('torn load/report or late project metadata never poisons subsequent complete receipt', () => {
  const a = snapshot(), b = snapshot('load-b', 'project-b');
  assert.ok(currentImageFacts(a));
  assert.equal(currentImageFacts({...b, project: a.project, doc_report: a.doc_report}), null);
  assert.ok(currentImageFacts(b));
  assert.equal(currentImageFacts({...b, project: a.project}), null);
  assert.ok(currentImageFacts(b));
  assert.equal(currentImageFacts({...b, engine_alive: false}), null);
  assert.equal(currentImageFacts({...b, session: {...b.session, index: -1, doc_state: null}}), null);
  assert.ok(currentImageFacts(snapshot('load-c', 'project-b')));
});

test('unmanaged session must explicitly report its project ownership too', () => {
  const a = snapshot();
  const project = {open: false, project_id: null, path: null};
  assert.ok(currentImageFacts({...a, project, session: {...a.session, project}}));
  assert.ok(currentImageFacts({...a, project: null, session: {...a.session, project}}));
  assert.equal(currentImageFacts({...a, project: undefined, session: {...a.session, project}}), null);
  assert.equal(currentImageFacts({...a, project: null, session: {...a.session, project: {open: false}}}), null);
  assert.equal(currentImageFacts({...a, project: null}), null);
});

test('ICC-bearing image replaces earlier assumption; notes and raw values stay bounded', () => {
  currentImageFacts(snapshot());
  const next = snapshot('load-b');
  const facts = currentImageFacts({...next, image: {...next.image,
    notes: ['输入嵌入 ICC 已转换至 sRGB 工作空间'], bytes_filter: -1, bytes_lut: NaN}})!;
  assert.deepEqual(facts.notes, ['输入嵌入 ICC 已转换至 sRGB 工作空间']);
  assert.deepEqual(facts.resources, []);
  const many = currentImageFacts({...next, image: {...next.image, notes: [
    ...Array.from({length: 15}, (_, i) => `普通说明 ${i}`),
    'PNG 没有 ICC 或其它非 sRGB/HDR 声明：按普通 SDR sRGB 输入假设处理',
  ]}})!;
  assert.equal(many.notes.length, 8);
  assert.match(many.notes[0], /输入假设/);
  assert.equal(boundedText('x'.repeat(500)).length, 241);
  assert.equal(boundedText('a\nb\u0000c'), 'a b c');
});
