import {describe,it,expect} from 'vitest';
import {KEYS,IDS,neutral,check,adjust,link} from './model';
describe('ten eye controls, parameter-only bilateral intent (unrun)',()=>{
  for(const k of KEYS)it(`${k} preserves unequal values through relink`,()=>{
    let r=link(neutral(),k,false);
    r=adjust(adjust(r,k,'left',.6),k,'right',-.2);
    const linked=link(r,k,true);
    expect(linked[k]).toEqual({linked:true,left:.6,right:-.2});
    expect(link(linked,k,false)).toEqual(r);
    expect(adjust(linked,k,'right',.3)[k]).toEqual({linked:true,left:.3,right:.3});
  });
  it('has eleven unique exact commercial IDs including family',()=>{
    expect(new Set(Object.values(IDS)).size).toBe(11);
    expect(IDS.family).toBe('PC-32466-C-9069cc8f2c');
    expect(IDS.height).toBe('PC-32466-C-c39023ab15');
    expect(IDS.position).toBe('PC-32466-C-37e5823f58');
  });
  it('never accepts source-specific fields or nonfinite values',()=>{
    expect(()=>check({...neutral(),face:'other'})).toThrow();
    expect(()=>adjust(neutral(),'height','left',NaN)).toThrow();
    expect(()=>check({...neutral(),version:2})).toThrow();
  });
});
