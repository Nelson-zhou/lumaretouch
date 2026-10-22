import {describe,it} from 'node:test';
import assert from 'node:assert/strict';
import {REGIONS,CONTROL_IDS,neutral,KEYS,LINK_KEY,active,linkedPatch,linkPatch,explanation} from './model.ts';
describe('PC-32464 facial wrinkle intent',()=>{
  it('exposes all eight manual regions, nine independent contributions',()=>{
    assert.equal(REGIONS.length,8);assert.equal(KEYS.length,9);
    assert.equal(new Set(Object.values(CONTROL_IDS)).size,9);
  });
  it('never treats the persisted unlock flag as a pixel effect',()=>{
    assert.equal(active({...neutral(),[LINK_KEY]:1}),false);
  });
  it('relinking unequal sides never silently destroys either strength',()=>{
    const previous={...neutral(),wrinkle_nasolabial_left:.2,wrinkle_nasolabial_right:.8};
    assert.deepEqual({...previous,...linkPatch(false)},previous);
    assert.deepEqual(linkedPatch(.4),{wrinkle_nasolabial_left:.4,wrinkle_nasolabial_right:.4});
  });
  it('reports side-specific skipped support instead of claiming a complete effect',()=>{
    assert.match(explanation({geom_px:100,gated_px:50,reason:null,partial:true,
      sides:{left:{geom_px:50,gated_px:0,reason:'foreshortened_or_inadequate_pose'}}})??'',/人物左侧/);
  });
});
