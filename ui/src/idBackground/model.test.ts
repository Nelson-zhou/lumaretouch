// AUTHORED, UNRUN: no product import, test runner, build or typecheck was executed.
import {describe,it,expect} from 'vitest';
import {hex,parseHex,editable, type Recipe} from './model';
describe('ID background input contracts (UNRUN)',()=>{
 it('RGB and HEX round trip exact byte colours',()=>{expect(hex([0,127,255])).toBe('#007fff');expect(parseHex('#007FFF')).toEqual([0,127,255]);});
 it('rejects partial and non-hex input',()=>{expect(parseHex('#fff')).toBeNull();expect(parseHex('zz0000')).toBeNull();});
 it('never exposes mutable source/support bindings in editable payload',()=>{
  const r={enabled:true,source:{opaque:'binding'},support:{opaque:'review'},background:{},selected_support:'subject',edge:0,opacity:1,shadow:{},favourites:[]} as unknown as Recipe;
  expect(Object.keys(editable(r)).sort()).toEqual(['background','edge','enabled','favourites','opacity','selected_support','shadow']);
 });
});
