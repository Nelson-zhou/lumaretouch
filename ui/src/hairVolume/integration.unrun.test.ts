// SPDX-License-Identifier: GPL-3.0-or-later
// AUTHORED / UNRUN. Pure admission specification and static wiring assertions; no application imports executed.
import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {hairFamilyAdmission, hairReviewBusy, hairVolumeProtocol, type HairFamilyMember, type HairFamilyLocks} from './familyAdmission.ts';
const source = (file: string) => readFileSync(new URL(file, import.meta.url), 'utf8');
const MEMBERS: HairFamilyMember[] = ['colour', 'unification', 'volume'];

test('each app-lifetime hair port ignores only its own reservation after the barrier', () => {
  for (const member of MEMBERS) {
    const locks: HairFamilyLocks = {colour: false, unification: false, volume: false};
    assert.equal(hairFamilyAdmission(member, true, locks), true);
    locks[member] = true;
    assert.equal(hairFamilyAdmission(member, true, locks), true, 'own pending must not disable admission');
    assert.equal(hairFamilyAdmission(member, false, locks), false, 'external source/capability/state guard still applies');
    for (const other of MEMBERS.filter(value => value !== member)) {
      assert.equal(hairFamilyAdmission(member, true, {...locks, [other]: true}), false, 'any sibling lock must block');
    }
  }
});

test('open, pending, checking, preparing, refreshing and uncertain all protect review ownership', () => {
  const idle = {open: false, pending: false, checking: false, preparing: false, refreshing: false, uncertain: false};
  assert.equal(hairReviewBusy(idle), false);
  for (const field of Object.keys(idle)) assert.equal(hairReviewBusy({...idle, [field]: true}), true);
});

test('hair lifetime binding, panel slots and activities are extracted, not inlined or compressed into App', () => {
  const app = source('../App.tsx'), family = source('./useHairFamily.tsx'), panel = source('../components/RetouchPanel.tsx');
  assert.ok(app.split('\n').length - 1 <= 2160, 'App cap');
  assert.match(app, /useHairFamily\(\{/);
  assert.match(app, /\.\.\.hairFamily\.slots/); assert.match(app, /\.\.\.hairFamily\.activities/);
  assert.doesNotMatch(app, /useHairColourPort|useHairUnificationPort|<HairUnificationPanel|<HairVolumePanel/);
  for (const creator of ['createHairColourPort', 'createHairUnificationPort', 'createHairVolumePort']) assert.match(family, new RegExp(creator));
  assert.match(family, /useMemo\(\(\) =>/);
  assert.match(family, /ports\.unification\.context\(people\)/); assert.match(family, /ports\.volume\.context\(people\)/);
  assert.match(family, /status\.image\?\.load_id === doc\.document_id/);
  assert.match(family, /hair_volume_protocol/); assert.match(family, /hairFamilyAdmission\(member, ready/);
  assert.match(family, /check: \(\) => ports\.volume\.recover\(\)/);
  assert.match(panel, /\{props\.hairVolumePanel\}/);
  assert.match(panel, /props\.hairVolumePanel&&\['颅顶调整&颅顶调整（头顶）','发量调整'\]/);
});

test('real volume modal and original-request query survive outside-edit protection', () => {
  const app = source('../App.tsx'), guards = source('../workspaces/guardCreativeWork.ts'), panel = source('./HairVolumePanel.tsx');
  assert.match(app, /hairVolume:hairFamily\.volumeLocked/);
  assert.match(app, /armBusyRef\.current=.+hairFamily\.workflowBusy/);
  assert.match(app, /if \(armBusyRef\.current \|\| fringeBusyRef\.current \|\| !pid \|\| comparingRef\.current\)/);
  assert.match(app, /PortraitCropWorkspaceHost[^\n]*!hairFamily\.workflowBusy/);
  assert.match(guards, /\[guards\.hairVolume === true, '\[data-hair-volume-workflow\],\.retouchToolActivity'\]/);
  assert.match(panel, /data-hair-volume-workflow data-readonly-scopes/);
  assert.match(source('./ReviewImages.tsx'), /源图诊断 · 轮廓与保护框 · 非候选分割/);
});

test('hair-volume protocol identity is exact without treating an absent numeric core as neutral-write authority', () => {
  const capability = {protocol: 1, operation_id: 'lnx.hair_volume.v1', available: true, reason: null};
  assert.equal(hairVolumeProtocol(1, capability), true);
  assert.equal(hairVolumeProtocol(1, {...capability, available: false, reason: 'Missing core'}), true);
  for (const other of [null, {...capability, operation_id: 'lnx.head_size.v1'}, {...capability, protocol: 2},
    {...capability, available: 'true'}, {...capability, reason: 1}]) assert.equal(hairVolumeProtocol(1, other), false);
  assert.equal(hairVolumeProtocol(2, capability), false);
  // This only admits the matching command family. The exact host still verifies source and retained edits on clear.
});
