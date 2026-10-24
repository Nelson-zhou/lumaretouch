// AUTHORED / UNRUN: no imports, tests, typechecks, builds, inference or photo acceptance performed.
import {test} from 'node:test';
import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {readFileSync} from 'node:fs';
import {faceStyleAck, faceStyleImage, faceStyleMemberKey, faceStyleReviewReady, sameFaceStyleAck,
  validFaceStyleAliasCommit, validFaceStyleConfirmation, validFaceStyleReview,
  type FaceStyleAliasCommit, type FaceStyleReviewV1, type FaceStyleReviewV2} from './model';
import type {PeopleAction, PeopleResult, PeopleView} from '../people/model';
import type {SpillImage} from '../spillRemoval/model';
import {createPeopleWorkflow} from '../people/workflow';
import {createBatchWorkflow, type BatchReply} from '../batch/batchWorkflow';
import {observeFaceStyleAliasHistory, faceStyleAliasHistoryClass} from './aliasHistoryRegistry';

function fixture() {
  const base64 = 'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aYOcAAAAASUVORK5CYII=';
  const image: SpillImage = {mime: 'image/png', width: 1, height: 1, base64,
    sha256: createHash('sha256').update(Buffer.from(base64, 'base64')).digest('hex')};
  const {base64: _, ...compact} = image;
  const face_ref = {asset_sha256: 'a'.repeat(64), face_instance_id: 'face-a', analysis_revision: 3};
  const view: PeopleView = {binding: {document_id: 'd'.repeat(32), document_epoch: 'epoch', document_revision: 7,
    asset_sha256: face_ref.asset_sha256}, revision: 5, association_revision: 2,
    faces: [{face_ref, enabled: true, analysis_status: 'verified', manual: false, box: [.1,.1,.6,.8]}],
    groups: {}, persons: {}, links: [], selected_face_id: 'face-a', editing_target: {scope: 'face', target_id: 'face-a', face_ref},
    editing_overrides: {}, resolved: {face_ref, state_revision: 5, association_revision: 2, conflicts: [], operations: {}}};
  const source_proof = {asset_sha256: face_ref.asset_sha256, original_sha256: face_ref.asset_sha256, creative_source: null};
  const single: FaceStyleReviewV1 = {version: 1, token: 'f'.repeat(32), recipe: {version: 1, style: 'classic', amount: .5}, face_ref,
    patches_sha256: '1'.repeat(64), review_sha256: '2'.repeat(64), owner: {document: {document_id: view.binding.document_id,
      epoch: 'epoch', revision: 7}, people_scope: 'project', state_revision: 5, association_revision: 2, graph_sha256: '3'.repeat(64), source_proof},
    visual: {version: 1, document_id: view.binding.document_id, revision: '7', source_proof,
      before_state_sha256: '4'.repeat(64), candidate_state_sha256: '5'.repeat(64), before_people_sha256: '6'.repeat(64), candidate_people_sha256: '7'.repeat(64),
      source_size: [1,1], before_output_size: [1,1], after_output_size: [1,1], before: {...compact}, after: {...compact}}};
  const review: FaceStyleReviewV2 = {...single, version: 2, members: [{path: '/photos/current.png', visual: structuredClone(single.visual)},
    {path: '/photos/other.png', visual: {...structuredClone(single.visual), document_id: 'e'.repeat(32), revision: '11',
      source_proof: {asset_sha256: face_ref.asset_sha256, original_sha256: 'b'.repeat(64),
        creative_source: {sha256: face_ref.asset_sha256, width: 1, height: 1}}, before_state_sha256: '8'.repeat(64)}}]};
  const context = {document_id: view.binding.document_id, document_epoch: 'epoch', document_revision: 7,
    state_revision: 5, association_revision: 2, target: view.editing_target!};
  const command: PeopleAction = {...context, request_id: 'confirm-request', action: 'face_style_confirm',
    payload: {token: review.token, ack: faceStyleAck(review)}};
  const next = {...structuredClone(view), binding: {...view.binding, document_revision: 8}, revision: 35,
    resolved: {...view.resolved!, state_revision: 35}};
  const {request_id: requestId, ...echo} = command;
  const result: PeopleResult = {protocol: 1, request_id: requestId, action: command.action, document_id: command.document_id,
    success: true, outcome_unknown: false, batch_id: 'actual-ledger-batch', doc_state: {people: next}, face_style_request: echo,
    payload: {kind: 'face_style_confirm', token: review.token, review_sha256: review.review_sha256, patches_sha256: review.patches_sha256,
      recipe: review.recipe, ack: faceStyleAck(review), alias_members: review.members.map(({visual}) => ({document_id: visual.document_id,
        expected_revision: visual.revision, result_revision: String(BigInt(visual.revision) + 1n)}))}};
  const commit: FaceStyleAliasCommit = {batchId: result.batch_id!, documentEpoch: 'epoch', requestId, command, result, review};
  return {view, next, single, review, image, command, result, commit, context};
}

test('v1 exact shape remains valid; v2 source-first fullset allows independent provenance but no partial/fake members', () => {
  const f = fixture(); assert.equal(validFaceStyleReview(f.single, f.view, f.single.recipe), true);
  assert.equal(validFaceStyleReview(f.review, f.view, f.review.recipe), true);
  const mutations: ((r: any) => void)[] = [r => r.members.reverse(), r => r.members.pop(), r => r.members.push(r.members[1]),
    r => r.members = Array.from({length: 17}, (_, n) => ({...r.members[0], visual: {...r.visual, document_id: n.toString(16).padStart(32, '0')}})),
    r => r.owner.people_scope = r.owner.document.document_id, r => r.members[1].visual.source_proof.asset_sha256 = 'c'.repeat(64),
    r => r.members[1].visual.recipe_sha256 = 'c'.repeat(64), r => r.members[1].visual.before.width = 2,
    r => r.members[1].path = '', r => r.members[1].path = '汉'.repeat(1400), r => r.members[1].visual.revision = '011',
    r => r.members[1].visual.revision = '9007199254740992', r => r.visual.before_state_sha256 = 'a'.repeat(64)];
  for (const mutate of mutations) {const r = structuredClone(f.review); mutate(r); assert.equal(validFaceStyleReview(r, f.view, r.recipe), false);}
  assert.equal(validFaceStyleReview({...f.single, members: f.review.members}, f.view, f.single.recipe), false);
  const sixteen = structuredClone(f.review);
  sixteen.members = Array.from({length: 16}, (_, n) => n === 0 ? sixteen.members[0] : {...sixteen.members[1],
    visual: {...sixteen.members[1].visual, document_id: n.toString(16).padStart(32, '0')}});
  assert.equal(validFaceStyleReview(sixteen, f.view, sixteen.recipe), true);
});

test('ACK covers exact ordered members; metadata/current pair/other token never unlock fullset', () => {
  const f = fixture(), ack = faceStyleAck(f.review); assert.ok('members' in ack); if (!('members' in ack)) return;
  assert.equal(sameFaceStyleAck(ack, ack), true);
  for (const members of [ack.members.slice(1), [...ack.members].reverse(), [ack.members[0], ack.members[0]],
    [{...ack.members[0], reviewed: true}, ack.members[1]]]) assert.equal(sameFaceStyleAck({...ack, members}, ack), false);
  assert.equal(sameFaceStyleAck(faceStyleAck(f.single), ack), false);
  const keys = f.review.members.map(({visual}) => faceStyleMemberKey(f.review, visual));
  const images = Object.fromEntries(keys.map(key => [key, {before: f.image, after: f.image}]));
  const loaded = Object.fromEntries(keys.map(key => [key, {before: true, after: true}]));
  const checked = Object.fromEntries(keys.map(key => [key, true]));
  assert.equal(faceStyleReviewReady(f.review, images, loaded, checked), true);
  assert.equal(faceStyleReviewReady(f.review, images, {...loaded, [keys[1]]: {before: true}}, checked), false);
  assert.equal(faceStyleReviewReady(f.review, images, loaded, {...checked, [keys[1]]: false}), false);
  assert.equal(faceStyleReviewReady(f.review, {[keys[0]]: images[keys[0]]}, loaded, checked), false);
  assert.equal(faceStyleReviewReady({...f.review, token: 'a'.repeat(32)}, images, loaded, checked), false);
});

test('v2 PNG reply binds document plus exact bytes/dimensions; v1 keeps old no-document shape', async () => {
  const f = fixture(), document_id = f.review.members[1].visual.document_id;
  const reply = {kind: 'face_style_image', token: f.review.token, side: 'before', sha256: f.image.sha256,
    review_sha256: f.review.review_sha256, image: f.image, document_id};
  assert.deepEqual(await faceStyleImage(reply, f.review, 'before', document_id), f.image);
  assert.equal(await faceStyleImage({...reply, document_id: f.review.visual.document_id}, f.review, 'before', document_id), null);
  const {document_id: _, ...legacy} = reply;
  assert.equal(await faceStyleImage(legacy, f.review, 'before', document_id), null);
  assert.deepEqual(await faceStyleImage(legacy, f.single, 'before'), f.image);
  assert.equal(await faceStyleImage(reply, f.single, 'before'), null);
  assert.equal(await faceStyleImage({...reply, image: {...f.image, width: 2}}, f.review, 'before', document_id), null);
  assert.equal(await faceStyleImage({...reply, image: {...f.image, base64: f.image.base64.replace('42mP8', '42mP9')}}, f.review, 'before', document_id), null);
});

test('alias confirmation requires real batch, exact +1 documents/+30 graph and full ordered proof', () => {
  const f = fixture(); assert.equal(validFaceStyleConfirmation(f.review, f.result), true); assert.equal(validFaceStyleAliasCommit(f.commit), true);
  for (const mutate of [(r: any) => r.batch_id = null, (r: any) => r.batch_id = '', (r: any) => r.payload.alias_members.reverse(),
    (r: any) => r.payload.alias_members.pop(), (r: any) => r.payload.alias_members[0].result_revision = '7',
    (r: any) => r.payload.alias_members[1].expected_revision = '10', (r: any) => r.payload.recipe.amount = .6,
    (r: any) => r.doc_state.people.revision = 6, (r: any) => r.doc_state.people.binding.document_revision = 9,
    (r: any) => r.doc_state.people.association_revision++, (r: any) => r.outcome_unknown = true]) {
    const result = structuredClone(f.result); mutate(result); assert.equal(validFaceStyleConfirmation(f.review, result), false);
  }
  assert.equal(validFaceStyleAliasCommit({...f.commit, command: {...f.command, payload: {...f.command.payload, extra: true}}}), false);
});

test('queue retains alias proof across refresh invalidation; bad proof remains query-only and is never resent', async () => {
  const f = fixture(), commands: PeopleAction[] = []; let bad = true;
  const flow = createPeopleWorkflow({send: async command => {commands.push(command);}, read: async request_id => {
    const command = commands.find(value => value.request_id === request_id)!;
    const {request_id: _, ...echo} = command;
    const result: PeopleResult = command.action === 'face_style_preview'
      ? {...f.result, action: command.action, request_id, face_style_request: echo, doc_state: undefined,
        payload: {kind: 'face_style_preview', review: f.review}}
      : {...structuredClone(f.result), ...(bad ? {batch_id: null} : {})};
    return {phase: 'done', request_id, result};
  }, refresh: async () => {if (commands.at(-1)?.action === 'face_style_confirm') flow.update(f.next, true);}});
  flow.update(f.view, true);
  await flow.submit({...f.context, request_id: 'preview-request', action: 'face_style_preview', payload: {...f.review.recipe}});
  await assert.rejects(flow.submit(f.command)); assert.equal(flow.snapshot().uncertain, true);
  assert.equal(flow.snapshot().lastAliasCommit, null); assert.equal(commands.length, 2);
  await assert.rejects(flow.submit({...f.command, request_id: 'never-resend'}));
  bad = false; await flow.check(); assert.equal(commands.length, 2);
  assert.equal(flow.snapshot().lastAliasCommit?.batchId, f.result.batch_id); assert.equal(flow.snapshot().uncertain, false);
  flow.update({...f.next, selected_face_id: null, editing_target: null}, true);
  assert.equal(flow.snapshot().lastFaceStyleResult, null); assert.equal(flow.snapshot().lastAliasCommit?.requestId, f.command.request_id);
});

test('protected history adopts only a full receipt; wrong batch and unknown cannot be dismissed or resent', async () => {
  const f = fixture(), calls: {action: string; id: string}[] = []; let corrected = false;
  const flow = createBatchWorkflow({request: async (action, options) => {calls.push({action, id: options.requestId!}); return {requested: true};},
    read: async request_id => ({phase: 'done', request_id, result: {request_id, action: 'undo', success: true,
      outcome_unknown: false, batch_id: corrected ? f.commit.batchId : 'different-batch',
      module_scope: ['lnx.people_graph.v1'], restored: [0,1], conflicts: []} as BatchReply})}, () => {});
  assert.equal(flow.protectFaceStyleAlias({...f.commit, batchId: 'fabricated'}), false);
  assert.equal(flow.protectFaceStyleAlias(f.commit), true);
  await flow.undo(f.commit.batchId); assert.equal(flow.snapshot().phase, 'uncertain');
  flow.acknowledgeInspection(); assert.equal(flow.snapshot().phase, 'uncertain');
  await flow.undo(f.commit.batchId); assert.equal(calls.length, 1);
  corrected = true; await flow.query(); assert.equal(flow.snapshot().phase, 'done'); assert.equal(calls.length, 1);
});

test('navigation during a read discards old preview without creating a mutation uncertainty lock', async () => {
  const f = fixture(); let command: PeopleAction;
  const other = {...f.view, binding: {...f.view.binding, document_id: '9'.repeat(32)}};
  const flow = createPeopleWorkflow({send: async value => {command = value; flow.update(other, true);},
    read: async request_id => {const {request_id: _, ...echo} = command;
      return {phase: 'done', request_id, result: {protocol: 1, request_id, action: 'face_style_preview',
        document_id: f.view.binding.document_id, success: true, outcome_unknown: false, face_style_request: echo,
        payload: {kind: 'face_style_preview', review: f.review}}};}, refresh: async () => {}});
  flow.update(f.view, true);
  await flow.submit({...f.context, request_id: 'stale-preview', action: 'face_style_preview', payload: {...f.review.recipe}});
  assert.equal(flow.snapshot().uncertain, false); assert.equal(flow.snapshot().pending, false);
  assert.equal(flow.snapshot().lastFaceStyleResult, null); assert.equal(flow.snapshot().lastAliasCommit, null);
});

test('known alias preparation refusal may retain prospective proof but cannot claim a real batch', async () => {
  for (const batch_id of [null, 'claimed-published-batch']) {
    const f = fixture(); let command: PeopleAction;
    const flow = createPeopleWorkflow({send: async value => {command = value;}, read: async request_id => {
      const {request_id: _, ...echo} = command;
      const result: PeopleResult = {...f.result, request_id, action: command.action, face_style_request: echo,
        ...(command.action === 'face_style_preview'
          ? {batch_id: null, payload: {kind: 'face_style_preview', review: f.review}}
          : {success: false, outcome_unknown: false, batch_id, error: 'Preparation refused without publication'})};
      return {phase: 'done', request_id, result};}, refresh: async () => {}});
    flow.update(f.view, true);
    await flow.submit({...f.context, request_id: 'preview-refusal', action: 'face_style_preview', payload: {...f.review.recipe}});
    await assert.rejects(flow.submit(f.command));
    assert.equal(flow.snapshot().uncertain, batch_id !== null); assert.equal(flow.snapshot().lastAliasCommit, null);
  }
});

test('alias history refuses empty/partial restore, conflicts, duplicate indices or wrong scope as successful completion', async () => {
  const f = fixture();
  for (const patch of [{restored: []}, {restored: [0]}, {restored: [0,0]}, {restored: [-1,1]},
    {conflicts: [{path: '/photos/other.png', reason: 'later edit'}]}, {module_scope: ['lnx.deform.v1']}]) {
    const flow = createBatchWorkflow({request: async () => ({requested: true}), read: async request_id => ({phase: 'done', request_id,
      result: {request_id, action: 'redo', success: true, outcome_unknown: false, batch_id: f.commit.batchId,
        module_scope: ['lnx.people_graph.v1'], restored: [0,1], conflicts: [], ...patch}})}, () => {});
    assert.equal(flow.protectFaceStyleAlias(f.commit), true); await flow.redo(f.commit.batchId);
    assert.equal(flow.snapshot().phase, 'uncertain'); flow.acknowledgeInspection(); assert.equal(flow.snapshot().phase, 'uncertain');
  }
});

test('source wiring has per-member paging, actual decoding and engine-owned protected history, not local undo', () => {
  const panel = readFileSync(new URL('./FaceStylePanel.tsx', import.meta.url), 'utf8');
  for (const text of ['member.visual.document_id', 'element.naturalWidth === member.visual[side].width',
    'element.naturalHeight === member.visual[side].height', 'faceStyleReviewReady(review, images, loaded, acknowledged)',
    '确认全部', '共享来源', 'history.undo()', 'history.redo()']) assert.ok(panel.includes(text), text);
  const owner = readFileSync(new URL('../people/usePeopleWorkflow.ts', import.meta.url), 'utf8');
  for (const text of ['status?.session?.sync?.batches.find', 'history.protectFaceStyleAlias(receipt)', 'historyBusy', 'historyRefreshError']) assert.ok(owner.includes(text), text);
  assert.equal(panel.includes('runHistory'), false); assert.equal(owner.includes('runHistory'), false);
});

test('reopened alias status protects the independent global undo route without adopting a current preview', async () => {
  const batch = {batch_id: 'reopened-alias', module_scope: ['lnx.people_graph.v1'], targets: 2, undone: false,
    face_style_alias_review: {version: 1, review_sha256: 'a'.repeat(64), member_count: 2}};
  observeFaceStyleAliasHistory({workspace_generation: 'reopened-workspace', batches: [batch]});
  assert.equal(faceStyleAliasHistoryClass(batch.batch_id)?.memberCount, 2);
  observeFaceStyleAliasHistory({workspace_generation: 'reopened-workspace', batches: []});
  assert.equal(faceStyleAliasHistoryClass(batch.batch_id)?.memberCount, 2);
  let corrected = false, sends = 0;
  const unrelatedController = createBatchWorkflow({request: async () => {sends++; return {requested: true};},
    read: async request_id => ({phase: 'done', request_id, result: {request_id, action: 'undo', success: true,
      outcome_unknown: false, batch_id: batch.batch_id, module_scope: ['lnx.people_graph.v1'],
      restored: corrected ? [4,7] : [], conflicts: []}})}, () => {});
  await unrelatedController.undo(batch.batch_id); assert.equal(unrelatedController.snapshot().queryOnly, true);
  assert.equal(unrelatedController.snapshot().phase, 'uncertain');
  unrelatedController.acknowledgeInspection(); assert.equal(unrelatedController.snapshot().phase, 'uncertain');
  corrected = true; await unrelatedController.query(); assert.equal(unrelatedController.snapshot().phase, 'done'); assert.equal(sends, 1);
  observeFaceStyleAliasHistory({workspace_generation: 'different-workspace', batches: []});
  assert.equal(faceStyleAliasHistoryClass(batch.batch_id), undefined);
  observeFaceStyleAliasHistory({workspace_generation: 'different-workspace', batches: [{...batch,
    face_style_alias_review: {...batch.face_style_alias_review, member_count: 1}}]});
  assert.equal(faceStyleAliasHistoryClass(batch.batch_id)?.memberCount, null);
  observeFaceStyleAliasHistory({workspace_generation: 'newest-workspace', batches: [batch]}, 200);
  observeFaceStyleAliasHistory({workspace_generation: 'old-inflight-workspace', batches: []}, 199);
  assert.equal(faceStyleAliasHistoryClass(batch.batch_id)?.memberCount, 2);
  observeFaceStyleAliasHistory({workspace_generation: 'epoch', batches: []});
  const native = readFileSync(new URL('../native.ts', import.meta.url), 'utf8');
  assert.ok(native.includes('observeFaceStyleAliasHistory(status.session?.sync, observation)'));
  assert.ok(native.includes('const observation = ++engineStatusRequestSequence'));
});
