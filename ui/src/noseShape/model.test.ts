import {describe,it,expect} from 'vitest';
import {KEYS,IDS,neutral,adjust,check} from './model';
describe('nose parameter-only recipe',()=>{
  it('keeps six controls independent and horizontal position scalar',()=>{
    const r=adjust(neutral(),'position',.4);
    expect(r.position).toBe(.4);for(const key of KEYS)if(key!=='position')expect(r[key]).toBe(0);
    expect(new Set(Object.values(IDS)).size).toBe(7);
  });
  it('rejects hidden source fields, nonfinite values and bilateral position',()=>{
    expect(()=>check({...neutral(),source:'face.png'})).toThrow();
    expect(()=>check({...neutral(),height:NaN})).toThrow();
    expect(()=>check({...neutral(),position:{left:0,right:0}})).toThrow();
  });
});
