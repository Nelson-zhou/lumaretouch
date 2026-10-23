// AUTHORED, UNRUN: no product import, test runner, build or typecheck was executed.
import {test} from 'node:test';
import assert from 'node:assert/strict';
import {hex,parseHex,editable, type Recipe} from './model.ts';
test('RGB and HEX round trip exact byte colours',()=>{assert.equal(hex([0,127,255]),'#007fff');assert.deepEqual(parseHex('#007FFF'),[0,127,255]);});
test('rejects partial and non-hex input',()=>{assert.equal(parseHex('#fff'),null);assert.equal(parseHex('zz0000'),null);});
test('never exposes mutable source/support/spill bindings in editable payload',()=>{
  const r={version:2,spill:{version:1,algorithm:'lrt-spill-removal-v1',enabled:true,strength:50,coverage:null},enabled:true,source:{opaque:'binding'},support:{opaque:'review'},background:{},selected_support:'subject',edge:0,opacity:1,shadow:{},favourites:[]} as unknown as Recipe;
  assert.deepEqual(Object.keys(editable(r)).sort(),['background','edge','enabled','favourites','opacity','selected_support','shadow']);
});
