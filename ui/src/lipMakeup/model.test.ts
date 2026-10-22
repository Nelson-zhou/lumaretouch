import {describe,it,expect} from 'vitest';
import {neutral,check,active,patch,preset,IDS} from './model';
describe('lip makeup three-control recipe v1',()=>{
  it('has exact official mapping IDs but local signed ranges',()=>{
    expect(Object.values(IDS)).toEqual(['944899f5fd','3d1502871b','d5fc30a763','21e4a8d464']);
    expect(active(neutral())).toBe(false);
    expect(patch(neutral(),'saturation',-1)).toEqual({...neutral(),saturation:-1});
  });
  it('preserves independent controls and excludes foreign-person state',()=>{
    const r=patch(patch(neutral(),'brightness',.5),'dimensionality',-.4);
    expect(patch(r,'saturation',1)).toEqual({...r,saturation:1});
    expect(()=>check({...r,face_index:0})).toThrow();
    expect(preset(r)).toEqual(r);
  });
  it('rejects malformed persisted intent instead of silently neutralizing it',()=>{
    for(const v of [{}, {...neutral(),version:2},{...neutral(),brightness:NaN},{...neutral(),saturation:2}]) expect(()=>check(v)).toThrow();
  });
});
