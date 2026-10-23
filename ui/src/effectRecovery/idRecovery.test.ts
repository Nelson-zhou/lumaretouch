// AUTHORED / UNRUN: source-only fixtures, not runtime or typecheck acceptance.
import test from 'node:test';
import assert from 'node:assert/strict';
import {LABELS,type RecoveryMutation} from './model.ts';
import {recoveryTargetMatches} from './workflow.ts';

test('ID and legacy recovery retain distinct named targets',()=>{
  const id:RecoveryMutation={action:'view',target:'id_background'};
  const legacy:RecoveryMutation={action:'view',target:'background_replace'};
  assert.equal(LABELS[id.target],'证件照换背景');
  assert.notEqual(LABELS[id.target],LABELS[legacy.target]);
  assert.equal(recoveryTargetMatches({target:id.target},id.target),true);
  assert.equal(recoveryTargetMatches({target:legacy.target},id.target),false);
});
test('missing or substituted preview targets cannot authorize ID recovery',()=>{
  for(const value of [null,{},[],{target:'sky'},{target:'ID_background'},{target:'background_replace'}]){
    assert.equal(recoveryTargetMatches(value,'id_background'),false);
  }
});
