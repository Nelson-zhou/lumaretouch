// SPDX-License-Identifier: GPL-3.0-or-later
// AUTHORED / UNRUN. Synthetic receipt and static source contracts only.
// No React lifecycle, PNG decode, native execution or photographic acceptance is claimed.
import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import type {PeopleAction, PeopleResult} from '../people/model';
import {access, CONTROLS, neutral, OP, referenceCurrent, releasedReferenceReceiptValid, reviewReceiptValid,
  type EyeReview, type ReferenceProof, type Review, type View} from './model.ts';

const a = 'a'.repeat(64), b = 'b'.repeat(64), c = 'c'.repeat(64), d = 'd'.repeat(64);
function eye(confirmed = true): EyeReview {
  return {makeup: [[.40,.30],[.45,.30],[.45,.34],[.40,.34]], exclusions: [],
    reference_a: confirmed ? [[.35,.35],[.38,.35],[.38,.37],[.35,.37]] : null,
    reference_b: confirmed ? [[.47,.35],[.49,.35],[.49,.37],[.47,.37]] : null,
    reference_confirmed: confirmed, visible_makeup: true, unoccluded: true,
    ownership_confirmed: true, globe_lashes_brows_excluded: true};
}
function fixture(eyes: Review = {left: eye()}) {
  const face = {asset_sha256: a, face_instance_id: 'face', analysis_revision: 2};
  const proof: ReferenceProof = {source: {sha256: a, width: 1024, height: 768}, face_ref: face,
    landmark_digest: b, preview_sha256: d, reference_request_id: 'makeup-source'};
  const request: PeopleAction = {document_id: 'photo', document_epoch: 'epoch', document_revision: 7,
    state_revision: 11, association_revision: 3, request_id: 'makeup-review',
    target: {scope: 'face', target_id: 'face', face_ref: face}, action: 'eye_makeup_enhance_review',
    payload: {eyes: structuredClone(eyes), reference_proof: structuredClone(proof)}};
  const view: View = {binding: {document_id: 'photo', document_epoch: 'epoch', document_revision: 8, asset_sha256: a},
    revision: 12, association_revision: 3, selected_face_id: 'face', editing_target: structuredClone(request.target),
    faces: [{face_ref: structuredClone(face), enabled: true, box: [0,0,100,100], manual: false, analysis_status: 'verified'}],
    groups: {}, persons: {}, links: [], editing_overrides: {},
    resolved: {face_ref: structuredClone(face), state_revision: 12, association_revision: 3, operations: {[OP]: {}}, conflicts: []},
    eye_makeup_enhance: {recipe: neutral(), facts: {}, source: structuredClone(proof.source), face_ref: structuredClone(face),
      landmark_digest: b, reviewed: true, support_sha256: c, sides: Object.fromEntries(Object.entries(eyes).map(([side, row]) =>
        [side, {reviewed: true, reference_reviewed: row.reference_confirmed}])), source_preview: null, reference_proof: null,
      native_available: false, support_available: true, support_reason: null, suspended: null}};
  syncRecipe(view);
  const {request_id: _id, ...echo} = structuredClone(request);
  const result = {event: 'people_result', protocol: 1, request_id: request.request_id, action: request.action,
    document_id: request.document_id, success: true, outcome_unknown: false, error: null, created_id: null,
    batch_id: null, frame_emitted: false, eye_makeup_enhance_request: echo,
    payload: {kind: request.action, reference_proof: structuredClone(proof), support_sha256: c},
    doc_state: {people: view}} as unknown as PeopleResult;
  return {request, result, view, proof};
}
function syncRecipe(view: View) {
  for (const control of CONTROLS) for (const field of ['linked', 'left', 'right'] as const)
    view.resolved!.operations[OP][`/${control}/${field}`] = {
      value: view.eye_makeup_enhance!.recipe[control][field], scope: 'default', target_id: null, overridden: false};
}
function reject(mutator: (value: ReturnType<typeof fixture>) => void, reason: string) {
  const value = fixture(); mutator(value);
  assert.equal(reviewReceiptValid(value.request, value.result), false, reason);
}

test('exact source-bound review +1 receipt does not claim native availability or a rendered frame', () => {
  const {request, result, view} = fixture();
  assert.equal(reviewReceiptValid(request, result), true);
  assert.equal(view.eye_makeup_enhance!.native_available, false);
  assert.equal(view.eye_makeup_enhance!.source_preview, null);
  assert.equal(view.eye_makeup_enhance!.reference_proof, null);
});
test('document and people revisions advance exactly once, association never advances', () => {
  for (const revision of [0,7,9,8.5,NaN,Infinity,Number.MAX_SAFE_INTEGER + 1])
    reject(({view}) => {view.binding.document_revision = revision;}, `document ${revision}`);
  for (const revision of [0,11,13,12.5,NaN,Infinity,Number.MAX_SAFE_INTEGER + 1])
    reject(({view}) => {view.revision = revision; view.resolved!.state_revision = revision;}, `people ${revision}`);
  for (const association of [2,4,3.5,NaN])
    reject(({view}) => {view.association_revision = association; view.resolved!.association_revision = association;}, `association ${association}`);
  for (const key of ['document_revision', 'state_revision'] as const)
    reject(({request,view}) => {
      request[key] = Number.MAX_SAFE_INTEGER;
      if (key === 'document_revision') view.binding.document_revision = Number.MAX_SAFE_INTEGER + 1;
      else view.revision = view.resolved!.state_revision = Number.MAX_SAFE_INTEGER + 1;
    }, `safe increment ${key}`);
});
test('receipt cannot transplant current selection, target, source, epoch or analysis', () => {
  const changes: [string, (value: ReturnType<typeof fixture>) => void][] = [
    ['document', ({view}) => {view.binding.document_id = 'other';}],
    ['epoch', ({view}) => {view.binding.document_epoch = 'later';}],
    ['source binding', ({view}) => {view.binding.asset_sha256 = d;}],
    ['selected face', ({view}) => {view.selected_face_id = 'other';}],
    ['editing scope', ({view}) => {view.editing_target!.scope = 'person';}],
    ['editing face', ({view}) => {view.editing_target!.target_id = 'other';}],
    ['editing analysis', ({view}) => {view.editing_target!.face_ref!.analysis_revision++;}],
    ['resolved face', ({view}) => {view.resolved!.face_ref.face_instance_id = 'other';}],
    ['resolved analysis', ({view}) => {view.resolved!.face_ref.analysis_revision++;}],
    ['resolved state', ({view}) => {view.resolved!.state_revision++;}],
    ['resolved association', ({view}) => {view.resolved!.association_revision++;}],
    ['report source dimensions', ({view}) => {view.eye_makeup_enhance!.source.width++;}],
    ['report face', ({view}) => {view.eye_makeup_enhance!.face_ref!.face_instance_id = 'other';}],
    ['report landmark', ({view}) => {view.eye_makeup_enhance!.landmark_digest = d;}],
    ['support digest', ({view}) => {view.eye_makeup_enhance!.support_sha256 = d;}],
    ['wrong request action', ({request}) => {request.action = 'eye_makeup_enhance_reference';}],
    ['mismatched request target', ({request}) => {request.target.face_ref = {...request.target.face_ref!, analysis_revision: 8};}],
    ['mismatched selected target id', ({request,view}) => {request.target.target_id = 'other'; view.editing_target!.target_id = 'other'; view.selected_face_id = 'other';}],
  ];
  for (const [label,mutate] of changes) reject(mutate, label);
});
test('all twelve resolved recipe leaves must equal independently validated report controls', () => {
  for (const control of CONTROLS) for (const field of ['linked','left','right'] as const) {
    const path = `/${control}/${field}`;
    reject(({view}) => {view.resolved!.operations[OP][path].value = field === 'linked' ? false : .1;}, `mismatch ${path}`);
    reject(({view}) => {delete view.resolved!.operations[OP][path];}, `missing ${path}`);
  }
  reject(({view}) => {delete view.resolved!.operations[OP];}, 'missing operation');
  reject(({view}) => {view.eye_makeup_enhance!.recipe.amount.left = .1; syncRecipe(view);}, 'linked unequal values');
  reject(({view}) => {view.eye_makeup_enhance!.recipe.structure.left = NaN; syncRecipe(view);}, 'non-finite recipe');
  const {request,result,view} = fixture();
  for (const control of CONTROLS) view.eye_makeup_enhance!.recipe[control] = {linked: false, left: -.5, right: .25};
  syncRecipe(view); assert.equal(reviewReceiptValid(request,result), true);
});
test('review must clear old source display and proof, never preserve reusable image authority', () => {
  reject(({view,proof}) => {view.eye_makeup_enhance!.reference_proof = proof;}, 'retained proof');
  reject(({view}) => {view.eye_makeup_enhance!.source_preview = {sha256:d} as never;}, 'retained image');
  reject(({view}) => {delete (view.eye_makeup_enhance as unknown as Record<string,unknown>).source_preview;}, 'missing explicit image null');
  reject(({view}) => {delete (view.eye_makeup_enhance as unknown as Record<string,unknown>).reference_proof;}, 'missing explicit proof null');
  reject(({result}) => {(result.payload as Record<string,unknown>).kind = 'eye_makeup_enhance_reference';}, 'wrong payload kind');
  reject(({result}) => {(result.payload as Record<string,unknown>).reference_proof = {};}, 'missing original proof');
});
test('live supported eyes must reflect every submitted side and its paired-reference consent', () => {
  reject(({view}) => {view.eye_makeup_enhance!.sides = {};}, 'missing submitted side');
  reject(({view}) => {view.eye_makeup_enhance!.sides = {right:{reviewed:true,reference_reviewed:true}};}, 'wrong side');
  reject(({view}) => {view.eye_makeup_enhance!.sides.left!.reviewed = false;}, 'not reviewed');
  reject(({view}) => {view.eye_makeup_enhance!.sides.left!.reference_reviewed = false;}, 'reference consent mismatch');
  reject(({view}) => {(view.eye_makeup_enhance!.sides as Record<string,unknown>).image_left = {reviewed:true,reference_reviewed:true};}, 'foreign side');
  reject(({view}) => {(view.eye_makeup_enhance!.sides.left as unknown as Record<string,unknown>).automatic = true;}, 'extra side authority');
  const withoutReferences = fixture({left:eye(false)});
  assert.equal(reviewReceiptValid(withoutReferences.request,withoutReferences.result),true);
  const both = fixture({left:eye(),right:eye(false)});
  assert.equal(reviewReceiptValid(both.request,both.result),true);
  both.view.eye_makeup_enhance!.sides.right!.reference_reviewed = true;
  assert.equal(reviewReceiptValid(both.request,both.result),false);
});
test('unsubmitted retained opposite side is allowed, and missing live analysis cannot invent support', () => {
  const retained = fixture(); retained.view.eye_makeup_enhance!.sides.right = {reviewed:true,reference_reviewed:false};
  assert.equal(reviewReceiptValid(retained.request,retained.result),true);
  const unavailable = fixture(), report = unavailable.view.eye_makeup_enhance!;
  report.support_available = false; report.sides = {}; report.support_reason = 'Live analysis no longer available';
  assert.equal(reviewReceiptValid(unavailable.request,unavailable.result),true);
  const state = access(unavailable.view,{eye_makeup_enhance_protocol:1,eye_makeup_enhance_available:true},
    {enabled:true,pending:false,uncertain:false,blocked:false,faceOk:true});
  assert.equal(state.changeDisabled,true); assert.equal(state.permitted('amount','left',.5,false),false);
});
test('exact report fields and native diagnostic types stay fail-closed', () => {
  reject(({view}) => {(view.eye_makeup_enhance as unknown as Record<string,unknown>).foreign = true;}, 'extra report field');
  for (const key of ['reviewed','native_available','support_available'] as const)
    reject(({view}) => {(view.eye_makeup_enhance as unknown as Record<string,unknown>)[key] = 1;}, `boolean ${key}`);
  for (const text of ['', '  ', 'bad\0message', 'x'.repeat(4097), '中'.repeat(1366)])
    reject(({view}) => {view.eye_makeup_enhance!.support_reason = text;}, 'bounded diagnostic');
  reject(({view}) => {view.eye_makeup_enhance!.facts = {changed_pixels:1};}, 'partial numeric facts');
});

function withFacts() {
  const value = fixture(), report = value.view.eye_makeup_enhance!;
  report.recipe.saturation = {linked:false,left:.2,right:0}; syncRecipe(value.view);
  const facts = {recipe:structuredClone(report.recipe),review_sha256:c,face_ref:structuredClone(report.face_ref),
    sides:{left:{reviewed_makeup_pixels:100,permitted_makeup_pixels:80,reference_pixels:[0,0],measured_eye_width:40,
      radius:2,controls:{amount:0,saturation:.2,brightness:0,structure:0},changed_pixels:20,reason:null as string|null}},
    landmark_digest:b,face_skin_observation:{contract:'mediapipe-face-skin-edit-weight-v1',source_sha256:a,
      semantic_model_sha256:d,producer_width:1024,producer_height:768},changed_pixels:20,
    native_solver:'rust-eye-makeup-enhance-v1',source_dimensions:[1024,768],render_dimensions:[512,384],
    protected_face_boxes:0,limitations:['user-reviewed-visible-makeup-not-cosmetic-segmentation',
      'paired-nearby-skin-reference-not-known-underlying-skin','bounded-appearance-fading-not-makeup-removal',
      'no-pigment-pattern-generation-or-hidden-anatomy','authored-unrun-no-photo-quality-acceptance']};
  report.facts = facts; return {...value,facts};
}
test('nonempty report diagnostics match native bounded source, recipe and side accounting', () => {
  const good = withFacts(); assert.equal(reviewReceiptValid(good.request,good.result),true);
  const mutations: [string,(value:ReturnType<typeof withFacts>)=>void][] = [
    ['source dimensions',({facts})=>{facts.source_dimensions[0]++;}],
    ['render bounds',({facts})=>{facts.render_dimensions[0]=0;}],
    ['support digest',({facts})=>{facts.review_sha256=d;}],
    ['observation identity',({facts})=>{facts.face_skin_observation.source_sha256=d;}],
    ['observation model',({facts})=>{facts.face_skin_observation.semantic_model_sha256='unknown';}],
    ['recipe',({facts})=>{facts.recipe.saturation.left=.3;}],
    ['controls',({facts})=>{facts.sides.left.controls.saturation=.3;}],
    ['inactive side',({facts})=>{(facts.sides as Record<string,unknown>).right=structuredClone(facts.sides.left);}],
    ['required side',({facts})=>{delete (facts.sides as Record<string,unknown>).left;}],
    ['coverage ratio',({facts})=>{facts.sides.left.permitted_makeup_pixels=69;}],
    ['coverage growth',({facts})=>{facts.sides.left.permitted_makeup_pixels=101;}],
    ['unrequested reference use',({facts})=>{facts.sides.left.reference_pixels=[16,16];}],
    ['changed accounting',({facts})=>{facts.changed_pixels=21;}],
    ['wrong success reason',({facts})=>{facts.sides.left.reason='no_measurable_change';}],
    ['radius',({facts})=>{facts.sides.left.radius=65;}],
    ['measured width',({facts})=>{facts.sides.left.measured_eye_width=31;}],
    ['solver',({facts})=>{facts.native_solver='other';}],
    ['limitations',({facts})=>{facts.limitations.pop();}],
  ];
  for (const [reason,mutate] of mutations) {const bad=withFacts();mutate(bad);assert.equal(reviewReceiptValid(bad.request,bad.result),false,reason);}
  const unchanged=withFacts();unchanged.facts.changed_pixels=unchanged.facts.sides.left.changed_pixels=0;
  unchanged.facts.sides.left.reason='no_measurable_change';assert.equal(reviewReceiptValid(unchanged.request,unchanged.result),true);
  const amount=withFacts();amount.view.eye_makeup_enhance!.recipe.amount={linked:false,left:-.2,right:0};syncRecipe(amount.view);
  amount.facts.recipe=structuredClone(amount.view.eye_makeup_enhance!.recipe);amount.facts.sides.left.controls.amount=-.2;
  amount.facts.sides.left.reference_pixels=[16,16];assert.equal(reviewReceiptValid(amount.request,amount.result),true);
  amount.facts.sides.left.reference_pixels[0]=15;assert.equal(reviewReceiptValid(amount.request,amount.result),false);
});

test('released stale-proof UI guard is synchronous, request-specific and independent of refreshed document data', () => {
  const {request,view,proof}=fixture();
  const read:PeopleAction={...request,action:'eye_makeup_enhance_reference',request_id:proof.reference_request_id,payload:{}};
  const stale=structuredClone(view);stale.binding.document_revision=request.document_revision;
  stale.revision=stale.resolved!.state_revision=request.state_revision;
  stale.eye_makeup_enhance!.reference_proof=proof;
  // Metadata-only stale reference fixture: no PNG bytes are decoded or accepted.
  stale.eye_makeup_enhance!.source_preview={sha256:proof.preview_sha256} as never;
  assert.equal(referenceCurrent(read,stale),true);
  const panel=readFileSync(new URL('./EyeMakeupEnhanceControl.tsx',import.meta.url),'utf8');
  assert.ok(panel.includes('const releasedRequestId=people.state.eyeMakeupEnhanceReleasedRequestId;'));
  assert.match(panel,/current\.current=\{view,state,binding,releasedRequestId,patch:people\.patch,submit:people\.submitCaptured,check:people\.check\}/);
  assert.match(panel,/const actualReference=!!reference&&releasedRequestId!==reference\.request\.request_id&&reference\.binding===binding&&referenceCurrent\(reference\.request,view\)/);
  assert.match(panel,/if\(reference&&releasedRequestId===reference\.request\.request_id\)\{\s*serial\.current\+=1;activeReference\.current=null;setReference\(null\);setError\(''\);\s*\}/);
  assert.ok(panel.includes('},[releasedRequestId,reference]);'));
  const reviewCallback=panel.slice(panel.indexOf('onReview={async eyes=>'),panel.indexOf('if(stillCurrent()&&activeReference.current===reference)setReference(null);'));
  assert.ok(reviewCallback.includes('latest.releasedRequestId===reference.request.request_id'));
  assert.ok(reviewCallback.indexOf('latest.releasedRequestId===reference.request.request_id')<reviewCallback.indexOf('await latest.submit('));
  assert.ok(reviewCallback.includes('activeReference.current!==reference'));
  assert.ok(panel.includes('if(stillCurrent()&&activeReference.current===reference)setReference(null);'));
  // A release of another request cannot clear this draft, and freshly wrapped
  // owner callbacks remain data-independent: neither appears in effect deps.
  assert.equal(/\},\[[^\]]*people\.(?:patch|submitCaptured|check)[^\]]*\]/.test(panel),false);
});
test('released reference has the exact native terminal-read field set and cannot release a review', () => {
  const {request:review,proof}=fixture();
  const request:PeopleAction={...review,action:'eye_makeup_enhance_reference',request_id:proof.reference_request_id,payload:{}};
  const {request_id:_id,...echo}=structuredClone(request);
  const result={event:'people_result',protocol:1,request_id:request.request_id,action:request.action,document_id:request.document_id,
    eye_makeup_enhance_request:echo,success:true,outcome_unknown:false,error:null,created_id:null,batch_id:null,frame_emitted:false,payload_released:true} as unknown as PeopleResult;
  assert.equal(releasedReferenceReceiptValid(request,result),true);
  for(const key of ['foreign','payload','doc_state','eye_bag_cancelled']) {
    const extra=structuredClone(result) as unknown as Record<string,unknown>;extra[key]=undefined;
    assert.equal(releasedReferenceReceiptValid(request,extra as unknown as PeopleResult),false,`extra ${key}`);
  }
  assert.equal(releasedReferenceReceiptValid(review,result),false);
});
